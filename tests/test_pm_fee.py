"""Polymarket dynamic fee model."""

from __future__ import annotations

from pm_spot_fair.config import ArbConfig
from pm_spot_fair.pm_book import polymarket_taker_fee_per_share, taker_fee_per_share
from pm_spot_fair.signals_arb import decide_arb


def test_pm_fee_at_mid() -> None:
    fee = polymarket_taker_fee_per_share(0.5, 0.07)
    assert abs(fee - 0.0175) < 1e-6


def test_taker_fee_fallback() -> None:
    assert taker_fee_per_share(0.5, flat_fee=0.01, fee_rate=None) == 0.01
    assert taker_fee_per_share(0.5, flat_fee=0.01, fee_rate=0.07) == 0.0175


def test_decide_arb_uses_pm_fee() -> None:
    cfg = ArbConfig(min_edge=0.03, taker_fee=0.01, pm_fee_rate=0.07)
    action, edge = decide_arb(
        p_star=0.60,
        yes_bid=0.50,
        yes_ask=0.52,
        tau_sec=120.0,
        cfg=cfg,
    )
    fee = polymarket_taker_fee_per_share(0.52, 0.07)
    assert action == "buy_yes"
    assert abs(edge - (0.60 - 0.52 - fee)) < 1e-9
