#!/bin/bash
# VisionX – update the running server with the latest bundle from S3 and rebuild.
# Keeps the server's backend/.env and deploy/.env. Log: /var/log/visionx-redeploy.log
set -euxo pipefail
exec > /var/log/visionx-redeploy.log 2>&1

BUCKET="visionx-deploy-135438495833"
APP_DIR="/opt/visionx"
AWS=/snap/bin/aws

$AWS s3 cp "s3://$BUCKET/visionx-bundle.tgz" /tmp/visionx-bundle.tgz
cp "$APP_DIR/backend/.env" /tmp/backend.env.keep
cp "$APP_DIR/deploy/.env" /tmp/deploy.env.keep
tar -xzf /tmp/visionx-bundle.tgz -C "$APP_DIR"
cp /tmp/backend.env.keep "$APP_DIR/backend/.env"
cp /tmp/deploy.env.keep "$APP_DIR/deploy/.env"
chmod 600 "$APP_DIR/backend/.env"

cd "$APP_DIR"
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build --remove-orphans
docker compose -f deploy/docker-compose.yml --env-file deploy/.env ps
docker image prune -f
echo "VISIONX REDEPLOY COMPLETE"
