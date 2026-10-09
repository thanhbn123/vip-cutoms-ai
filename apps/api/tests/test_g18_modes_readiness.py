"""G18 — explicit runtime modes and fail-closed FULL-mode readiness.

Mandatory negative tests (owner brief §16):
    FULL + mock AI                     → startup refused AND readiness 503
    FULL + demo customs data           → readiness 503
    FULL + expired authoritative data  → readiness 503
    FULL + missing provider credential → startup refused / provider not configured
    LIMITED + demo data                → allowed, visible warning
    DEMO                               → allowed
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.ai import gateway
from app.core import config, modes
from app.core.config import Settings
from app.db import get_sessionmaker
from app.models.identity import User
from app.models.knowledge import KnowledgeDataset
from app.services import readiness
from app.services.customs_data import KINDS, DatasetPackage, register, verify

FULL_ENV = {"APP_MODE": "full", "APP_ENV": "production", "AI_PROVIDER": "http-llm", "AI_PROVIDER_BASE_URL": "https://llm.example.test/v1",
            "AI_PROVIDER_API_KEY": "test-placeholder-not-a-real-key", "AI_PROVIDER_MODEL": "test-model", "AI_DAILY_BUDGET_USD": "5",
            "DOCUMENT_OCR_PROVIDER": "mock"}


@pytest.fixture
def reset_runtime(monkeypatch):
    """Every test here changes settings via env; always restore the default test runtime."""
    yield monkeypatch
    for k in ("APP_MODE", "AI_PROVIDER_BASE_URL", "AI_PROVIDER_API_KEY", "AI_PROVIDER_MODEL", "AI_DAILY_BUDGET_USD", "BACKUP_STATUS_FILE",
              "DOCUMENT_OCR_PROVIDER", "DOCUMENT_AI_PROVIDER", "HS_AI_PROVIDER", "COPILOT_PROVIDER", "RELEASE_SHA"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    config.get_settings.cache_clear()
    gateway.reset_cache()


def _apply(monkeypatch, env: dict[str, str]) -> Settings:
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    config.get_settings.cache_clear()
    gateway.reset_cache()
    return config.get_settings()


def _authoritative_world(db, admin, *, effective_to: date | None = None, kinds=KINDS) -> list[KnowledgeDataset]:
    out = []
    payloads = {"HS_RULES": {"rules": [{"heading": "8413", "title": "Pumps", "keywords": ["pump"], "base_confidence": 0.9}]},
                "TARIFF": {"rates": {"8413": {"mfn_duty_pct": 1.0, "vat_pct": 10.0}}},
                "FTA": {"forms": {"E": {"agreement": "ACFTA (test)", "origin_countries": ["CN"], "allowed_criteria": ["WO"], "checks": [],
                                        "preferential_duty_pct": {"8413": 0.0}}}},
                "POLICY": {"requirements": {}}}
    for kind in kinds:
        payload = payloads[kind]
        pkg = DatasetPackage(kind=kind, version=f"auth-{kind.lower()}-2026.01", label=f"Authoritative {kind} (test)",
                             effective_from=date(2026, 1, 1), effective_to=effective_to, source_authority="Test Authority",
                             source_document="Decision 1/2026/TEST", source_reference="https://example.test/legal/1-2026", payload=payload)
        ds = register(db, pkg, admin, reason="test import")
        verify(db, ds, admin, reason="test verify")
        ds.is_active = True
        out.append(ds)
    db.commit()
    return out


def _fresh_backup(tmp_path) -> str:
    f = tmp_path / "backup-status.json"
    f.write_text(json.dumps({"last_success_at": datetime.now(UTC).isoformat(), "destination_kind": "rclone", "offsite": True}))
    return str(f)


# --- startup -------------------------------------------------------------------------------------
def test_mode_must_be_known():
    with pytest.raises(ValueError):
        Settings(app_mode="production")
    assert Settings(app_mode="LIMITED").app_mode == "limited"


def test_demo_and_limited_start_with_mock_and_demo_data():
    for mode in ("demo", "limited"):
        s = Settings(app_mode=mode, ai_provider="mock")
        assert modes.startup_problems(s) == []
        assert modes.policy(s).mock_ai_allowed and modes.policy(s).demo_data_allowed and not modes.policy(s).real_filing_decisions
    assert modes.policy(Settings(app_mode="limited")).notice and "KHÔNG" in modes.policy(Settings(app_mode="limited")).notice


def test_full_mode_with_mock_ai_refuses_startup():
    s = Settings(app_mode="full", app_env="production", ai_provider="mock", app_secret_key="x" * 40)
    problems = modes.startup_problems(s)
    assert any("mock" in p for p in problems)
    with pytest.raises(RuntimeError, match="APP_MODE=full refused"):
        modes.enforce_startup(s)


def test_full_mode_with_missing_provider_credential_refuses_startup():
    s = Settings(app_mode="full", app_env="production", ai_provider="http-llm", ai_provider_base_url="https://llm.example.test",
                 ai_provider_api_key=None, ai_provider_model="m", app_secret_key="x" * 40, ai_daily_budget_usd=1, backup_status_file="/x")
    problems = modes.startup_problems(s)
    assert any("AI_PROVIDER_API_KEY" in p for p in problems)
    with pytest.raises(RuntimeError):
        modes.enforce_startup(s)


def test_full_mode_requires_budget_and_backup_status_and_non_dev_env():
    s = Settings(app_mode="full", app_env="test", ai_provider="http-llm", ai_provider_base_url="https://llm.example.test",
                 ai_provider_api_key="k" * 20, ai_provider_model="m")
    joined = " ".join(modes.startup_problems(s))
    assert "AI_DAILY_BUDGET_USD" in joined and "BACKUP_STATUS_FILE" in joined and "development/test" in joined


def test_create_app_refuses_full_mode_with_mock(reset_runtime):
    from app.main import create_app  # import first: app.main builds the default (demo) app at import time

    _apply(reset_runtime, {"APP_MODE": "full", "APP_ENV": "production", "AI_PROVIDER": "mock", "APP_SECRET_KEY": "y" * 40})
    with pytest.raises(RuntimeError, match="mock"):
        create_app()


def test_per_capability_provider_selection(reset_runtime):
    s = _apply(reset_runtime, {"AI_PROVIDER": "mock", "COPILOT_PROVIDER": "http-llm"})
    assert s.provider_for("document_ai") == "mock" and s.provider_for("copilot") == "http-llm"
    with pytest.raises(gateway.ProviderNotConfigured):  # selected but no credentials → refused, no fallback to mock
        gateway.get_capability("copilot")
    assert gateway.get_capability("document_ai").name == "mock"


def test_http_llm_never_implements_ocr(reset_runtime):
    _apply(reset_runtime, FULL_ENV | {"DOCUMENT_OCR_PROVIDER": "http-llm", "APP_ENV": "test", "APP_MODE": "demo"})
    with pytest.raises(gateway.ProviderNotConfigured, match="OCR"):
        gateway.get_capability("document_ocr")


# --- readiness -----------------------------------------------------------------------------------
def test_demo_mode_ready_reports_mode_and_release_sha(client, reset_runtime):
    _apply(reset_runtime, {"RELEASE_SHA": "abc123def456"})
    r = client.get("/ready")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["mode"] == "demo" and b["checks"]["release_sha"] == "abc123def456" and b["checks"]["ai_provider"] == "mock"
    assert b["checks"]["migration_in_sync"] is True and b["checks"]["migrations"] == b["checks"]["migration_head"]
    assert set(b["checks"]["providers"]) == {"document_ocr", "document_ai", "hs_ai", "copilot"}
    assert b["checks"]["customs_data_authoritative"]["all_authoritative"] is False  # demo data only
    assert b["blocking"] == []


def test_limited_mode_with_demo_data_is_allowed_with_visible_warning(world, client, reset_runtime):
    _apply(reset_runtime, {"APP_MODE": "limited"})
    assert client.get("/ready").status_code == 200
    assert client.get("/api/v1/knowledge/datasets", headers=world.h()).status_code == 200  # lazily seeds the demo datasets
    n = client.get("/api/v1/knowledge/notice", headers=world.h()).json()
    assert n["app_mode"] == "limited" and n["demo_active"] is True and n["mock_ai_active"] is True
    assert n["mode_notice"] and "KHÔNG" in n["mode_notice"] and n["real_filing_decisions"] is False


def test_full_mode_readiness_fails_with_mock_ai_and_demo_data(world, client, reset_runtime):
    # Startup would refuse this configuration; readiness must ALSO fail if the mode is flipped on a running process.
    _apply(reset_runtime, {"APP_MODE": "full"})
    r = client.get("/ready")
    assert r.status_code == 503
    b = r.json()
    assert b["status"] == "not_ready" and b["mode"] == "full"
    assert any("mock provider not allowed" in x for x in b["blocking"])
    assert any("authoritative customs data unavailable" in x for x in b["blocking"])
    assert any("backup status" in x for x in b["blocking"])


def test_full_mode_readiness_fails_on_expired_authoritative_dataset(world, client, reset_runtime, tmp_path):
    db = get_sessionmaker()()
    admin = db.execute(select(User).where(User.id == world.users[("T1", "ADMIN")].id)).scalar_one()
    _authoritative_world(db, admin, effective_to=date.today() - timedelta(days=1))
    db.close()
    _apply(reset_runtime, {"APP_MODE": "full", "BACKUP_STATUS_FILE": _fresh_backup(tmp_path)})
    b = client.get("/ready").json()
    assert b["status"] == "not_ready"
    cds = b["checks"]["customs_data_authoritative"]
    assert cds["all_authoritative"] is False and all(cds[k]["authoritative"] is False for k in KINDS)


def test_full_mode_customs_data_check_passes_with_verified_current_authoritative_data(world, client, reset_runtime, tmp_path):
    db = get_sessionmaker()()
    admin = db.execute(select(User).where(User.id == world.users[("T1", "ADMIN")].id)).scalar_one()
    _authoritative_world(db, admin)
    db.close()
    _apply(reset_runtime, {"APP_MODE": "full", "BACKUP_STATUS_FILE": _fresh_backup(tmp_path)})
    b = client.get("/ready").json()
    cds = b["checks"]["customs_data_authoritative"]
    assert cds["all_authoritative"] is True and all(cds[k]["is_demo"] is False for k in KINDS)
    assert b["checks"]["backup_status"]["state"] == "fresh"
    # still not ready: AI providers are mock → the ONLY remaining blockers are the providers
    assert b["status"] == "not_ready" and all("provider" in x for x in b["blocking"]), b["blocking"]


def test_full_mode_readiness_fails_on_stale_backup(reset_runtime, tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"last_success_at": (datetime.now(UTC) - timedelta(hours=40)).isoformat()}))
    s = Settings(app_mode="full", backup_status_file=str(f))
    assert readiness.backup_status(s)["state"] == "stale"
    s2 = Settings(backup_status_file=str(tmp_path / "missing.json"))
    assert readiness.backup_status(s2)["state"] == "missing"


def test_metrics_endpoint_exposes_mode_http_and_ai_counters(client):
    client.get("/health")
    r = client.get("/metrics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert 'vip_app_mode_info{mode="demo"} 1' in body and "vip_http_requests_total" in body and "vip_ai_cost_usd_today" in body
    assert "vip_http_5xx_total" in body and "Authorization" not in body
