"""Latency timestamps and simple histograms — phase 1b/6."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


def monotonic_ns() -> int:
    return time.monotonic_ns()


def utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@dataclass
class LatencyHistogram:
    """Rolling sample of delays in milliseconds."""

    name: str
    _samples_ms: list[float] = field(default_factory=list)
    max_samples: int = 10_000

    def record_ms(self, ms: float) -> None:
        self._samples_ms.append(ms)
        if len(self._samples_ms) > self.max_samples:
            self._samples_ms = self._samples_ms[-self.max_samples :]

    def percentile(self, p: float) -> float:
        if not self._samples_ms:
            return 0.0
        sorted_s = sorted(self._samples_ms)
        idx = min(int(len(sorted_s) * p / 100.0), len(sorted_s) - 1)
        return sorted_s[idx]

    @property
    def p50(self) -> float:
        return self.percentile(50)

    @property
    def p95(self) -> float:
        return self.percentile(95)
