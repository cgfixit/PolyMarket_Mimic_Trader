"""Tests for the v2 Gamma API client (returns typed Market objects)."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from polymarket_copier.api.gamma_client import GammaClient, _parse_fee_rate, _parse_market, _parse_resolve_time
from polymarket_copier.models.types import Market
from tests.conftest import FakeSession


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
        session = FakeSession({"mid": "0.72"})
        with patch.object(gamma_client, "_get_session", new_callable=AsyncMock, return_value=session):
            price = await gamma_client.get_market_price("token-1")
            assert price == pytest.approx(0.72)

    @pytest.mark.asyncio
    async def test_get_market_price_error(self, gamma_client):
        # A valid payload, so only the raised exception can make this return None.
        session = FakeSession({"mid": "0.72"}, get_exc=Exception("timeout"))
        with patch.object(gamma_client, "_get_session", new_callable=AsyncMock, return_value=session):
            price = await gamma_client.get_market_price("token-1")
            assert price is None

    @pytest.mark.asyncio
    async def test_get_market_fee_rate_from_clob_info(self, gamma_client):
        session = FakeSession({"fd": {"r": 0.05, "e": 2, "to": True}})
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

    @pytest.mark.parametrize("raw_volume", ["nan", "inf", "-inf", -1, "invalid"])
    def test_invalid_volume_fails_closed(self, raw_volume):
        market = _parse_market({"condition_id": "c1", "volume24hr": raw_volume})
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


class TestResolveTimeIsUtc:
    """Regression: an offset-less Gamma ``endDate`` is venue UTC, not host-local time.

    ``_parse_resolve_time`` used to return a naive datetime for it, and the copier's
    ``resolve_time.timestamp()`` then read it in the host's timezone. On a US Eastern
    host that pushed the resolution blackout four hours late, so the entry skip and
    the MARKET_RESOLVING exit both fired late. Every resolve time must be aware UTC.
    """

    @pytest.fixture
    def eastern_host(self, monkeypatch):
        if not hasattr(time, "tzset"):
            pytest.skip("time.tzset() is unavailable on this platform")
        monkeypatch.setenv("TZ", "America/New_York")
        time.tzset()
        yield
        monkeypatch.undo()
        time.tzset()

    def test_naive_end_date_is_utc_not_host_local(self, eastern_host):
        expected = datetime(2026, 7, 21, 1, 44, 14, tzinfo=timezone.utc).timestamp()
        result = _parse_resolve_time({"endDate": "2026-07-21T01:44:14"})
        assert result is not None
        assert result.tzinfo is not None
        assert result.timestamp() == pytest.approx(expected)

    def test_date_only_end_date_is_utc_midnight(self, eastern_host):
        expected = datetime(2026, 7, 21, tzinfo=timezone.utc).timestamp()
        result = _parse_resolve_time({"endDate": "2026-07-21"})
        assert result is not None
        assert result.timestamp() == pytest.approx(expected)

    def test_hours_to_resolve_matches_the_venue_clock(self, eastern_host):
        """The copier's blackout arithmetic sees the true distance to resolution."""
        now = time.time()
        venue_naive = datetime.fromtimestamp(now + 21 * 3600, tz=timezone.utc).replace(tzinfo=None)
        market = _parse_market({"conditionId": "c", "endDate": venue_naive.isoformat(timespec="seconds")})
        hours_to_resolve = (market.resolve_time.timestamp() - now) / 3600
        assert hours_to_resolve == pytest.approx(21.0, abs=0.01)
        assert 0 < hours_to_resolve < 24  # inside the default 24h blackout

    def test_explicit_offset_keeps_its_instant(self):
        expected = datetime(2026, 7, 20, 23, 44, 14, tzinfo=timezone.utc).timestamp()
        result = _parse_resolve_time({"endDate": "2026-07-21T01:44:14+02:00"})
        assert result is not None
        assert result.timestamp() == pytest.approx(expected)
