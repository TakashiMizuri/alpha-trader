"""Polymarket book helpers — phase 1b."""

from __future__ import annotations

from typing import Literal

FillMode = Literal["touch", "half_spread", "full_spread", "extreme", "nightmare"]

_SPREAD_MULT: dict[str, float] = {
    "touch": 0.0,
    "half_spread": 0.5,
    "full_spread": 1.0,
    "extreme": 2.0,
    "nightmare": 3.0,
}


def mid_price(best_bid: float, best_ask: float) -> float:
    return 0.5 * (best_bid + best_ask)


def microprice(
    best_bid: float, best_ask: float, bid_qty: float, ask_qty: float
) -> float:
    total = bid_qty + ask_qty
    if total <= 0:
        return mid_price(best_bid, best_ask)
    return (best_ask * bid_qty + best_bid * ask_qty) / total


def polymarket_taker_fee_per_share(price: float, fee_rate: float) -> float:
    """
    Polymarket taker fee per share (USDC).

    ``fee = C × feeRate × p × (1 - p)`` — see docs.polymarket.com/trading/fees.
    Crypto ``feeRate`` = 0.07 (max ~3.5% of notional at p=0.50).
    """
    price = max(0.0, min(1.0, price))
    return fee_rate * price * (1.0 - price)


def taker_fee_per_share(
    price: float,
    *,
    flat_fee: float | None = None,
    fee_rate: float | None = None,
) -> float:
    """Dynamic PM fee if ``fee_rate`` set, else flat per-share fallback."""
    if fee_rate is not None:
        return polymarket_taker_fee_per_share(price, fee_rate)
    return flat_fee if flat_fee is not None else 0.01


def taker_edge_buy_yes(*, p_star: float, ask: float, fee: float) -> float:
    return p_star - ask - fee


def taker_edge_sell_yes(*, p_star: float, bid: float, fee: float) -> float:
    return bid - p_star - fee


def taker_fill_price(
    action: Literal["buy_yes", "sell_yes"],
    *,
    yes_bid: float,
    yes_ask: float,
    mode: FillMode = "touch",
    slippage: float = 0.0,
) -> float:
    """
    Worse-than-touch taker fill for stress tests.

    - touch: buy at ask, sell at bid
    - half_spread: +half spread vs touch (buy pays more, sell receives less)
    - full_spread: +full spread vs touch
    - extreme: +2× spread vs touch
    - nightmare: +3× spread vs touch
    """
    spread = yes_ask - yes_bid
    penalty = spread * _SPREAD_MULT.get(mode, 1.0)
    if action == "buy_yes":
        return min(0.99, yes_ask + penalty + slippage)
    return max(0.01, yes_bid - penalty - slippage)
