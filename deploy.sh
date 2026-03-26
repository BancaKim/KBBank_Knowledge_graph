#!/usr/bin/env bash
set -euo pipefail

SERVER="ubuntu@144.24.74.197"
SSH_KEY="$HOME/.ssh/oracle_key"
REMOTE_DIR="/home/ubuntu/KBBank_Knowledge_graph"
REPO="https://github.com/BancaKim/KBBank_Knowledge_graph.git"

ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SERVER" bash -s -- "$REMOTE_DIR" "$REPO" <<'REMOTE'
set -euo pipefail
REMOTE_DIR="$1"
REPO="$2"

echo "=== Pulling latest code ==="
if [ -d "$REMOTE_DIR" ]; then
    cd "$REMOTE_DIR"
    git fetch origin master
    git reset --hard origin/master
else
    git clone "$REPO" "$REMOTE_DIR"
    cd "$REMOTE_DIR"
fi

echo "=== Syncing .env ==="
# .env should already exist on server; skip if missing
[ -f .env ] || echo "WARNING: .env not found — create it manually"

echo "=== Building and restarting Docker ==="
docker compose -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.prod.yml up -d --force-recreate

echo "=== Cleaning up old images ==="
docker image prune -f

echo "=== Verifying ==="
sleep 3
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -sf http://localhost:80/api/health && echo " <- health OK" || echo " <- health check failed (may need a moment)"

echo "=== Deploy complete ==="
REMOTE
