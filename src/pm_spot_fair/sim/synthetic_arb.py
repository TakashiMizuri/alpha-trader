"""Arb backtest on synthetic klines via EventSim — phase 2."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pm_spot_fair.config import ArbConfig
from pm_spot_fair.sim.backtest_opts import ArbReplayOptions
from pm_spot_fair.sim.event_sim import EventSim, EventSimConfig
from pm_spot_fair.sim.market_log_arb import backtest_arb_market_log
from pm_spot_fair.spot import load_klines_years


def backtest_arb_klines(
    data_dir: Path,
    symbol: str,
    years: list[int],
    cfg: ArbConfig,
    opts: ArbReplayOptions | None = None,
    *,
    sim_cfg: EventSimConfig | None = None,
) -> dict[str, Any]:
    klines = load_klines_years(data_dir, symbol, years)
    sim = EventSim(sim_cfg)
    rows = sim.rows_from_klines(klines, symbol=symbol)
    report = backtest_arb_market_log(rows, cfg, opts)
    report["mode"] = "synthetic_klines"
    report["symbol"] = symbol
    report["years"] = years
    report["n_kline_windows"] = sum(1 for r in rows if r.get("type") == "settle")
    if sim_cfg or opts:
        report["sim_lag_ms"] = (sim_cfg or EventSimConfig()).lag_ms
    return report
