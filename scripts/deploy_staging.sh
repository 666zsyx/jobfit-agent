#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "缺少 .env；请先从 .env.staging.example 复制并填写生产值。" >&2
  exit 1
fi

docker compose   -f docker-compose.prod.yml   -f docker-compose.staging.yml   config >/dev/null

docker compose   -f docker-compose.prod.yml   -f docker-compose.staging.yml   up -d --build

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/ready >/dev/null; then
    echo "staging ready"
    exit 0
  fi
  sleep 2
done

echo "staging 未就绪，请查看容器日志。" >&2
exit 1
