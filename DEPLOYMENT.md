# VisionX – Production Deployment (AWS)

Step-by-step record of how VisionX is hosted publicly. Updated as each step is done.

## Architecture

```
Internet ──HTTPS──> Elastic IP ──> EC2 c7i-flex.large (us-east-1, Ubuntu 24.04)
                                    └─ Docker Compose
                                        ├─ caddy     :80/:443  HTTPS (Let's Encrypt) + routing
                                        ├─ frontend  :3000     Next.js production build
                                        └─ backend   :8000     FastAPI (uvicorn)
                                                │
                                                └──IAM token──> Aurora PostgreSQL `database-1` (db `visionx`)
```

- One public URL serves both frontend and API. Caddy sends `/api/auth/*`, `/api/v1/*`, `/video/*`, `/health`, `/storage/*`, `/docs` to the backend and everything else to the frontend.
- The server has **no SSH port open**; admin access is through AWS Systems Manager (Session Manager / Run Command).
- The backend logs in to Aurora with the EC2 **IAM role** (no database password anywhere).
- Paid from AWS credits (account is on the AWS **Free plan**, which only allows free-tier-eligible instance types).
  Approximate monthly cost: EC2 c7i-flex.large ~$62, 30 GB gp3 disk ~$2.40, public IPv4 ~$3.60, plus Aurora usage.

## Live

- URL: **https://98-87-250-9.sslip.io** (sslip.io maps the hostname to the IP, so Let's Encrypt can issue a certificate)
- Server: EC2 `i-0ab4fda61c7e01896` (`visionx-prod`), us-east-1

## AWS resources created (all tagged `Project=visionx`)

| Resource | ID / name |
|---|---|
| Elastic IP | `eipalloc-09289838e38220b2b` → 98.87.250.9 |
| IAM role + instance profile | `visionx-prod-ec2` (inline policy `visionx-prod-access` + AWS managed `AmazonSSMManagedInstanceCore`) |
| S3 bucket (private, encrypted, public access blocked) | `visionx-deploy-135438495833` — holds `visionx-bundle.tgz` and `backend.env.production` |
| Security group | `sg-0e7d5e7da1f4b7c8a` (`visionx-prod-web`) — inbound TCP 80 and 443 only |
| EC2 instance | `i-0ab4fda61c7e01896` — c7i-flex.large, Ubuntu 24.04 (`ami-02a9cdd4e98bc3c78`), 30 GB gp3 encrypted, IMDSv2 required |
| Database (existing) | Aurora `database-1`, instance `database-1-instance-1` |

## Steps

1. **Elastic IP** allocated: 98.87.250.9 → hostname `98-87-250-9.sslip.io`.
2. **Deployment files** added to the repo in `deploy/`:
   - `backend.Dockerfile` – Python 3.12 slim, ffmpeg + OpenCV libs, CPU-only PyTorch, runs uvicorn as non-root user.
   - `frontend.Dockerfile` – Next.js standalone build on Node 22, runs `node server.js` as non-root.
   - `Caddyfile` – automatic HTTPS, routes API paths to the backend, the rest to the frontend, security headers, 500 MB upload limit.
   - `docker-compose.yml` – backend + frontend + caddy, persistent volumes for uploads, model cache and certificates.
   - `server-setup.sh` – first-boot script (EC2 user-data).
3. **IAM role** `visionx-prod-ec2` for the server:
   - `rds-db:connect` on `dbuser:cluster-6VM5NIRCOUDNP54CG7EA54HZHM/postgres` (IAM login to Aurora, no password),
   - `s3:GetObject` on the deploy bucket only,
   - `AmazonSSMManagedInstanceCore` (admin access via Systems Manager instead of SSH).
4. **S3 bucket** `visionx-deploy-135438495833` created private + encrypted.
5. **Security group** `visionx-prod-web`: only ports 80/443 open to the internet; no SSH.
6. **Production settings** generated from the local `.env` files with: new `JWT_SECRET_KEY` and `SECRET_KEY`, `ENVIRONMENT=production`, `DEBUG=false`, `CORS_ORIGINS=https://98-87-250-9.sslip.io`, `PUBLIC_API_URL` set to the public URL, `STORAGE_LOCAL_PATH=/app/storage`. Uploaded only to the private bucket (never committed).
   - New JWT secret means **everyone signs in again** on the public site (accounts and passwords are unchanged).
7. **Code bundle** (`tar`, ~0.3 MB) uploaded to the bucket. Excludes `.venv`, `node_modules`, `.next`, `.git`, uploads and all local `.env` files.
8. **EC2 launched**: `t3.medium` was refused (Free plan) → used free-tier-eligible `c7i-flex.large` (2 vCPU, 4 GB RAM). First boot runs `server-setup.sh`: 4 GB swap, Docker + Compose, AWS CLI, download bundle + settings, `docker compose up -d --build`.
9. **Elastic IP attached** to the instance.
10. **First build failed** on `insightface==0.7.3` (needs a C++ compiler to build). It is not imported anywhere in the code, so it was **removed from `backend/requirements.txt`**, and `build-essential` was added to the backend image for any other package that must compile.
11. **Bare-IP redirect** added to the `Caddyfile`: `http://98.87.250.9` (or any other hostname on port 80) redirects to `https://98-87-250-9.sslip.io`.
12. **Redeploy** with `deploy/redeploy.sh` (new): downloads the latest bundle from S3, keeps the server's `backend/.env` and `deploy/.env`, runs `docker compose up -d --build`. Log: `/var/log/visionx-redeploy.log`.

## How to update the live site later

From the `Vision_X` folder on your PC (Git Bash):

```bash
# 1. Bundle the code (no secrets, no node_modules/.venv)
tar -czf /tmp/visionx-bundle.tgz --exclude=./.venv --exclude=./.git --exclude='*/node_modules' \
  --exclude=./frontend/.next --exclude='*/__pycache__' --exclude=./storage --exclude=./uploads \
  --exclude=./reports --exclude=./.env --exclude=./backend/.env --exclude='./frontend/.env*' .
# 2. Upload it
aws s3 cp /tmp/visionx-bundle.tgz s3://visionx-deploy-135438495833/visionx-bundle.tgz
# 3. Tell the server to update and rebuild (runs in the background, ~5-15 min)
MSYS_NO_PATHCONV=1 aws ssm send-command --region us-east-1 --instance-ids i-0ab4fda61c7e01896 \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["nohup /opt/visionx/deploy/redeploy.sh >/dev/null 2>&1 &"]'
```

Check progress: AWS console → Systems Manager → Session Manager → start a session on `visionx-prod`, then `tail -f /var/log/visionx-redeploy.log`.

## Useful admin commands (in a Session Manager shell on the server)

```bash
cd /opt/visionx
sudo docker compose -f deploy/docker-compose.yml --env-file deploy/.env ps          # status
sudo docker compose -f deploy/docker-compose.yml --env-file deploy/.env logs -f backend   # live backend logs
sudo docker compose -f deploy/docker-compose.yml --env-file deploy/.env restart backend   # restart
```

## Stop / remove everything (to stop spending credits)

1. EC2 → terminate `i-0ab4fda61c7e01896` (deletes its disk and the uploaded files on it).
2. EC2 → Elastic IPs → release `eipalloc-09289838e38220b2b` (an unattached Elastic IP is still billed).
3. Optional: delete security group `sg-0e7d5e7da1f4b7c8a`, S3 bucket `visionx-deploy-135438495833`, IAM role/instance profile `visionx-prod-ec2`.
4. The Aurora database is separate – see PROJECT_NOTES.md.
