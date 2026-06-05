# Runbook — недельный прогон и gate к пилоту (v0.2+)

**Для человека и AI-агента.** Текущий статус проекта: фазы 0–1b done, фаза 2 **частично** (replay +PnL на 20h логе), фаза 3 начата.  
**Эмпирика 20h:** `STRATEGY.md` §10.1 · отчёты `output/reports/run_20h*`.

**Цель runbook:** получить **независимый** лайв-лог 7–10 дней **с settle в файле**, прогнать analyze + backtest, решить — можно ли думать о пилоте (фаза 6, BTC only).

---

## Статус чеклиста (обновляйте вручную)

| Шаг | Статус | Дата / примечание |
|-----|--------|-------------------|
| 1 Redeploy VPS + settle в логе | ☐ | |
| 2 Логгер 7–10 дней | ☐ | |
| 3 analyze → GO | ☐ | |
| 4 stress-hard BTC → критерии | ☐ | |
| 5 edge-sweep → min_edge | ☐ | |
| 6 Не торговать / не SOL | ☐ | |
| 7 Фаза 3 S₀ / пилот | ☐ | |

---

## Шаг 1 — VPS: redeploy (обязательно)

**Почему:** сырой `run_20h.jsonl` имел **0 settle-строк** (старая сборка). Текущий код пишет v3 CSV: тики `0,...`, settle `1,...`.

На VPS:

```bash
cd /opt/alpha-trader-src
git pull
sudo bash deploy/install.sh
sudo systemctl restart alpha-trader-logger
```

Проверка через ~10 мин (после закрытия одного 5m окна):

```bash
head -6 /opt/alpha-trader/output/logs/market_$(date -u +%Y-%m-%d).jsonl
# ожидаем: # alpha-trader market log v3  и  0,BTCUSDT,...

grep -c '^1,' /opt/alpha-trader/output/logs/market_$(date -u +%Y-%m-%d).jsonl
# ожидаем: > 0
```

Опционально в `.env` (Gamma poll при settle):

```bash
SETTLE_GAMMA_MAX_WAIT_SEC=12
SETTLE_GAMMA_POLL_SEC=2
```

Подробнее: `deploy/DEPLOY.md` § Redeploy.

**Gate шага 1:** `grep '^1,'` > 0 без `enrich_settle.py`.

---

## Шаг 2 — Логгер 7–10 дней

- **Не менять** настройки (символы, interval, `.env`).
- Убедиться: `systemctl status alpha-trader-logger` active, health OK.
- Цель: **несколько сотен** закрытых 5m-окон, settle **внутри** файла.

Мониторинг:

```bash
sudo systemctl status alpha-trader-logger
cat /opt/alpha-trader/output/health/logger.json
grep -c '^1,' /opt/alpha-trader/output/logs/market_$(date -u +%Y-%m-%d).jsonl
```

**Gate шага 2:** ≥ ~1000 settle-строк суммарно за период (порядок 3 символа × ~288 окон/день × 7 дней).

---

## Шаг 3 — Скачать лог, analyze (локально или агент)

Скопировать лог(и) с VPS, например:

```bash
# с VPS на локальную машину (пример)
scp user@vps:/opt/alpha-trader/output/logs/market_*.jsonl output/logs/
```

Объединить при необходимости в один файл `output/logs/market_week.jsonl`, затем:

```bash
py -3 tools/analyze_market_logs.py \
  --logs output/logs/market_week.jsonl \
  --out output/reports/market_week1/
```

**Смотреть:** `summary.md`, `config_recommendation.json` — **go_arb**, **lag_pm_ms p95**, **Brier**, mean |gap|.

**Gate шага 3:** `go_arb=True` (как на 20h). Записать `lag_ms_for_sim` из recommendation (обычно ≈ p95, было **601**).

Если NO-GO — **не** идти к шагу 4; чинить feeds / σ / S₀, повторить 1b.

---

## Шаг 4 — Backtest stress-hard (BTC)

Использовать **lag_ms** из шага 3 (пока ориентир **601**):

