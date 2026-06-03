"""Tests for clock.py — phase 1."""

from datetime import datetime, timedelta, timezone

from pm_spot_fair.clock import Window, tau_sec


def test_tau_decreases_toward_end():
    t0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_end = t0 + timedelta(minutes=5)
    w = Window(window_id="test", t0_utc=t0, t_end_utc=t_end)

    mid = t0 + timedelta(minutes=2)
    near_end = t_end - timedelta(seconds=30)

    tau_mid = tau_sec(mid, w)
    tau_near = tau_sec(near_end, w)

    assert tau_mid > tau_near
    assert tau_near == 30.0
    assert tau_sec(t_end, w) == 0.0
