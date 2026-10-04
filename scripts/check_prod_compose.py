# 检查生产 Compose 的持久化和单 Worker 配置。

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.prod.yml"
DOCKERFILE = PROJECT_ROOT / "Dockerfile"


CHECKS = {
    "compose_vector_index_path": (
        COMPOSE_FILE,
        "VECTOR_INDEX_PATH: /app/.cache/chroma",
    ),
    "compose_embedding_cache_path": (
        COMPOSE_FILE,
        "EMBEDDING_CACHE_PATH: /app/.cache/fastembed",
    ),
    "compose_chroma_volume": (
        COMPOSE_FILE,
        "chroma_prod_data:/app/.cache/chroma",
    ),
    "compose_fastembed_volume": (
        COMPOSE_FILE,
        "fastembed_prod_data:/app/.cache/fastembed",
    ),
    "compose_single_worker": (
        COMPOSE_FILE,
        "--workers 1",
    ),
    "dockerfile_chroma_directory": (
        DOCKERFILE,
        "/app/.cache/chroma",
    ),
    "dockerfile_fastembed_directory": (
        DOCKERFILE,
        "/app/.cache/fastembed",
    ),
}


def run_checks() -> list[str]:
    missing: list[str] = []
    file_cache: dict[Path, str] = {}
    for name, (path, marker) in CHECKS.items():
        text = file_cache.setdefault(
            path,
            path.read_text(encoding="utf-8"),
        )
        if marker not in text:
            missing.append(name)
    return missing


def main() -> None:
    missing = run_checks()
    report = {
        "ready": not missing,
        "missing": missing,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
