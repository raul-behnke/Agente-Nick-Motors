from fastapi.testclient import TestClient

from zoi_agent.main import app


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert "status" in body
        assert "db" in body


def test_metrics_endpoint() -> None:
    with TestClient(app) as client:
        r = client.get("/metrics")
        assert r.status_code == 200
        assert b"zoi_turns_total" in r.content


def test_config_loads() -> None:
    from zoi_agent.config import settings

    assert settings.ghl_location_id
    assert settings.openai_api_key
    assert settings.webhook_secret
