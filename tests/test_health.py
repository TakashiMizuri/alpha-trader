"""Health and path helpers."""

import json
from pathlib import Path

from pm_spot_fair.health import LoggerHealth, write_health
from pm_spot_fair.market_logger_service import resolve_log_path


def test_resolve_log_path_strftime(tmp_path: Path):
    p = resolve_log_path(str(tmp_path / "market_%Y-%m-%d.jsonl"))
    assert p.name.startswith("market_")
    assert p.suffix == ".jsonl"


def test_write_health(tmp_path: Path):
    path = tmp_path / "logger.json"
    h = LoggerHealth(
        status="ok",
        ticks_written=10,
        last_tick_utc="2026-01-01T00:00:00.000Z",
        binance_connected=True,
        pm_connected=True,
        mock_pm=False,
        feed_gap_sec=0.5,
        pid=12345,
        symbols=["BTCUSDT", "ETHUSDT"],
        ticks_by_symbol={"BTCUSDT": 6, "ETHUSDT": 4},
    )
    write_health(path, h)
    data = json.loads(path.read_text())
    assert data["status"] == "ok"
    assert data["ticks_written"] == 10
