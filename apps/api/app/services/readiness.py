"""Readiness evaluation with mode-aware, fail-closed requirements (G18).

/ready reports: mode, database, migration (current vs head), AI providers per capability,
authoritative customs data per kind, backup status, release SHA. In FULL mode readiness FAILS
when any of these is missing: a real AI provider that is configured and healthy for every
capability, a verified authoritative (non-demo, non-expired, non-superseded) dataset for every
knowledge kind, migration at head, a fresh backup status. Demo and limited modes report the same
facts but only require database + migration + a configured provider.

Secrets are never part of the output.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai import gateway
from app.core.config import AI_CAPABILITIES, Settings, get_settings
from app.core.modes import MOCK_PROVIDERS

KNOWLEDGE_KINDS = ("HS_RULES", "TARIFF", "FTA", "POLICY")


@dataclass
class Readiness:
    ok: bool
    mode: str
    checks: dict[str, Any]
    blocking: list[str] = field(default_factory=list)

    def body(self) -> dict[str, Any]:
        return {"status": "ready" if self.ok else "not_ready", "mode": self.mode, "checks": self.checks, "blocking": self.blocking}


def alembic_head() -> str | None:
    """Head revision of the bundled migration scripts (not the database)."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        cfg = Config(os.path.join(here, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(here, "alembic"))
        heads = ScriptDirectory.from_config(cfg).get_heads()
        return heads[0] if len(heads) == 1 else None
    except Exception:  # noqa: BLE001
        return None


