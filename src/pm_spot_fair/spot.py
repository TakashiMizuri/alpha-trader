"""Spot price loading from kline JSON files."""

from __future__ import annotations

import json
from pathlib import Path


def kline_path(data_dir: Path, symbol: str, year: int) -> Path:
    sym = symbol.lower()
    return data_dir / "binance" / f"{sym}_5m_{year}.json"


def load_klines(path: Path) -> list[dict]:
    """Load klines JSON array: {t, o, h, l, c, v}."""
    if not path.exists():
        raise FileNotFoundError(f"Klines not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return sorted(raw, key=lambda k: k["t"])


def load_klines_years(
    data_dir: Path, symbol: str, years: list[int]
) -> list[dict]:
    """Concatenate klines for multiple years."""
    out: list[dict] = []
    for year in years:
        path = kline_path(data_dir, symbol, year)
        out.extend(load_klines(path))
    return sorted(out, key=lambda k: k["t"])


def mid_from_kline(k: dict) -> float:
    """Use close as S_t proxy for calibration."""
    return float(k["c"])
