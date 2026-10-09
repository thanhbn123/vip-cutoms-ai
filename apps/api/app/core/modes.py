"""Explicit runtime modes (G18): demo | limited | full.

The mode decides what the application is *allowed* to rely on. It never widens what the
product does: no mode submits anything to a customs system (product rule #7).

    demo     mock AI and demo knowledge data allowed; for development, acceptance and training.
    limited  real users; DRAFT workflow only; mock/demo limitations are prominently visible;
             no real customs filing decision is produced.
    full     requires real AI providers that are configured AND healthy, authoritative customs
             datasets active for every kind, migrations at head and production controls. The
             application REFUSES to start (configuration problems) or to report ready (runtime
             problems) when any requirement is missing. There is no silent downgrade to demo.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import AI_CAPABILITIES, Settings

MOCK_PROVIDERS = {"mock"}
# Vietnamese UI notice for limited mode (demo-data notice stays in app.services.declaration).
LIMITED_MODE_NOTICE = ("CHẾ ĐỘ GIỚI HẠN (LIMITED): chỉ soạn tờ khai NHÁP nội bộ; AI/dữ liệu tri thức có thể là mock/demo; "
                       "KHÔNG dùng để khai hải quan thực; không kết nối VNACCS.")
DEMO_MODE_NOTICE = "CHẾ ĐỘ DEMO: AI mock + dữ liệu demo — chỉ để nghiệm thu quy trình, không khai hải quan."


@dataclass(frozen=True)
class ModePolicy:
    mode: str
    mock_ai_allowed: bool
    demo_data_allowed: bool
    real_filing_decisions: bool  # the ONLY mode in which rule-derived values may be called authoritative
    notice: str | None


POLICIES: dict[str, ModePolicy] = {
    "demo": ModePolicy("demo", mock_ai_allowed=True, demo_data_allowed=True, real_filing_decisions=False, notice=DEMO_MODE_NOTICE),
    "limited": ModePolicy("limited", mock_ai_allowed=True, demo_data_allowed=True, real_filing_decisions=False,
                          notice=LIMITED_MODE_NOTICE),
    "full": ModePolicy("full", mock_ai_allowed=False, demo_data_allowed=False, real_filing_decisions=True, notice=None),
}


def policy(settings: Settings) -> ModePolicy:
    return POLICIES[settings.app_mode]


def startup_problems(settings: Settings) -> list[str]:
    """Configuration-level requirements that can be checked without a database. Empty list = OK.

    Runtime requirements (provider health, authoritative datasets, migration head, backup
    freshness) are checked by app.services.readiness on every /ready call.
    """
    problems: list[str] = []
    if not settings.is_full_mode:
        return problems
    if settings.is_development:
        problems.append("APP_MODE=full is not allowed with APP_ENV=development/test")
    for cap in AI_CAPABILITIES:
        name = settings.provider_for(cap)
        if name in MOCK_PROVIDERS:
            problems.append(f"{cap}: provider '{name}' is a mock; full mode requires a real provider")
    if not settings.real_provider_configured():
        problems.append("AI_PROVIDER_BASE_URL / AI_PROVIDER_API_KEY / AI_PROVIDER_MODEL must all be set in full mode")
    if settings.ai_daily_budget_usd is None:
        problems.append("AI_DAILY_BUDGET_USD must be set in full mode (cost control)")
    if not settings.backup_status_file:
        problems.append("BACKUP_STATUS_FILE must be set in full mode (backup freshness is a readiness check)")
    return problems


def enforce_startup(settings: Settings) -> None:
    problems = startup_problems(settings)
    if problems:
        raise RuntimeError("APP_MODE=full refused: " + "; ".join(problems))
