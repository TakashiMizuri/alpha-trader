"""Supported Binance spot symbols and env parsing."""

from __future__ import annotations

import json
import os
import re

DEFAULT_SYMBOLS: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "HYPEUSDT",
    "BNBUSDT",
)

# Rough spot anchors for mock/logger smoke (not used in live)
MOCK_BASE_PRICE: dict[str, float] = {
    "BTCUSDT": 100_000.0,
    "ETHUSDT": 3_500.0,
    "SOLUSDT": 150.0,
    "XRPUSDT": 0.60,
    "DOGEUSDT": 0.15,
    "BNBUSDT": 600.0,
    "HYPEUSDT": 25.0,
}


def parse_symbols(
    value: str | None = None,
    *,
    fallback_single: str | None = None,
) -> list[str]:
    """
    Parse comma-separated symbols or legacy single symbol.

    Priority: explicit value > BINANCE_SYMBOLS > BINANCE_SYMBOL > defaults.
    """
    raw = value or os.environ.get("BINANCE_SYMBOLS") or os.environ.get("BINANCE_SYMBOL")
    if not raw and fallback_single:
        raw = fallback_single
    if not raw:
        return list(DEFAULT_SYMBOLS)
    parts = [p.strip().upper() for p in re.split(r"[\s,;]+", raw) if p.strip()]
    return parts or list(DEFAULT_SYMBOLS)


def parse_pm_slug_map() -> dict[str, str]:
    """
    Per-symbol Polymarket slugs.

    PM_MARKET_SLUGS='{"BTCUSDT":"btc-updown-5m"}'
    or PM_MARKET_SLUG_BTCUSDT=... for each symbol.
    Legacy PM_MARKET_SLUG applies to BTCUSDT only.
    """
    out: dict[str, str] = {}
    legacy = os.environ.get("PM_MARKET_SLUG", "").strip()
    if legacy:
        out["BTCUSDT"] = legacy
    raw = os.environ.get("PM_MARKET_SLUGS", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    if v:
                        out[k.strip().upper()] = str(v).strip()
        except json.JSONDecodeError:
            pass
    for sym in DEFAULT_SYMBOLS:
        key = f"PM_MARKET_SLUG_{sym}"
        val = os.environ.get(key, "").strip()
        if val:
            out[sym] = val
    return out


def parse_pm_token_map() -> dict[str, str]:
    """PM_YES_TOKEN_ID_<SYMBOL> or PM_YES_TOKEN_IDS JSON."""
    out: dict[str, str] = {}
    legacy = os.environ.get("PM_YES_TOKEN_ID", "").strip()
    if legacy:
        out["BTCUSDT"] = legacy
    raw = os.environ.get("PM_YES_TOKEN_IDS", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    if v:
                        out[k.strip().upper()] = str(v).strip()
        except json.JSONDecodeError:
            pass
    for sym in DEFAULT_SYMBOLS:
        key = f"PM_YES_TOKEN_ID_{sym}"
        val = os.environ.get(key, "").strip()
        if val:
            out[sym] = val
    return out


def mock_base_price(symbol: str) -> float:
    return MOCK_BASE_PRICE.get(symbol.upper(), 100.0)
