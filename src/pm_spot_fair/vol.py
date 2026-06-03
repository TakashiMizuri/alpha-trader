"""Annualized volatility from close prices."""

from __future__ import annotations

import math

SEC_PER_YEAR = 365.25 * 24 * 3600
# 5m bars → bars per year
BARS_PER_YEAR_5M = 365.25 * 24 * 12


def sigma_ann_from_closes(closes: list[float], *, span: int = 60) -> float:
    """
    EWMA variance of log-returns, annualized.

    Assumes closes are evenly spaced (e.g. 5m klines).
    Returns at least a small positive value when data is insufficient.
    """
    if len(closes) < 2:
        return 0.15

    log_rets: list[float] = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0 and closes[i] > 0:
            log_rets.append(math.log(closes[i] / closes[i - 1]))

    if not log_rets:
        return 0.15

    alpha = 2.0 / (span + 1)
    var = log_rets[0] ** 2
    for r in log_rets[1:]:
        var = alpha * r**2 + (1 - alpha) * var

    sigma_per_bar = math.sqrt(max(var, 1e-16))
    return sigma_per_bar * math.sqrt(BARS_PER_YEAR_5M)
