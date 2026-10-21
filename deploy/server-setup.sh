#!/bin/bash
# VisionX – first-boot setup for the production EC2 server (Ubuntu 24.04).
# Used as EC2 user-data. Log: /var/log/visionx-setup.log
set -euxo pipefail
exec > /var/log/visionx-setup.log 2>&1

BUCKET="visionx-deploy-135438495833"
SITE_HOST="98-87-250-9.sslip.io"
APP_DIR="/opt/visionx"

# 4 GB swap: the backend image installs PyTorch and the instance has 4 GB RAM
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2
systemctl enable --now docker
snap install aws-cli --classic
AWS=/snap/bin/aws

# Code + production settings from the private deploy bucket (read via the instance IAM role)
mkdir -p "$APP_DIR"
$AWS s3 cp "s3://$BUCKET/visionx-bundle.tgz" /tmp/visionx-bundle.tgz
tar -xzf /tmp/visionx-bundle.tgz -C "$APP_DIR"
$AWS s3 cp "s3://$BUCKET/backend.env.production" "$APP_DIR/backend/.env"
chmod 600 "$APP_DIR/backend/.env"
echo "SITE_HOST=$SITE_HOST" > "$APP_DIR/deploy/.env"

cd "$APP_DIR"
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
docker compose -f deploy/docker-compose.yml --env-file deploy/.env ps
echo "VISIONX SETUP COMPLETE"
