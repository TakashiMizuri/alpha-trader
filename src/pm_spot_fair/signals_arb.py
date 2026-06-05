"""Arbitrage sleeve signals — phase 2."""

from __future__ import annotations

from typing import Literal

from pm_spot_fair.config import ArbConfig
from pm_spot_fair.pm_book import (
    FillMode,
    taker_edge_buy_yes,
    taker_edge_sell_yes,
    taker_fee_per_share,
    taker_fill_price,
)

Action = Literal["buy_yes", "sell_yes", "skip"]


def edge_at_fill(
    action: Action,
    *,
    p_star: float,
    fill_price: float,
    fee: float,
) -> float:
    if action == "buy_yes":
        return p_star - fill_price - fee
    return fill_price - p_star - fee


def decide_arb(
    *,
    p_star: float,
    yes_bid: float,
    yes_ask: float,
    tau_sec: float,
    cfg: ArbConfig,
    max_spread: float = 0.08,
    fill_mode: FillMode = "touch",
    slippage: float = 0.0,
) -> tuple[Action, float]:
    """
    Taker arb vs fair. Returns (action, edge).

    edge = p* - ask - fee (buy) or bid - p* - fee (sell).
    """
    spread = yes_ask - yes_bid
    if spread > max_spread or tau_sec < cfg.min_tau_sec:
        return "skip", 0.0
    if yes_bid <= 0 or yes_ask <= 0 or yes_ask >= 1 or yes_bid >= yes_ask:
        return "skip", 0.0

    fee_buy_q = taker_fee_per_share(
        yes_ask, flat_fee=cfg.taker_fee, fee_rate=cfg.pm_fee_rate
    )
    buy_edge_q = taker_edge_buy_yes(p_star=p_star, ask=yes_ask, fee=fee_buy_q)
    if buy_edge_q >= cfg.min_edge:
        fill = taker_fill_price(
            "buy_yes",
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            mode=fill_mode,
            slippage=slippage,
        )
        fee_buy = taker_fee_per_share(
            fill, flat_fee=cfg.taker_fee, fee_rate=cfg.pm_fee_rate
        )
        buy_edge = edge_at_fill(
            "buy_yes", p_star=p_star, fill_price=fill, fee=fee_buy
        )
        if buy_edge >= cfg.min_edge:
            return "buy_yes", buy_edge

    fee_sell_q = taker_fee_per_share(
        yes_bid, flat_fee=cfg.taker_fee, fee_rate=cfg.pm_fee_rate
    )
    sell_edge_q = taker_edge_sell_yes(p_star=p_star, bid=yes_bid, fee=fee_sell_q)
    if sell_edge_q >= cfg.min_edge:
        fill = taker_fill_price(
            "sell_yes",
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            mode=fill_mode,
            slippage=slippage,
        )
        fee_sell = taker_fee_per_share(
            fill, flat_fee=cfg.taker_fee, fee_rate=cfg.pm_fee_rate
        )
        sell_edge = edge_at_fill(
            "sell_yes", p_star=p_star, fill_price=fill, fee=fee_sell
        )
        if sell_edge >= cfg.min_edge:
            return "sell_yes", sell_edge

    return "skip", 0.0


def settle_pnl(
    action: Action,
    *,
    entry_price: float,
    outcome_up: bool,
    fee: float,
) -> float:
    """Mark-to-settle PnL per YES share (0..1 payoff)."""
    if action == "skip":
        return 0.0
    outcome = 1.0 if outcome_up else 0.0
    if action == "buy_yes":
        return outcome - entry_price - fee
    return entry_price - outcome - fee
