# Project map — alpha-trader (PM Spot Fair)

**Repo:** `alpha-trader` · **Package:** `pm_spot_fair` · **Spec:** `STRATEGY.md` v2.0  
**Current release:** v0.2.0 (phases 0–1b done; **phase 2 partial** — replay arb + PM fees; **phase 3 started** — PM calendar)

---

## Purpose

Mechanistic fair probability \(p^\*\) from Binance BTC spot, time-to-expiry \(\tau\), and volatility \(\sigma\); compare to Polymarket YES mid; log gaps and latency **without trading** until phase 1b go/no-go is proven on live data.

---

## Phase status

| Phase | Status | Deliverable |
|-------|--------|-------------|
| **0** | Done | `fair.py`, `vol.py`, `tests/test_fair.py` |
| **1** | Done | klines fetch, `clock`, `spot`, `run_calibration.py` |
| **1b** | Done (redeploy for settle) | live `market_logger`, `analyze_market_logs`, `deploy/` |
| **2** | **Partial** | `signals_arb`, `market_log_arb`, `run_backtest` (replay + stress + edge-sweep) |
| **3** | **Started** | `fetch_pm_windows`, `pm_windows.py` — Gamma calendar |
| **4** | Stub | `book_pressure` |
| **5** | Stub | `signals_mm` |
| **6** | Stub | `bot/`, `order_gateway`, `reconcile_pm` |

**Gate:** phase 2 full exit — positive replay on **independent** week log + PM fee + stress; phase 6 only after 2/3 green.

**Next actions (human + agent):** **[deploy/RUNBOOK.md](deploy/RUNBOOK.md)** — redeploy VPS → 7–10d log → analyze → stress → edge sweep → pilot.

**Empirical snapshot (20h log, Jun 2026):** see `STRATEGY.md` §10.1 · reports under `output/reports/run_20h*`.

---

## Directory layout (canonical)

```text
alpha-trader/
├── AGENTS.md              # AI/human agent rules
├── PROJECT_MAP.md         # This file — always update when structure changes
├── STRATEGY.md            # Full strategy spec (Russian)
├── README.md              # Quick start
├── changelog/             # Release notes v0.x.md
├── pyproject.toml
├── .env.example           # Copy → .env on VPS (never commit .env)
│
├── src/pm_spot_fair/      # Import: pm_spot_fair.*
│   ├── fair.py            # p_up_gbm, p_up_mc  [0]
│   ├── vol.py             # sigma_ann_from_closes  [0-1]
│   ├── clock.py           # Window, tau_sec  [1]
│   ├── spot.py            # kline JSON load  [1]
│   ├── config.py          # ArbConfig, LoggerConfig, …  [1]
│   ├── pm_book.py         # mid, edge, PM fee, fill stress  [1b/2]
│   ├── pm_windows.py      # Gamma 5m calendar  [3]
│   ├── latency.py         # histograms  [1b/6]
│   ├── health.py          # logger.json for ops  [1b deploy]
│   ├── log_format.py      # v3 CSV log (+ legacy JSONL) + expand  [1b]
│   ├── market_logger_service.py  # live engine + settle worker  [1b]
│   ├── feeds/             # Binance WS, PM CLOB, Gamma  [1b]
│   ├── signals_arb.py     # buy/sell/skip  [2]
│   ├── sim/
│   │   ├── market_log_arb.py   # log replay backtest  [2]
│   │   ├── bankroll.py         # compound stake  [2]
│   │   ├── backtest_opts.py    # replay options  [2]
│   │   ├── event_sim.py        # synthetic ticks  [2]
│   │   └── synthetic_arb.py    # klines wrapper  [2]
│   ├── book_pressure.py   # stub → phase 4
│   ├── signals_mm.py      # stub → phase 5
│   └── signals_rebate.py  # stub → phase 6
│
├── scripts/               # Data ingestion (offline)
│   ├── fetch_binance_klines.py   [1]
│   ├── fetch_pm_windows.py       [3]
│   └── reconcile_pm.py           [6 stub]
│
├── tools/                 # CLI entrypoints (run from repo root)
│   ├── market_logger.py          [1b] ← systemd runs this
│   ├── analyze_market_logs.py    [1b]
│   ├── enrich_settle.py          [1b offline settle]
│   ├── run_calibration.py        [1]
│   ├── verify_deploy.py          [deploy]
│   ├── run_backtest.py           [2] replay / stress / edge-sweep
│   └── report.py                 [2] aggregate JSON reports
│
├── bot/                   # Live trading [6 stub only]
├── tests/                 # pytest (46 tests)
├── deploy/                # VPS: install.sh, systemd, DEPLOY.md, RUNBOOK.md
├── data/                  # gitignored JSON (binance klines, pm windows)
└── output/                # gitignored logs & reports
    ├── logs/              # JSONL / v3 CSV market logs
    ├── health/            # logger.json
    └── reports/           # calibration, smoke, backtest, week1
```

