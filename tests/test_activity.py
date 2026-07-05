from __future__ import annotations

import pytest

from polymarket_copier.utils.activity import (
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
    raw = {"id": "t1", "market": "m", "asset": "a", "type": "trade", "side": "SELL", "size": "10"}

    assert activity_id(raw) == "t1"
    assert activity_market_id(raw) == "m"
    assert activity_token_id(raw) == "a"
    assert activity_side(raw) == "SELL"
    assert activity_notional_usdc(raw) == pytest.approx(10.0)
    assert is_trade_activity(raw)
