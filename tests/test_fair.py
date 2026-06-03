"""Tests for fair.py — phase 0."""

import math

import pytest

from pm_spot_fair.fair import p_up_gbm, p_up_mc


def test_at_money_long_tau_near_half():
    p = p_up_gbm(s=100.0, s0=100.0, tau_sec=300.0, sigma_ann=0.5)
    assert 0.45 < p < 0.55


def test_deep_itm_short_tau_near_one():
    p = p_up_gbm(s=110.0, s0=100.0, tau_sec=30.0, sigma_ann=0.5)
    assert p > 0.9


def test_deep_otm_short_tau_near_zero():
    p = p_up_gbm(s=90.0, s0=100.0, tau_sec=30.0, sigma_ann=0.5)
    assert p < 0.1


def test_expired_above():
    assert p_up_gbm(s=101.0, s0=100.0, tau_sec=0.0, sigma_ann=0.5) == 1.0


def test_expired_below():
    assert p_up_gbm(s=99.0, s0=100.0, tau_sec=0.0, sigma_ann=0.5) == 0.0


def test_expired_at_strike():
    assert p_up_gbm(s=100.0, s0=100.0, tau_sec=0.0, sigma_ann=0.5) == 0.5


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        p_up_gbm(s=0.0, s0=100.0, tau_sec=300.0, sigma_ann=0.5)


def test_mc_close_to_gbm():
    gbm = p_up_gbm(s=100.0, s0=100.0, tau_sec=300.0, sigma_ann=0.5)
    mc = p_up_mc(
        s=100.0,
        s0=100.0,
        tau_sec=300.0,
        sigma_ann=0.5,
        n_paths=20_000,
        seed=42,
    )
    assert math.isclose(gbm, mc, abs_tol=0.03)
