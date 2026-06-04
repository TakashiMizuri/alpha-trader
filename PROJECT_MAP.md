# Project map — alpha-trader (PM Spot Fair)

**Repo:** `alpha-trader` · **Package:** `pm_spot_fair` · **Spec:** `STRATEGY.md` v2.0  
**Current release:** v0.1.1 (phases 0, 1, 1b + VPS deploy; logger **100 ms**, compact JSONL)

---

## Purpose

Mechanistic fair probability \(p^\*\) from Binance BTC spot, time-to-expiry \(\tau\), and volatility \(\sigma\); compare to Polymarket YES mid; log gaps and latency **without trading** until phase 1b go/no-go is proven on live data.

---

## Phase status

| Phase | Status | Deliverable |
|-------|--------|-------------|
| **0** | Done | `fair.py`, `vol.py`, `tests/test_fair.py` |
| **1** | Done | klines fetch, `clock`, `spot`, `run_calibration.py` |
| **1b** | Done (deploy-ready) | live/mock `market_logger`, `analyze_market_logs`, `deploy/` |
| **2** | Not started | `event_sim`, `signals_arb`, `run_backtest` |
| **3** | Stub | `fetch_pm_windows`, real PM calendar |
| **4** | Stub | `book_pressure` |
| **5** | Stub | `signals_mm` |
| **6** | Stub | `bot/`, `order_gateway`, `reconcile_pm` |

**Gate:** phase 2 only after **live** 1b report (`go_arb`, `lag_pm_ms_p95`) — not mock smoke alone.

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
│   ├── pm_book.py         # mid, microprice, edge  [1b]
│   ├── latency.py         # histograms  [1b/6]
│   ├── health.py          # logger.json for ops  [1b deploy]
│   ├── log_format.py      # v3 CSV log (+ legacy JSONL) + expand  [1b]
│   ├── market_logger_service.py  # live engine  [1b]
│   ├── feeds/             # Binance WS, PM CLOB, Gamma  [1b]
│   ├── book_pressure.py   # stub → phase 4
│   ├── signals_*.py       # stub → phases 2,5,6
│   └── sim/event_sim.py   # stub → phase 2
│
├── scripts/               # Data ingestion (offline)
│   ├── fetch_binance_klines.py   [1]
│   ├── fetch_pm_windows.py       [3 stub]
│   └── reconcile_pm.py           [6 stub]
│
├── tools/                 # CLI entrypoints (run from repo root)
│   ├── market_logger.py          [1b] ← systemd runs this
│   ├── analyze_market_logs.py    [1b]
│   ├── run_calibration.py        [1]
│   ├── verify_deploy.py          [deploy]
│   ├── run_backtest.py           [2 stub]
│   └── report.py                 [2+ stub]
│
├── bot/                   # Live trading [6 stub only]
├── tests/                 # pytest
├── deploy/                # VPS: install.sh, systemd, logrotate, DEPLOY.md
├── data/                  # gitignored JSON (binance klines, pm windows)
└── output/                # gitignored logs & reports
    ├── logs/              # JSONL market_%Y-%m-%d.jsonl
    ├── health/            # logger.json
    └── reports/           # calibration, smoke, week1 analysis
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
| `PM_API_*` | phase 6 only (not 1b) |

---

## External dependencies

- Binance: `wss://stream.binance.com:9443/ws/{symbol}@bookTicker`
- Polymarket: Gamma API + CLOB REST/WS (read-only in 1b)
- Binance Vision: historical klines (phase 1)

---

## When editing this map

Update `PROJECT_MAP.md` when you add/remove top-level dirs, change phase ownership of a module, or shift deploy paths. Keep `changelog/vX.Y.md` in sync.
