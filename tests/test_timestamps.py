"""Regression tests: offset-less ISO 8601 timestamps are venue UTC, not host-local time.

Guards the fix for naive-datetime .timestamp() calls being interpreted in the
server's local timezone, which skewed monitor wall_age (stale-trade gate) and
tracker recency by the host's UTC offset on non-UTC hosts.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from polymarket_copier.core.monitor import _parse_trade_event
from polymarket_copier.core.tracker import _parse_timestamp

_NAIVE_ISO = "2026-07-21T01:44:14"
_EXPECTED_UTC = datetime(2026, 7, 21, 1, 44, 14, tzinfo=timezone.utc).timestamp()


@pytest.fixture
def non_utc_host(monkeypatch):
    """Force the host timezone to US Eastern so a local-time misread is visible."""
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset() is unavailable on this platform")
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def _raw_trade(ts: str) -> dict:
    return {
        "id": "evt-1",
        "market": "0xmarket",
        "asset": "0xtoken",
        "side": "BUY",
        "price": 0.5,
        "usdcSize": 25.0,
        "timestamp": ts,
        "transactionHash": "0xhash",
    }


class TestMonitorTradeEventTimestamp:
    def test_naive_iso_parsed_as_utc_not_local(self, non_utc_host):
        """Fails on main under TZ=America/New_York: naive .timestamp() reads host-local."""
        event = _parse_trade_event("0xwallet", _raw_trade(_NAIVE_ISO))
        assert event is not None
        assert event.timestamp == pytest.approx(_EXPECTED_UTC)

    def test_z_suffix_unaffected(self, non_utc_host):
        """An explicit Z suffix was already timezone-aware before the fix."""
        event = _parse_trade_event("0xwallet", _raw_trade(_NAIVE_ISO + "Z"))
        assert event is not None
        assert event.timestamp == pytest.approx(_EXPECTED_UTC)


class TestTrackerParseTimestamp:
    def test_naive_iso_parsed_as_utc_not_local(self, non_utc_host):
        """Fails on main under TZ=America/New_York: naive .timestamp() reads host-local."""
        assert _parse_timestamp(_NAIVE_ISO) == pytest.approx(_EXPECTED_UTC)

    def test_garbage_still_returns_zero(self):
        """L4: unparseable input must keep returning 0.0 (unknown = stale)."""
        assert _parse_timestamp("not-a-date") == 0.0
