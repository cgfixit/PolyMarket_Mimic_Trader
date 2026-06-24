"""Client for the Polymarket CLOB API (order placement, requires authentication)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import logging
import threading
from typing import Any, Optional

from polymarket_copier.config import AppConfig
from polymarket_copier.models.types import Order

logger = logging.getLogger("polymarket_copier")

CLOB_BASE = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet


class InsufficientLiquidityError(RuntimeError):
    """Raised when the order book lacks depth to fill an order within 1% of price."""


class ClobClient:
    """Wraps the Polymarket CLOB for order placement and management.

    In paper mode, orders are logged but not sent. In live mode, uses
    py-clob-client to sign and submit orders.

    C1 fix: all blocking py-clob-client calls (EIP-712 signing + requests POST)
    run in a dedicated ThreadPoolExecutor so they never stall the asyncio event
    loop. The 8 s poll budget and every open position's TP/SL evaluation continue
    uninterrupted while an order is in flight.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.paper_mode = config.mode == "paper"
        self._client: Any = None
        # Threading lock protects the lazy-init guard against concurrent threads
        # in the executor both seeing _client=None and double-initialising.
        self._init_lock = threading.Lock()
        # Dedicated thread pool for blocking CLOB calls (signing + HTTP).
        # Not created in paper mode — there are no blocking calls there.
        self._executor: Optional[concurrent.futures.ThreadPoolExecutor] = (
            None if self.paper_mode
            else concurrent.futures.ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="clob-signer"
            )
        )

    async def _run_blocking(self, fn) -> Any:
        """Run a zero-arg callable in the CLOB thread pool without blocking the loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, fn)

    async def close(self) -> None:
        """Shut down the signer thread pool (call on bot shutdown)."""
        if self._executor:
            self._executor.shutdown(wait=False)

    def _init_live_client(self) -> None:
        """Lazily construct and authenticate the live py-clob-client (thread-safe, single-init)."""
        with self._init_lock:
            if self._client is not None:
                return
            if not self.config.private_key:
                raise ValueError("POLY_PRIVATE_KEY required for live trading")
            try:
                from py_clob_client.client import ClobClient as _ClobClient

                self._client = _ClobClient(
                    CLOB_BASE,
                    key=self.config.private_key,
                    chain_id=CHAIN_ID,
                )
                if self.config.api_key and self.config.api_secret:
                    self._client.set_api_creds(
                        type("Creds", (), {
                            "api_key": self.config.api_key,
                            "api_secret": self.config.api_secret,
                            "api_passphrase": self.config.api_passphrase,
                        })()
                    )
                else:
                    creds = self._client.create_or_derive_api_creds()
                    self._client.set_api_creds(creds)
                logger.info("Live CLOB client initialized")
            except ImportError:
                raise ImportError(
                    "py-clob-client required for live trading: pip install py-clob-client"
                ) from None

    async def get_order_book(self, token_id: str) -> dict[str, Any]:
        """Return the order book for a token (a synthetic book in paper mode)."""
        if self.paper_mode:
            return {
                "bids": [{"price": "0.50", "size": "10000"}],
                "asks": [{"price": "0.51", "size": "10000"}],
            }
        # C1: run in thread pool so the HTTP GET doesn't stall the event loop.
        return await self._run_blocking(
            functools.partial(self._get_order_book_sync, token_id)
        )

    def _get_order_book_sync(self, token_id: str) -> dict[str, Any]:
        self._init_live_client()
        return self._client.get_order_book(token_id)

    def _check_liquidity(self, book: dict, price: float, size_usdc: float) -> None:
        """Ensure the ASK side has enough resting depth to fill a BUY without walking
        the book more than max_live_slippage_pct above the order price. A market BUY
        lifts asks, so the ask side — not the bid side — is what determines fillability.

        We compare available SHARES (not notional) against the shares we need to buy.
        Comparing notional was a bug: it would reject valid orders whose ask-side
        notional happened to be less than size_usdc despite having ample share depth.
        """
        slippage_cap  = self.config.copy_trading.max_live_slippage_pct
        asks          = book.get("asks", [])
        max_price     = price * (1.0 + slippage_cap)
        needed_shares = size_usdc / max(price, 1e-6)
        avail_shares  = 0.0
        for level in asks:
            level_price = float(level.get("price", 0))
            level_size  = float(level.get("size", 0))
            if level_price <= max_price:
                avail_shares += level_size
        if avail_shares < needed_shares:
            raise InsufficientLiquidityError(
                f"Insufficient liquidity: need {needed_shares:.2f} shares, "
                f"available {avail_shares:.2f} shares on ask side within "
                f"{slippage_cap * 100:.1f}% of ${price:.4f}"
            )

    async def place_order(self, order: Order) -> dict[str, Any]:
        """Place an order on the CLOB. Returns order details or paper-mode simulation."""
        # The depth check only applies to live trading against a real order book.
        # Paper mode has no real book, so it does not gate — otherwise a synthetic
        # book would systematically skip valid markets across the [0,1] price range.
        if not self.paper_mode and order.side == "BUY":
            book = await self.get_order_book(order.token_id)
            self._check_liquidity(book, order.price, order.size_usdc)

        if self.paper_mode:
            # Simulate realistic fill: apply half-spread slippage + taker fee so
            # paper PnL reflects live execution costs (not a zero-cost fill).
            slip = self.config.copy_trading.paper_fill_slippage_pct
            fee  = self.config.copy_trading.paper_taker_fee_pct
            cost = slip + fee
            if order.side == "BUY":
                fill_price = min(order.price * (1.0 + cost), 1.0)
            else:
                fill_price = max(order.price * (1.0 - cost), 0.0)

            result = {
                "status": "PAPER",
                "market_id": order.market_id,
                "token_id": order.token_id,
                "side": order.side,
                "size_usdc": order.size_usdc,
                "price": order.price,
                "fill_price": fill_price,
            }
            logger.info(
                "[PAPER] Order: %s $%.2f @ %.4f (fill %.4f, %.1f%% slip+fee) on %s",
                order.side, order.size_usdc, order.price, fill_price,
                cost * 100, order.market_id,
            )
            return result

        # C1: run signing + HTTP POST in thread pool — never blocks the event loop.
        # C2: pass the order_type field through so GTC/FOK/FAK are honoured on live orders.
        #     Also price aggressively through the book (slippage cap) so FOK entries
        #     cross the spread and FAK exits hit the bid — not a resting mid-limit.
        slippage_cap = self.config.copy_trading.max_live_slippage_pct
        if order.side == "BUY":
            exec_price = min(order.price * (1.0 + slippage_cap), 1.0)
        else:
            exec_price = max(order.price * (1.0 - slippage_cap), 0.0)

        size_shares = order.size_usdc / order.price if order.price > 0 else 0
        order_type_str = order.order_type  # capture for closure

        def _place_sync() -> Any:
            self._init_live_client()
            from py_clob_client.order_builder.constants import BUY as CLOB_BUY, SELL as CLOB_SELL
            side = CLOB_BUY if order.side == "BUY" else CLOB_SELL
            kwargs: dict[str, Any] = dict(
                token_id=order.token_id,
                price=exec_price,
                size=size_shares,
                side=side,
            )
            # Wire the order type through; graceful fallback if clob_types unavailable.
            try:
                from py_clob_client.clob_types import OrderType
                otype = {
                    "GTC": OrderType.GTC,
                    "FOK": OrderType.FOK,
                    "FAK": getattr(OrderType, "FAK", OrderType.FOK),
                    "GTD": getattr(OrderType, "GTD", OrderType.GTC),
                }.get(order_type_str, OrderType.GTC)
                kwargs["order_type"] = otype
            except ImportError:
                pass  # older py-clob-client: fall through without order_type
            return self._client.create_and_post_order(**kwargs)

        signed_order = await self._run_blocking(_place_sync)
        logger.info(
            "[LIVE] Order: %s %s $%.2f @ %.4f (exec %.4f) -> %s",
            order.order_type, order.side, order.size_usdc, order.price, exec_price, signed_order,
        )
        return {"status": "LIVE", "result": signed_order}

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order by id, returning True on success (always True in paper mode)."""
        if self.paper_mode:
            logger.info("[PAPER] Cancel: %s", order_id)
            return True
        # C1: cancellations are also blocking HTTP calls.
        def _cancel_sync() -> None:
            self._init_live_client()
            self._client.cancel(order_id)

        try:
            await self._run_blocking(_cancel_sync)
            return True
        except Exception as e:
            logger.error("Failed to cancel %s: %s", order_id, e)
            return False

    async def get_balance(self) -> Optional[float]:
        """Return the available USDC balance (configured bankroll in paper mode, None on error)."""
        if self.paper_mode:
            return self.config.bankroll
        def _balance_sync() -> float:
            self._init_live_client()
            return float(self._client.get_balance())

        try:
            return await self._run_blocking(_balance_sync)
        except Exception as e:
            logger.error("Failed to get balance: %s", e)
            return None
