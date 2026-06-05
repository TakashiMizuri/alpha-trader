"""Polymarket 5m window calendar — phase 3."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from pm_spot_fair.feeds.gamma import (
    FIVE_MIN_SEC,
    fetch_market_by_slug,
    five_min_interval_unix,
    parse_outcome_up_from_market,
    slug_for_window,
)

logger = logging.getLogger(__name__)


def bucket_unix_from_slug(slug: str) -> int | None:
    """Extract 5m bucket start unix from slug suffix ``...-<unix>``."""
    if "-" not in slug:
        return None
    suffix = slug.rsplit("-", 1)[-1]
    if not suffix.isdigit() or len(suffix) < 10:
        return None
    return int(suffix)


def window_bounds_from_bucket(bucket_unix: int) -> tuple[datetime, datetime]:
    t0 = datetime.fromtimestamp(bucket_unix, tz=timezone.utc)
    t_end = t0 + timedelta(seconds=FIVE_MIN_SEC)
    return t0, t_end


def iter_bucket_unix(start: datetime, end: datetime) -> list[int]:
    """Inclusive 5m bucket starts between ``start`` and ``end`` (UTC)."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    lo = five_min_interval_unix(start)
    hi = five_min_interval_unix(end)
    return list(range(lo, hi + FIVE_MIN_SEC, FIVE_MIN_SEC))


async def fetch_window_record(
    client: httpx.AsyncClient,
    *,
    symbol: str,
    slug_prefix: str,
    bucket_unix: int,
) -> dict[str, Any] | None:
    t0, t_end = window_bounds_from_bucket(bucket_unix)
    slug = slug_for_window(slug_prefix, t0)
    market = await fetch_market_by_slug(client, slug, closed=None)
    if market is None:
        market = await fetch_market_by_slug(client, slug, closed=True)
    if market is None:
        logger.debug("No Gamma market slug=%s", slug)
        return None

    condition_id = str(market.get("conditionId") or market.get("condition_id") or "")
    outcome_up = parse_outcome_up_from_market(market)
    rec: dict[str, Any] = {
        "window_id": slug,
        "symbol": symbol.upper(),
        "t0_utc": t0.isoformat().replace("+00:00", "Z"),
        "t_end_utc": t_end.isoformat().replace("+00:00", "Z"),
        "slug": slug,
        "condition_id": condition_id,
        "bucket_unix": bucket_unix,
        "closed": bool(market.get("closed")),
    }
    if outcome_up is not None:
        rec["outcome_up"] = outcome_up
    uma = market.get("umaResolutionStatus") or market.get("uma_resolution_status")
    if uma:
        rec["uma_status"] = str(uma)
    return rec


async def fetch_window_calendar(
    client: httpx.AsyncClient,
    *,
    symbol: str,
    slug_prefix: str,
    start: datetime,
    end: datetime,
    concurrency: int = 8,
) -> list[dict[str, Any]]:
    """Fetch PM window metadata for each 5m bucket in ``[start, end]``."""
    buckets = iter_bucket_unix(start, end)
    sem = asyncio.Semaphore(max(1, concurrency))
    results: list[dict[str, Any]] = []

    async def one(bucket: int) -> None:
        async with sem:
            rec = await fetch_window_record(
                client,
                symbol=symbol,
                slug_prefix=slug_prefix,
                bucket_unix=bucket,
            )
            if rec:
                results.append(rec)

    await asyncio.gather(*(one(b) for b in buckets))
    results.sort(key=lambda r: r["bucket_unix"])
    return results
