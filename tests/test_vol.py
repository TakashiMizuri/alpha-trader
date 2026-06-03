"""Tests for vol.py — phase 1."""

from pm_spot_fair.vol import sigma_ann_from_closes


def test_sigma_positive_from_closes():
    closes = [100.0 + i * 0.1 for i in range(100)]
    sigma = sigma_ann_from_closes(closes, span=30)
    assert sigma > 0


def test_sigma_floor_on_short_series():
    sigma = sigma_ann_from_closes([100.0])
    assert sigma == 0.15
