#!/usr/bin/env python3
"""Backtest runner — phase 2 arb (market logs + synthetic klines)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pm_spot_fair.config import ArbConfig
from pm_spot_fair.log_format import expand_log_row, load_log_file
from pm_spot_fair.sim.backtest_opts import ArbReplayOptions
from pm_spot_fair.sim.event_sim import EventSimConfig
from pm_spot_fair.sim.market_log_arb import backtest_arb_market_log
from pm_spot_fair.sim.synthetic_arb import backtest_arb_klines
from pm_spot_fair.symbols import parse_symbols


def _filter_log_rows(
    rows: list[dict], symbols: list[str] | None
) -> list[dict]:
    if not symbols:
        return rows
    allowed = {s.upper() for s in symbols}
    return [r for r in rows if r.get("symbol", "").upper() in allowed]


def _log_symbols(args: argparse.Namespace) -> list[str] | None:
    if args.symbols:
        return parse_symbols(args.symbols, fallback_single=args.symbol)
    if args.symbol_only:
        return [args.symbol.upper()]
    return None


def _opts_from_args(args: argparse.Namespace) -> ArbReplayOptions:
    return ArbReplayOptions(
        max_spread=args.max_spread,
        lag_ms=args.lag_ms,
        cooldown_sec=args.cooldown_sec,
        one_per_window=not args.multi_per_window,
        fill_mode=args.fill_mode,
        slippage=args.slippage,
        bankroll_start=args.bankroll,
        stake_pct=args.stake_pct,
        bankroll_compound=not args.no_compound,
    )


def _summary_md(report: dict, title: str, extra: list[str] | None = None) -> str:
    lines = [
        f"# {title}",
        "",
        *(extra or []),
        f"- Mode: {report.get('mode')}",
        f"- Trades: {report['n_trades']} / {report['windows_with_settle']} windows",
        f"- cooldown_sec: {report.get('cooldown_sec', 0)}",
        f"- fill: {report.get('fill_mode')} slippage={report.get('slippage')}",
        f"- fee: pm_fee_rate={report.get('pm_fee_rate')} "
        f"(flat taker_fee={report.get('taker_fee')})",
        f"- **Total PnL** (per-share unit): {report['total_pnl']}",
        f"- Mean PnL / trade: {report['mean_pnl_per_trade']}",
        f"- Win rate: {report['win_rate']}",
    ]
    if br := report.get("bankroll"):
        lines.extend(
            [
                f"- Bankroll ${br['start']} → ${br['end']} "
                f"({br['return_pct']:+.1f}%, max DD {br['max_drawdown_pct']}%)",
            ]
        )
    lines.extend(["", "## Per symbol", ""])
    lines.append("| symbol | trades | total_pnl | mean | win_rate |")
    lines.append("|--------|--------|-----------|------|----------|")
    for sym, ps in sorted(report.get("per_symbol", {}).items()):
        lines.append(
            f"| {sym} | {ps['n_trades']} | {ps['total_pnl']} | "
            f"{ps['mean_pnl']} | {ps['win_rate']} |"
        )
    return "\n".join(lines)


def _stress_scenarios(hard: bool = False) -> list[tuple[str, ArbReplayOptions]]:
    base = ArbReplayOptions()
    standard = [
        ("baseline_touch", base),
        ("cooldown_300s", ArbReplayOptions(cooldown_sec=300.0)),
        ("cooldown_900s", ArbReplayOptions(cooldown_sec=900.0)),
        (
            "half_spread_slip1c",
            ArbReplayOptions(fill_mode="half_spread", slippage=0.01),
        ),
        (
            "full_spread_slip2c",
            ArbReplayOptions(fill_mode="full_spread", slippage=0.02),
        ),
        (
            "stress_combo",
            ArbReplayOptions(
                cooldown_sec=300.0,
                fill_mode="half_spread",
                slippage=0.01,
            ),
        ),
    ]
    if not hard:
        return standard
    brutal = [
        ("baseline_touch", base),
        (
            "full_spread_slip3c",
            ArbReplayOptions(fill_mode="full_spread", slippage=0.03),
        ),
        (
            "full_spread_slip5c",
            ArbReplayOptions(fill_mode="full_spread", slippage=0.05),
        ),
        (
            "extreme_slip2c",
            ArbReplayOptions(fill_mode="extreme", slippage=0.02),
        ),
        (
            "extreme_slip3c",
            ArbReplayOptions(fill_mode="extreme", slippage=0.03),
        ),
        (
            "nightmare_slip3c",
            ArbReplayOptions(fill_mode="nightmare", slippage=0.03),
        ),
        (
            "nightmare_slip5c",
            ArbReplayOptions(fill_mode="nightmare", slippage=0.05),
        ),
        (
            "nightmare_cd300_slip5c",
            ArbReplayOptions(
                fill_mode="nightmare",
                slippage=0.05,
                cooldown_sec=300.0,
            ),
        ),
        (
            "stress_combo",
            ArbReplayOptions(
                cooldown_sec=300.0,
                fill_mode="half_spread",
                slippage=0.01,
            ),
        ),
    ]
    return brutal


def main() -> None:
    p = argparse.ArgumentParser(description="PM Spot Fair backtest")
    p.add_argument("--sleeve", choices=["arb", "mm", "rebate"], required=True)
    p.add_argument("--logs", type=Path, help="Market log (ticks + settle)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--years", nargs="+", type=int)
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated (log replay filter, or multi-symbol --years)",
    )
    p.add_argument(
        "--symbol-only",
        action="store_true",
        help="Log replay: only --symbol (e.g. BTCUSDT)",
    )
    p.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    p.add_argument("--lag-ms", type=float, default=None)
    p.add_argument("--min-edge", type=float, default=0.03)
    p.add_argument("--min-tau-sec", type=float, default=30.0)
    p.add_argument(
        "--taker-fee",
        type=float,
        default=0.01,
        help="Flat per-share fee fallback when --pm-fee-rate is off",
    )
    p.add_argument(
        "--pm-fee-rate",
        type=float,
        default=0.07,
        help="Polymarket dynamic feeRate (crypto=0.07); 0 = use flat --taker-fee",
    )
    p.add_argument("--max-spread", type=float, default=0.08)
    p.add_argument("--cooldown-sec", type=float, default=0.0)
    p.add_argument("--multi-per-window", action="store_true")
    p.add_argument(
        "--fill-mode",
        choices=["touch", "half_spread", "full_spread", "extreme", "nightmare"],
        default="touch",
    )
    p.add_argument("--slippage", type=float, default=0.0, help="Extra price penalty")
    p.add_argument("--bankroll", type=float, default=None)
    p.add_argument("--stake-pct", type=float, default=None)
    p.add_argument("--no-compound", action="store_true")
    p.add_argument(
        "--stress",
        action="store_true",
        help="Run baseline + cooldown/slippage scenarios (requires --logs)",
    )
    p.add_argument(
        "--stress-hard",
        action="store_true",
        help="Worse fills: extreme/nightmare spread + 3-5c slippage",
    )
    p.add_argument(
        "--edge-sweep",
        nargs="+",
        type=float,
        metavar="MIN_EDGE",
        help="Sweep min_edge values (requires --logs); uses --fill-mode/--slippage",
    )
    p.add_argument("--pm-spread", type=float, default=0.02, help="Synthetic PM spread")
    args = p.parse_args()

    if args.sleeve != "arb":
        raise NotImplementedError(f"sleeve {args.sleeve!r} is not implemented yet")

    fee_rate = args.pm_fee_rate if args.pm_fee_rate > 0 else None
    cfg = ArbConfig(
        min_edge=args.min_edge,
        min_tau_sec=args.min_tau_sec,
        taker_fee=args.taker_fee,
        pm_fee_rate=fee_rate,
    )
    args.out.mkdir(parents=True, exist_ok=True)

    if args.edge_sweep:
        if args.logs is None:
            raise SystemExit("--edge-sweep requires --logs")
        rows = [expand_log_row(r) for r in load_log_file(args.logs)]
        sym_filter = _log_symbols(args)
        rows = _filter_log_rows(rows, sym_filter)
        opts = _opts_from_args(args)
        if opts.lag_ms is None and args.lag_ms is not None:
            opts = ArbReplayOptions(
                max_spread=opts.max_spread,
                lag_ms=args.lag_ms,
                cooldown_sec=opts.cooldown_sec,
                one_per_window=opts.one_per_window,
                fill_mode=opts.fill_mode,
                slippage=opts.slippage,
                bankroll_start=opts.bankroll_start,
                stake_pct=opts.stake_pct,
                bankroll_compound=opts.bankroll_compound,
            )
        results: dict[str, dict] = {}
        md = [
            "# Edge sweep",
            "",
            f"Log: `{args.logs}`",
            f"fill: {opts.fill_mode} slippage={opts.slippage}",
            f"pm_fee_rate: {fee_rate}",
        ]
        if sym_filter:
            md.append(f"Symbols: {', '.join(sym_filter)}")
        md.extend(["", "| min_edge | trades | total_pnl | win_rate | bankroll |", "|----------|--------|-----------|----------|----------|"])
        for edge in sorted(set(args.edge_sweep)):
            sweep_cfg = ArbConfig(
                min_edge=edge,
                min_tau_sec=args.min_tau_sec,
                taker_fee=args.taker_fee,
                pm_fee_rate=fee_rate,
            )
            rep = backtest_arb_market_log(rows, sweep_cfg, opts)
            key = f"{edge:.4f}".rstrip("0").rstrip(".")
            results[key] = {k: v for k, v in rep.items() if k != "trades"}
            br = rep.get("bankroll", {})
            br_s = f"${br.get('end', '—')}" if br else "—"
            md.append(
                f"| {key} | {rep['n_trades']} | {rep['total_pnl']} | "
                f"{rep['win_rate']} | {br_s} |"
            )
        payload = {
            "meta": {
                "log": str(args.logs),
                "fill_mode": opts.fill_mode,
                "slippage": opts.slippage,
                "pm_fee_rate": fee_rate,
                "lag_ms": opts.lag_ms,
            },
            "results": results,
        }
        (args.out / "edge_sweep.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        (args.out / "edge_sweep.md").write_text("\n".join(md), encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return

    if args.stress or args.stress_hard:
        if args.logs is None:
            raise SystemExit("--stress requires --logs")
        rows = [expand_log_row(r) for r in load_log_file(args.logs)]
        sym_filter = _log_symbols(args)
        rows = _filter_log_rows(rows, sym_filter)
        scenarios = _stress_scenarios(hard=args.stress_hard)
        if args.bankroll and args.stake_pct:
            scenarios = [
                (n, ArbReplayOptions(
                    cooldown_sec=o.cooldown_sec,
                    one_per_window=o.one_per_window,
                    fill_mode=o.fill_mode,
                    slippage=o.slippage,
                    max_spread=o.max_spread,
                    lag_ms=args.lag_ms,
                    bankroll_start=args.bankroll,
                    stake_pct=args.stake_pct,
                    bankroll_compound=not args.no_compound,
                ))
                for n, o in scenarios
            ]
        results: dict[str, dict] = {}
        title = "Arb stress matrix (hard)" if args.stress_hard else "Arb stress matrix"
        md = [f"# {title}", "", f"Log: `{args.logs}`"]
        if sym_filter:
            md.append(f"Symbols: {', '.join(sym_filter)}")
        md.append("")
        md.append("| scenario | trades | total_pnl | win_rate | bankroll |")
        md.append("|----------|--------|-----------|----------|----------|")
        for name, opts in scenarios:
            if opts.lag_ms is None:
                opts = ArbReplayOptions(
                    max_spread=opts.max_spread,
                    lag_ms=args.lag_ms,
                    cooldown_sec=opts.cooldown_sec,
                    one_per_window=opts.one_per_window,
                    fill_mode=opts.fill_mode,
                    slippage=opts.slippage,
                    bankroll_start=opts.bankroll_start,
                    stake_pct=opts.stake_pct,
                    bankroll_compound=opts.bankroll_compound,
                )
            rep = backtest_arb_market_log(rows, cfg, opts)
            rep["scenario"] = name
            results[name] = {k: v for k, v in rep.items() if k != "trades"}
            br = rep.get("bankroll", {})
            br_s = (
                f"${br.get('end', '—')}" if br else "—"
            )
            md.append(
                f"| {name} | {rep['n_trades']} | {rep['total_pnl']} | "
                f"{rep['win_rate']} | {br_s} |"
            )
        (args.out / "stress_matrix.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )
        (args.out / "stress_matrix.md").write_text("\n".join(md), encoding="utf-8")
        print(json.dumps(results, indent=2))
        return

    if args.logs is not None:
        rows = [expand_log_row(r) for r in load_log_file(args.logs)]
        sym_filter = _log_symbols(args)
        rows = _filter_log_rows(rows, sym_filter)
        if not rows:
            print("No rows in log", file=sys.stderr)
            sys.exit(1)
        opts = _opts_from_args(args)
        report = backtest_arb_market_log(rows, cfg, opts)
        (args.out / "arb_backtest.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        extra = [f"- Log: `{args.logs}`"]
        if sym_filter:
            extra.append(f"- Symbols: {', '.join(sym_filter)}")
        (args.out / "summary.md").write_text(
            _summary_md(report, "Arb backtest (market log)", extra),
            encoding="utf-8",
        )
        print(json.dumps({k: v for k, v in report.items() if k != "trades"}, indent=2))
        return

    if args.years:
        symbols = parse_symbols(args.symbols, fallback_single=args.symbol)
        sim_cfg = EventSimConfig(
            lag_ms=args.lag_ms or 600.0,
            pm_half_spread=args.pm_spread / 2.0,
        )
        combined: dict[str, dict] = {}
        for sym in symbols:
            try:
                rep = backtest_arb_klines(
                    args.data_dir,
                    sym,
                    args.years,
                    cfg,
                    _opts_from_args(args),
                    sim_cfg=sim_cfg,
                )
                combined[sym] = {k: v for k, v in rep.items() if k != "trades"}
            except FileNotFoundError as e:
                combined[sym] = {"error": str(e)}
        (args.out / "synthetic_backtest.json").write_text(
            json.dumps(combined, indent=2), encoding="utf-8"
        )
        print(json.dumps(combined, indent=2))
        return

    raise SystemExit("Provide --logs, --years, or --stress with --logs")


if __name__ == "__main__":
    main()
