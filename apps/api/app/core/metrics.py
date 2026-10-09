"""Basic local metrics (G18, no paid service): Prometheus text exposition at /metrics.

In-process counters only — enough for a free scraper (Prometheus, Uptime Kuma "keyword"
checks, a cron + curl) to alert on 5xx rate, provider failures, cost and dataset age. No
labels carry tenant, user, case or document identifiers (docs/G18_MONITORING_ALERTS.md).
"""

from __future__ import annotations

import threading
from collections import Counter
from collections.abc import Iterable

_lock = threading.Lock()
_http: Counter = Counter()  # key: (method, status_class)
_http_5xx = 0


def observe_http(method: str, status: int) -> None:
    global _http_5xx
    with _lock:
        _http[(method, f"{status // 100}xx")] += 1
        if status >= 500:
            _http_5xx += 1


def reset() -> None:  # tests only
    global _http_5xx
    with _lock:
        _http.clear()
        _http_5xx = 0


def _line(name: str, value: float | int, labels: dict[str, str] | None = None) -> str:
    if labels:
        lab = ",".join(f'{k}="{str(v).replace(chr(34), "")}"' for k, v in sorted(labels.items()))
        return f"{name}{{{lab}}} {value}"
    return f"{name} {value}"


def render(extra: Iterable[str] = ()) -> str:
    """Prometheus 0.0.4 text format. `extra` lines come from the readiness/provider layers."""
    with _lock:
        http = dict(_http)
        five = _http_5xx
    lines = ["# TYPE vip_http_requests_total counter"]
    lines += [_line("vip_http_requests_total", v, {"method": m, "status_class": c}) for (m, c), v in sorted(http.items())]
    lines += ["# TYPE vip_http_5xx_total counter", _line("vip_http_5xx_total", five)]
    lines += list(extra)
    return "\n".join(lines) + "\n"
