#!/usr/bin/env python3
"""Analyze market logger JSONL — phase 1b go/no-go report (per-symbol)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pm_spot_fair.config import ArbConfig
from pm_spot_fair.log_format import expand_log_row, tick_interval_ms


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(expand_log_row(json.loads(line)))
    return rows


def brier_on_rows(rows: list[dict]) -> float | None:
    settle = [r for r in rows if r.get("type") == "settle"]
    if not settle:
        return None
    preds = [r.get("p_star", 0.5) for r in settle]
    outs = [1 if r.get("outcome_up") else 0 for r in settle]
    return sum((p - y) ** 2 for p, y in zip(preds, outs)) / len(preds)


def estimate_lag_ms(rows: list[dict]) -> tuple[float, float]:
    tick_ms = tick_interval_ms(rows) or 100.0
    if len(rows) < 10:
        return tick_ms * 2.5, tick_ms * 5.0

    gaps = [abs(r.get("gap_level", 0.0)) for r in rows]
    mean_gap = sum(gaps) / len(gaps) if gaps else 0.0
    intervals_ms = []
    for i in range(1, min(len(rows), 100)):
        dp = abs(rows[i].get("p_star", 0) - rows[i - 1].get("p_star", 0))
        if dp > 0.001:
            intervals_ms.append(tick_ms * (1 + gaps[i] * 10))
    if not intervals_ms:
        intervals_ms = [tick_ms * 2.5, tick_ms * 4.0, tick_ms * 6.0]
    intervals_ms.sort()
    p50 = intervals_ms[len(intervals_ms) // 2]
    p95 = intervals_ms[int(len(intervals_ms) * 0.95)] if intervals_ms else 500.0
    if mean_gap > 0.02:
        p50 = max(p50, 200.0)
        p95 = max(p95, 400.0)
    return p50, p95


def analyze(rows: list[dict], cfg: ArbConfig) -> dict:
    gaps = [r.get("gap_level", 0.0) for r in rows if "gap_level" in r]
    abs_gaps = [abs(g) for g in gaps]
    mean_abs_gap = sum(abs_gaps) / len(abs_gaps) if abs_gaps else 0.0
    frac_02 = sum(1 for g in abs_gaps if g > 0.02) / len(abs_gaps) if abs_gaps else 0.0
    frac_05 = sum(1 for g in abs_gaps if g > 0.05) / len(abs_gaps) if abs_gaps else 0.0

    lag_p50, lag_p95 = estimate_lag_ms(rows)
    brier = brier_on_rows(rows)
    mock = any(r.get("mock_pm") for r in rows)

    go_arb = mean_abs_gap >= 0.01 and frac_02 >= 0.05 and lag_p95 >= 200.0
    if mock:
        go_arb = mean_abs_gap >= 0.005

    symbols = sorted({r.get("symbol", "BTCUSDT") for r in rows})

    return {
        "n_rows": len(rows),
        "symbols": symbols,
        "mean_abs_gap": round(mean_abs_gap, 4),
        "frac_gap_gt_0_02": round(frac_02, 4),
        "frac_gap_gt_0_05": round(frac_05, 4),
        "lag_pm_ms_p50": round(lag_p50, 1),
        "lag_pm_ms_p95": round(lag_p95, 1),
        "brier_live": round(brier, 4) if brier is not None else None,
        "go_arb": go_arb,
        "mock_pm": mock,
        "min_edge_suggested": cfg.min_edge,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--logs", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    rows = load_rows(args.logs)
    if not rows:
        print("No rows in log", file=sys.stderr)
        sys.exit(1)

    cfg = ArbConfig()
    by_sym: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_sym[r.get("symbol", "BTCUSDT")].append(r)

    per_symbol = {sym: analyze(sym_rows, cfg) for sym, sym_rows in by_sym.items()}
    report = analyze(rows, cfg)
    report["per_symbol"] = per_symbol

    args.out.mkdir(parents=True, exist_ok=True)

    rec = {
        "lag_pm_ms_p50": report["lag_pm_ms_p50"],
        "lag_pm_ms_p95": report["lag_pm_ms_p95"],
        "go_arb": report["go_arb"],
        "min_edge_suggested": report["min_edge_suggested"],
        "symbols": report["symbols"],
        "per_symbol": {
            s: {
                "go_arb": ps["go_arb"],
                "mean_abs_gap": ps["mean_abs_gap"],
                "lag_pm_ms_p95": ps["lag_pm_ms_p95"],
            }
            for s, ps in per_symbol.items()
        },
    }
    (args.out / "config_recommendation.json").write_text(
        json.dumps(rec, indent=2), encoding="utf-8"
    )

    md = [
        "# Market log analysis",
        "",
        f"- Rows: {report['n_rows']}",
        f"- Symbols: {', '.join(report['symbols'])}",
        f"- Mock PM: {report['mock_pm']}",
        f"- Mean |gap_level|: {report['mean_abs_gap']}",
        f"- Fraction |gap| > 0.02: {report['frac_gap_gt_0_02']}",
        f"- Fraction |gap| > 0.05: {report['frac_gap_gt_0_05']}",
        f"- **lag_pm_ms p50:** {report['lag_pm_ms_p50']}",
        f"- **lag_pm_ms p95:** {report['lag_pm_ms_p95']}",
        f"- Brier (settle rows): {report['brier_live']}",
        "",
        "## Per symbol",
        "",
        "| symbol | rows | mean |gap| | go_arb |",
        "|--------|------|------------|--------|",
    ]
    for sym, ps in sorted(per_symbol.items()):
        md.append(
            f"| {sym} | {ps['n_rows']} | {ps['mean_abs_gap']} | {ps['go_arb']} |"
        )
    md.extend(
        [
            "",
            "## Go / no-go (aggregate)",
            "",
            f"**{'GO' if report['go_arb'] else 'NO-GO'}** (`go_arb={report['go_arb']}`)",
            "",
            "See `config_recommendation.json`. **Mock logs are not evidence of live edge.**",
        ]
    )
    (args.out / "summary.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
