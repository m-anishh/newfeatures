"""
Database Client
Returns the PostgreSQL client (AWS RDS or any PostgreSQL) configured via DATABASE_URL.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

from backend.core.logging import get_logger
from backend.database.pg_client import PgClient, normalize_dsn

logger = get_logger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Module-level client instance
_client: Optional[PgClient] = None
_lock = threading.Lock()


def get_db_client() -> PgClient:
    """
    Get or create the database client.

    Raises:
        RuntimeError: If DATABASE_URL is not configured
    """
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                url = os.getenv("DATABASE_URL")
                if not url:
                    raise RuntimeError(
                        "Database not configured. Set DATABASE_URL in backend/.env, e.g. "
                        "postgresql://user:password@your-rds-endpoint:5432/visionx?sslmode=require"
                    )
                _client = PgClient(normalize_dsn(url))
    return _client



def init_schema() -> None:
    """Create all tables if they do not exist (idempotent)."""
    get_db_client().execute_sql(SCHEMA_PATH.read_text(encoding="utf-8"))
    logger.info("Database schema verified")


def reset_client():
    """Reset the client instance (useful for testing)."""
    global _client
    _client = None
