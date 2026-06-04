"""v3 CSV log format with header."""

from __future__ import annotations

from pathlib import Path

from pm_spot_fair.log_format import (
    build_compact_row,
    build_settle_row,
    ensure_log_header,
    expand_log_row,
    load_log_file,
    serialize_row,
)


def test_v3_header_and_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "test.jsonl"
    ensure_log_header(path)
    tick = build_compact_row(
        symbol="ETHUSDT",
        window_t0_ms=1_780_000_000_000,
        ts_ms=1_780_000_001_000,
        b_event_ms=1_780_000_001_000,
        b_recv_ms=1_780_000_001_001,
        pm_recv_ms=1_780_000_001_002,
        s0=2000.0,
        s_t=2001.0,
        sigma=0.2,
        tau=100.0,
        p_star=0.55,
        p_mid=0.52,
        p_micro=0.519,
        bid=0.51,
        ask=0.53,
        pm_mock=False,
        pm_connected=True,
    )
    settle = build_settle_row(
        symbol="ETHUSDT",
        window_t0_ms=1_780_000_000_000,
        ts_ms=1_780_000_300_000,
        s0=2000.0,
        s_t=2002.0,
        p_star=0.6,
        p_mid=0.58,
        outcome_up=True,
        outcome_up_spot=True,
        outcome_source="gamma",
        outcome_up_pm=True,
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(serialize_row(tick) + "\n")
        f.write(serialize_row(settle) + "\n")

    text = path.read_text(encoding="utf-8")
    assert "# alpha-trader market log v3" in text
    assert "# tick:" in text
    assert "# settle:" in text

    rows = load_log_file(path)
    assert len(rows) == 2
    exp_tick = expand_log_row(rows[0])
    exp_settle = expand_log_row(rows[1])
    assert exp_tick["symbol"] == "ETHUSDT"
    assert exp_settle["type"] == "settle"
    assert exp_settle["outcome_source"] == "gamma"
