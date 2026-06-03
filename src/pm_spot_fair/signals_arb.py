"""Arbitrage sleeve signals — phase 2."""

from __future__ import annotations

from typing import Literal

Action = Literal["buy_yes", "sell_yes", "skip"]


def decide_arb(*args, **kwargs) -> Action:
    raise NotImplementedError("signals_arb is implemented in phase 2")
