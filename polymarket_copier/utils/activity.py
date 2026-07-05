"""Helpers for Polymarket Data API activity records."""

from __future__ import annotations


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
    """Return activity notional in USDC, preferring the current usdcSize field."""
    return float(raw.get("usdcSize", raw.get("size", 0)))
