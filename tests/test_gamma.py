"""Gamma API slug resolution (mocked)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pm_spot_fair.feeds.gamma import resolve_market_by_slug


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
