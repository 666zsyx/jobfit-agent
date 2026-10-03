# 验证 readiness 接口和容器依赖状态。

from app.routers import health as health_router


def test_ready_returns_200_when_dependencies_are_ok(
    client,
    monkeypatch,
):
    async def fake_collect_readiness():
        return {
            "status": "ready",
            "checks": {
                "database": "ok",
                "checkpoint": "ok",
                "redis": "ok",
            },
        }

    monkeypatch.setattr(
        health_router,
        "collect_readiness",
        fake_collect_readiness,
    )

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"]["database"] == "ok"


def test_ready_returns_503_when_dependency_fails(
    client,
    monkeypatch,
):
    async def fake_collect_readiness():
        return {
            "status": "not_ready",
            "checks": {
                "database": "failed",
                "checkpoint": "ok",
                "redis": "ok",
            },
        }

    monkeypatch.setattr(
        health_router,
        "collect_readiness",
        fake_collect_readiness,
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["database"] == "failed"
