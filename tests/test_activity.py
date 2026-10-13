from __future__ import annotations

import math
import time
from datetime import datetime, timezone

import pytest

from polymarket_copier.utils.activity import (
    parse_activity_timestamp,
    activity_id,
    activity_market_id,
    activity_notional_usdc,
    activity_side,
    activity_token_id,
    is_trade_activity,
)


def test_activity_helpers_normalize_current_activity_shape():
    raw = {
        "transactionHash": "0xabc",
        "conditionId": "cond-1",
        "tokenId": "tok-1",
        "type": "buy",
        "size": "100",
        "usdcSize": "50",
    }

    assert activity_id(raw) == "0xabc"
    assert activity_market_id(raw) == "cond-1"
    assert activity_token_id(raw) == "tok-1"
    assert activity_side(raw) == "BUY"
    assert activity_notional_usdc(raw) == pytest.approx(50.0)
    assert is_trade_activity(raw)


def test_activity_helpers_keep_legacy_shape():
    raw = {
        "id": "t1",
        "market": "m",
        "asset": "a",
        "type": "trade",
        "side": "SELL",
        "size": "10",
        "price": "0.50",
    }

    assert activity_id(raw) == "t1"
    assert activity_market_id(raw) == "m"
    assert activity_token_id(raw) == "a"
    assert activity_side(raw) == "SELL"
    assert activity_notional_usdc(raw) == pytest.approx(5.0)
    assert is_trade_activity(raw)


def test_activity_helpers_fail_closed_when_notional_cannot_be_derived():
    raw = {"id": "t2", "market": "m", "asset": "a", "type": "trade", "side": "BUY", "size": "10"}

    assert activity_notional_usdc(raw) == pytest.approx(0.0)


class TestParseActivityTimestamp:
    """Guards the shared timestamp helper both the monitor and the tracker now route
    through (Ponytail audit P1). Each caller keeps its own failure policy, so the
    helper must raise on a malformed string rather than pick a fallback itself."""

    def test_naive_iso_is_utc_not_host_local(self, monkeypatch):
        """An offset-less string is venue UTC; reading it as host-local skews staleness."""
        if not hasattr(time, "tzset"):
            pytest.skip("time.tzset() is unavailable on this platform")
        monkeypatch.setenv("TZ", "America/New_York")
        time.tzset()
        try:
            expected = datetime(2026, 7, 21, 1, 44, 14, tzinfo=timezone.utc).timestamp()
            assert parse_activity_timestamp("2026-07-21T01:44:14") == pytest.approx(expected)
            assert parse_activity_timestamp("2026-07-21T01:44:14Z") == pytest.approx(expected)
        finally:
            monkeypatch.undo()
            time.tzset()

    def test_explicit_offset_is_honoured(self):
        expected = datetime(2026, 7, 20, 23, 44, 14, tzinfo=timezone.utc).timestamp()
        assert parse_activity_timestamp("2026-07-21T01:44:14+02:00") == pytest.approx(expected)

    def test_milliseconds_are_detected_above_1e12(self):
        assert parse_activity_timestamp(1_700_000_000_000) == pytest.approx(1_700_000_000)
        assert parse_activity_timestamp(1_700_000_000) == pytest.approx(1_700_000_000)

    def test_malformed_string_raises_so_callers_choose_the_fallback(self):
        with pytest.raises(ValueError, match="isoformat"):
            parse_activity_timestamp("garbage")
        with pytest.raises(ValueError, match="isoformat"):
            parse_activity_timestamp("")

    def test_unsupported_type_returns_none(self):
        assert parse_activity_timestamp(None) is None
        assert parse_activity_timestamp([1]) is None

    def test_non_finite_number_passes_through_for_the_caller_to_reject(self):
        assert math.isnan(parse_activity_timestamp(float("nan")))
        assert parse_activity_timestamp(float("inf")) == float("inf")
