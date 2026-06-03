"""Health/status artifacts for ops and systemd watchdog."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class LoggerHealth:
    status: str  # ok | degraded | down
    ticks_written: int
    last_tick_utc: str | None
    binance_connected: bool
    pm_connected: bool
    mock_pm: bool
    feed_gap_sec: float | None
    pid: int
    symbols: list[str] = field(default_factory=list)
    ticks_by_symbol: dict[str, int] = field(default_factory=dict)
    pm_connected_symbols: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def write_health(path: Path, health: LoggerHealth) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(health.to_json(), encoding="utf-8")
    tmp.replace(path)


def utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
