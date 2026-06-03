"""Polymarket Gamma API — resolve market slug to CLOB token IDs."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"


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
    r = await client.get(f"{GAMMA_API}/markets", params={"slug": slug})
    r.raise_for_status()
    markets = r.json()
    if not markets:
        raise LookupError(f"No Polymarket market found for slug={slug!r}")
    m = markets[0]
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
