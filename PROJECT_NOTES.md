# VisionX – Project Notes

Living notes on how the app is wired today and what is still open.

## Stack

| Part | What we use |
|---|---|
| Frontend | Next.js (`frontend/`), runs on **port 4000** |
| Backend | FastAPI (`backend/`), runs on **port 8000** |
| Database | **AWS Aurora PostgreSQL** (Serverless v2), cluster `database-1`, region `us-east-1`, database `visionx` |
| Auth | Our own: bcrypt password hashes in the `users` table + JWT access/refresh tokens |
| File storage | Local disk: `Vision_X/storage/<bucket>/...`, served by the backend at `/storage/...` |

**Supabase is fully removed** (it was the old database/auth/storage; the project no longer exists). No Supabase packages, env vars or code remain.

## How it fits together

- `backend/database/pg_client.py` – database client: query builder (`.table().select().eq()...execute()`) over psycopg2, plus local-disk storage.
- `backend/database/db_client.py` – `get_db_client()` returns the shared client; `init_schema()` applies the schema.
- `backend/database/schema.sql` – **single source of truth for all tables**. Idempotent; applied automatically on every backend startup.
- `backend/core/auth.py` – password hashing and JWT create/verify.
- `backend/api/auth.py` – `/api/auth/register`, `/login`, `/logout`, `/me`, `/profile`, `/refresh-token`, `/reset-password`.
  - Sign-up does **not** log the user in: `/register` returns no session; the register page redirects to `/login?registered=1`, which shows "Account created" and pre-fills the email.
- `backend/api/dependencies.py` – `get_current_user` (validates the JWT, returns the user id).
- `frontend/src/lib/auth-session.ts` – stores the session in localStorage, refreshes tokens.

## Database connection (AWS)

`backend/.env`:

```
DATABASE_URL=postgresql://postgres@database-1.cluster-ci72m6g8o0nh.us-east-1.rds.amazonaws.com:5432/visionx?sslmode=require
DB_IAM_AUTH=true
AWS_REGION=us-east-1
```

- There is **no database password**. With `DB_IAM_AUTH=true` the backend signs a short-lived IAM token for every new connection using this machine's AWS credentials (`aws configure`, IAM user `manish1`). Check with `aws sts get-caller-identity`.
- The cluster **auto-pauses after 5 minutes idle**; the first request after a pause takes ~15–30 s.
- Connections are pooled and run in autocommit mode – needed because each round trip to us-east-1 is ~280 ms.
- AWS takes automatic daily backups of the cluster.

## AWS inventory (checked 2026-10-16, all regions)

| Resource | Region | Details | Created |
|---|---|---|---|
| Aurora PostgreSQL cluster `database-1` | us-east-1 | engine 17.9, Serverless v2 (0–4 ACU, auto-pause 5 min), deletion protection **off**, backups kept 1 day | 2026-10-13 |
| Aurora instance `database-1-instance-1` | us-east-1 | `db.serverless`, writer of the cluster above. Deleted 2026-10-16 (deletion interrupted; cluster + data kept), re-created 2026-10-21 | 2026-10-21 |
| EC2 instance `i-027bc3e9706a549ec` | eu-north-1 | `t3.micro`, **stopped**, not created by this project's sessions | 2026-10-11 |

No S3 buckets, NAT gateways, Elastic IPs or load balancers.

What lives in `database-1` → database `visionx`: 20 app tables (schema in `backend/database/schema.sql`) – users/profiles, image analyses, reports, news analyses, video tables (empty).

To recreate the database later: create an Aurora PostgreSQL (or RDS PostgreSQL) instance, create database `visionx`, set `DATABASE_URL` in `backend/.env` (with `DB_IAM_AUTH=true` for IAM login, or a password in the URL with `DB_IAM_AUTH=false`). The backend creates all tables on startup.

## Run locally

```powershell
# Backend
cd D:\Add-new-features\Vision_X
.\.venv\Scripts\uvicorn.exe backend.main:app --reload --port 8000

# Frontend
cd D:\Add-new-features\Vision_X\frontend
npm run dev -- -p 4000
```

Open http://localhost:4000. If you change the frontend port, add it to `CORS_ORIGINS` in `backend/.env`.

## News verification (20 trusted sources)

- `backend/services/trusted_sources.py` – the 20 sources (wire services, public broadcasters, newspapers, fact-checkers, WHO/UN/NASA, ScienceDaily) and the search.
  - RSS feeds of 18 sources (recent articles) + GDELT search for Reuters, AP, Snopes, FactCheck.org, BBC (last ~3 months; max 1 request / 5 s, so it is often rate-limited).
  - Keyword matching weighted by rarity (names count more than common words); relevance ≥ 0.5 to count.
  - A match means a trusted source covered the same story – not that it confirms every detail.
- `backend/services/news_evidence_collector.py` – builds the evidence package from real matched articles (real URLs). Replaced a previous version that invented evidence.
- Verdict without an AI key (`_fallback_reasoning`): each corroborating source +10 from 55; fact-check debunks lower it; **no coverage = "mixed" (45)**, because absence of coverage is not proof of falsehood.
- Each report stores `source_coverage` (which sources were checked, reachable, matched).

## Video analysis – current state (2026-10-16)

- The upload pipeline (`services/video_pipeline.py`) uses **placeholder data**: fake frames, fixed "Sample OCR text", fixed transcript, deepfake probability always 0.
- The upload endpoint (`api/video.py`) reads the uploaded file but does **not save it**, so no real analysis can run on it.
- `backend/video/deepfake.py` is a **placeholder that returns random numbers** – there is no real deepfake detection.
- Real building blocks exist in `backend/video/` (ffprobe metadata, OpenCV frames, MediaPipe faces, EasyOCR, faster-whisper – the Whisper base model is cached locally) but are not connected to the upload.
- A real implementation (ViT deepfake model, feature/dataset pipeline with tests) was built on 2026-10-16 and then **fully removed at the user's request**; the code above is back to its earlier state.

## Open items

- ~~Image analysis page showed "Not Found"~~ – fixed 2026-10-16: frontend called `/api/v1/analysis/analysis/{id}` (backend route is `/analyses/{id}`), and all video calls used `/api/video/...` (backend is `/video/...`). Fixed in `lib/unified-api.ts` and `lib/api-client.ts`.
- **Password reset email** is not implemented (needs AWS SES or SMTP); the endpoint only logs the request.
- Broken links found in the UI (pages that don't exist): `/api-docs`, `/history/uploads`, `/incidents/new`, `/incidents/<id>`.
- A few test rows from integration testing remain in the Aurora database.
