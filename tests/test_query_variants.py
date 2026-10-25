# 验证岗位要求 query 变体的确定性归一化。

from app.services.query_variants import (
    build_query_variants,
    normalize_requirement_query,
)
from app.services.text_similarity import requirements_are_similar


def test_docker_phrasings_normalize_to_same_keyword_query() -> None:
    first = normalize_requirement_query(
        "具备 Docker 和 docker-compose 部署经验"
    )
    second = normalize_requirement_query(
        "使用 Docker 和 docker-compose 进行部署"
    )

    assert first == second == "Docker 和 docker-compose 部署"


def test_build_query_variants_keeps_original_and_keyword_form() -> None:
    variants = build_query_variants(
        "具备 Python 和 FastAPI 后端开发经验"
    )

    assert variants[0] == "具备 Python 和 FastAPI 后端开发经验"
    assert "Python 和 FastAPI 后端开发" in variants


def test_empty_requirement_has_no_variants() -> None:
    assert build_query_variants("   ") == []

def test_generic_chinese_requirement_merges_into_specific() -> None:
    assert requirements_are_similar(
        "后端开发",
        "具备 Python 和 FastAPI 后端开发经验",
    )


def test_java_is_not_merged_with_javascript() -> None:
    assert not requirements_are_similar("Java", "JavaScript")

def test_python_fastapi_paraphrases_are_similar() -> None:
    assert requirements_are_similar(
        "负责基于 Python 与 FastAPI 的后端开发工作",
        "具备 Python 和 FastAPI 后端开发经验",
    )

