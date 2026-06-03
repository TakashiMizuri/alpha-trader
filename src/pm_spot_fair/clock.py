"""Event windows and time-to-expiry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Window:
    window_id: str
    t0_utc: datetime
    t_end_utc: datetime


def _parse_utc(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def tau_sec(now_utc: datetime, window: Window) -> float:
    """Seconds until window end; 0 if at or past end."""
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    end = window.t_end_utc
    delta = (end - now_utc).total_seconds()
    return max(0.0, delta)


def load_windows(path: Path) -> list[Window]:
    """Load PM windows from JSON: [{window_id, t0_utc, t_end_utc, slug?}, ...]."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    windows: list[Window] = []
    for i, row in enumerate(raw):
        wid = row.get("window_id") or row.get("slug") or f"win_{i}"
        t0 = _parse_utc(row["t0_utc"])
        t_end = _parse_utc(row["t_end_utc"])
        windows.append(Window(window_id=wid, t0_utc=t0, t_end_utc=t_end))
    return windows


def s0_for_window(klines_before: list[dict], window: Window) -> float | None:
    """S_0 = open of first kline at or after window t0 (v0 proxy)."""
    t0_ms = int(window.t0_utc.timestamp() * 1000)
    for k in klines_before:
        if k["t"] >= t0_ms:
            return float(k["o"])
    return None


def windows_from_klines(klines: list[dict]) -> list[Window]:
    """Phase 1 v0: each 5m bar is a window (open → close+5m)."""
    windows: list[Window] = []
    for k in klines:
        t0 = datetime.fromtimestamp(k["t"] / 1000.0, tz=timezone.utc)
        t_end = datetime.fromtimestamp((k["t"] + 300_000) / 1000.0, tz=timezone.utc)
        wid = f"binance_5m_{k['t']}"
        windows.append(Window(window_id=wid, t0_utc=t0, t_end_utc=t_end))
    return windows
