"""Bankroll simulation on arb trade list — phase 2."""

from __future__ import annotations

from typing import Any


def shares_for_stake(action: str, stake_usd: float, entry_price: float) -> float:
    if stake_usd <= 0 or entry_price <= 0:
        return 0.0
    if action == "buy_yes":
        return stake_usd / entry_price
    risk = 1.0 - entry_price
    return stake_usd / risk if risk > 0.01 else 0.0


def simulate_bankroll(
    trades: list[dict[str, Any]],
    *,
    start: float,
    stake_pct: float,
    compound: bool = True,
) -> dict[str, Any]:
    """Apply stake_pct of balance per trade in chronological order."""
    ordered = sorted(
        trades,
        key=lambda t: (t.get("window_t0_ms", 0), t.get("symbol", "")),
    )
    bal = start
    peak = bal
    max_dd = 0.0
    curve: list[dict[str, float]] = []

    for t in ordered:
        stake = bal * stake_pct if compound else start * stake_pct
        sh = shares_for_stake(t["action"], stake, float(t["entry_price"]))
        pnl = float(t["pnl"]) * sh
        bal += pnl
        peak = max(peak, bal)
        if peak > 0:
            max_dd = max(max_dd, (peak - bal) / peak)
        curve.append({"balance": round(bal, 4), "pnl": round(pnl, 4)})

    return {
        "start": start,
        "end": round(bal, 4),
        "profit": round(bal - start, 4),
        "return_pct": round((bal / start - 1) * 100, 2) if start else 0.0,
        "max_drawdown_pct": round(max_dd * 100, 2),
        "stake_pct": stake_pct,
        "compound": compound,
    }
