#!/usr/bin/env python3
"""Append missing settle rows to an existing market log (Gamma + last tick)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pm_spot_fair.clock import Window
from pm_spot_fair.feeds.gamma import fetch_settled_outcome, slug_for_window
from pm_spot_fair.log_format import (
    build_settle_row,
    ensure_log_header,
    expand_log_row,
    is_settle_row,
    load_log_file,
    serialize_row,
)
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


def _window_from_row(row: dict) -> Window:
    t0_ms = int(row.get("window_t0_ms", row.get("w", 0)))
    t0 = datetime.fromtimestamp(t0_ms / 1000.0, tz=timezone.utc)
    t_end = t0 + timedelta(minutes=5)
    return Window(window_id=row["window_id"], t0_utc=t0, t_end_utc=t_end)


async def enrich(path: Path, out: Path, pm_slugs: dict[str, str]) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        ensure_log_header(out)
    existing_settle: set[tuple[str, int]] = set()
    last_tick: dict[tuple[str, int], dict] = {}

    for raw in load_log_file(path):
        if is_settle_row(raw):
            sym = raw.get("sym") or raw.get("symbol")
            existing_settle.add((sym, int(raw.get("w", 0))))
            continue
        row = expand_log_row(raw)
        key = (row["symbol"], int(row["window_t0_ms"]))
        last_tick[key] = row

    added = 0
    async with httpx.AsyncClient(timeout=15.0) as client:
        for (sym, w_ms), tick in sorted(last_tick.items()):
            if (sym, w_ms) in existing_settle:
                continue
            prefix = pm_slugs.get(sym)
            if not prefix:
                logger.warning("No PM_MARKET_SLUG for %s — skip", sym)
                continue
            window = _window_from_row(tick)
            slug = slug_for_window(prefix, window.t0_utc)
            s0, s_t = float(tick["s0"]), float(tick["s_t"])
            outcome_up_spot = s_t > s0
            gamma = await fetch_settled_outcome(
                client, slug, poll_sec=3.0, max_wait_sec=30.0
            )
            outcome_up_pm = gamma.outcome_up if gamma else None
            source = "gamma" if gamma else "spot_proxy"
            row = build_settle_row(
                symbol=sym,
                window_t0_ms=w_ms,
                ts_ms=int(window.t_end_utc.timestamp() * 1000),
                s0=s0,
                s_t=s_t,
                p_star=float(tick["p_star"]),
                p_mid=float(tick["p_mkt_mid"]),
                outcome_up=outcome_up_pm if outcome_up_pm is not None else outcome_up_spot,
                outcome_up_spot=outcome_up_spot,
                outcome_source=source,
                outcome_up_pm=outcome_up_pm,
                pm_mock=bool(tick.get("mock_pm")),
                pm_slug=slug,
            )
            with out.open("a", encoding="utf-8") as f:
                f.write(serialize_row(row) + "\n")
            added += 1
            logger.info("Settle %s w=%s src=%s", sym, w_ms, source)
    return added


def main() -> None:
    p = argparse.ArgumentParser(description="Append settle rows to JSONL log")
    p.add_argument("--logs", type=Path, required=True)
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: append in-place to --logs)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )
    _load_dotenv()
    out = args.out or args.logs
    if out != args.logs and out.exists():
        out.unlink()
    elif out == args.logs and not args.logs.exists():
        print("Log missing", file=sys.stderr)
        sys.exit(1)
    pm_slugs = parse_pm_slug_map()
    if not pm_slugs:
        print(
            "No PM_MARKET_SLUGS in .env — copy .env.example or set slugs.",
            file=sys.stderr,
        )
        sys.exit(1)
    n = asyncio.run(enrich(args.logs, out, pm_slugs))
    print(f"Added {n} settle rows -> {out}")
    if n == 0:
        print(
            "Hint: all windows may already have settle rows, or log failed to parse.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
