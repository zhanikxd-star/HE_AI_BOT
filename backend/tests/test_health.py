def test_health_reports_test_adapters(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["telegram"] == "test"
    assert body["llm"] == "test"


def test_bot_router_imports():
    from app.bot.handlers import router

    assert router is not None
