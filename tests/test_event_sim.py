"""Synthetic EventSim and stress replay."""

from __future__ import annotations

from pm_spot_fair.config import ArbConfig
from pm_spot_fair.pm_book import taker_fill_price
from pm_spot_fair.sim.backtest_opts import ArbReplayOptions
from pm_spot_fair.sim.bankroll import simulate_bankroll
from pm_spot_fair.sim.event_sim import EventSim
from pm_spot_fair.sim.market_log_arb import backtest_arb_market_log


def test_taker_fill_worse_than_touch() -> None:
    touch = taker_fill_price(
        "buy_yes", yes_bid=0.48, yes_ask=0.52, mode="touch"
    )
    half = taker_fill_price(
        "buy_yes", yes_bid=0.48, yes_ask=0.52, mode="half_spread"
    )
    nightmare = taker_fill_price(
        "buy_yes", yes_bid=0.48, yes_ask=0.52, mode="nightmare", slippage=0.05
    )
    assert half > touch
    assert nightmare > half


def test_cooldown_reduces_trades() -> None:
    cfg = ArbConfig(min_edge=0.03, min_tau_sec=30.0, taker_fee=0.01)
    rows = []
    for w in [1_000, 2_000, 3_000]:
        rows.append(
            {
                "symbol": "BTCUSDT",
                "window_t0_ms": w,
                "p_star": 0.65,
                "yes_bid": 0.50,
                "yes_ask": 0.52,
                "tau_sec": 200.0,
                "spread_pm": 0.02,
                "mock_pm": False,
                "_tick_ms": w + 100,
            }
        )
        rows.append(
            {
                "type": "settle",
                "symbol": "BTCUSDT",
                "window_t0_ms": w,
                "outcome_up": True,
            }
        )
    base = backtest_arb_market_log(rows, cfg, ArbReplayOptions())
    cool = backtest_arb_market_log(
        rows, cfg, ArbReplayOptions(cooldown_sec=5000.0)
    )
    assert base["n_trades"] == 3
    assert cool["n_trades"] == 1


def test_event_sim_generates_settles() -> None:
    klines = [
        {"t": 1_000_000, "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.2, "v": 1},
        {"t": 1_300_000, "o": 100.2, "h": 101.0, "l": 99.0, "c": 100.5, "v": 1},
        {"t": 1_600_000, "o": 100.5, "h": 99.0, "l": 98.0, "c": 99.0, "v": 1},
    ]
    rows = EventSim().rows_from_klines(klines)
    settles = [r for r in rows if r.get("type") == "settle"]
    ticks = [r for r in rows if r.get("type") != "settle"]
    assert len(settles) >= 1
    assert len(ticks) > 0


def test_bankroll_sim() -> None:
    trades = [
        {
            "window_t0_ms": 1,
            "symbol": "BTCUSDT",
            "action": "buy_yes",
            "entry_price": 0.5,
            "pnl": 0.47,
        }
    ]
    br = simulate_bankroll(trades, start=100.0, stake_pct=0.015, compound=True)
    assert br["end"] > 100.0
