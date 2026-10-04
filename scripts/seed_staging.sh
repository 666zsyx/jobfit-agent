#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

docker compose   -f docker-compose.prod.yml   -f docker-compose.staging.yml   exec -T jobfit-agent python scripts/seed_demo_data.py
