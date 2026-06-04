"""Settle rows and Gamma outcome parsing."""

from __future__ import annotations

from pm_spot_fair.feeds.gamma import parse_outcome_up_from_market
from pm_spot_fair.log_format import build_settle_row, expand_log_row, is_settle_row


def test_parse_gamma_up_wins() -> None:
    m = {
        "outcomes": '["Up", "Down"]',
        "outcomePrices": '["1", "0"]',
        "closed": True,
        "umaResolutionStatus": "resolved",
    }
    assert parse_outcome_up_from_market(m) is True


def test_parse_gamma_down_wins() -> None:
    m = {
        "outcomes": '["Up", "Down"]',
        "outcomePrices": '["0", "1"]',
    }
    assert parse_outcome_up_from_market(m) is False


def test_settle_row_expand() -> None:
    row = build_settle_row(
        symbol="BTCUSDT",
        window_t0_ms=1_780_497_900_000,
        ts_ms=1_780_498_200_000,
        s0=100.0,
        s_t=100.5,
        p_star=0.6,
        p_mid=0.55,
        outcome_up=True,
        outcome_up_spot=True,
        outcome_source="gamma",
        outcome_up_pm=True,
        pm_slug="btc-updown-5m-1780497900",
    )
    assert is_settle_row(row)
    exp = expand_log_row(row)
    assert exp["type"] == "settle"
    assert exp["outcome_up"] is True
    assert exp["outcome_source"] == "gamma"
    assert exp["gap_level"] == -0.05
    from pm_spot_fair.log_format import parse_log_line, serialize_row

    line = serialize_row(row)
    assert line.startswith("1,")
    assert parse_log_line(line)["sym"] == "BTCUSDT"
