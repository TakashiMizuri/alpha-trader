"""Compact market log row format."""

from __future__ import annotations

from pm_spot_fair.log_format import (
    build_compact_row,
    expand_log_row,
    is_compact_row,
    serialize_row,
    tick_interval_ms,
)


def test_compact_roundtrip() -> None:
    row = build_compact_row(
        symbol="BTCUSDT",
        window_t0_ms=1_700_000_000_000,
        ts_ms=1_700_000_001_234,
        b_event_ms=1_700_000_001_200,
        b_recv_ms=1_700_000_001_210,
        pm_recv_ms=1_700_000_001_220,
        s0=100_000.12,
        s_t=100_010.34,
        sigma=0.55,
        tau=120.5,
        p_star=0.52,
        p_mid=0.48,
        p_micro=0.479,
        bid=0.47,
        ask=0.49,
        pm_mock=False,
        pm_connected=True,
    )
    assert is_compact_row(row)
    line = serialize_row(row)
    assert " " not in line
    exp = expand_log_row(row)
    assert exp["symbol"] == "BTCUSDT"
    assert exp["gap_level"] == round(0.48 - 0.52, 4)
    assert exp["spread_pm"] == round(0.49 - 0.47, 4)
    assert exp["window_id"] == "btc_5m_1700000000"
    assert exp["mock_pm"] is False
    assert exp["pm_connected"] is True


def test_legacy_row_gap_derived() -> None:
    legacy = {
        "ts_utc": "2026-01-15T12:34:56.123Z",
        "symbol": "ETHUSDT",
        "p_star": 0.5,
        "p_mkt_mid": 0.55,
        "yes_bid": 0.54,
        "yes_ask": 0.56,
    }
    exp = expand_log_row(legacy)
    assert exp["gap_level"] == 0.05
    assert exp["spread_pm"] == 0.02


def test_tick_interval_ms() -> None:
    rows = [
        {"t": 1000},
        {"t": 1100},
        {"t": 1200},
        {"t": 1305},
    ]
    assert tick_interval_ms(rows) == 100.0
