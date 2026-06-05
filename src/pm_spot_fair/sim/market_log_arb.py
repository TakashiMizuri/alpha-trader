"""Replay phase 1b market logs — arb mark-to-settle (phase 2)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from pm_spot_fair.config import ArbConfig
from pm_spot_fair.pm_book import taker_fill_price
from pm_spot_fair.pm_book import taker_fee_per_share
from pm_spot_fair.signals_arb import Action, decide_arb, settle_pnl
from pm_spot_fair.sim.backtest_opts import ArbReplayOptions
from pm_spot_fair.sim.bankroll import simulate_bankroll


@dataclass(frozen=True)
class ArbTrade:
    symbol: str
    window_t0_ms: int
    tick_ms: int
    action: Action
    entry_price: float
    edge: float
    p_star: float
    tau_sec: float
    spread_pm: float
    outcome_up: bool
    pnl: float


def _window_key(row: dict[str, Any]) -> tuple[str, int]:
    return (row["symbol"], int(row["window_t0_ms"]))


def _tick_ms(row: dict[str, Any]) -> int:
    return int(row.get("_tick_ms", row.get("t", 0)))


def backtest_arb_market_log(
    rows: list[dict[str, Any]],
    cfg: ArbConfig,
    opts: ArbReplayOptions | None = None,
) -> dict[str, Any]:
    """
    Replay ticks with optional cooldown, fill stress, and bankroll sim.

    Default: one entry per (symbol, window) on first qualifying tick.
    ``cooldown_sec``: min wall-clock gap between trades per symbol.
    """
    opts = opts or ArbReplayOptions()
    ticks_by_window: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    settles: dict[tuple[str, int], dict[str, Any]] = {}

    for row in rows:
        if row.get("type") == "settle":
            settles[_window_key(row)] = row
            continue
        if row.get("mock_pm"):
            continue
        ticks_by_window[_window_key(row)].append(row)

    trades: list[ArbTrade] = []
    last_trade_ms: dict[str, int] = {}
    windows_seen = 0
    windows_traded = 0
    cooldown_skips = 0

    for key in sorted(ticks_by_window.keys()):
        settle = settles.get(key)
        if settle is None:
            continue
        windows_seen += 1
        outcome_up = bool(settle.get("outcome_up"))
        sym, w_ms = key
        window_ticks = sorted(ticks_by_window[key], key=_tick_ms)
        window_traded = False

        for tick in window_ticks:
            if opts.one_per_window and window_traded:
                break
            ts = _tick_ms(tick)
            if opts.cooldown_sec > 0 and sym in last_trade_ms:
                gap_ms = ts - last_trade_ms[sym]
                if gap_ms < opts.cooldown_sec * 1000:
                    cooldown_skips += 1
                    continue

            bid = float(tick.get("yes_bid", tick.get("yb", 0)))
            ask = float(tick.get("yes_ask", tick.get("ya", 1)))
            action, edge = decide_arb(
                p_star=float(tick["p_star"]),
                yes_bid=bid,
                yes_ask=ask,
                tau_sec=float(tick.get("tau_sec", tick.get("tau", 0))),
                cfg=cfg,
                max_spread=opts.max_spread,
                fill_mode=opts.fill_mode,
                slippage=opts.slippage,
            )
            if action == "skip":
                continue

            entry = taker_fill_price(
                action,
                yes_bid=bid,
                yes_ask=ask,
                mode=opts.fill_mode,
                slippage=opts.slippage,
            )
            fee = taker_fee_per_share(
                entry, flat_fee=cfg.taker_fee, fee_rate=cfg.pm_fee_rate
            )
            pnl = settle_pnl(
                action,
                entry_price=entry,
                outcome_up=outcome_up,
                fee=fee,
            )
            spread = float(tick.get("spread_pm", ask - bid))
            trades.append(
                ArbTrade(
                    symbol=sym,
                    window_t0_ms=w_ms,
                    tick_ms=ts,
                    action=action,
                    entry_price=round(entry, 4),
                    edge=round(edge, 4),
                    p_star=float(tick["p_star"]),
                    tau_sec=float(tick.get("tau_sec", tick.get("tau", 0))),
                    spread_pm=round(spread, 4),
                    outcome_up=outcome_up,
                    pnl=round(pnl, 4),
                )
            )
            last_trade_ms[sym] = ts
            window_traded = True
            windows_traded += 1

    total_pnl = sum(t.pnl for t in trades)
    wins = sum(1 for t in trades if t.pnl > 0)
    n = len(trades)
    by_sym: dict[str, dict[str, Any]] = {}
    for sym in sorted({t.symbol for t in trades}):
        st = [t for t in trades if t.symbol == sym]
        by_sym[sym] = {
            "n_trades": len(st),
            "total_pnl": round(sum(t.pnl for t in st), 4),
            "mean_pnl": round(sum(t.pnl for t in st) / len(st), 4) if st else 0.0,
            "win_rate": round(sum(1 for t in st if t.pnl > 0) / len(st), 4)
            if st
            else 0.0,
        }

    trade_dicts = [asdict(t) for t in trades]
    report: dict[str, Any] = {
        "sleeve": "arb",
        "mode": "market_log_replay",
        "lag_ms": opts.lag_ms,
        "min_edge": cfg.min_edge,
        "min_tau_sec": cfg.min_tau_sec,
        "taker_fee": cfg.taker_fee,
        "max_spread": opts.max_spread,
        "cooldown_sec": opts.cooldown_sec,
        "one_per_window": opts.one_per_window,
        "fill_mode": opts.fill_mode,
        "slippage": opts.slippage,
        "cooldown_skips": cooldown_skips,
        "windows_with_settle": windows_seen,
        "windows_traded": windows_traded,
        "n_trades": n,
        "total_pnl": round(total_pnl, 4),
        "mean_pnl_per_trade": round(total_pnl / n, 4) if n else 0.0,
        "win_rate": round(wins / n, 4) if n else 0.0,
        "per_symbol": by_sym,
        "trades": trade_dicts,
    }
    if opts.bankroll_start is not None and opts.stake_pct is not None:
        report["bankroll"] = simulate_bankroll(
            trade_dicts,
            start=opts.bankroll_start,
            stake_pct=opts.stake_pct,
            compound=opts.bankroll_compound,
        )
    return report
