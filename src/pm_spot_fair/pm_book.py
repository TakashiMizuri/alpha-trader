"""Polymarket book helpers — phase 1b."""

from __future__ import annotations


def mid_price(best_bid: float, best_ask: float) -> float:
    return 0.5 * (best_bid + best_ask)


def microprice(
    best_bid: float, best_ask: float, bid_qty: float, ask_qty: float
) -> float:
    total = bid_qty + ask_qty
    if total <= 0:
        return mid_price(best_bid, best_ask)
    return (best_ask * bid_qty + best_bid * ask_qty) / total


def taker_edge_buy_yes(*, p_star: float, ask: float, fee: float) -> float:
    return p_star - ask - fee


def taker_edge_sell_yes(*, p_star: float, bid: float, fee: float) -> float:
    return bid - p_star - fee
