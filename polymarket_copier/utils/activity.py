"""Helpers for Polymarket Data API activity records."""

from __future__ import annotations

import math
from datetime import datetime, timezone


def _float_or_none(value) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def activity_side(raw: dict) -> str:
    """Return BUY/SELL from either explicit side or buy/sell activity type."""
    side = str(raw.get("side", "")).strip().upper()
    if side in {"BUY", "SELL"}:
        return side

    item_type = str(raw.get("type", "")).strip().upper()
    if item_type in {"BUY", "SELL"}:
        return item_type

    return ""


def activity_type(raw: dict) -> str:
    """Return the normalized activity type."""
    return str(raw.get("type", "")).strip().lower()


def is_trade_activity(raw: dict) -> bool:
    """Return True for Data API activity rows that represent trades."""
    return activity_type(raw) in {"trade", "buy", "sell"}


def activity_id(raw: dict) -> str:
    """Return the stable activity id from current or legacy fields."""
    return str(raw.get("id") or raw.get("transactionHash", ""))


def activity_market_id(raw: dict) -> str:
    """Return the market/condition id from current or legacy fields."""
    return str(raw.get("market", raw.get("conditionId", "")))


def activity_token_id(raw: dict) -> str:
    """Return the token/asset id from current or legacy fields."""
    return str(raw.get("asset", raw.get("tokenId", "")))


def activity_notional_usdc(raw: dict) -> float:
    """Return activity notional in USDC, preferring usdcSize over derived size * price."""
    usdc_size = _float_or_none(raw.get("usdcSize"))
    if usdc_size is not None:
        return usdc_size

    size = _float_or_none(raw.get("size"))
    price = _float_or_none(raw.get("price"))
    if size is None or price is None or price <= 0:
        return 0.0
    return size * price


def parse_activity_timestamp(raw) -> float | None:
    """Return a Data API timestamp as Unix seconds, or None for an unsupported type.

    ISO 8601 strings accept a ``Z`` suffix, and an offset-less string is venue
    UTC, not host-local time: a naive datetime makes ``.timestamp()`` read it in
    the server's timezone, skewing staleness and recency by the UTC offset.
    Numbers above 1e12 are milliseconds. A malformed string raises ValueError and
    a non-finite number is returned as-is, so each caller keeps its own
    fail-closed policy (the monitor drops the event, the tracker scores 0.0).
    """
    if isinstance(raw, str):
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    if isinstance(raw, (int, float)):
        return raw / 1_000.0 if raw > 1e12 else float(raw)
    return None
