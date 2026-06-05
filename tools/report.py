#!/usr/bin/env python3
"""Aggregate phase-2 backtest reports into one markdown summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    sep = "|" + "|".join("---" for _ in headers) + "|"
    lines = ["| " + " | ".join(headers) + " |", sep]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return lines


def aggregate(report_dir: Path) -> str:
    lines = [f"# Backtest aggregate", "", f"Source: `{report_dir}`", ""]

    stress = report_dir / "stress_matrix.json"
    if stress.exists():
        data = _load_json(stress)
        lines.append("## Stress matrix")
        lines.append("")
        rows = []
        for name, rep in data.items():
            br = rep.get("bankroll", {})
            rows.append(
                [
                    name,
                    rep.get("n_trades", "—"),
                    rep.get("total_pnl", "—"),
                    rep.get("win_rate", "—"),
                    f"${br.get('end', '—')}" if br else "—",
                ]
            )
        lines.extend(
            _table(
                ["scenario", "trades", "total_pnl", "win_rate", "bankroll_end"],
                rows,
            )
        )
        lines.append("")

    sweep = report_dir / "edge_sweep.json"
    if sweep.exists():
        data = _load_json(sweep)
        lines.append("## Edge sweep")
        lines.append("")
        if meta := data.get("meta"):
            lines.append(f"- fill: {meta.get('fill_mode')} slippage={meta.get('slippage')}")
            lines.append(f"- pm_fee_rate: {meta.get('pm_fee_rate')}")
            lines.append("")
        rows = []
        for edge, rep in sorted(data.get("results", {}).items(), key=lambda x: float(x[0])):
            br = rep.get("bankroll", {})
            rows.append(
                [
                    edge,
                    rep.get("n_trades", "—"),
                    rep.get("total_pnl", "—"),
                    rep.get("win_rate", "—"),
                    f"${br.get('end', '—')}" if br else "—",
                ]
            )
        lines.extend(
            _table(
                ["min_edge", "trades", "total_pnl", "win_rate", "bankroll_end"],
                rows,
            )
        )
        lines.append("")

    arb = report_dir / "arb_backtest.json"
    if arb.exists():
        rep = _load_json(arb)
        lines.append("## Single backtest")
        lines.append("")
        lines.append(f"- Trades: {rep.get('n_trades')} / {rep.get('windows_with_settle')}")
        lines.append(f"- Total PnL: {rep.get('total_pnl')}")
        lines.append(f"- Win rate: {rep.get('win_rate')}")
        if br := rep.get("bankroll"):
            lines.append(
                f"- Bankroll: ${br.get('start')} → ${br.get('end')} "
                f"({br.get('return_pct'):+.1f}%)"
            )
        lines.append("")

    if len(lines) <= 4:
        lines.append("_No recognized report files in directory._")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description="Aggregate backtest JSON reports")
    p.add_argument("--dir", type=Path, required=True, help="Report directory")
    p.add_argument("--out", type=Path, default=None, help="Write summary.md here")
    args = p.parse_args()
    md = aggregate(args.dir)
    out = args.out or (args.dir / "aggregate.md")
    out.write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
