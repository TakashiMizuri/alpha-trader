"""Polymarket CLOB read-only quotes (REST poll + optional WS)."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import websockets

from pm_spot_fair.pm_book import mid_price, microprice

logger = logging.getLogger(__name__)

CLOB_API = "https://clob.polymarket.com"
PM_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


@dataclass(frozen=True)
class PMQuote:
    yes_bid: float
    yes_ask: float
    p_mid: float
    p_micro: float
    recv_time_utc: datetime
    mock: bool = False


class PMClobFeed:
    """Top-of-book for YES token; poll REST or stream WS."""

    def __init__(
        self,
        yes_token_id: str,
        *,
        poll_interval_sec: float = 0.5,
        use_websocket: bool = True,
    ) -> None:
        self.yes_token_id = yes_token_id
        self._poll_interval = poll_interval_sec
        self._use_ws = use_websocket
        self._latest: PMQuote | None = None
        self._connected = False
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def latest(self) -> PMQuote | None:
        return self._latest

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._client = httpx.AsyncClient(timeout=10.0)
        if self._use_ws:
            self._task = asyncio.create_task(self._run_ws(), name="pm-clob-ws")
        else:
            self._task = asyncio.create_task(self._run_poll(), name="pm-clob-poll")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._client:
            await self._client.aclose()
            self._client = None
        self._connected = False

    def _set_quote(
        self, bid: float, ask: float, bid_sz: float = 1.0, ask_sz: float = 1.0
    ) -> None:
        if bid <= 0 and ask <= 0:
            return
        if bid <= 0:
            bid = max(0.01, ask - 0.02)
        if ask <= 0:
            ask = min(0.99, bid + 0.02)
        p_mid = mid_price(bid, ask)
        p_micro = microprice(bid, ask, bid_sz, ask_sz)
        self._latest = PMQuote(
            yes_bid=bid,
            yes_ask=ask,
            p_mid=p_mid,
            p_micro=p_micro,
            recv_time_utc=datetime.now(timezone.utc),
        )

    async def _fetch_book_rest(self) -> None:
        assert self._client is not None
        r = await self._client.get(
            f"{CLOB_API}/book",
            params={"token_id": self.yes_token_id},
        )
        r.raise_for_status()
        book = r.json()
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        best_bid = float(bids[0]["price"]) if bids else 0.0
        best_ask = float(asks[0]["price"]) if asks else 0.0
        bid_sz = float(bids[0].get("size", 1)) if bids else 1.0
        ask_sz = float(asks[0].get("size", 1)) if asks else 1.0
        self._set_quote(best_bid, best_ask, bid_sz, ask_sz)

    async def _run_poll(self) -> None:
        assert self._client is not None
        self._connected = True
        while not self._stop.is_set():
            try:
                await self._fetch_book_rest()
            except Exception:
                logger.exception("PM REST book poll failed")
                self._connected = False
            await asyncio.sleep(self._poll_interval)

    async def _run_ws(self) -> None:
        delay = 3.0
        while not self._stop.is_set():
            try:
                await self._connect_ws_once()
                delay = 3.0
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("PM WS error; reconnect in %.1fs", delay)
                self._connected = False
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60.0)

    async def _connect_ws_once(self) -> None:
        logger.info("Connecting PM CLOB WS")
        if self._client is not None:
            try:
                await self._fetch_book_rest()
            except Exception:
                logger.warning("PM REST bootstrap before WS failed", exc_info=True)
        async with websockets.connect(
            PM_WS_URL,
            ping_interval=None,
            close_timeout=5,
        ) as ws:
            sub = {
                "assets_ids": [self.yes_token_id],
                "type": "market",
                "custom_feature_enabled": True,
            }
            await ws.send(json.dumps(sub))
            self._connected = True
            ping_task = asyncio.create_task(self._ping_loop(ws))
            try:
                while not self._stop.is_set():
                    raw = await asyncio.wait_for(ws.recv(), timeout=90.0)
                    if raw == "PONG":
                        continue
                    self._on_ws_message(raw)
            finally:
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass

    async def _ping_loop(self, ws) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(10.0)
            await ws.send("PING")

    def _on_ws_message(self, raw: str | bytes) -> None:
        payload = json.loads(raw)
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    self._apply_market_event(item)
            return
        if isinstance(payload, dict):
            self._apply_market_event(payload)

    def _apply_market_event(self, data: dict) -> None:
        asset_id = data.get("asset_id")
        if asset_id is not None and str(asset_id) != str(self.yes_token_id):
            return

        event = data.get("event_type") or data.get("type")
        if event == "best_bid_ask":
            self._set_quote(
                float(data.get("best_bid", 0)),
                float(data.get("best_ask", 0)),
            )
            return
        if event == "book":
            self._apply_book_levels(data.get("bids") or [], data.get("asks") or [])
            return
        if event == "price_change":
            for pc in data.get("price_changes") or []:
                if str(pc.get("asset_id", "")) != str(self.yes_token_id):
                    continue
                self._set_quote(
                    float(pc.get("best_bid", 0)),
                    float(pc.get("best_ask", 0)),
                )
            return

    def _apply_book_levels(self, bids: list, asks: list) -> None:
        if not bids and not asks:
            return
        bid = float(bids[0]["price"]) if bids else 0.0
        ask = float(asks[0]["price"]) if asks else 0.0
        bid_sz = float(bids[0].get("size", 1)) if bids else 1.0
        ask_sz = float(asks[0].get("size", 1)) if asks else 1.0
        self._set_quote(bid, ask, bid_sz, ask_sz)
