def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_reports_db_migrations_and_provider(client):
    r = client.get("/ready")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["migrations"] != "missing"
    assert body["checks"]["ai_provider"] == "mock"


def test_missing_secret_outside_development_fails_closed(monkeypatch):
    from app.core.config import Settings

    s = Settings(app_env="staging", app_secret_key=None)
    import pytest

    with pytest.raises(RuntimeError):
        s.resolved_secret()


def test_unknown_ai_provider_fails_closed(monkeypatch):
    import pytest

    from app.ai import gateway
    from app.core import config

    monkeypatch.setenv("AI_PROVIDER", "some-real-llm")
    config.get_settings.cache_clear()
    gateway.get_provider.cache_clear()
    try:
        with pytest.raises(gateway.ProviderNotConfigured):
            gateway.get_provider()
    finally:
        monkeypatch.setenv("AI_PROVIDER", "mock")
        config.get_settings.cache_clear()
        gateway.get_provider.cache_clear()
