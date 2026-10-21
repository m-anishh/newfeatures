"""
PostgreSQL Client
Query-builder client over a plain PostgreSQL database (AWS RDS or local) via
DATABASE_URL, with local-disk file storage.

API:
    client.schema("public").table("x").select("*", count="exact")
          .eq("col", v).in_("col", [...]).order("col", desc=True)
          .limit(n).offset(n).execute()
    .insert(dict | list) / .update(dict) / .upsert(dict | list) / .delete()
    client.storage.from_(bucket).upload/update/download/remove/list/
          get_public_url/create_signed_url
"""

from __future__ import annotations

import datetime as _dt
import decimal
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import psycopg2
import psycopg2.extras
import psycopg2.pool
from psycopg2 import sql

from backend.core.logging import get_logger

logger = get_logger(__name__)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Embedded relation in a select, e.g. "uploads(original_filename, public_url)"
_EMBED_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)")


class PostgrestError(Exception):
    """Raised on query failure ."""


@dataclass
class APIResponse:
    data: Any
    count: Optional[int] = None


def _ident(name: str) -> str:
    if not _IDENT_RE.match(name):
        raise PostgrestError(f"Invalid identifier: {name!r}")
    return name


def _to_jsonable(value: Any) -> Any:
    """Convert DB values to JSON-friendly values (ISO dates, str UUIDs, floats)."""
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, memoryview):
        return bytes(value)
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    return value


def _json_default(o: Any) -> Any:
    j = _to_jsonable(o)
    if j is o:
        return str(o)
    return j


def _iam_auth_enabled() -> bool:
    return os.getenv("DB_IAM_AUTH", "").strip().lower() in ("1", "true", "yes")


class _IamConnectionPool(psycopg2.pool.ThreadedConnectionPool):
    """Pool that signs a fresh AWS RDS IAM auth token for every new connection.

    Tokens are valid for 15 minutes but only need to be valid at connect time.
    Uses the machine's normal AWS credentials (env vars, ~/.aws, or instance role).
    """

    _rds_client = None

    def _connect(self, key=None):
        if self._rds_client is None:
            import boto3

            region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
            self._rds_client = boto3.client("rds", region_name=region)

        params = psycopg2.extensions.parse_dsn(self._kwargs["dsn"])
        token = self._rds_client.generate_db_auth_token(
            DBHostname=params["host"],
            Port=int(params.get("port", 5432)),
            DBUsername=params["user"],
        )
        conn = psycopg2.connect(self._kwargs["dsn"], password=token)
        if key is not None:
            self._used[key] = conn
            self._rused[id(conn)] = key
        else:
            self._pool.append(conn)
        return conn


class _Database:
    """Connection pool plus a per-table column-type cache."""

    def __init__(self, dsn: str):
        params = psycopg2.extensions.parse_dsn(dsn)
        # Serverless Aurora can take a while to resume from auto-pause
        params.setdefault("connect_timeout", "60")
        dsn = psycopg2.extensions.make_dsn(**params)
        pool_cls = _IamConnectionPool if _iam_auth_enabled() else psycopg2.pool.ThreadedConnectionPool
        maxconn = int(os.getenv("DATABASE_POOL_SIZE", "10"))
        # Open nothing up front (startup works even if the DB is paused/unreachable)...
        self._pool = pool_cls(minconn=0, maxconn=maxconn, dsn=dsn)
        # ...but keep up to maxconn idle connections for reuse: psycopg2 closes any
        # returned connection once the idle count reaches minconn.
        self._pool.minconn = maxconn
        self._columns: Dict[str, Dict[str, str]] = {}
        self._lock = threading.Lock()

    def run(self, query, params: Sequence[Any] = ()) -> tuple[list[dict], int]:
        # One retry on a dropped connection (e.g. Aurora auto-pause, network blip)
        for attempt in range(2):
            conn = self._pool.getconn()
            broken = False
            try:
                if conn.closed:
                    raise psycopg2.InterfaceError("connection already closed")
                # Every call is a single statement; autocommit saves the BEGIN/COMMIT
                # round trips, which matter on a high-latency link to RDS.
                if not conn.autocommit:
                    conn.autocommit = True
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(query, params)
                    rows = [dict(r) for r in cur.fetchall()] if cur.description else []
                    rowcount = cur.rowcount
                return rows, rowcount
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                broken = True
                if attempt == 0:
                    logger.warning(f"[pg_client] Connection lost, reconnecting: {str(e).strip()}")
                    continue
                raise PostgrestError(str(e).strip()) from e
            except psycopg2.Error as e:
                raise PostgrestError(str(e).strip()) from e
            finally:
                self._pool.putconn(conn, close=broken or bool(conn.closed))
        raise PostgrestError("Database connection failed")

    def columns(self, table: str) -> Dict[str, str]:
        """Return {column_name: data_type} for a table (cached)."""
        cols = self._columns.get(table)
        if cols is None:
            rows, _ = self.run(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = %s",
                (table,),
            )
            cols = {r["column_name"]: r["data_type"] for r in rows}
            if not cols:
                raise PostgrestError(f'relation "{table}" does not exist')
            with self._lock:
                self._columns[table] = cols
        return cols

    def reset_cache(self) -> None:
        with self._lock:
            self._columns.clear()


