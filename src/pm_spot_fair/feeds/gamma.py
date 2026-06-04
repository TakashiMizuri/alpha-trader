"""Polymarket Gamma API — resolve market slug to CLOB token IDs."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"
FIVE_MIN_SEC = 300
_BUCKETED_SLUG_RE = re.compile(r"^.+-\d{10,}$")


def five_min_interval_unix(now: datetime | None = None) -> int:
    """UTC 5m window start (Polymarket up/down slug suffix)."""
    ts = now or datetime.now(timezone.utc)
    return int(ts.timestamp()) // FIVE_MIN_SEC * FIVE_MIN_SEC


def effective_pm_slug(slug: str, now: datetime | None = None) -> str:
    """
    Map config slug to the active Gamma slug.

    Polymarket BTC/ETH/SOL 5m markets use rolling slugs like
    ``btc-updown-5m-1780493400``. ``.env`` may store the prefix only
    (``btc-updown-5m``) or the full bucketed slug.
    """
    slug = slug.strip()
    if not slug:
        raise ValueError("empty slug")
    if _BUCKETED_SLUG_RE.match(slug):
        return slug
    return f"{slug}-{five_min_interval_unix(now)}"


@dataclass(frozen=True)
class PMMarketTokens:
    slug: str
    condition_id: str
    yes_token_id: str
    no_token_id: str | None


async def resolve_market_by_slug(
    client: httpx.AsyncClient, slug: str
) -> PMMarketTokens:
    """Fetch YES/NO token IDs for an active market slug."""
    m = await fetch_market_by_slug(client, slug)
    if not m:
        raise LookupError(f"No Polymarket market found for slug={slug!r}")
    tokens = m.get("clobTokenIds") or m.get("clob_token_ids")
    if isinstance(tokens, str):
        import json

        tokens = json.loads(tokens)
    if not tokens or len(tokens) < 1:
        raise LookupError(f"Market {slug!r} has no clobTokenIds")
    yes_id = str(tokens[0])
    no_id = str(tokens[1]) if len(tokens) > 1 else None
    condition_id = str(m.get("conditionId") or m.get("condition_id") or "")
    logger.info(
        "Resolved slug=%s condition=%s yes_token=%s",
        slug,
        condition_id[:16] if condition_id else "?",
        yes_id[:16],
    )
    return PMMarketTokens(
        slug=slug,
        condition_id=condition_id,
        yes_token_id=yes_id,
        no_token_id=no_id,
    )


@dataclass(frozen=True)
class PMSettleOutcome:
    """Resolved Up/Down (YES wins Up) from Gamma outcomePrices."""

    slug: str
    outcome_up: bool
    uma_status: str | None


def slug_for_window(slug_prefix: str, window_t0: datetime) -> str:
    """Build bucketed slug for a closed window start time."""
    return effective_pm_slug(slug_prefix, window_t0)


def parse_outcome_up_from_market(market: dict) -> bool | None:
    """
    Return True if Up/Yes outcome won.

    Resolved 5m markets: outcomes ["Up","Down"], outcomePrices ["1","0"].
    """
    raw_prices = market.get("outcomePrices") or market.get("outcome_prices")
    raw_outcomes = market.get("outcomes")
    if raw_prices is None or raw_outcomes is None:
        return None
    if isinstance(raw_prices, str):
        prices = json.loads(raw_prices)
    else:
        prices = raw_prices
    if isinstance(raw_outcomes, str):
        outcomes = json.loads(raw_outcomes)
    else:
        outcomes = raw_outcomes
    if not prices or not outcomes or len(prices) != len(outcomes):
        return None
    try:
        floats = [float(p) for p in prices]
    except (TypeError, ValueError):
        return None
    winner_idx = max(range(len(floats)), key=lambda i: floats[i])
    if floats[winner_idx] < 0.5:
        return None
    label = str(outcomes[winner_idx]).strip().lower()
    if label in ("up", "yes"):
        return True
    if label in ("down", "no"):
        return False
    return None


async def fetch_market_by_slug(
    client: httpx.AsyncClient, slug: str, *, closed: bool | None = None
) -> dict | None:
    params: dict[str, str] = {"slug": slug}
    if closed is True:
        params["closed"] = "true"
    r = await client.get(f"{GAMMA_API}/markets", params=params)
    r.raise_for_status()
    markets = r.json()
    return markets[0] if markets else None


async def fetch_settled_outcome(
    client: httpx.AsyncClient,
    slug: str,
    *,
    poll_sec: float = 5.0,
    max_wait_sec: float = 120.0,
) -> PMSettleOutcome | None:
    """
    Poll Gamma until market is resolved or timeout.

    Uses ``closed=true`` filter once the 5m window has ended.
    """
    deadline = time.monotonic() + max_wait_sec
    last_status: str | None = None
    while time.monotonic() < deadline:
        for closed_flag in (True, None):
            market = await fetch_market_by_slug(
                client, slug, closed=closed_flag if closed_flag else None
            )
            if not market:
                continue
            last_status = market.get("umaResolutionStatus") or market.get(
                "uma_resolution_status"
            )
            outcome_up = parse_outcome_up_from_market(market)
            if outcome_up is not None:
                if market.get("closed") or str(last_status).lower() == "resolved":
                    return PMSettleOutcome(
                        slug=slug,
                        outcome_up=outcome_up,
                        uma_status=str(last_status) if last_status else None,
                    )
        await asyncio.sleep(poll_sec)
    logger.warning("Gamma settle timeout slug=%s status=%s", slug, last_status)
    return None
