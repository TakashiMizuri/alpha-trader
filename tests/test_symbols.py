"""Symbol list and env parsing."""

import os

from pm_spot_fair.symbols import (
    DEFAULT_SYMBOLS,
    parse_pm_slug_map,
    parse_symbols,
)


def test_default_symbols():
    assert "BTCUSDT" in DEFAULT_SYMBOLS
    assert "ETHUSDT" in DEFAULT_SYMBOLS
    assert "HYPEUSDT" in DEFAULT_SYMBOLS
    assert len(DEFAULT_SYMBOLS) == 7


def test_parse_symbols_csv():
    assert parse_symbols("btcusdt, ethusdt") == ["BTCUSDT", "ETHUSDT"]


def test_parse_symbols_defaults(monkeypatch):
    monkeypatch.delenv("BINANCE_SYMBOLS", raising=False)
    monkeypatch.delenv("BINANCE_SYMBOL", raising=False)
    syms = parse_symbols(None)
    assert syms == list(DEFAULT_SYMBOLS)


def test_parse_pm_slug_map_legacy(monkeypatch):
    monkeypatch.setenv("PM_MARKET_SLUG", "btc-5m-test")
    monkeypatch.delenv("PM_MARKET_SLUGS", raising=False)
    m = parse_pm_slug_map()
    assert m.get("BTCUSDT") == "btc-5m-test"
