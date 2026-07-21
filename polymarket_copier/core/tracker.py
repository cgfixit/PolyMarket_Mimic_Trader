from __future__ import annotations

import asyncio
import logging
import math
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from polymarket_copier.utils.addresses import normalize_address
from polymarket_copier.utils.activity import (
    activity_id,
    activity_market_id,
    activity_notional_usdc,
    activity_side,
    activity_token_id,
    activity_type,
    is_trade_activity,
)

logger = logging.getLogger(__name__)

_EPSILON = 1e-9
POLYMARKET_DATA_API = "https://data-api.polymarket.com"
