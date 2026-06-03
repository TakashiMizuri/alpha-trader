"""Order book pressure and p_target — phase 4."""

from __future__ import annotations


def _phase_not_ready() -> None:
    raise NotImplementedError("book_pressure is implemented in phase 4")


def order_book_imbalance(bid_qtys: list[float], ask_qtys: list[float]) -> float:
    _phase_not_ready()
    return 0.0  # pragma: no cover


def p_target(
    *,
    p_star: float,
    tau_sec: float,
    i_bin: float,
    delta_bin: float,
    alpha_scale: float = 0.05,
) -> float:
    _phase_not_ready()
    return 0.0  # pragma: no cover