---

## What goes where (anti-clutter)

| Put it here | Not here |
|-------------|----------|
| Reusable math/feeds in `src/pm_spot_fair/` | Business logic duplicated in `tools/` |
| One-off CLIs in `tools/` or `scripts/` | New top-level random folders |
| Ops/deployment in `deploy/` | Secrets in git |
| Experiments / one-off analysis | `output/` only, or delete after |
| Release notes | `changelog/vX.Y.md` |

---

## Key commands

```bash
# Dev install
py -3 -m pip install -e ".[dev]"

# Tests
py -3 -m pytest -q

# Phase 1b smoke (CI / local)
py -3 tools/market_logger.py --duration-sec 60 --mock-pm --out output/logs/smoke.jsonl
py -3 tools/analyze_market_logs.py --logs output/logs/smoke.jsonl --out output/reports/smoke/

# Phase 2 replay (after enrich if no settle rows)
py -3 tools/enrich_settle.py --in output/logs/run_20h.jsonl --out output/logs/run_20h_enriched.jsonl
py -3 tools/run_backtest.py --sleeve arb --logs output/logs/run_20h_enriched.jsonl \
  --lag-ms 601 --pm-fee-rate 0.07 --out output/reports/backtest --bankroll 100 --stake-pct 0.015

# Phase 3 PM calendar
py -3 scripts/fetch_pm_windows.py --from-log output/logs/run_20h_enriched.jsonl \
  --symbol BTCUSDT --slug-prefix btc-updown-5m --out data/pm/windows_btc_20h.json

# VPS preflight
py -3 tools/verify_deploy.py

# Production logger (see deploy/DEPLOY.md)
# systemd: alpha-trader-logger.service
```

---

## Environment variables

| Variable | Used by |
|----------|---------|
| `BINANCE_SYMBOLS` | logger, fetch, calibration (default: 7 symbols) |
| `PM_MARKET_SLUGS` | JSON map symbol → Polymarket slug |
| `PM_MARKET_SLUG` | legacy: BTC only |
| `PM_YES_TOKEN_ID_*` | per-symbol CLOB YES token |
| `LOG_OUT_TEMPLATE` | dated JSONL path |
| `HEALTH_FILE` | `output/health/logger.json` |
| `LOGGER_INTERVAL_MS` | tick interval (default 100 ms) |
| `SETTLE_GAMMA_MAX_WAIT_SEC` | settle worker poll budget |
| `PM_API_*` | phase 6 only (not 1b) |

---

## External dependencies

- Binance: `wss://stream.binance.com:9443/ws/{symbol}@bookTicker`
- Polymarket: Gamma API + CLOB REST/WS (read-only in 1b)
- Binance Vision: historical klines (phase 1)

---

## When editing this map

Update `PROJECT_MAP.md` when you add/remove top-level dirs, change phase ownership of a module, or shift deploy paths. Keep `changelog/vX.Y.md` in sync.
