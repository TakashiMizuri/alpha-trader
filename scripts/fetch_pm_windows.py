#!/usr/bin/env python3
"""Fetch PM 5m window calendar from Gamma API — phase 3."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pm_spot_fair.log_format import expand_log_row, is_settle_row, load_log_file
from pm_spot_fair.pm_windows import fetch_window_calendar
from pm_spot_fair.symbols import parse_pm_slug_map

logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except ImportError:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _range_from_log(path: Path, symbol: str | None) -> tuple[datetime, datetime]:
    t0_min: int | None = None
    t0_max: int | None = None
    for raw in load_log_file(path):
        if is_settle_row(raw):
            continue
        row = expand_log_row(raw)
        sym = row.get("symbol", "")
        if symbol and sym.upper() != symbol.upper():
            continue
        w = int(row.get("window_t0_ms", row.get("w", 0)))
        if w <= 0:
            continue
        t0_min = w if t0_min is None else min(t0_min, w)
        t0_max = w if t0_max is None else max(t0_max, w)
    if t0_min is None:
        raise SystemExit(f"No windows in log {path}")
    start = datetime.fromtimestamp(t0_min / 1000.0, tz=timezone.utc)
    end = datetime.fromtimestamp(t0_max / 1000.0, tz=timezone.utc) + timedelta(
        minutes=5
    )
    return start, end


async def _fetch_all(
    symbols: dict[str, str],
    start: datetime,
    end: datetime,
    concurrency: int,
) -> list[dict]:
    out: list[dict] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for sym, prefix in sorted(symbols.items()):
            rows = await fetch_window_calendar(
                client,
                symbol=sym,
                slug_prefix=prefix,
                start=start,
                end=end,
                concurrency=concurrency,
            )
            logger.info("%s: %d windows", sym, len(rows))
            out.extend(rows)
    out.sort(key=lambda r: (r["symbol"], r["bucket_unix"]))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Fetch Polymarket 5m window calendar")
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--slug-prefix", default=None, help="e.g. btc-updown-5m")
    p.add_argument(
        "--from-log",
        type=Path,
        help="Derive time range from market log window_t0_ms",
    )
    p.add_argument("--hours", type=float, default=None, help="Last N hours from now")
    p.add_argument("--start", default=None, help="ISO UTC start (with --end)")
    p.add_argument("--end", default=None, help="ISO UTC end")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    _load_dotenv()
    slug_map = parse_pm_slug_map()
    sym = args.symbol.upper()

    if args.slug_prefix:
        symbols = {sym: args.slug_prefix}
    elif sym in slug_map:
        symbols = {sym: slug_map[sym]}
    elif slug_map:
        symbols = slug_map
    else:
        raise SystemExit(
            "Set --slug-prefix or PM_MARKET_SLUGS / PM_MARKET_SLUG in .env"
        )

    if args.from_log:
        start, end = _range_from_log(args.from_log, sym if len(symbols) == 1 else None)
    elif args.hours is not None:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=args.hours)
    elif args.start and args.end:
        start = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
        end = datetime.fromisoformat(args.end.replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
    else:
        raise SystemExit("Provide --from-log, --hours, or --start/--end")

    rows = asyncio.run(_fetch_all(symbols, start, end, args.concurrency))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "out": str(args.out),
                "n_windows": len(rows),
                "symbols": sorted({r["symbol"] for r in rows}),
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
