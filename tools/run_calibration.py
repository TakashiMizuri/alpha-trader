#!/usr/bin/env python3
"""Calibrate p* on historical Binance 5m windows — phase 1."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pm_spot_fair.clock import windows_from_klines
from pm_spot_fair.config import ArbConfig
from pm_spot_fair.fair import p_up_gbm
from pm_spot_fair.spot import load_klines_years
from pm_spot_fair.symbols import parse_symbols
from pm_spot_fair.vol import sigma_ann_from_closes


def brier_score(predictions: list[float], outcomes: list[int]) -> float:
    if not predictions:
        return 1.0
    return sum((p - y) ** 2 for p, y in zip(predictions, outcomes)) / len(
        predictions
    )


def reliability_bins(
    predictions: list[float], outcomes: list[int], n_bins: int = 10
) -> list[dict]:
    bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for p, y in zip(predictions, outcomes):
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx].append((p, y))
    result = []
    for i, bucket in enumerate(bins):
        if not bucket:
            continue
        mean_p = sum(x[0] for x in bucket) / len(bucket)
        freq = sum(x[1] for x in bucket) / len(bucket)
        result.append(
            {
                "bin": i,
                "count": len(bucket),
                "mean_p": round(mean_p, 4),
                "freq_up": round(freq, 4),
            }
        )
    return result


def run_calibration(
    data_dir: Path,
    symbol: str,
    years: list[int],
    cfg: ArbConfig,
    sigma_floor: float,
) -> dict:
    klines = load_klines_years(data_dir, symbol, years)
    windows = windows_from_klines(klines)
    closes_hist: list[float] = []
    preds: list[float] = []
    outcomes: list[int] = []

    k_by_t = {k["t"]: k for k in klines}
    window_sec = 300.0

    for w in windows:
        t0_ms = int(w.t0_utc.timestamp() * 1000)
        if t0_ms not in k_by_t:
            continue
        k = k_by_t[t0_ms]
        idx = klines.index(k)
        if idx < 1:
            continue
        prev = klines[idx - 1]
        s0 = float(k["o"])
        s_t = float(prev["c"])  # spot at window open, no look-ahead in current bar
        hist = [float(x["c"]) for x in klines[max(0, idx - 120) : idx]]
        if len(hist) < 2:
            continue
        sigma = max(
            sigma_ann_from_closes(hist, span=cfg.sigma_ewma_span),
            sigma_floor,
        )
        p = p_up_gbm(s=s_t, s0=s0, tau_sec=window_sec, sigma_ann=sigma)
        outcome = 1 if float(k["c"]) > s0 else 0
        preds.append(p)
        outcomes.append(outcome)
        closes_hist.append(float(k["c"]))

    brier = brier_score(preds, outcomes)
    brier_const = brier_score([0.5] * len(outcomes), outcomes)
    return {
        "symbol": symbol,
        "years": years,
        "n_windows": len(preds),
        "brier": round(brier, 6),
        "brier_constant_0_5": round(brier_const, 6),
        "brier_improves_over_0_5": brier < brier_const,
        "pass_brier_0_25": brier < 0.25,
        "note": (
            "v0 uses prev close vs window open (no intra-bar look-ahead). "
            "Brier near 0.25 is expected until PM calendar / 1m data."
        ),
        "reliability": reliability_bins(preds, outcomes),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=None, help="Legacy single symbol")
    p.add_argument("--symbols", default=None, help="Comma-separated; default: all 7")
    p.add_argument("--years", nargs="+", type=int, required=True)
    p.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--sigma-floor", type=float, default=0.15)
    args = p.parse_args()

    symbols = parse_symbols(args.symbols, fallback_single=args.symbol)
    cfg = ArbConfig()
    per_symbol: dict[str, dict] = {}
    failed = False

    for sym in symbols:
        try:
            per_symbol[sym] = run_calibration(
                args.data_dir, sym, args.years, cfg, args.sigma_floor
            )
        except FileNotFoundError as e:
            print(f"SKIP {sym}: {e}", file=sys.stderr)
            per_symbol[sym] = {"symbol": sym, "error": str(e)}
            failed = True

    args.out.mkdir(parents=True, exist_ok=True)
    aggregate = {"symbols": symbols, "per_symbol": per_symbol}
    (args.out / "calibration.json").write_text(
        json.dumps(aggregate, indent=2), encoding="utf-8"
    )

    md = ["# Calibration report", "", f"- Symbols: {symbols}", ""]
    for sym, report in per_symbol.items():
        if "error" in report:
            md.append(f"## {sym} — SKIPPED ({report['error']})")
            continue
        md.append(f"## {sym}")
        md.append(f"- Windows: {report['n_windows']}")
        md.append(f"- **Brier:** {report['brier']} (constant 0.5: {report['brier_constant_0_5']})")
        md.append("")
        if report["brier"] >= 0.5:
            failed = True
    (args.out / "summary.md").write_text("\n".join(md), encoding="utf-8")

    print(json.dumps(aggregate, indent=2))
    if failed:
        print("WARN: some symbols missing data or Brier >= 0.5", file=sys.stderr)


if __name__ == "__main__":
    main()
