"""PM CLOB WebSocket message parsing."""

from __future__ import annotations

import json

from pm_spot_fair.feeds.pm_clob import PMClobFeed

TOKEN = "2812587729933607053641537041655921728711203069492741544948716980558018894310"
OTHER = "87205421823799435882516434693589315512030269151757526327832539037380917468514"


def test_ws_initial_book_list() -> None:
    feed = PMClobFeed(TOKEN, use_websocket=False)
    feed._on_ws_message(
        json.dumps(
            [
                {
                    "event_type": "book",
                    "asset_id": TOKEN,
                    "bids": [{"price": "0.48", "size": "10"}],
                    "asks": [{"price": "0.52", "size": "8"}],
                }
            ]
        )
    )
    assert feed.latest is not None
    assert feed.latest.yes_bid == 0.48
    assert feed.latest.yes_ask == 0.52


def test_ws_price_change_filters_asset() -> None:
    feed = PMClobFeed(TOKEN, use_websocket=False)
    feed._on_ws_message(
        json.dumps(
            {
                "event_type": "price_change",
                "price_changes": [
                    {
                        "asset_id": OTHER,
                        "best_bid": "0.99",
                        "best_ask": "1",
                    },
                    {
                        "asset_id": TOKEN,
                        "best_bid": "0.47",
                        "best_ask": "0.51",
                    },
                ],
            }
        )
    )
    assert feed.latest is not None
    assert feed.latest.yes_bid == 0.47
    assert feed.latest.yes_ask == 0.51


def test_ws_best_bid_ask() -> None:
    feed = PMClobFeed(TOKEN, use_websocket=False)
    feed._on_ws_message(
        json.dumps(
            {
                "event_type": "best_bid_ask",
                "asset_id": TOKEN,
                "best_bid": "0.44",
                "best_ask": "0.46",
            }
        )
    )
    assert feed.latest is not None
    assert feed.latest.p_mid == 0.45