def backup_status(settings: Settings) -> dict[str, Any]:
    """Reads the JSON written by scripts/production/backup_offsite.sh. Missing file → 'unknown'."""
    path = settings.backup_status_file
    if not path:
        return {"state": "unconfigured"}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        last = datetime.fromisoformat(str(data.get("last_success_at")).replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        age_h = (datetime.now(UTC) - last).total_seconds() / 3600.0
        fresh = age_h <= settings.backup_max_age_hours
        return {"state": "fresh" if fresh else "stale", "last_success_at": last.isoformat(), "age_hours": round(age_h, 1),
                "destination": data.get("destination_kind"), "offsite": bool(data.get("offsite"))}
    except FileNotFoundError:
        return {"state": "missing", "path_configured": True}
    except (ValueError, TypeError, OSError) as exc:
        return {"state": "invalid", "detail": type(exc).__name__}


def customs_data_status(db: Session, settings: Settings) -> dict[str, Any]:
    from app.services.customs_data import ConflictingDatasets, NoActiveDataset, describe, select_dataset

    out: dict[str, Any] = {}
    all_ok = True
    for kind in KNOWLEDGE_KINDS:
        try:
            ds = select_dataset(db, kind, date.today(), mode="full")  # authoritative-only view, regardless of current mode
            out[kind] = describe(ds) | {"authoritative": True}
        except ConflictingDatasets as exc:
            out[kind] = {"authoritative": False, "reason": "conflict", "detail": str(exc)}
            all_ok = False
        except NoActiveDataset as exc:
            out[kind] = {"authoritative": False, "reason": str(exc) or "none"}
            all_ok = False
    out["all_authoritative"] = all_ok
    return out


def evaluate(db: Session | None, settings: Settings | None = None, *, live_provider_probe: bool = True) -> Readiness:
    s = settings or get_settings()
    full = s.is_full_mode
    checks: dict[str, Any] = {"mode": s.app_mode, "environment": s.app_env, "release_sha": s.release_sha}
    blocking: list[str] = []
    ok = True

    # --- database + migrations
    head = alembic_head()
    checks["migration_head"] = head or "unknown"
    try:
        if db is None:
            raise RuntimeError("no session")
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
        rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        checks["migrations"] = rev or "missing"
        in_sync = bool(rev) and (head is None or rev == head)
        checks["migration_in_sync"] = in_sync
        if not rev:
            ok = False
            blocking.append("migrations missing")
        elif not in_sync:
            blocking.append(f"migration mismatch: db={rev} head={head}")
            ok = False
    except Exception as exc:  # noqa: BLE001 - readiness must report, not raise
        checks["database"] = f"error: {type(exc).__name__}"
        checks["migrations"] = "unknown"
        checks["migration_in_sync"] = False
        ok = False
        blocking.append("database unreachable")

    # --- AI providers
    status = gateway.provider_status(live=live_provider_probe and full)
    checks["providers"] = status
    checks["ai_provider"] = status["document_ai"]["name"] if status["document_ai"]["configured"] else f"error: {status['document_ai']['detail']}"
    checks["document_provider"] = status["document_ocr"]["name"]
    for cap in AI_CAPABILITIES:
        st = status[cap]
        if not st["configured"]:
            ok = False
            blocking.append(f"{cap}: provider not configured ({st['detail']})")
        elif full:
            if st["name"] in MOCK_PROVIDERS or st["is_mock"]:
                ok = False
                blocking.append(f"{cap}: mock provider not allowed in full mode")
            elif not st["healthy"]:
                ok = False
                blocking.append(f"{cap}: provider unhealthy ({st['detail']})")

    # --- customs data
    if db is not None and checks.get("database") == "ok" and checks.get("migrations") not in (None, "missing", "unknown"):
        try:
            cds = customs_data_status(db, s)
        except Exception as exc:  # noqa: BLE001 - e.g. migration 0011 not applied yet
            cds = {"all_authoritative": False, "error": type(exc).__name__}
        checks["customs_data_authoritative"] = cds
        if full and not cds.get("all_authoritative"):
            ok = False
            missing = [k for k in KNOWLEDGE_KINDS if not (cds.get(k) or {}).get("authoritative")]
            blocking.append("authoritative customs data unavailable for: " + ", ".join(missing))
    else:
        checks["customs_data_authoritative"] = {"all_authoritative": False, "reason": "database unavailable"}
        if full:
            ok = False

    # --- backup
    bs = backup_status(s)
    checks["backup_status"] = bs
    if full and bs.get("state") != "fresh":
        ok = False
        blocking.append(f"backup status {bs.get('state')}")

    # --- mandatory production dependency: a real secret (never printed)
    if full:
        try:
            s.resolved_secret()
        except RuntimeError as exc:
            ok = False
            blocking.append(str(exc))

    return Readiness(ok=ok, mode=s.app_mode, checks=checks, blocking=blocking)


def metrics_lines(db: Session | None) -> list[str]:
    """Extra Prometheus lines: mode, providers, cost ledger, dataset age."""
    from app.ai.accounting import ACCOUNTANT

    s = get_settings()
    lines = ["# TYPE vip_app_mode_info gauge", f'vip_app_mode_info{{mode="{s.app_mode}"}} 1']
    from app.core.ratelimit import login_limiters

    lims = login_limiters()
    lines += ["# TYPE vip_login_throttled_total counter", f"vip_login_throttled_total {lims.throttled_total}",
              "# TYPE vip_login_locks_total counter", f"vip_login_locks_total {lims.locks_total}",
              "# TYPE vip_login_tracked_keys gauge",
              f'vip_login_tracked_keys{{dimension="pair"}} {lims.pair.tracked_keys()}',
              f'vip_login_tracked_keys{{dimension="email"}} {lims.email.tracked_keys()}',
              f'vip_login_tracked_keys{{dimension="ip"}} {lims.ip.tracked_keys()}']
    led = ACCOUNTANT.snapshot()
    lines += ["# TYPE vip_ai_calls_total counter", f"vip_ai_calls_total {led.calls}", "# TYPE vip_ai_failures_total counter",
              f"vip_ai_failures_total {led.failures}", "# TYPE vip_ai_cost_usd_today gauge", f"vip_ai_cost_usd_today {led.cost_usd}",
              "# TYPE vip_ai_tokens_today gauge", f'vip_ai_tokens_today{{direction="input"}} {led.input_tokens}',
              f'vip_ai_tokens_today{{direction="output"}} {led.output_tokens}']
    for cap, st in gateway.provider_status(live=False).items():
        lines.append(f'vip_ai_provider_configured{{capability="{cap}",provider="{st["name"]}"}} {int(bool(st["configured"]))}')
    if db is not None:
        try:
            from app.services.customs_data import active_dataset_ages

            for kind, (age_days, authoritative) in active_dataset_ages(db).items():
                lines.append(f'vip_customs_dataset_age_days{{kind="{kind}",authoritative="{str(authoritative).lower()}"}} {age_days}')
        except Exception:  # noqa: BLE001
            pass
    bs = backup_status(s)
    if "age_hours" in bs:
        lines += ["# TYPE vip_backup_age_hours gauge", f"vip_backup_age_hours {bs['age_hours']}"]
    return lines
