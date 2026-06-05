"""Market logger settle row persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from pm_spot_fair.config import LoggerConfig
from pm_spot_fair.log_format import load_log_file
from pm_spot_fair.market_logger_service import MarketLoggerService, window_from_utc_5m


@pytest.mark.asyncio
async def test_emit_settle_writes_v3_settle_line(tmp_path: Path) -> None:
    log_path = tmp_path / "market_test.jsonl"
    svc = MarketLoggerService(
        symbols=["BTCUSDT"],
        out_template=str(log_path),
        interval_ms=100,
        cfg=LoggerConfig(),
        mock_pm=True,
        pm_slugs={},
        pm_token_ids={},
        health_path=tmp_path / "health.json",
    )
    now = datetime(2026, 6, 4, 12, 0, 0, tzinfo=timezone.utc)
    window = window_from_utc_5m(now, "BTCUSDT")
    snapshot = {
        "s0": 100.0,
        "s_t": 101.0,
        "p_star": 0.62,
        "p_mid": 0.55,
        "pm_mock": True,
        "pm_slug": None,
    }
    await svc._emit_settle("BTCUSDT", window, snapshot)

    lines = log_path.read_text(encoding="utf-8").splitlines()
    data = [r for r in load_log_file(log_path) if r.get("type") == "settle"]
    assert len(data) == 1
    assert any(line.startswith("1,") for line in lines if not line.startswith("#"))


@pytest.mark.asyncio
async def test_schedule_settle_via_worker(tmp_path: Path) -> None:
    log_path = tmp_path / "market_worker.jsonl"
    svc = MarketLoggerService(
        symbols=["BTCUSDT"],
        out_template=str(log_path),
        interval_ms=100,
        cfg=LoggerConfig(),
        mock_pm=True,
        pm_slugs={},
        pm_token_ids={},
        health_path=tmp_path / "health.json",
    )
    svc._settle_worker_task = __import__("asyncio").create_task(svc._settle_worker())
    now = datetime(2026, 6, 4, 12, 0, 0, tzinfo=timezone.utc)
    window = window_from_utc_5m(now, "BTCUSDT")
    snapshot = {
        "s0": 50.0,
        "s_t": 49.0,
        "p_star": 0.4,
        "p_mid": 0.45,
        "pm_mock": True,
    }
    svc._schedule_settle("BTCUSDT", window, snapshot)
    await svc._settle_queue.join()
    await svc._settle_queue.put(None)
    await svc._settle_worker_task

    settles = [r for r in load_log_file(log_path) if r.get("type") == "settle"]
    assert len(settles) == 1
