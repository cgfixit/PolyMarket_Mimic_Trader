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
