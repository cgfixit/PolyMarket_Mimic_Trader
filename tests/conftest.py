"""Shared test fixtures for the Polymarket copy trading bot v2."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_leaderboard_entry() -> dict:
    return {
        "name": "0xaaa111",
        "pseudonym": "WhaleOne",
        "pnl": 50000,
        "tradesCount": 200,
    }


@pytest.fixture
def sample_activity() -> list[dict]:
    """A round-trip BUY then SELL on the same market/token (a winning trade)."""
    return [
        {
            "id": "t1",
            "type": "trade",
            "side": "BUY",
            "market": "mkt-a",
            "asset": "tok-a",
            "price": "0.50",
            "size": "100",
            "timestamp": 1_700_000_000,
        },
        {
            "id": "t2",
            "type": "trade",
            "side": "SELL",
            "market": "mkt-a",
            "asset": "tok-a",
            "price": "0.65",
            "size": "65",
            "timestamp": 1_700_001_000,
        },
    ]


class FakeResp:
    """aiohttp response stand-in for ``async with session.get(...) as resp``.

    ``enter_exc`` is raised on entering the context, mimicking a request that
    fails after ``get()`` returns (connection error, timeout).
    """

    def __init__(self, data=None, *, status=200, reason="OK", enter_exc: Exception | None = None):
        self._data = data
        self.status = status
        self.reason = reason
        self._enter_exc = enter_exc

    async def __aenter__(self):
        if self._enter_exc:
            raise self._enter_exc
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        return None

    async def json(self):
        return self._data


class FakeSession:
    """Minimal aiohttp.ClientSession stand-in: every ``get()`` returns the same canned response.

    Shared by the API, monitor, chaos, integration and main tests (Ponytail audit P2).
    ``get_exc`` raises from ``get()`` itself; ``enter_exc`` raises on entering the
    response context. Requested URLs are recorded in ``urls``.
    """

    def __init__(
        self,
        data=None,
        *,
        status=200,
        reason="OK",
        get_exc: Exception | None = None,
        enter_exc: Exception | None = None,
    ):
        self._data = data
        self._status = status
        self._reason = reason
        self._get_exc = get_exc
        self._enter_exc = enter_exc
        self.urls: list[str] = []

    def get(self, url, params=None):
        self.urls.append(url)
        if self._get_exc:
            raise self._get_exc
        return FakeResp(self._data, status=self._status, reason=self._reason, enter_exc=self._enter_exc)
