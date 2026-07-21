"""Regression test: set_wallets() must evict seen-id state for removed wallets."""

from __future__ import annotations

from polymarket_copier.core.monitor import TradeMonitor


def _make_monitor(wallets):
    async def _noop(event):
        return None

    return TradeMonitor(tracked_wallets=wallets, on_trade=_noop, prime_on_start=False)


class TestSetWalletsEviction:
    async def test_removed_wallet_seen_ids_evicted(self):
        """Removed wallets must not accumulate dead seen-id dicts across rebalance
        cycles. Retained-wallet state stays pinned by test_invariants.py."""
        m = _make_monitor(["0xaaa", "0xbbb"])
        m._seen_trade_ids["0xbbb"]["t9"] = None
        await m.set_wallets(["0xaaa"])
        assert "0xbbb" not in m._seen_trade_ids
        assert "0xaaa" in m._seen_trade_ids