class QueryBuilder:
    def __init__(self, db: _Database, table: str):
        self._db = db
        self._table = _ident(table)
        self._op = "select"
        self._columns = "*"
        self._embeds: List[tuple[str, List[str]]] = []
        self._count: Optional[str] = None
        self._payload: Any = None
        self._on_conflict = "id"
        self._filters: List[tuple[str, str, Any]] = []
        self._order: List[tuple[str, bool]] = []
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None
        self._single = False
        self._maybe_single = False

    # ---- operations -------------------------------------------------------
    def select(self, columns: str = "*", count: Optional[str] = None, **_: Any) -> "QueryBuilder":
        self._op = "select"
        self._count = count
        self._embeds = [(m.group(1), [c.strip() for c in m.group(2).split(",") if c.strip()])
                        for m in _EMBED_RE.finditer(columns)]
        plain = _EMBED_RE.sub("", columns)
        self._columns = ",".join(c.strip() for c in plain.split(",") if c.strip()) or "*"
        return self

    def insert(self, payload: Any, **_: Any) -> "QueryBuilder":
        self._op, self._payload = "insert", payload
        return self

    def upsert(self, payload: Any, on_conflict: str = "id", **_: Any) -> "QueryBuilder":
        self._op, self._payload, self._on_conflict = "upsert", payload, on_conflict
        return self

    def update(self, payload: Dict[str, Any], **_: Any) -> "QueryBuilder":
        self._op, self._payload = "update", payload
        return self

    def delete(self, **_: Any) -> "QueryBuilder":
        self._op = "delete"
        return self

    # ---- filters / modifiers ---------------------------------------------
    def _f(self, col: str, op: str, value: Any) -> "QueryBuilder":
        self._filters.append((_ident(col), op, value))
        return self

    def eq(self, col: str, value: Any) -> "QueryBuilder":
        return self._f(col, "=", value)

    def neq(self, col: str, value: Any) -> "QueryBuilder":
        return self._f(col, "<>", value)

    def gt(self, col: str, value: Any) -> "QueryBuilder":
        return self._f(col, ">", value)

    def gte(self, col: str, value: Any) -> "QueryBuilder":
        return self._f(col, ">=", value)

    def lt(self, col: str, value: Any) -> "QueryBuilder":
        return self._f(col, "<", value)

    def lte(self, col: str, value: Any) -> "QueryBuilder":
        return self._f(col, "<=", value)

    def like(self, col: str, value: Any) -> "QueryBuilder":
        return self._f(col, "LIKE", value)

    def ilike(self, col: str, value: Any) -> "QueryBuilder":
        return self._f(col, "ILIKE", value)

    def in_(self, col: str, values: Sequence[Any]) -> "QueryBuilder":
        return self._f(col, "IN", list(values))

    def is_(self, col: str, value: Any) -> "QueryBuilder":
        return self._f(col, "IS", None if value in (None, "null") else value)

    def order(self, col: str, desc: bool = False, **_: Any) -> "QueryBuilder":
        self._order.append((_ident(col), desc))
        return self

    def limit(self, n: int, **_: Any) -> "QueryBuilder":
        self._limit = int(n)
        return self

    def offset(self, n: int, **_: Any) -> "QueryBuilder":
        self._offset = int(n)
        return self

    def range(self, start: int, end: int, **_: Any) -> "QueryBuilder":
        self._offset, self._limit = int(start), int(end) - int(start) + 1
        return self

    def single(self) -> "QueryBuilder":
        self._single = True
        return self

    def maybe_single(self) -> "QueryBuilder":
        self._maybe_single = True
        return self

    # ---- SQL building -----------------------------------------------------
    def _adapt(self, col: str, value: Any, types: Dict[str, str]) -> Any:
        """Adapt a Python value to the target column's type."""
        t = types.get(col, "")
        if t in ("json", "jsonb"):
            if value is None:
                return None
            return psycopg2.extras.Json(value, dumps=lambda o: json.dumps(o, default=_json_default))
        if isinstance(value, (dict, list)) and t != "ARRAY":
            return json.dumps(value, default=_json_default)
        return value

    def _where(self, types: Dict[str, str]) -> tuple[sql.Composable, list]:
        if not self._filters:
            return sql.SQL(""), []
        parts, params = [], []
        for col, op, value in self._filters:
            ident = sql.Identifier(col)
            if op == "IN":
                if not value:
                    parts.append(sql.SQL("FALSE"))
                    continue
                parts.append(sql.SQL("{} = ANY(%s)").format(ident))
                params.append([str(v) if isinstance(v, uuid.UUID) else v for v in value])
                # cast text[] to the column type when needed
                if types.get(col) == "uuid":
                    parts[-1] = sql.SQL("{}::text = ANY(%s)").format(ident)
                    params[-1] = [str(v) for v in value]
            elif op == "IS":
                parts.append(sql.SQL("{} IS NULL").format(ident) if value is None
                             else sql.SQL("{} IS %s").format(ident))
                if value is not None:
                    params.append(value)
            else:
                parts.append(sql.SQL("{} " + op + " %s").format(ident))
                params.append(self._adapt(col, value, types))
        return sql.SQL(" WHERE ") + sql.SQL(" AND ").join(parts), params

    def _rows_payload(self) -> List[Dict[str, Any]]:
        p = self._payload
        rows = p if isinstance(p, list) else [p]
        return [r for r in rows if r]

    def _filter_known(self, row: Dict[str, Any], types: Dict[str, str]) -> Dict[str, Any]:
        unknown = [k for k in row if k not in types]
        if unknown:
            logger.warning(f"[pg_client] {self._table}: ignoring unknown columns {unknown}")
        return {k: v for k, v in row.items() if k in types}

    def execute(self) -> APIResponse:
        types = self._db.columns(self._table)
        table = sql.Identifier(self._table)

        if self._op == "select":
            cols = (sql.SQL("*") if self._columns.strip() == "*"
                    else sql.SQL(", ").join(sql.Identifier(_ident(c)) for c in self._columns.split(",")))
            where, params = self._where(types)
            if self._count:
                # Total row count in the same round trip
                cols = cols + sql.SQL(", COUNT(*) OVER() AS __total_count")
            q = sql.SQL("SELECT {} FROM {}").format(cols, table) + where
            if self._order:
                q += sql.SQL(" ORDER BY ") + sql.SQL(", ").join(
                    sql.SQL("{} {}").format(sql.Identifier(c), sql.SQL("DESC" if d else "ASC"))
                    for c, d in self._order)
            if self._limit is not None:
                q += sql.SQL(" LIMIT %s")
                params.append(self._limit)
            if self._offset is not None:
                q += sql.SQL(" OFFSET %s")
                params.append(self._offset)
            rows, _ = self._db.run(q, params)
            count = None
            if self._count:
                if rows:
                    count = int(rows[0]["__total_count"])
                    for r in rows:
                        r.pop("__total_count", None)
                elif self._offset:
                    # Page past the end: no rows to carry the count
                    cwhere, cparams = self._where(types)
                    crow, _ = self._db.run(sql.SQL("SELECT COUNT(*) AS n FROM {}").format(table) + cwhere, cparams)
                    count = int(crow[0]["n"])
                else:
                    count = 0
            data = [_to_jsonable(r) for r in rows]
            for rel, rel_cols in self._embeds:
                self._embed(data, rel, rel_cols)
            return self._finish(data, count)

        if self._op in ("insert", "upsert"):
            rows = [self._filter_known(r, types) for r in self._rows_payload()]
            if not rows:
                return APIResponse(data=[])
            out: List[Dict[str, Any]] = []
            for row in rows:
                cols = list(row.keys())
                q = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    table,
                    sql.SQL(", ").join(sql.Identifier(c) for c in cols),
                    sql.SQL(", ").join(sql.Placeholder() for _ in cols),
                )
                if self._op == "upsert":
                    conflict = [c.strip() for c in self._on_conflict.split(",")]
                    updates = [c for c in cols if c not in conflict]
                    q += sql.SQL(" ON CONFLICT ({}) ").format(
                        sql.SQL(", ").join(sql.Identifier(_ident(c)) for c in conflict))
                    q += (sql.SQL("DO UPDATE SET ") + sql.SQL(", ").join(
                        sql.SQL("{0} = EXCLUDED.{0}").format(sql.Identifier(c)) for c in updates)
                          if updates else sql.SQL("DO NOTHING"))
                q += sql.SQL(" RETURNING *")
                res, _ = self._db.run(q, [self._adapt(c, row[c], types) for c in cols])
                out.extend(res)
            return APIResponse(data=[_to_jsonable(r) for r in out])

        if self._op == "update":
            row = self._filter_known(dict(self._payload or {}), types)
            if not row:
                return APIResponse(data=[])
            sets = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(c)) for c in row)
            where, wparams = self._where(types)
            q = sql.SQL("UPDATE {} SET ").format(table) + sets + where + sql.SQL(" RETURNING *")
            res, _ = self._db.run(q, [self._adapt(c, v, types) for c, v in row.items()] + wparams)
            return APIResponse(data=[_to_jsonable(r) for r in res])

        if self._op == "delete":
            where, params = self._where(types)
            q = sql.SQL("DELETE FROM {}").format(table) + where + sql.SQL(" RETURNING *")
            res, _ = self._db.run(q, params)
            return APIResponse(data=[_to_jsonable(r) for r in res])

        raise PostgrestError(f"Unsupported operation {self._op}")

    def _embed(self, data: List[Dict[str, Any]], rel: str, rel_cols: List[str]) -> None:
        """Resolve a many-to-one embed like reports -> uploads via reports.upload_id."""
        fk = (rel[:-1] if rel.endswith("s") else rel) + "_id"
        ids = list({r[fk] for r in data if r.get(fk)})
        related: Dict[str, Dict[str, Any]] = {}
        if ids:
            res = QueryBuilder(self._db, rel).select(",".join(["id", *rel_cols]) if rel_cols else "*") \
                .in_("id", ids).execute()
            related = {str(r["id"]): r for r in res.data}
        for r in data:
            hit = related.get(str(r.get(fk))) if r.get(fk) else None
            if hit is not None and rel_cols and "id" not in rel_cols:
                hit = {k: v for k, v in hit.items() if k != "id"}
            r[rel] = hit

    def _finish(self, data: List[Dict[str, Any]], count: Optional[int]) -> APIResponse:
        if self._single:
            if len(data) != 1:
                raise PostgrestError(f"Expected 1 row, got {len(data)}")
            return APIResponse(data=data[0], count=count)
        if self._maybe_single:
            return APIResponse(data=data[0] if data else None, count=count)
        return APIResponse(data=data, count=count)


