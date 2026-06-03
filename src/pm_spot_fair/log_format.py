"""Compact JSONL rows for market logger — lossless vs expanded legacy schema."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

# Compact keys (v2). expand_log_row() restores legacy names for analysis/tools.
_KEY_TO_LEGACY: dict[str, str] = {
    "t": "ts_utc",
    "sym": "symbol",
    "te": "ts_binance_event",
    "tr": "ts_recv",
    "tp": "ts_pm_recv",
    "w": "window_t0_ms",
    "tau": "tau_sec",
    "s0": "s0",
    "st": "s_t",
    "sig": "sigma_ann",
    "ps": "p_star",
    "pm": "p_mkt_mid",
    "pu": "p_mkt_micro",
    "yb": "yes_bid",
    "ya": "yes_ask",
    "mock": "mock_pm",
    "pc": "pm_connected",
}


def _ms_to_iso(ms: int | float) -> str:
    dt = datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _iso_to_ms(iso: str) -> int:
    s = iso.rstrip("Z")
    if "." in s:
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f")
    else:
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _window_id(symbol: str, window_t0_ms: int) -> str:
    prefix = symbol.lower().replace("usdt", "")[:8]
    return f"{prefix}_5m_{window_t0_ms // 1000}"


def build_compact_row(
    *,
    symbol: str,
    window_t0_ms: int,
    ts_ms: int,
    b_event_ms: int,
    b_recv_ms: int,
    pm_recv_ms: int,
    s0: float,
    s_t: float,
    sigma: float,
    tau: float,
    p_star: float,
    p_mid: float,
    p_micro: float,
    bid: float,
    ask: float,
    pm_mock: bool,
    pm_connected: bool,
) -> dict[str, Any]:
    """Minimal row payload; derived fields added on expand."""
    return {
        "t": ts_ms,
        "sym": symbol,
        "te": b_event_ms,
        "tr": b_recv_ms,
        "tp": pm_recv_ms,
        "w": window_t0_ms,
        "tau": round(tau, 3),
        "s0": round(s0, 6),
        "st": round(s_t, 6),
        "sig": round(sigma, 4),
        "ps": round(p_star, 4),
        "pm": round(p_mid, 4),
        "pu": round(p_micro, 4),
        "yb": round(bid, 4),
        "ya": round(ask, 4),
        "mock": int(pm_mock),
        "pc": int(pm_connected),
    }


def serialize_row(row: dict[str, Any]) -> str:
    return json.dumps(row, separators=(",", ":"))


def is_compact_row(row: dict[str, Any]) -> bool:
    return "t" in row and "ts_utc" not in row


def expand_log_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize compact or legacy JSONL row to the full analysis schema."""
    if not is_compact_row(row):
        out = dict(row)
        if "gap_level" not in out and "p_mkt_mid" in out and "p_star" in out:
            out["gap_level"] = round(out["p_mkt_mid"] - out["p_star"], 4)
        if "spread_pm" not in out and "yes_ask" in out and "yes_bid" in out:
            out["spread_pm"] = round(out["yes_ask"] - out["yes_bid"], 4)
        return out

    sym = row["sym"]
    w_ms = int(row["w"])
    p_mid = float(row["pm"])
    p_star = float(row["ps"])
    bid = float(row["yb"])
    ask = float(row["ya"])
    out: dict[str, Any] = {
        "ts_utc": _ms_to_iso(row["t"]),
        "symbol": sym,
        "ts_binance_event": _ms_to_iso(row["te"]),
        "ts_recv": _ms_to_iso(row["tr"]),
        "ts_pm_recv": _ms_to_iso(row["tp"]),
        "window_id": _window_id(sym, w_ms),
        "window_t0_ms": w_ms,
        "tau_sec": row["tau"],
        "s0": row["s0"],
        "s_t": row["st"],
        "sigma_ann": row["sig"],
        "p_star": p_star,
        "p_mkt_mid": p_mid,
        "p_mkt_micro": row["pu"],
        "yes_bid": bid,
        "yes_ask": ask,
        "gap_level": round(p_mid - p_star, 4),
        "spread_pm": round(ask - bid, 4),
        "mock_pm": bool(row.get("mock", 0)),
        "pm_connected": bool(row.get("pc", 0)),
        "_tick_ms": int(row["t"]),
    }
    return out


def tick_interval_ms(rows: list[dict[str, Any]]) -> float | None:
    """Median spacing between rows (expanded or compact)."""
    if len(rows) < 2:
        return None
    ts: list[int] = []
    for r in rows:
        if "_tick_ms" in r:
            ts.append(int(r["_tick_ms"]))
        elif "t" in r:
            ts.append(int(r["t"]))
        elif "ts_utc" in r:
            ts.append(_iso_to_ms(r["ts_utc"]))
    if len(ts) < 2:
        return None
    deltas = [ts[i] - ts[i - 1] for i in range(1, len(ts)) if ts[i] >= ts[i - 1]]
    if not deltas:
        return None
    deltas.sort()
    return float(deltas[len(deltas) // 2])
