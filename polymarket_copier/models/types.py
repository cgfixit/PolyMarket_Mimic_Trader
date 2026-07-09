"""Data models for the Polymarket copy trading bot v2."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Market(BaseModel):
    """A Polymarket prediction market."""

    condition_id: str
    question: str = ""
    token_id_yes: str = ""
    token_id_no: str = ""
    resolve_time: Optional[datetime] = None
    volume_24h: float = 0.0
    active: bool = True
    closed: bool = False
    archived: bool = False
    restricted: bool = False
    accepting_orders: bool = True
    enable_order_book: bool = True
    fees_enabled: bool = False
    fee_rate: Optional[float] = None


class Order(BaseModel):
    """An order to place on the CLOB."""

    market_id: str
    token_id: str
    side: Literal["BUY", "SELL"]
    price: float = Field(ge=0.0, le=1.0)
    size_usdc: float = Field(gt=0.0)
    order_type: Literal["GTC", "FOK", "GTD", "FAK"] = "GTC"
    # Market-specific taker fee rate the caller already resolved (CLOB market
    # info > Gamma > config default). None => the paper-fill simulator falls
    # back to the flat config default, matching pre-existing behavior.
    fee_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
