# Alpha Trader — PM Spot Fair

Mechanistic fair probability \(p^\*\) for Polymarket BTC Up/Down 5m markets from Binance spot, time-to-expiry, and volatility.

| Doc | Purpose |
|-----|---------|
| [STRATEGY.md](STRATEGY.md) | Full strategy spec |
| [PROJECT_MAP.md](PROJECT_MAP.md) | Repo structure & phase status |
| [AGENTS.md](AGENTS.md) | Rules for AI agents |
| [deploy/DEPLOY.md](deploy/DEPLOY.md) | VPS installation |
| [changelog/v0.1.md](changelog/v0.1.md) | Release notes |

## Install

```bash
py -3 -m pip install -e ".[dev]"
py -3 -m pytest -q
```

## Phases 0–1b (local)

| Phase | Command |
|-------|---------|
| 0 | `py -3 -m pytest tests/test_fair.py -q` |
| 1 | `py -3 scripts/fetch_binance_klines.py --symbol BTCUSDT --years 2024` |
| 1 | `py -3 tools/run_calibration.py --years 2024 --out output/reports/cal_2024` |
| 1b | `py -3 tools/market_logger.py --duration-sec 60 --mock-pm --out output/logs/smoke.jsonl` |
| 1b | `py -3 tools/analyze_market_logs.py --logs output/logs/smoke.jsonl --out output/reports/smoke/` |

## VPS (production logger)

```bash
sudo bash deploy/install.sh
sudo nano /opt/alpha-trader/.env   # PM_MARKET_SLUG or PM_YES_TOKEN_ID
sudo systemctl enable --now alpha-trader-logger
cat /opt/alpha-trader/output/health/logger.json
```

Preflight: `py -3 tools/verify_deploy.py`

Package: `src/pm_spot_fair/` — `from pm_spot_fair.fair import p_up_gbm`
