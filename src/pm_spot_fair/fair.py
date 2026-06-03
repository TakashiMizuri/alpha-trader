"""Fair probability p* under GBM and Monte Carlo."""

from __future__ import annotations

import math

import numpy as np

SEC_PER_YEAR = 365.25 * 24 * 3600


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def p_up_gbm(*, s: float, s0: float, tau_sec: float, sigma_ann: float) -> float:
    """Probability S_T > S_0 under GBM (risk-neutral d2)."""
    if tau_sec <= 0:
        if s > s0:
            return 1.0
        if s < s0:
            return 0.0
        return 0.5
    if s0 <= 0 or s <= 0 or sigma_ann <= 0:
        raise ValueError("s, s0, sigma_ann must be positive")
    tau_y = tau_sec / SEC_PER_YEAR
    d2 = (math.log(s / s0) - 0.5 * sigma_ann**2 * tau_y) / (
        sigma_ann * math.sqrt(tau_y)
    )
    return _norm_cdf(d2)


def p_up_mc(
    *,
    s: float,
    s0: float,
    tau_sec: float,
    sigma_ann: float,
    n_paths: int = 10_000,
    n_steps: int = 50,
    seed: int = 42,
) -> float:
    """Monte Carlo estimate of P(S_T > S_0) via GBM paths from S_t."""
    if tau_sec <= 0:
        return p_up_gbm(s=s, s0=s0, tau_sec=tau_sec, sigma_ann=sigma_ann)
    if s0 <= 0 or s <= 0 or sigma_ann <= 0:
        raise ValueError("s, s0, sigma_ann must be positive")

    rng = np.random.default_rng(seed)
    tau_y = tau_sec / SEC_PER_YEAR
    dt = tau_y / n_steps
    drift = -0.5 * sigma_ann**2 * dt
    vol_step = sigma_ann * math.sqrt(dt)

    log_rets = rng.normal(drift, vol_step, size=(n_paths, n_steps))
    log_s_t = math.log(s)
    log_paths = log_s_t + np.cumsum(log_rets, axis=1)
    s_T = np.exp(log_paths[:, -1])
    return float(np.mean(s_T > s0))
