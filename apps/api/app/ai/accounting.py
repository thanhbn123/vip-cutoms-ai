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
        """Raise before a call when the day's spend has reached the budget."""
        if budget_usd is None:
            return
        with self._lock:
            spent = self._roll().cost_usd
        if spent >= budget_usd:
            raise ProviderBudgetExceeded(f"daily AI budget reached ({spent:.4f} >= {budget_usd:.4f} USD); {capability} refused")

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
