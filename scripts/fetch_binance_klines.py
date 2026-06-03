#!/usr/bin/env python3
"""Download Binance Vision 5m klines and save as JSON per year."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import zipfile
from pathlib import Path

import httpx

VISION_BASE = "https://data.binance.vision/data/spot/monthly/klines"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _month_url(symbol: str, year: int, month: int) -> str:
    sym = symbol.upper()
    ym = f"{year}-{month:02d}"
    fname = f"{sym}-5m-{ym}.zip"
    return f"{VISION_BASE}/{sym}/5m/{fname}"


def _parse_csv_zip(content: bytes) -> list[dict]:
    rows: list[dict] = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        name = zf.namelist()[0]
        with zf.open(name) as f:
            text = io.TextIOWrapper(f, encoding="utf-8")
            reader = csv.reader(text)
            for line in reader:
                if len(line) < 6:
                    continue
                rows.append(
                    {
                        "t": int(line[0]),
                        "o": float(line[1]),
                        "h": float(line[2]),
                        "l": float(line[3]),
                        "c": float(line[4]),
                        "v": float(line[5]),
                    }
                )
    return rows


def fetch_year(symbol: str, year: int, out_dir: Path, client: httpx.Client) -> int:
    all_rows: list[dict] = []
    for month in range(1, 13):
        url = _month_url(symbol, year, month)
        try:
            r = client.get(url, timeout=120.0)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            all_rows.extend(_parse_csv_zip(r.content))
            print(f"  {year}-{month:02d}: {len(all_rows)} bars total", file=sys.stderr)
        except httpx.HTTPError as e:
            print(f"  skip {url}: {e}", file=sys.stderr)

    if not all_rows:
        return 0

    all_rows.sort(key=lambda k: k["t"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{symbol.lower()}_5m_{year}.json"
    out_path.write_text(json.dumps(all_rows), encoding="utf-8")
    print(f"Wrote {out_path} ({len(all_rows)} bars)")
    return len(all_rows)


def main() -> None:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from pm_spot_fair.symbols import parse_symbols

    p = argparse.ArgumentParser(description="Fetch Binance Vision 5m klines")
    p.add_argument("--symbol", default=None)
    p.add_argument("--symbols", default=None)
    p.add_argument("--years", nargs="+", type=int, required=True)
    p.add_argument(
        "--data-dir",
        type=Path,
        default=REPO_ROOT / "data",
    )
    args = p.parse_args()
    symbols = parse_symbols(args.symbols, fallback_single=args.symbol)
    out_dir = args.data_dir / "binance"

    with httpx.Client(follow_redirects=True) as client:
        for symbol in symbols:
            for year in args.years:
                n = fetch_year(symbol, year, out_dir, client)
                if n == 0:
                    print(f"No data for {symbol} {year}", file=sys.stderr)
                    sys.exit(1)


if __name__ == "__main__":
    main()
