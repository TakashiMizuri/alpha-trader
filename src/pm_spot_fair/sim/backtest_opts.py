"""Backtest replay options — phase 2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FillMode = Literal["touch", "half_spread", "full_spread", "extreme", "nightmare"]


@dataclass(frozen=True)
class ArbReplayOptions:
    max_spread: float = 0.08
    lag_ms: float | None = None
    cooldown_sec: float = 0.0
    one_per_window: bool = True
    fill_mode: FillMode = "touch"
    slippage: float = 0.0
    bankroll_start: float | None = None
    stake_pct: float | None = None
    bankroll_compound: bool = True
