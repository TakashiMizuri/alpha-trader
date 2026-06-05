"""PM window calendar helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from pm_spot_fair.pm_windows import (
    bucket_unix_from_slug,
    iter_bucket_unix,
    window_bounds_from_bucket,
)


def test_bucket_unix_from_slug() -> None:
    assert bucket_unix_from_slug("btc-updown-5m-1780493400") == 1780493400
    assert bucket_unix_from_slug("bad") is None


def test_window_bounds_from_bucket() -> None:
    t0, t_end = window_bounds_from_bucket(1780493400)
    assert t0 == datetime.fromtimestamp(1780493400, tz=timezone.utc)
    assert (t_end - t0).total_seconds() == 300


def test_iter_bucket_unix() -> None:
    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 1, 12, 12, 0, tzinfo=timezone.utc)
    buckets = iter_bucket_unix(start, end)
    assert len(buckets) == 3
    assert buckets[1] - buckets[0] == 300
