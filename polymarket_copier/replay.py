"""Paper-only evaluation of a held-out copy-decision trace.

This module deliberately does not submit orders or simulate an order book.  It
scores the same recorded v1 leaderboard/activity shape consumed by the runtime,
then prices known outcomes with the existing paper fee/slippage functions.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from polymarket_copier.api.clob_client import gross_buy_fill_price, net_sell_fill_price
from polymarket_copier.core.tracker import TrackerConfig, TraderScorer, _compute_trader_stats
from polymarket_copier.utils.addresses import normalize_address


_OUTCOMES = ("filled", "partial_fill", "no_fill", "skipped", "unknown_fill")


@dataclass(frozen=True)
class HeldoutReplayReport:
    """Measured outcomes from a held-out decision trace, never a profitability claim."""

    selected_wallets: list[str]
    decision_counts: dict[str, int]
    skip_reasons: dict[str, int]
    unknown_fills: int
    net_pnl_usdc: float
    net_expectancy_usdc: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_wallets": self.selected_wallets,
            "decision_counts": self.decision_counts,
            "skip_reasons": self.skip_reasons,
            "unknown_fills": self.unknown_fills,
            "net_pnl_usdc": self.net_pnl_usdc,
            "net_expectancy_usdc": self.net_expectancy_usdc,
        }


def build_heldout_report(fixture: Mapping[str, Any]) -> HeldoutReplayReport:
    """Score Window A and evaluate Window B without allowing temporal overlap.

    ``fixture`` is intentionally a captured-decision format.  ``skipped`` and
    fill-certainty outcomes must come from a recorded decision trace; this first
    R1 slice does not duplicate the async ``CopyTrader`` decision engine.
    """
    training_end = _finite_number(fixture.get("training_end_timestamp"), "training_end_timestamp")
    leaderboard = _mapping(fixture.get("leaderboard"), "leaderboard")
    all_window = _rows(leaderboard.get("all"), "leaderboard.all")
    recent_window = _rows(leaderboard.get("recent"), "leaderboard.recent")
    activity_by_wallet = _mapping(fixture.get("activity_by_wallet"), "activity_by_wallet")

    scorer_config = _mapping(fixture.get("scorer_config", {}), "scorer_config")
    scorer = TraderScorer(TrackerConfig(**scorer_config))
    recent_wallets = {_wallet(row, "leaderboard.recent") for row in recent_window}
    stats = []
    for row in all_window:
        wallet = _wallet(row, "leaderboard.all")
        if wallet not in recent_wallets:
            continue
        activity = _rows(
            activity_by_wallet.get(wallet, activity_by_wallet.get(str(row.get("proxyWallet", "")), [])), "activity"
        )
        stats.append(
            _compute_trader_stats(
                wallet,
                str(row.get("userName", row.get("pseudonym", ""))),
                _finite_number(row.get("pnl", 0.0), "leaderboard pnl"),
                activity,
            )
        )

    selected_wallets = [trader.stats.address for trader in scorer.score_many(stats)]
    selected = set(selected_wallets)
    decision_counts = {outcome: 0 for outcome in _OUTCOMES}
    skip_reasons: dict[str, int] = {}
    net_pnl_usdc = 0.0
    seen_event_ids: set[str] = set()

    for record in _rows(fixture.get("heldout"), "heldout"):
        event_id = str(record.get("event_id", "")).strip()
        if not event_id or event_id in seen_event_ids:
            raise ValueError("heldout event_id values must be non-empty and unique")
        seen_event_ids.add(event_id)

        source_timestamp = _finite_number(record.get("source_timestamp"), "heldout source_timestamp")
        if source_timestamp <= training_end:
            raise ValueError("heldout source_timestamp must be strictly after training_end_timestamp")

        if _wallet(record, "heldout") not in selected:
            decision_counts["skipped"] += 1
            _increment(skip_reasons, "not_selected")
            continue

        outcome = str(record.get("outcome", "")).strip()
        if outcome not in _OUTCOMES:
            raise ValueError(f"unsupported heldout outcome: {outcome!r}")
        decision_counts[outcome] += 1

        if outcome == "skipped":
            reason = str(record.get("skip_reason", "")).strip()
            if not reason:
                raise ValueError("skipped heldout records require skip_reason")
            _increment(skip_reasons, reason)
        elif outcome in {"filled", "partial_fill"}:
            fill_fraction = 1.0 if outcome == "filled" else _finite_number(record.get("fill_fraction"), "fill_fraction")
            if not 0.0 < fill_fraction <= 1.0:
                raise ValueError("fill_fraction must be in (0, 1]")
            net_pnl_usdc += _net_pnl_usdc(record, fill_fraction)

    known_decisions = sum(decision_counts[outcome] for outcome in ("filled", "partial_fill", "no_fill", "skipped"))
    return HeldoutReplayReport(
        selected_wallets=selected_wallets,
        decision_counts=decision_counts,
        skip_reasons=dict(sorted(skip_reasons.items())),
        unknown_fills=decision_counts["unknown_fill"],
        net_pnl_usdc=net_pnl_usdc,
        net_expectancy_usdc=net_pnl_usdc / known_decisions if known_decisions else None,
    )


def _net_pnl_usdc(record: Mapping[str, Any], fill_fraction: float) -> float:
    copy_size_usdc = _finite_number(record.get("copy_size_usdc"), "copy_size_usdc")
    entry_quote = _price(record.get("entry_quote_price"), "entry_quote_price")
    exit_quote = _price(record.get("exit_quote_price"), "exit_quote_price")
    fee_rate = _finite_number(record.get("fee_rate"), "fee_rate")
    entry_slippage = _finite_number(record.get("entry_slippage_pct", 0.0), "entry_slippage_pct")
    exit_slippage = _finite_number(record.get("exit_slippage_pct", 0.0), "exit_slippage_pct")
    if copy_size_usdc <= 0.0 or fee_rate < 0.0 or entry_slippage < 0.0 or exit_slippage < 0.0:
        raise ValueError("copy size, fee rate, and slippage must be non-negative (copy size positive)")

    entry = gross_buy_fill_price(entry_quote, entry_slippage, fee_rate)
    exit_price = net_sell_fill_price(exit_quote, exit_slippage, fee_rate)
    if entry <= 0.0:
        raise ValueError("gross entry price must be positive")
    shares = (copy_size_usdc * fill_fraction) / entry
    return (exit_price - entry) * shares


def _wallet(row: Mapping[str, Any], context: str) -> str:
    wallet = normalize_address(str(row.get("wallet", row.get("proxyWallet", row.get("address", "")))))
    if not wallet:
        raise ValueError(f"{context} row is missing a wallet address")
    return wallet


def _finite_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _price(value: Any, field: str) -> float:
    price = _finite_number(value, field)
    if not 0.0 < price <= 1.0:
        raise ValueError(f"{field} must be in (0, 1]")
    return price


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _rows(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f"{field} must be a list of objects")
    return value


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def main() -> None:
    """Render one captured R1 fixture as JSON without making network calls."""
    parser = argparse.ArgumentParser(description="Evaluate a paper-only held-out replay fixture.")
    parser.add_argument("fixture", type=Path, help="Path to an R1 replay JSON fixture")
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    print(json.dumps(build_heldout_report(fixture).to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
