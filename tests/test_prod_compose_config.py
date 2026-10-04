# 验证生产 Compose 已挂载向量与模型缓存，并限制单 Worker。

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.prod.yml"
DOCKERFILE = PROJECT_ROOT / "Dockerfile"


def test_prod_compose_persists_rag_runtime_data():
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "VECTOR_INDEX_PATH: /app/.cache/chroma" in compose
    assert "EMBEDDING_CACHE_PATH: /app/.cache/fastembed" in compose
    assert "chroma_prod_data:/app/.cache/chroma" in compose
    assert "fastembed_prod_data:/app/.cache/fastembed" in compose
    assert "chroma_prod_data:" in compose
    assert "fastembed_prod_data:" in compose


def test_prod_compose_uses_single_worker():
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "--workers 1" in compose
    assert "--workers 2" not in compose


def test_dockerfile_creates_writable_cache_directories():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "/app/.cache/chroma" in dockerfile
    assert "/app/.cache/fastembed" in dockerfile
    assert '"--workers", "1"' in dockerfile


def test_prod_compose_check_script_passes():
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "check_prod_compose.py"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "ready": True,
        "missing": [],
    }
