"""Gamma API slug resolution (mocked)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from datetime import datetime, timezone

from pm_spot_fair.feeds.gamma import effective_pm_slug, resolve_market_by_slug


@pytest.mark.asyncio
async def test_resolve_market_by_slug():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = [
        {
            "slug": "test-market",
            "conditionId": "0xabc",
            "clobTokenIds": '["111","222"]',
        }
    ]

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        import httpx

        async with httpx.AsyncClient() as client:
            t = await resolve_market_by_slug(client, "test-market")

    assert t.yes_token_id == "111"
    assert t.no_token_id == "222"


def test_effective_pm_slug_adds_bucket() -> None:
    from pm_spot_fair.feeds.gamma import five_min_interval_unix

    now = datetime(2026, 6, 3, 16, 30, 0, tzinfo=timezone.utc)
    assert (
        effective_pm_slug("btc-updown-5m", now)
        == f"btc-updown-5m-{five_min_interval_unix(now)}"
    )


def test_effective_pm_slug_passes_through_bucketed() -> None:
    assert effective_pm_slug("btc-updown-5m-1780493400") == "btc-updown-5m-1780493400"