class _Schema:
    """Schema names are ignored: all tables live in the database's search_path."""

    def __init__(self, db: _Database):
        self._db = db

    def table(self, name: str) -> QueryBuilder:
        return QueryBuilder(self._db, name)

    from_ = table


# ---------------------------------------------------------------------------
# Local-disk storage
# ---------------------------------------------------------------------------

def storage_root() -> Path:
    root = os.getenv("STORAGE_LOCAL_PATH") or str(Path(__file__).resolve().parents[2] / "storage")
    path = Path(root).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def public_base_url() -> str:
    return os.getenv("PUBLIC_API_URL", f"http://localhost:{os.getenv('PORT', '8000')}").rstrip("/")


@dataclass
class UploadResponse:
    path: str
    full_path: str


class _Bucket:
    def __init__(self, bucket: str):
        if not re.match(r"^[A-Za-z0-9_-]+$", bucket):
            raise PostgrestError(f"Invalid bucket name: {bucket!r}")
        self._bucket = bucket
        self._root = storage_root() / bucket

    def _resolve(self, path: str) -> Path:
        target = (self._root / path.lstrip("/")).resolve()
        if self._root.resolve() not in target.parents and target != self._root.resolve():
            raise PostgrestError(f"Invalid storage path: {path}")
        return target

    def upload(self, path: str, file: Any, file_options: Optional[dict] = None) -> UploadResponse:
        target = self._resolve(path)
        if target.exists() and str((file_options or {}).get("upsert", "false")).lower() != "true":
            raise PostgrestError("The resource already exists")
        return self._write(path, target, file)

    def update(self, path: str, file: Any, file_options: Optional[dict] = None) -> UploadResponse:
        return self._write(path, self._resolve(path), file)

    def _write(self, path: str, target: Path, file: Any) -> UploadResponse:
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(file, (str, os.PathLike)) and Path(file).exists():
            data = Path(file).read_bytes()
        elif hasattr(file, "read"):
            data = file.read()
        else:
            data = file
        target.write_bytes(data)
        return UploadResponse(path=path, full_path=f"{self._bucket}/{path}")

    def download(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    def remove(self, paths: List[str]) -> List[dict]:
        removed = []
        for p in paths:
            t = self._resolve(p)
            if t.exists():
                t.unlink()
                removed.append({"name": p})
        return removed

    def list(self, path: str = "", *_: Any, **__: Any) -> List[dict]:
        folder = self._resolve(path) if path else self._root
        if not folder.exists():
            return []
        return [{"name": f.name, "id": f.name, "metadata": {"size": f.stat().st_size}}
                for f in sorted(folder.iterdir())]

    def get_public_url(self, path: str, *_: Any, **__: Any) -> str:
        return f"{public_base_url()}/storage/{self._bucket}/{path.lstrip('/')}"

    def create_signed_url(self, path: str, expires_in: int = 3600, *_: Any, **__: Any) -> dict:
        url = self.get_public_url(path)
        return {"signedURL": url, "signedUrl": url, "signed_url": url}


class _Storage:
    def from_(self, bucket: str) -> _Bucket:
        return _Bucket(bucket)


class PgClient:
    """Database client over PostgreSQL + local storage."""

    def __init__(self, dsn: str):
        self._db = _Database(dsn)
        self.storage = _Storage()

    def schema(self, _name: str = "public") -> _Schema:
        return _Schema(self._db)

    def table(self, name: str) -> QueryBuilder:
        return QueryBuilder(self._db, name)

    from_ = table

    def execute_sql(self, query: str) -> None:
        """Run raw SQL (used for schema setup)."""
        self._db.run(query)
        self._db.reset_cache()


def normalize_dsn(url: str) -> str:
    """Accept SQLAlchemy-style URLs and return a libpq DSN."""
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url
