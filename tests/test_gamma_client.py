"""Tests for the v2 Gamma API client (returns typed Market objects)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from polymarket_copier.api.gamma_client import GammaClient, _parse_fee_rate, _parse_market, _parse_resolve_time
from polymarket_copier.models.types import Market


class _FakeResp:
    def __init__(self, data):
        self._data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        return None

    async def json(self):
        return self._data


class _FakeSession:
    """Minimal aiohttp.ClientSession stand-in for get_market_price's session.get."""

    def __init__(self, data, exc=None):
        self._data = data
        self._exc = exc

    def get(self, url, params=None):
        if self._exc:
            raise self._exc
        return _FakeResp(self._data)


@pytest.fixture
def gamma_client():
    return GammaClient(base_url="https://gamma-api.polymarket.com")


class TestGammaClient:
    @pytest.mark.asyncio
    async def test_get_active_markets(self, gamma_client):
        mock_data = [
            {"condition_id": "c1", "question": "Will X happen?", "active": True},
        ]
        with patch.object(gamma_client, "_get", new_callable=AsyncMock, return_value=mock_data):
            result = await gamma_client.get_active_markets()
            assert len(result) == 1
            assert isinstance(result[0], Market)
            assert result[0].condition_id == "c1"

    @pytest.mark.asyncio
    async def test_get_market_returns_typed(self, gamma_client):
        mock_data = {"condition_id": "c1", "question": "Q?", "volume24hr": 12000}
        with patch.object(gamma_client, "_get", new_callable=AsyncMock, return_value=mock_data):
            result = await gamma_client.get_market("c1")
            assert isinstance(result, Market)
            assert result.volume_24h == 12000

    @pytest.mark.asyncio
    async def test_get_market_error_returns_none(self, gamma_client):
        with patch.object(gamma_client, "_get", new_callable=AsyncMock, side_effect=Exception("boom")):
            result = await gamma_client.get_market("c1")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_market_price_midpoint(self, gamma_client):
        # get_market_price hits the CLOB /midpoint endpoint via session.get.
        session = _FakeSession({"mid": "0.72"})
        with patch.object(gamma_client, "_get_session", new_callable=AsyncMock, return_value=session):
            price = await gamma_client.get_market_price("token-1")
            assert price == pytest.approx(0.72)

    @pytest.mark.asyncio
    async def test_get_market_price_error(self, gamma_client):
        session = _FakeSession(None, exc=Exception("timeout"))
        with patch.object(gamma_client, "_get_session", new_callable=AsyncMock, return_value=session):
            price = await gamma_client.get_market_price("token-1")
            assert price is None

    @pytest.mark.asyncio
    async def test_get_market_fee_rate_from_clob_info(self, gamma_client):
        session = _FakeSession({"fd": {"r": 0.05, "e": 2, "to": True}})
        with patch.object(gamma_client, "_get_session", new_callable=AsyncMock, return_value=session):
            fee_rate = await gamma_client.get_market_fee_rate("condition-1")
            assert fee_rate == pytest.approx(0.05)


class TestParseResolveTime:
    def test_iso_string(self):
        raw = {"endDate": "2026-12-31T00:00:00Z"}
        result = _parse_resolve_time(raw)
        assert result is not None
        assert result.year == 2026

    def test_unix_millis(self):
        ts_millis = 1_800_000_000_000
        raw = {"resolutionTime": ts_millis}
        result = _parse_resolve_time(raw)
        assert result is not None
        assert result.tzinfo is not None

    def test_unix_seconds(self):
        raw = {"endDate": 1_800_000_000}
        result = _parse_resolve_time(raw)
        assert result is not None

    def test_missing_returns_none(self):
        assert _parse_resolve_time({}) is None

    def test_invalid_returns_none(self):
        assert _parse_resolve_time({"endDate": "not-a-date"}) is None


class TestParseMarket:
    def test_extracts_tokens(self):
        raw = {
            "condition_id": "c1",
            "question": "Will it rain?",
            "tokens": [
                {"outcome": "Yes", "token_id": "yes-tok"},
                {"outcome": "No", "token_id": "no-tok"},
            ],
            "volume24hr": 5000,
            "active": "true",
            "closed": "false",
            "archived": False,
            "restricted": False,
            "acceptingOrders": True,
            "enableOrderBook": True,
        }
        market = _parse_market(raw)
        assert market.token_id_yes == "yes-tok"
        assert market.token_id_no == "no-tok"
        assert market.volume_24h == 5000
        assert market.active is True
        assert market.closed is False
        assert market.accepting_orders is True
        assert market.enable_order_book is True
        assert market.fees_enabled is False

    def test_handles_missing_volume(self):
        market = _parse_market({"condition_id": "c1"})
        assert market.volume_24h == 0.0

    def test_extracts_fee_metadata(self):
        market = _parse_market({"condition_id": "c1", "feesEnabled": True, "feeRate": "0.07"})
        assert market.fees_enabled is True
        assert market.fee_rate == pytest.approx(0.07)


class TestParseFeeRate:
    def test_nested_fd_decimal_rate(self):
        assert _parse_fee_rate({"fd": {"r": 0.04}}) == pytest.approx(0.04)

    def test_basis_points_rate(self):
        assert _parse_fee_rate({"base_fee": 30}) == pytest.approx(0.003)

    def test_invalid_rate_returns_none(self):
        assert _parse_fee_rate({"fd": {"r": "bad"}}) is None
        assert _parse_fee_rate({"fd": {"r": 1.0}}) is None
