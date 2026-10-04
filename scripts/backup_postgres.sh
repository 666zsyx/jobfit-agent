#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKUP_DIR="${1:-$ROOT_DIR/backups}"
mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
TARGET="$BACKUP_DIR/jobfit_${STAMP}.dump"

docker compose   -f docker-compose.prod.yml   exec -T postgres   pg_dump -U jobfit_app -d jobfit_prod -Fc > "$TARGET"

echo "backup created: $TARGET"
