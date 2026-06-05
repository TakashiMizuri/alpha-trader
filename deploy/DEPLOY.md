# VPS deployment (phase 1b)

## Requirements

- Ubuntu 22.04+ (or Debian 12+)
- Python 3.11+
- `chrony` or `systemd-timesyncd` for UTC sync
- Outbound HTTPS + WSS (Binance, Polymarket Gamma/CLOB)

## Quick install

```bash
git clone <your-repo> /opt/alpha-trader-src
cd /opt/alpha-trader-src
sudo bash deploy/install.sh
sudo nano /opt/alpha-trader/.env
sudo systemctl enable --now alpha-trader-logger
```

## `.env` (production)

```bash
BINANCE_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT,HYPEUSDT,BNBUSDT
PM_MARKET_SLUGS={"BTCUSDT":"<btc-5m-slug>"}
# Add ETH/SOL slugs when PM markets exist; others log p* + mock PM until configured
# Or set explicitly after resolving Gamma API:
# PM_YES_TOKEN_ID=21742...

LOG_OUT_TEMPLATE=/opt/alpha-trader/output/logs/market_%Y-%m-%d.jsonl
HEALTH_FILE=/opt/alpha-trader/output/health/logger.json
LOGGER_INTERVAL_MS=100
LOG_LEVEL=INFO
```

Do **not** set `PM_API_*` keys for phase 1b — read-only public feeds only.

## Redeploy (after `git pull` — required for settle rows + v3 CSV)

The logger must run **current** code: v3 CSV lines (`0,...` ticks, `1,...` settle) with a `# alpha-trader market log v3` header. Old builds wrote compact JSON only and **no settle rows**.

```bash
cd /opt/alpha-trader-src   # or your clone path
git pull
sudo bash deploy/install.sh
sudo systemctl restart alpha-trader-logger
```

Verify within one 5m window (or after stop):

```bash
head -6 /opt/alpha-trader/output/logs/market_$(date -u +%Y-%m-%d).jsonl
# expect: # alpha-trader market log v3  and  0,BTCUSDT,...
grep -c '^1,' /opt/alpha-trader/output/logs/market_$(date -u +%Y-%m-%d).jsonl
# expect: > 0 after at least one window closed
```

Optional `.env` (live Gamma poll on settle; falls back to `spot_proxy`):

```bash
SETTLE_GAMMA_MAX_WAIT_SEC=12
SETTLE_GAMMA_POLL_SEC=2
```

Offline ground truth: `tools/enrich_settle.py` on finished logs.

## Operations

| Task | Command |
|------|---------|
| Status | `sudo systemctl status alpha-trader-logger` |
| Logs (journal) | `sudo journalctl -u alpha-trader-logger -f` |
| Health | `cat /opt/alpha-trader/output/health/logger.json` |
| Stop | `sudo systemctl stop alpha-trader-logger` |
| Weekly report | `.venv/bin/python tools/analyze_market_logs.py --logs '/opt/alpha-trader/output/logs/market_*.jsonl' --out /opt/alpha-trader/output/reports/week1/` |

## Smoke test (before enable)

```bash
cd /opt/alpha-trader
.venv/bin/python tools/market_logger.py --duration-sec 30 --mock-pm \
  --out output/logs/smoke.jsonl
.venv/bin/python tools/analyze_market_logs.py \
  --logs output/logs/smoke.jsonl --out output/reports/smoke/
```

## Firewall

No inbound ports required. Egress to:

- `stream.binance.com:9443`
- `gamma-api.polymarket.com:443`
- `clob.polymarket.com:443`
- `ws-subscriptions-clob.polymarket.com:443`

## Disk

~4–20 MB/day at 100 ms (v3 CSV rows + header); logrotate keeps 14 days by default.
