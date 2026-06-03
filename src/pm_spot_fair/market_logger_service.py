"""Production market logger engine — phase 1b (multi-symbol)."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import random
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from pm_spot_fair.clock import Window, tau_sec
from pm_spot_fair.config import LoggerConfig
from pm_spot_fair.fair import p_up_gbm
from pm_spot_fair.feeds.binance_ws import BinanceMultiBookTickerFeed, BinanceTick
from pm_spot_fair.feeds.gamma import resolve_market_by_slug
from pm_spot_fair.feeds.pm_clob import PMClobFeed
from pm_spot_fair.health import LoggerHealth, utc_iso, write_health
from pm_spot_fair.latency import utc_now_iso
from pm_spot_fair.symbols import mock_base_price
from pm_spot_fair.vol import sigma_ann_from_closes

logger = logging.getLogger(__name__)


def window_from_utc_5m(now: datetime, symbol: str) -> Window:
    minute = (now.minute // 5) * 5
    t0 = now.replace(minute=minute, second=0, microsecond=0)
    t_end = t0 + timedelta(minutes=5)
    prefix = symbol.lower().replace("usdt", "")[:8]
    wid = f"{prefix}_5m_{int(t0.timestamp())}"
    return Window(window_id=wid, t0_utc=t0, t_end_utc=t_end)


def resolve_log_path(template: str, now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    return Path(now.strftime(template))


@dataclass
class SymbolState:
    symbol: str
    closes: list[float] = field(default_factory=list)
    s0: float | None = None
    window: Window | None = None
    lag_state: dict = field(default_factory=dict)
    pm_feed: PMClobFeed | None = None
    pm_mock: bool = True
    ticks: int = 0


class MarketLoggerService:
    def __init__(
        self,
        *,
        symbols: list[str],
        out_template: str,
        interval_ms: int,
        cfg: LoggerConfig,
        mock_pm: bool,
        pm_slugs: dict[str, str],
        pm_token_ids: dict[str, str],
        health_path: Path,
        duration_sec: float | None = None,
    ) -> None:
        self.symbols = [s.upper() for s in symbols]
        self.out_template = out_template
        self.interval_ms = interval_ms
        self.cfg = cfg
        self.mock_pm_global = mock_pm
        self.pm_slugs = {k.upper(): v for k, v in pm_slugs.items()}
        self.pm_token_ids = {k.upper(): v for k, v in pm_token_ids.items()}
        self.health_path = health_path
        self.duration_sec = duration_sec

        self._binance = BinanceMultiBookTickerFeed(self.symbols)
        self._states: dict[str, SymbolState] = {
            s: SymbolState(symbol=s) for s in self.symbols
        }
        self._ticks = 0
        self._stop = asyncio.Event()
        self._last_tick_mono = time.monotonic()
        self._rng_seed = 42
        self._mock_feeds = mock_pm

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._stop.set)
            except NotImplementedError:
                signal.signal(sig, lambda *_: self._stop.set())

        if self._mock_feeds:
            await self._run_mock_loop()
            return

        await self._setup_pm_feeds()
        await self._binance.start()
        started = time.monotonic()
        try:
            while not self._stop.is_set():
                if self.duration_sec and (time.monotonic() - started) >= self.duration_sec:
                    break
                await self._tick_all()
                await asyncio.sleep(self.interval_ms / 1000.0)
        finally:
            await self._binance.stop()
            for st in self._states.values():
                if st.pm_feed:
                    await st.pm_feed.stop()
            self._write_health("down")

    async def _setup_pm_feeds(self) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for sym, st in self._states.items():
                token = self.pm_token_ids.get(sym)
                slug = self.pm_slugs.get(sym)
                if token:
                    st.pm_feed = PMClobFeed(token, use_websocket=True)
                    st.pm_mock = False
                    await st.pm_feed.start()
                elif slug and not self.mock_pm_global:
                    try:
                        tokens = await resolve_market_by_slug(client, slug)
                        st.pm_feed = PMClobFeed(tokens.yes_token_id, use_websocket=True)
                        st.pm_mock = False
                        await st.pm_feed.start()
                    except Exception:
                        logger.warning(
                            "PM slug resolve failed for %s (%s); PM mock for symbol",
                            sym,
                            slug,
                        )
                        st.pm_mock = True
                else:
                    st.pm_mock = True

    async def _run_mock_loop(self) -> None:
        rng = random.Random(self._rng_seed)
        started = time.monotonic()
        last_t0: dict[str, float] = {}

        while not self._stop.is_set():
            if self.duration_sec and (time.monotonic() - started) >= self.duration_sec:
                break
            now = datetime.now(timezone.utc)
            elapsed = time.monotonic() - started

            for sym, st in self._states.items():
                window = window_from_utc_5m(now, sym)
                base = mock_base_price(sym)
                if last_t0.get(sym) != window.t0_utc.timestamp():
                    st.s0 = base * (1.0 + rng.gauss(0, 0.0005))
                    last_t0[sym] = window.t0_utc.timestamp()
                s0 = st.s0 or base
                phase = hash(sym) % 100
                s_t = s0 * (
                    1.0
                    + 0.0003 * math.sin((elapsed + phase) / 30.0)
                    + 0.0001 * math.cos((elapsed + phase) / 7.0)
                )
                st.closes.append(s_t)
                if len(st.closes) > 200:
                    st.closes = st.closes[-200:]
                sigma = max(
                    sigma_ann_from_closes(st.closes, span=60),
                    self.cfg.sigma_floor_ann,
                )
                tau = tau_sec(now, window)
                p_star = p_up_gbm(s=s_t, s0=s0, tau_sec=tau, sigma_ann=sigma)
                p_mid, p_micro, bid, ask = self._mock_pm_quotes(st, p_star)
                row = self._build_row(
                    symbol=sym,
                    window=window,
                    s0=s0,
                    s_t=s_t,
                    sigma=sigma,
                    tau=tau,
                    p_star=p_star,
                    p_mid=p_mid,
                    p_micro=p_micro,
                    bid=bid,
                    ask=ask,
                    pm_mock=True,
                    pm_connected=False,
                    b_event_iso=utc_now_iso(),
                    b_recv_iso=utc_now_iso(),
                    pm_recv_iso=utc_now_iso(),
                )
                self._write_row(row, now)
                st.ticks += 1

            self._ticks += len(self.symbols)
            self._last_tick_mono = time.monotonic()
            self._write_health("ok", binance_connected=False, pm_connected=False)
            await asyncio.sleep(self.interval_ms / 1000.0)
        self._write_health("down")

    async def _tick_all(self) -> None:
        now = datetime.now(timezone.utc)
        any_written = False
        pm_any = False

        for sym, st in self._states.items():
            b = self._binance.latest(sym)
            if b is None:
                continue
            row = await self._tick_symbol(sym, st, b, now)
            if row:
                self._write_row(row, now)
                st.ticks += 1
                any_written = True
                if row.get("pm_connected"):
                    pm_any = True

        if not any_written:
            self._write_health("degraded")
            return

        self._ticks += len([s for s in self.symbols if self._binance.latest(s)])
        self._last_tick_mono = time.monotonic()
        self._write_health(
            "ok",
            binance_connected=self._binance.connected,
            pm_connected=pm_any,
        )

    async def _tick_symbol(
        self, sym: str, st: SymbolState, b: BinanceTick, now: datetime
    ) -> dict | None:
        window = window_from_utc_5m(now, sym)
        if st.window is None or window.t0_utc != st.window.t0_utc:
            st.window = window
            st.s0 = b.mid

        s0 = st.s0 or b.mid
        s_t = b.mid
        st.closes.append(s_t)
        if len(st.closes) > 500:
            st.closes = st.closes[-500:]
        sigma = max(
            sigma_ann_from_closes(st.closes, span=60),
            self.cfg.sigma_floor_ann,
        )
        tau = tau_sec(now, window)
        p_star = p_up_gbm(s=s_t, s0=s0, tau_sec=tau, sigma_ann=sigma)

        if st.pm_mock or self.mock_pm_global:
            p_mid, p_micro, bid, ask = self._mock_pm_quotes(st, p_star)
            pm_recv = utc_now_iso()
            pm_connected = False
            pm_mock = True
        else:
            assert st.pm_feed is not None
            q = st.pm_feed.latest
            if q is None:
                return None
            p_mid, p_micro, bid, ask = q.p_mid, q.p_micro, q.yes_bid, q.yes_ask
            pm_recv = q.recv_time_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            pm_connected = st.pm_feed.connected
            pm_mock = False

        event_iso = (
            datetime.fromtimestamp(b.event_time_ms / 1000.0, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            )[:-3]
            + "Z"
            if b.event_time_ms
            else utc_now_iso()
        )
        return self._build_row(
            symbol=sym,
            window=window,
            s0=s0,
            s_t=s_t,
            sigma=sigma,
            tau=tau,
            p_star=p_star,
            p_mid=p_mid,
            p_micro=p_micro,
            bid=bid,
            ask=ask,
            pm_mock=pm_mock,
            pm_connected=pm_connected,
            b_event_iso=event_iso,
            b_recv_iso=b.recv_time_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            pm_recv_iso=pm_recv,
        )

    def _build_row(
        self,
        *,
        symbol: str,
        window: Window,
        s0: float,
        s_t: float,
        sigma: float,
        tau: float,
        p_star: float,
        p_mid: float,
        p_micro: float,
        bid: float,
        ask: float,
        pm_mock: bool,
        pm_connected: bool,
        b_event_iso: str,
        b_recv_iso: str,
        pm_recv_iso: str,
    ) -> dict:
        return {
            "ts_utc": utc_now_iso(),
            "symbol": symbol,
            "ts_binance_event": b_event_iso,
            "ts_recv": b_recv_iso,
            "ts_pm_recv": pm_recv_iso,
            "window_id": window.window_id,
            "tau_sec": round(tau, 3),
            "s0": round(s0, 6),
            "s_t": round(s_t, 6),
            "sigma_ann": round(sigma, 4),
            "p_star": round(p_star, 4),
            "p_mkt_mid": round(p_mid, 4),
            "p_mkt_micro": round(p_micro, 4),
            "yes_bid": round(bid, 4),
            "yes_ask": round(ask, 4),
            "gap_level": round(p_mid - p_star, 4),
            "i_bin": 0.0,
            "i_pm": 0.0,
            "gap_flow": 0.0,
            "spread_pm": round(ask - bid, 4),
            "outcome_pending": True,
            "mock_pm": pm_mock,
            "pm_connected": pm_connected,
        }

    def _write_row(self, row: dict, now: datetime) -> None:
        out_path = resolve_log_path(self.out_template, now)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def _mock_pm_quotes(
        self, st: SymbolState, p_star: float
    ) -> tuple[float, float, float, float]:
        rng = random.Random(self._rng_seed + st.ticks + hash(st.symbol))
        alpha = 0.15
        st.lag_state["p"] = st.lag_state.get("p", 0.5) + alpha * (
            p_star - st.lag_state.get("p", 0.5)
        )
        st.lag_state["p"] += rng.gauss(0, 0.002)
        st.lag_state["p"] = max(0.02, min(0.98, st.lag_state["p"]))
        p_mid = st.lag_state["p"]
        spread = 0.02
        bid = max(0.01, p_mid - spread / 2)
        ask = min(0.99, p_mid + spread / 2)
        from pm_spot_fair.pm_book import microprice

        p_micro = microprice(bid, ask, 10.0, 8.0)
        return p_mid, p_micro, bid, ask

    def _write_health(
        self,
        status: str,
        *,
        binance_connected: bool | None = None,
        pm_connected: bool | None = None,
    ) -> None:
        gap = time.monotonic() - self._last_tick_mono if self._ticks else None
        pm_syms = [
            s
            for s, st in self._states.items()
            if st.pm_feed and st.pm_feed.connected and not st.pm_mock
        ]
        health = LoggerHealth(
            status=status,
            ticks_written=self._ticks,
            last_tick_utc=utc_iso() if self._ticks else None,
            binance_connected=binance_connected
            if binance_connected is not None
            else self._binance.connected,
            pm_connected=pm_connected if pm_connected is not None else bool(pm_syms),
            mock_pm=self._mock_feeds,
            feed_gap_sec=round(gap, 3) if gap is not None else None,
            pid=os.getpid(),
            symbols=self.symbols,
            ticks_by_symbol={s: st.ticks for s, st in self._states.items()},
            pm_connected_symbols=pm_syms,
        )
        write_health(self.health_path, health)
