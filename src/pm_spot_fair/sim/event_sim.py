"""Synthetic lagging PM from spot path — phase 2."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pm_spot_fair.clock import Window, tau_sec, windows_from_klines
from pm_spot_fair.fair import p_up_gbm
from pm_spot_fair.vol import sigma_ann_from_closes


@dataclass(frozen=True)
class EventSimConfig:
    lag_ms: float = 600.0
    pm_half_spread: float = 0.01
    pm_alpha: float = 0.12
    ticks_per_window: int = 10
    sigma_floor_ann: float = 0.15
    sigma_ewma_span: int = 60


class EventSim:
    """Build synthetic market-log rows from 5m klines (arb stress / --years)."""

    def __init__(self, cfg: EventSimConfig | None = None) -> None:
        self.cfg = cfg or EventSimConfig()

    def rows_from_klines(
        self,
        klines: list[dict],
        *,
        symbol: str = "BTCUSDT",
    ) -> list[dict[str, Any]]:
        windows = windows_from_klines(klines)
        k_by_t = {k["t"]: k for k in klines}
        idx_by_t = {k["t"]: i for i, k in enumerate(klines)}
        rows: list[dict[str, Any]] = []
        closes_hist: list[float] = []

        for w in windows:
            t0_ms = int(w.t0_utc.timestamp() * 1000)
            if t0_ms not in k_by_t:
                continue
            k = k_by_t[t0_ms]
            idx = idx_by_t[t0_ms]
            hist = [float(x["c"]) for x in klines[max(0, idx - 120) : idx]]
            if len(hist) < 2:
                continue
            sigma = max(
                sigma_ann_from_closes(hist, span=self.cfg.sigma_ewma_span),
                self.cfg.sigma_floor_ann,
            )
            s0 = float(k["o"])
            s_end = float(k["c"])
            outcome_up = s_end > s0
            pm_mid = 0.5
            t_end_ms = int(w.t_end_utc.timestamp() * 1000)

            for step in range(self.cfg.ticks_per_window):
                frac = (step + 1) / self.cfg.ticks_per_window
                ts_ms = t0_ms + int(frac * 300_000)
                if ts_ms >= t_end_ms:
                    ts_ms = t_end_ms - 1
                s_t = s0 + (s_end - s0) * frac
                now = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
                tau = tau_sec(now, w)
                p_star = p_up_gbm(s=s_t, s0=s0, tau_sec=tau, sigma_ann=sigma)
                pm_mid = pm_mid + self.cfg.pm_alpha * (p_star - pm_mid)
                bid = max(0.01, pm_mid - self.cfg.pm_half_spread)
                ask = min(0.99, pm_mid + self.cfg.pm_half_spread)
                rows.append(
                    {
                        "symbol": symbol,
                        "window_t0_ms": t0_ms,
                        "_tick_ms": ts_ms,
                        "p_star": round(p_star, 4),
                        "yes_bid": round(bid, 4),
                        "yes_ask": round(ask, 4),
                        "spread_pm": round(ask - bid, 4),
                        "tau_sec": round(tau, 3),
                        "mock_pm": False,
                    }
                )

            rows.append(
                {
                    "type": "settle",
                    "symbol": symbol,
                    "window_t0_ms": t0_ms,
                    "outcome_up": outcome_up,
                    "p_star": 1.0 if outcome_up else 0.0,
                    "p_mkt_mid": pm_mid,
                }
            )
            closes_hist.append(s_end)

        return rows
