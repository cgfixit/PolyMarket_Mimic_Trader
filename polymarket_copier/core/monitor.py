    async def set_wallets(self, wallets: list[str]) -> None:
        """Replace the tracked-wallet list without losing seen-id state for retained wallets."""
        wallets = [w.lower() for w in wallets]
        async with self._wallet_lock:
            # Removed wallets must re-prime before they can emit trades again.
            self._primed_wallets.intersection_update(wallets)
            # Evict seen-id state for wallets no longer tracked; retained wallets
            # keep their dedup state (invariant). A re-added wallet is unprimed
            # (above), so its first poll re-seeds a fresh baseline (DD-12).
            self._seen_trade_ids = {w: self._seen_trade_ids.get(w, OrderedDict()) for w in wallets}
            self._wallets = wallets