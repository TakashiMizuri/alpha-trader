"""Arb signal and market-log backtest."""

from __future__ import annotations

from pm_spot_fair.config import ArbConfig
from pm_spot_fair.signals_arb import decide_arb, settle_pnl
from pm_spot_fair.sim.backtest_opts import ArbReplayOptions
from pm_spot_fair.sim.market_log_arb import backtest_arb_market_log


def test_decide_buy_yes() -> None:
    cfg = ArbConfig(min_edge=0.03, taker_fee=0.01, pm_fee_rate=None)
    action, edge = decide_arb(
        p_star=0.60,
        yes_bid=0.50,
        yes_ask=0.52,
        tau_sec=120.0,
        cfg=cfg,
    )
    assert action == "buy_yes"
    assert edge == 0.60 - 0.52 - 0.01


def test_settle_pnl_buy_win() -> None:
    assert settle_pnl("buy_yes", entry_price=0.52, outcome_up=True, fee=0.01) == 0.47


def test_market_log_backtest_one_window() -> None:
    cfg = ArbConfig(min_edge=0.03, min_tau_sec=30.0, taker_fee=0.01, pm_fee_rate=None)
    rows = [
        {
            "symbol": "BTCUSDT",
            "window_t0_ms": 1_000,
            "p_star": 0.65,
            "yes_bid": 0.50,
            "yes_ask": 0.52,
            "tau_sec": 200.0,
            "spread_pm": 0.02,
            "mock_pm": False,
            "_tick_ms": 100,
        },
        {
            "type": "settle",
            "symbol": "BTCUSDT",
            "window_t0_ms": 1_000,
            "outcome_up": True,
            "p_star": 1.0,
            "p_mkt_mid": 0.99,
        },
    ]
    rep = backtest_arb_market_log(rows, cfg, ArbReplayOptions())
    assert rep["n_trades"] == 1
    assert rep["total_pnl"] == 0.47
    assert rep["win_rate"] == 1.0


def test_stress_fill_reduces_pnl() -> None:
    cfg = ArbConfig(min_edge=0.03, min_tau_sec=30.0, taker_fee=0.01, pm_fee_rate=None)
    rows = [
        {
            "symbol": "BTCUSDT",
            "window_t0_ms": 1_000,
            "p_star": 0.65,
            "yes_bid": 0.50,
            "yes_ask": 0.52,
            "tau_sec": 200.0,
            "spread_pm": 0.02,
            "mock_pm": False,
            "_tick_ms": 100,
        },
        {
            "type": "settle",
            "symbol": "BTCUSDT",
            "window_t0_ms": 1_000,
            "outcome_up": True,
        },
    ]
    base = backtest_arb_market_log(rows, cfg, ArbReplayOptions())
    stress = backtest_arb_market_log(
        rows,
        cfg,
        ArbReplayOptions(fill_mode="half_spread", slippage=0.01),
    )
    assert stress["total_pnl"] < base["total_pnl"]
