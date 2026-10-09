"""Token/cost accounting and daily budget enforcement for real AI providers (G18).

In-process, thread-safe, UTC-day window. It is deliberately simple: the point is that a
misconfigured or runaway integration stops *before* the invoice does, and that every call has
a correlation id and a cost line in the logs. Persisting the ledger is a later gate; the
counters are also exported on /metrics so an external monitor can graph them.

Nothing here ever logs prompt or document content.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.ai.base import CallMeta, ProviderBudgetExceeded

log = logging.getLogger("vip.ai.accounting")


@dataclass
class DailyLedger:
    day: str
    calls: int = 0
    failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    by_capability: dict[str, int] = field(default_factory=dict)


class Accountant:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ledger = DailyLedger(day=self._today())

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).date().isoformat()

    def _roll(self) -> DailyLedger:
        today = self._today()
        if self._ledger.day != today:
            self._ledger = DailyLedger(day=today)
        return self._ledger

    def check_budget(self, budget_usd: float | None, capability: str) -> None:
        """Raise before a call when the day's spend has reached the budget.

        Spend = max(in-process ledger, persisted ledger for today). The persisted sum makes the budget survive
        restarts (G18B); if the database is unreachable the in-process figure still applies (never skips the check).
        """
        if budget_usd is None:
            return
        with self._lock:
            spent = self._roll().cost_usd
        spent = max(spent, self.persisted_spend_today())
        if spent >= budget_usd:
            raise ProviderBudgetExceeded(f"daily AI budget reached ({spent:.4f} >= {budget_usd:.4f} USD); {capability} refused")

    @staticmethod
    def persisted_spend_today() -> float:
        try:
            from sqlalchemy import func, select

            from app.db import get_sessionmaker
            from app.models.ai_usage import AiUsageEvent

            start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            with get_sessionmaker()() as db:
                return float(db.execute(select(func.coalesce(func.sum(AiUsageEvent.cost_usd), 0.0))
                                        .where(AiUsageEvent.created_at >= start)).scalar() or 0.0)
        except Exception as exc:  # noqa: BLE001 - accounting must never break a request path
            log.warning("ai_ledger_read_failed detail=%s", type(exc).__name__)
            return 0.0

    @staticmethod
    def persist(meta: CallMeta) -> None:
        """Write one ledger row (accounting fields only). Failure is logged, never raised."""
        try:
            from app.db import get_sessionmaker
            from app.models.ai_usage import AiUsageEvent

            with get_sessionmaker()() as db:
                db.add(AiUsageEvent(correlation_id=meta.correlation_id, capability=meta.capability, provider=meta.provider, model=meta.model,
                                    outcome=meta.outcome, attempts=meta.attempts, latency_ms=meta.latency_ms, input_tokens=meta.input_tokens,
                                    output_tokens=meta.output_tokens, cost_usd=meta.cost_usd))
                db.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("ai_ledger_write_failed correlation_id=%s detail=%s", meta.correlation_id, type(exc).__name__)

    def record(self, meta: CallMeta) -> None:
        with self._lock:
            led = self._roll()
            led.calls += 1
            if meta.outcome != "ok":
                led.failures += 1
            led.input_tokens += meta.input_tokens
            led.output_tokens += meta.output_tokens
            led.cost_usd = round(led.cost_usd + meta.cost_usd, 6)
            led.by_capability[meta.capability] = led.by_capability.get(meta.capability, 0) + 1
        self.persist(meta)
        log.info("ai_call correlation_id=%s capability=%s provider=%s model=%s outcome=%s attempts=%d latency_ms=%d "
                 "in_tokens=%d out_tokens=%d cost_usd=%.6f", meta.correlation_id, meta.capability, meta.provider, meta.model,
                 meta.outcome, meta.attempts, meta.latency_ms, meta.input_tokens, meta.output_tokens, meta.cost_usd)

    def snapshot(self) -> DailyLedger:
        with self._lock:
            led = self._roll()
            return DailyLedger(led.day, led.calls, led.failures, led.input_tokens, led.output_tokens, led.cost_usd, dict(led.by_capability))

    def reset(self) -> None:  # tests only
        with self._lock:
            self._ledger = DailyLedger(day=self._today())


def estimate_cost(input_tokens: int, output_tokens: int, per_1k_in: float, per_1k_out: float) -> float:
    return round(input_tokens / 1000.0 * per_1k_in + output_tokens / 1000.0 * per_1k_out, 6)


ACCOUNTANT = Accountant()
