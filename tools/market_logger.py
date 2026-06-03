#!/usr/bin/env python3
"""Market logger CLI — phase 1b (VPS-ready, multi-symbol)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def main() -> None:
    _load_dotenv()
    from pm_spot_fair.symbols import (
        DEFAULT_SYMBOLS,
        parse_pm_slug_map,
        parse_pm_token_map,
        parse_symbols,
    )

    p = argparse.ArgumentParser(description="PM Spot Fair market logger")
    p.add_argument(
        "--symbols",
        default=None,
        help=f"Comma-separated (default: BINANCE_SYMBOLS or {','.join(DEFAULT_SYMBOLS)})",
    )
    p.add_argument(
        "--symbol",
        default=None,
        help="Legacy single symbol (overrides list if set)",
    )
    p.add_argument("--pm-market", default=None, help="Legacy BTC PM slug")
    p.add_argument("--pm-yes-token-id", default=os.environ.get("PM_YES_TOKEN_ID"))
    p.add_argument("--mock-pm", action="store_true")
    p.add_argument(
        "--interval-ms",
        type=int,
        default=int(os.environ.get("LOGGER_INTERVAL_MS", "250")),
    )
    p.add_argument(
        "--out",
        type=str,
        default=os.environ.get(
            "LOG_OUT_TEMPLATE",
            str(REPO_ROOT / "output" / "logs" / "market_%Y-%m-%d.jsonl"),
        ),
    )
    p.add_argument("--duration-sec", type=float, default=None)
    p.add_argument(
        "--health-file",
        type=Path,
        default=Path(
            os.environ.get(
                "HEALTH_FILE",
                str(REPO_ROOT / "output" / "health" / "logger.json"),
            )
        ),
    )
    p.add_argument("--log-level", default=os.environ.get("LOG_LEVEL", "INFO"))
    args = p.parse_args()

    _configure_logging(args.log_level)

    symbols = parse_symbols(
        args.symbols,
        fallback_single=args.symbol or os.environ.get("BINANCE_SYMBOL"),
    )
    pm_slugs = parse_pm_slug_map()
    if args.pm_market:
        pm_slugs["BTCUSDT"] = args.pm_market
    pm_tokens = parse_pm_token_map()
    if args.pm_yes_token_id:
        pm_tokens["BTCUSDT"] = args.pm_yes_token_id

    has_pm = bool(pm_slugs or pm_tokens)
    mock = args.mock_pm or not has_pm
    if mock and not args.mock_pm:
        logging.warning("No PM slugs/tokens configured; using --mock-pm for all symbols")

    from pm_spot_fair.config import LoggerConfig
    from pm_spot_fair.market_logger_service import MarketLoggerService

    cfg = LoggerConfig(interval_ms=args.interval_ms)
    svc = MarketLoggerService(
        symbols=symbols,
        out_template=args.out,
        interval_ms=args.interval_ms,
        cfg=cfg,
        mock_pm=mock,
        pm_slugs=pm_slugs,
        pm_token_ids=pm_tokens,
        health_path=args.health_file,
        duration_sec=args.duration_sec,
    )
    logging.info("Market logger starting: %s", ", ".join(symbols))
    asyncio.run(svc.run())
    logging.info("Market logger stopped (%d row batches)", svc._ticks)


if __name__ == "__main__":
    main()