```bash
py -3 tools/run_backtest.py --sleeve arb \
  --logs output/logs/market_week.jsonl \
  --symbol-only --symbol BTCUSDT \
  --lag-ms 601 --pm-fee-rate 0.07 \
  --stress-hard --bankroll 100 --stake-pct 0.015 \
  --out output/reports/week_btc_stress
```

Отчёты: `stress_matrix.md`, `stress_matrix.json`.

### Критерии «можно думать о пилоте»

| Сценарий | Критерий (bankroll $100, 1.5%) |
|----------|-------------------------------|
| **baseline_touch** | return **> 0%** |
| **nightmare_slip3c** | return **> 0%** (желательно ≥ +5–10%) |
| **stress_combo** | не проваливается (return > 0%) |

**Ориентир с 20h лога:** baseline +45%, nightmare+3¢ +9%, combo +105% — на **новом** логе цифры будут другими; важен знак и порядок.

**Gate шага 4:** все три критерия выполнены на **недельном** логе.

---

## Шаг 5 — Edge sweep (подтвердить min_edge)

```bash
py -3 tools/run_backtest.py --sleeve arb \
  --logs output/logs/market_week.jsonl \
  --symbol-only --symbol BTCUSDT \
  --edge-sweep 0.03 0.04 0.05 0.06 \
  --fill-mode nightmare --slippage 0.03 \
  --lag-ms 601 --pm-fee-rate 0.07 \
  --bankroll 100 --stake-pct 0.015 \
  --out output/reports/week_edge_sweep
```

**Интерпретация:**

- Sweep гоняется под **жёсткий** fill (nightmare) — не боевой режим, а проверка порога.
- На 20h логе лучший был **min_edge=0.05** (+29% vs +9% при 0.03).
- **Gate шага 5:** на недельном логе снова разумный победитель (часто 0.05) → фиксируем для пилота.

**Черновик конфига пилота (после gate):**

```text
min_edge     = 0.05   (подтвердить sweep)
min_tau_sec  = 30
pm_fee_rate  = 0.07
lag_ms       = <из config_recommendation.json>
symbol       = BTCUSDT only
```

`nightmare` в лайв **не** включаем — только для stress-тестов.

---

## Шаг 6 — Пока НЕ делать

| Запрет | Причина |
|--------|---------|
| Торговать **SOL** (и альты без отдельного GO) | 20h: share-PnL SOL < 0 под PM fee |
| Лайв-бот с реальными деньгами | Нет gate недельного лога |
| Grid / подбор на holdout | Переобучение (STRATEGY §12, §16) |
| Считать baseline +45% «гарантией» | Оптимистичный fill, один лог |

---

## Шаг 7 — После зелёного недельного прогона

1. **Фаза 3:** сверить \(S_0\) логгера с правилами PM (~4% расхождений spot vs Gamma на 20h).
   ```bash
   py -3 scripts/fetch_pm_windows.py --from-log output/logs/market_week.jsonl \
     --symbol BTCUSDT --slug-prefix btc-updown-5m \
     --out data/pm/windows_btc_week.json
   ```
2. **Фаза 6 пилот:** только **BTC**, `dry-run` → малый notional (~$5), замер **p95 tick→ack** vs `lag_ms` из 1b.
3. Обновить `STRATEGY.md` §10.1 и `changelog/v0.x.md` с результатами недели.

---

## Для AI-агента (быстрый контекст)

1. Прочитать этот файл + `STRATEGY.md` §10.1.
2. Если пользователь принёс новый лог — шаги **3 → 4 → 5** по порядку, без подбора параметров под максимальный PnL.
3. `enrich_settle.py` — только если в логе **нет** `^1,` строк (аварийный fallback).
4. Агрегат отчётов: `py -3 tools/report.py --dir output/reports/week_btc_stress`.
5. Коммит / версия — только по запросу пользователя.

---

## Ссылки

| Документ | Содержание |
|----------|------------|
| `deploy/DEPLOY.md` | Установка, redeploy, firewall |
| `STRATEGY.md` §10.1 | Эмпирика 20h, фазы, ограничения |
| `PROJECT_MAP.md` | Структура репо, phase status |
| `changelog/v0.2.md` | Релиз phase 2 replay + команды |
