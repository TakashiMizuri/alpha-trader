"""Binance spot bookTicker WebSocket feed (single + combined stream)."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import websockets

logger = logging.getLogger(__name__)

BINANCE_WS_BASE = "wss://stream.binance.com:9443/ws"
BINANCE_STREAM_BASE = "wss://stream.binance.com:9443/stream"


@dataclass(frozen=True)
class BinanceTick:
    symbol: str
    bid: float
    ask: float
    mid: float
    event_time_ms: int
    recv_time_utc: datetime


class BinanceBookTickerFeed:
    """Single-symbol bookTicker stream."""

    def __init__(
        self,
        symbol: str,
        *,
        reconnect_delay_sec: float = 3.0,
        max_reconnect_delay_sec: float = 60.0,
    ) -> None:
        self.symbol = symbol.upper()
        self._stream = f"{self.symbol.lower()}@bookTicker"
        self._url = f"{BINANCE_WS_BASE}/{self._stream}"
        self._reconnect_delay = reconnect_delay_sec
        self._max_reconnect_delay = max_reconnect_delay_sec
        self._latest: BinanceTick | None = None
        self._connected = False
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def latest(self) -> BinanceTick | None:
        return self._latest

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name=f"binance-{self.symbol}")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._connected = False

    async def _run(self) -> None:
        delay = self._reconnect_delay
        while not self._stop.is_set():
            try:
                await self._connect_once()
                delay = self._reconnect_delay
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Binance WS error; reconnecting in %.1fs", delay)
                self._connected = False
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._max_reconnect_delay)

    async def _connect_once(self) -> None:
        logger.info("Connecting Binance WS %s", self._url)
        async with websockets.connect(
            self._url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        ) as ws:
            self._connected = True
            logger.info("Binance WS connected (%s)", self.symbol)
            while not self._stop.is_set():
                raw = await asyncio.wait_for(ws.recv(), timeout=90.0)
                self._on_message(raw)

    def _on_message(self, raw: str | bytes) -> None:
        data = json.loads(raw)
        self._latest = _tick_from_payload(data, self.symbol)


class BinanceMultiBookTickerFeed:
    """Combined stream for multiple symbols (one WS connection)."""

    def __init__(
        self,
        symbols: list[str],
        *,
        reconnect_delay_sec: float = 3.0,
        max_reconnect_delay_sec: float = 60.0,
    ) -> None:
        self.symbols = [s.upper() for s in symbols]
        streams = "/".join(f"{s.lower()}@bookTicker" for s in self.symbols)
        self._url = f"{BINANCE_STREAM_BASE}?streams={streams}"
        self._reconnect_delay = reconnect_delay_sec
        self._max_reconnect_delay = max_reconnect_delay_sec
        self._latest: dict[str, BinanceTick] = {}
        self._connected = False
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    def latest(self, symbol: str) -> BinanceTick | None:
        return self._latest.get(symbol.upper())

    def all_latest(self) -> dict[str, BinanceTick]:
        return dict(self._latest)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(
            self._run(), name=f"binance-multi-{len(self.symbols)}"
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._connected = False

    async def _run(self) -> None:
        delay = self._reconnect_delay
        while not self._stop.is_set():
            try:
                await self._connect_once()
                delay = self._reconnect_delay
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Binance multi WS error; reconnecting in %.1fs", delay
                )
                self._connected = False
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._max_reconnect_delay)

    async def _connect_once(self) -> None:
        logger.info(
            "Connecting Binance combined WS (%d symbols)", len(self.symbols)
        )
        async with websockets.connect(
            self._url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        ) as ws:
            self._connected = True
            logger.info("Binance multi WS connected: %s", ", ".join(self.symbols))
            while not self._stop.is_set():
                raw = await asyncio.wait_for(ws.recv(), timeout=90.0)
                self._on_message(raw)

    def _on_message(self, raw: str | bytes) -> None:
        wrapper = json.loads(raw)
        if "stream" in wrapper and "data" in wrapper:
            stream: str = wrapper["stream"]
            sym = stream.split("@")[0].upper()
            self._latest[sym] = _tick_from_payload(wrapper["data"], sym)
        else:
            sym = str(wrapper.get("s", "")).upper()
            if sym:
                self._latest[sym] = _tick_from_payload(wrapper, sym)


def _tick_from_payload(data: dict, symbol: str) -> BinanceTick:
    bid = float(data["b"])
    ask = float(data["a"])
    sym = str(data.get("s") or symbol).upper()
    event_ms = int(data.get("E") or data.get("u") or 0)
    recv = datetime.now(timezone.utc)
    return BinanceTick(
        symbol=sym,
        bid=bid,
        ask=ask,
        mid=0.5 * (bid + ask),
        event_time_ms=event_ms,
        recv_time_utc=recv,
    )
