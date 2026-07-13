"""Invariant pins from the 2026-07-08 due-diligence audit.

Every test in this file is named after the invariant it protects and exists so
that a future change which silently breaks that invariant fails CI instead of
shipping. Read INVARIANTS.md before editing any of the code under test; each
class docstring cites the audit finding (docs/DUE_DILIGENCE_AUDIT_2026-07-08.md,
DD-xx) or the CLAUDE.md rule it guards.

Property-based tests (hypothesis) cover the pure money-math; async example
tests cover the orchestration invariants. None of these tests pin a known bug —
known divergences are documented in the audit report, not enshrined here.
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from polymarket_copier.api.clob_client import (
    ClobClient,
    gross_buy_fill_price,
    net_sell_fill_price,
    taker_fee_per_share,
)
from polymarket_copier.config import AppConfig, ConfigError, load_config
from polymarket_copier.core.copier import CopyTrader
from polymarket_copier.core.monitor import PriceTick, TradeEvent, TradeMonitor, TradeType
from polymarket_copier.core.portfolio import PortfolioManager
from polymarket_copier.core.risk_manager import (
    ExitReason,
    ExposureCapError,
    Position,
    RiskConfig,
    RiskManager,
    Side,
    _midnight_utc,
)
from polymarket_copier.core.sizing import kelly_fraction, kelly_size_from_edge, kelly_size_usdc
from polymarket_copier.core.tracker import TraderScorer, TraderStats, TrackerConfig
from polymarket_copier.models.types import Market, Order

# Property tests exercise pure math; keep them deterministic-ish and fast in CI.
settings.register_profile(
    "invariants",
    deadline=None,
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("invariants")

# Default copy-path entry band (config.py CopyTradingConfig.min/max_entry_price).
# The min_reward_risk floor is only guaranteed inside this band — see DD-04.
ENTRY_BAND = st.floats(min_value=0.05, max_value=0.95, allow_nan=False)


def _rm(bankroll: float = 10_000, **overrides) -> RiskManager:
    return RiskManager(config=RiskConfig(**overrides), bankroll=bankroll)


def _position(rm: RiskManager, entry: float, shares: float = 100.0, **kw) -> Position:
    tp, sl = rm._compute_thresholds(entry)
    return Position(
        position_id=kw.pop("position_id", "pos-1"),
        market_id="mkt-1",
        token_id="tok-1",
        trader_address="0xwhale",
        side=Side.BUY,
        entry_price=entry,
        size_shares=shares,
        tp_price=tp,
        sl_price=sl,
        **kw,
    )


# ─── TP/SL threshold structure (risk_manager.py::_compute_thresholds) ─────────


class TestThresholdStructure:
    """Range-relative TP/SL is owned by _compute_thresholds() alone (CLAUDE.md
    'Money math'). These pins guard the structural properties every caller
    (pre-copy estimate, post-fill recompute, build_position) relies on."""

    @given(entry=st.floats(min_value=0.001, max_value=0.999, allow_nan=False))
    def test_tp_is_strictly_above_sl_for_every_entry(self, entry):
        tp, sl = _rm()._compute_thresholds(entry)
        assert sl < tp

    @given(entry=st.floats(min_value=0.001, max_value=0.999, allow_nan=False))
    def test_thresholds_stay_inside_token_bounds(self, entry):
        tp, sl = _rm()._compute_thresholds(entry)
        assert 0.0 <= sl < entry
        assert entry < tp <= 1.0

    @given(entry=st.floats(min_value=0.001, max_value=0.999, allow_nan=False))
    def test_thresholds_are_rounded_to_six_decimals(self, entry):
        tp, sl = _rm()._compute_thresholds(entry)
        assert tp == round(tp, 6)
        assert sl == round(sl, 6)

    @given(entry=ENTRY_BAND)
    def test_reward_risk_floor_holds_across_default_entry_band(self, entry):
        """H2: R:R never inverts below min_reward_risk — guaranteed for entries
        inside the default copy band [0.05, 0.95]. (Above ~0.97 the post-cap TP
        clamp violates the floor — audit DD-04; do NOT widen this band without
        fixing that first.)"""
        rm = _rm()
        tp, sl = rm._compute_thresholds(entry)
        # 2e-6 tolerance: tp/sl are independently rounded to 6 decimals.
        assert (tp - entry) >= (entry - sl) * rm.cfg.min_reward_risk - 2e-6

    @given(entry=st.floats(min_value=0.02, max_value=0.19, allow_nan=False))
    def test_low_entry_tp_taper_targets_less_than_full_fraction(self, entry):
        """L5: below low_entry_threshold the TP fraction tapers down so the
        target stays achievable — the untapered 40%-of-range TP must never be
        produced for a low entry."""
        rm = _rm()
        tp, _ = rm._compute_thresholds(entry)
        untapered_tp = entry + (1.0 - entry) * rm.cfg.tp_range_fraction
        assert tp < untapered_tp

    def test_flat_percentage_tp_is_impossible_but_range_relative_is_clamped(self):
        """The module's founding motivation: entry $0.97 + naive 15% = $1.12
        (impossible); range-relative TP must clamp to the $1.00 ceiling."""
        tp, sl = _rm()._compute_thresholds(0.97)
        assert tp <= 1.0
        assert sl >= 0.0


# ─── Trailing stop (risk_manager.py::_compute_trail_sl) ───────────────────────


class TestTrailingStop:
    """H1: the trail gives back a fraction of the run-up FROM ENTRY (not the
    peak-to-hard-SL gap — that is the removed pre-H1 formula the README still
    describes, audit DD-17) and never drops below the hard SL."""

    @given(entry=ENTRY_BAND, peak_frac=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    def test_trailing_stop_never_drops_below_hard_sl(self, entry, peak_frac):
        rm = _rm()
        pos = _position(rm, entry)
        peak = entry + (1.0 - entry) * peak_frac
        trail = rm._compute_trail_sl(pos, peak_override=peak)
        assert trail >= pos.sl_price - 1e-12
        assert trail <= max(peak, pos.sl_price) + 1e-12

    def test_trailing_stop_formula_is_run_up_from_entry_not_peak_to_sl_gap(self):
        rm = _rm()
        pos = _position(rm, 0.50)
        trail = rm._compute_trail_sl(pos, peak_override=0.70)
        # run-up formula: 0.70 - (0.70-0.50)*0.40 = 0.62
        assert trail == pytest.approx(0.62)
        # the removed formula would give 0.70 - (0.70 - sl)*0.40 instead
        old_formula = 0.70 - (0.70 - pos.sl_price) * rm.cfg.trailing_stop_fraction
        assert trail != pytest.approx(old_formula)


# ─── Per-tick evaluation (risk_manager.py::evaluate) ──────────────────────────


class TestEvaluateSemantics:
    """Pins the exit-priority behavior handle_price_tick/check_all_exits rely on."""

    def test_evaluate_never_mutates_the_position(self):
        """The caller persists peak updates (H11 debounced flush); evaluate()
        must stay read-only or the DB and cache silently diverge."""
        rm = _rm()
        pos = _position(rm, 0.50)
        before = (pos.peak_price, pos.tp_price, pos.sl_price, pos.entry_price)
        rm.evaluate(pos, 0.60)
        assert (pos.peak_price, pos.tp_price, pos.sl_price, pos.entry_price) == before

    def test_take_profit_triggers_at_threshold(self):
        rm = _rm()
        pos = _position(rm, 0.50)
        assert rm.evaluate(pos, pos.tp_price) == ExitReason.TAKE_PROFIT

    def test_stop_loss_triggers_at_threshold(self):
        rm = _rm()
        pos = _position(rm, 0.50)
        assert rm.evaluate(pos, pos.sl_price) == ExitReason.STOP_LOSS

    def test_daily_loss_breach_flags_every_open_position_for_exit(self):
        """Current design: breaching the daily-loss limit does not merely halt
        entries — evaluate() returns DAILY_LOSS_LIMIT for every position, i.e.
        full liquidation (audit DD-14 documents the doc mismatch)."""
        rm = _rm(bankroll=10_000)
        rm._daily_pnl = Decimal("-1000")  # limit is 3% of 10k = $300
        pos = _position(rm, 0.50)
        assert rm.evaluate(pos, 0.55) == ExitReason.DAILY_LOSS_LIMIT

    def test_resolution_blackout_flags_position_before_resolve(self):
        rm = _rm()
        pos = _position(rm, 0.50, resolve_time=time.time() + 6 * 3600)
        assert rm.evaluate(pos, 0.55) == ExitReason.MARKET_RESOLVING

    def test_time_exit_spares_profitable_positions(self):
        """M8: a stale-but-profitable position holds; a stale losing one exits."""
        rm = _rm()
        pos = _position(rm, 0.50, entry_time=time.time() - 100 * 3600)
        assert rm.evaluate(pos, 0.51) == ExitReason.HOLD
        assert rm.evaluate(pos, 0.49) == ExitReason.TIME_EXIT


# ─── Exposure accounting (risk_manager.py) ────────────────────────────────────


class TestExposureAccounting:
    """Exposure is accumulated as Decimal via str() conversion — cap
    comparisons rely on EXACT accumulation (CLAUDE.md 'Money math')."""

    async def test_exposure_accumulates_exactly_as_decimal_not_float(self):
        rm = _rm(
            bankroll=1_000,
            max_market_exposure_pct=1.0,
            max_trader_allocation=1.0,
            max_total_exposure_pct=1.0,
        )
        for i in range(10):
            await rm.build_position(f"p{i}", "mkt", "tok", "0xw", entry_price=0.1, size_shares=1.0)
        # Control: sequential float accumulation (how exposure would build if
        # regressed to float) drifts to 0.9999999999999999 on every CPython.
        # NB: don't use sum() here — 3.12+ gives it compensated summation.
        naive_float_total = 0.0
        for _ in range(10):
            naive_float_total += 0.1
        assert naive_float_total != 1.0
        # The Decimal-by-str path must be exact.
        assert rm.market_exposure("mkt") == 1.0
        for _ in range(10):
            await rm.release_exposure("mkt", 0.1, trader_address="0xw")
        assert rm.market_exposure("mkt") == 0.0
        assert rm.trader_exposure("0xw") == 0.0

    async def test_build_position_enforces_per_market_cap(self):
        rm = _rm(bankroll=1_000)  # market cap 8% = $80
        await rm.build_position("p1", "mkt", "tok", "0xa", entry_price=0.5, size_shares=100)
        with pytest.raises(ExposureCapError, match="cap"):
            await rm.build_position("p2", "mkt", "tok", "0xb", entry_price=0.5, size_shares=100)

    async def test_build_position_enforces_per_trader_allocation_cap(self):
        rm = _rm(bankroll=1_000)  # trader cap 5% = $50
        with pytest.raises(ExposureCapError, match="Trader"):
            await rm.build_position("p1", "mkt", "tok", "0xa", entry_price=0.51, size_shares=100)

    async def test_build_position_enforces_total_exposure_cap(self):
        rm = _rm(bankroll=1_000, max_market_exposure_pct=1.0, max_trader_allocation=1.0)
        # total cap 30% = $300; six $50 positions hit it exactly, the 7th breaches
        for i in range(6):
            await rm.build_position(f"p{i}", f"mkt{i}", "tok", f"0x{i}", entry_price=0.5, size_shares=100)
        with pytest.raises(ExposureCapError, match="Total exposure"):
            await rm.build_position("p7", "mkt7", "tok", "0x7", entry_price=0.5, size_shares=100)

    async def test_record_exit_releases_the_registered_notional_when_entry_unmutated(self):
        rm = _rm(bankroll=1_000)
        pos = await rm.build_position("p1", "mkt", "tok", "0xa", entry_price=0.5, size_shares=100)
        await rm.record_exit(pos, exit_price=0.6, reason=ExitReason.TAKE_PROFIT)
        assert rm.market_exposure("mkt") == 0.0
        assert rm.trader_exposure("0xa") == 0.0
        assert rm.bankroll == pytest.approx(1_010.0)

    async def test_release_without_trader_address_leaves_trader_allocation_reserved(self):
        """Documented footgun (CLAUDE.md failure-path rule): omitting
        trader_address silently leaks the per-trader allocation. Every rollback
        call site MUST pass it — this pin makes the semantics explicit."""
        rm = _rm(bankroll=1_000)
        pos = await rm.build_position("p1", "mkt", "tok", "0xa", entry_price=0.4, size_shares=100)
        await rm.release_exposure(pos.market_id, 40.0)  # no trader_address
        assert rm.market_exposure("mkt") == 0.0
        assert rm.trader_exposure("0xa") == 40.0  # leaked — caller must release it

    async def test_exposure_never_goes_negative_on_over_release(self):
        rm = _rm(bankroll=1_000)
        await rm.build_position("p1", "mkt", "tok", "0xa", entry_price=0.4, size_shares=100)
        await rm.release_exposure("mkt", 10_000.0, trader_address="0xa")
        assert rm.market_exposure("mkt") == 0.0
        assert rm.trader_exposure("0xa") == 0.0

    def test_positions_cannot_be_constructed_without_thresholds(self):
        """Position must be built via build_position() — a TP/SL-less position
        would silently never exit."""
        with pytest.raises(ValueError, match="tp_price"):
            Position(
                position_id="p",
                market_id="m",
                token_id="t",
                trader_address="0xw",
                side=Side.BUY,
                entry_price=0.5,
                size_shares=1.0,
            )


# ─── Cooldown & circuit-breaker semantics (risk_manager.py) ───────────────────


class TestCooldownAndHalt:
    """L5 cooldown filter + the entry/exit asymmetry of is_trading_halted()."""

    async def _lose(self, rm, reason, pid):
        pos = await rm.build_position(pid, f"mkt-{pid}", "tok", f"0x{pid}", entry_price=0.5, size_shares=10)
        await rm.record_exit(pos, exit_price=0.45, reason=reason)

    async def test_only_stop_loss_class_losses_advance_the_streak(self):
        rm = _rm(bankroll=100_000)
        await self._lose(rm, ExitReason.STOP_LOSS, "a")
        await self._lose(rm, ExitReason.TRAILING_STOP, "b")
        assert rm.consecutive_losses() == 2

    async def test_source_exit_and_time_exit_losses_never_advance_the_streak(self):
        rm = _rm(bankroll=100_000)
        await self._lose(rm, ExitReason.SOURCE_EXIT, "a")
        await self._lose(rm, ExitReason.TIME_EXIT, "b")
        assert rm.consecutive_losses() == 0

    async def test_reasonless_losses_count_conservatively(self):
        rm = _rm(bankroll=100_000)
        await self._lose(rm, None, "a")
        assert rm.consecutive_losses() == 1

    async def test_any_win_resets_the_streak(self):
        rm = _rm(bankroll=100_000)
        await self._lose(rm, ExitReason.STOP_LOSS, "a")
        pos = await rm.build_position("w", "mkt-w", "tok", "0xw", entry_price=0.5, size_shares=10)
        await rm.record_exit(pos, exit_price=0.6, reason=ExitReason.SOURCE_EXIT)
        assert rm.consecutive_losses() == 0

    async def test_cooldown_engages_after_configured_streak_and_blocks_entries(self):
        rm = _rm(bankroll=100_000)
        for pid in ("a", "b", "c"):  # cooldown_after_losses default = 3
            await self._lose(rm, ExitReason.STOP_LOSS, pid)
        assert rm.cooldown_remaining() > 0
        assert rm.is_trading_halted() is not None
        assert rm.consecutive_losses() == 0  # streak resets when cooldown engages

    def test_halt_gates_entries_only_never_position_evaluation_exits(self):
        """is_trading_halted() is an ENTRY gate; a halted bot must still be able
        to exit — evaluate() must keep returning position-level exit reasons."""
        rm = _rm()
        rm._cooldown_until = time.time() + 600
        assert rm.is_trading_halted() is not None
        pos = _position(rm, 0.50)
        assert rm.evaluate(pos, pos.sl_price) == ExitReason.STOP_LOSS

    def test_unrealized_losses_count_toward_the_daily_halt(self):
        """H3: conservative unrealized PnL is added to realized daily PnL."""
        rm = _rm(bankroll=10_000)  # limit = $300
        assert rm.is_trading_halted(unrealized_pnl=0.0) is None
        assert rm.is_trading_halted(unrealized_pnl=-400.0) is not None


class TestDailyWindowUTC:
    """The daily-loss window resets at UTC midnight regardless of host TZ
    (CLAUDE.md persistence rule; risk_manager.py::_midnight_utc)."""

    def test_daily_window_resets_at_utc_midnight_not_local_midnight(self, monkeypatch):
        # Force a non-UTC host timezone so local-time date math would misfire.
        if hasattr(time, "tzset"):
            monkeypatch.setenv("TZ", "America/New_York")
            time.tzset()
        try:
            rm = _rm()
            day_start = _midnight_utc()
            rm._day_start_ts = day_start
            rm._daily_pnl = Decimal("-50")

            # 1 second BEFORE the next UTC midnight: window must NOT reset
            # (local-date math would already have rolled over in New York).
            # risk_manager reads the shared `time` module, so patching it here
            # patches the module under test too.
            monkeypatch.setattr(time, "time", lambda: day_start + 86_399.0)
            rm.is_trading_halted()
            assert rm.daily_pnl() == -50.0

            # 1 second AFTER UTC midnight: window must reset.
            monkeypatch.setattr(time, "time", lambda: day_start + 86_401.0)
            rm.is_trading_halted()
            assert rm.daily_pnl() == 0.0
        finally:
            monkeypatch.undo()
            if hasattr(time, "tzset"):
                time.tzset()


# ─── The retry matrix (api/clob_client.py::place_order_with_timeout) ──────────


def _live_clob(**copy_overrides) -> ClobClient:
    cfg = AppConfig(mode="live", copy_trading=copy_overrides)
    return ClobClient(cfg)


def _order(order_type: str = "FOK", price: float = 0.5, size: float = 100.0) -> Order:
    return Order(market_id="m", token_id="t", side="BUY", price=price, size_usdc=size, order_type=order_type)


class TestRetryMatrix:
    """The retry matrix is deliberate and asymmetric (CLAUDE.md 'Money math').
    Entry FOK/FAK: never retried. Resting GTC/GTD: cancel at timeout, confirm
    terminal, retry ONCE sized to the confirmed-unfilled remainder. Ambiguity
    always degrades to NO retry."""

    async def test_fok_entry_is_placed_exactly_once_even_on_zero_fill(self):
        clob = _live_clob()
        clob.place_order = AsyncMock(
            return_value={"status": "LIVE", "order_id": "o1", "filled_size": 0.0, "avg_price": None, "raw": {}}
        )
        await clob.place_order_with_timeout(_order("FOK"))
        assert clob.place_order.await_count == 1

    async def test_fok_entry_failure_propagates_without_retry(self):
        clob = _live_clob()
        clob.place_order = AsyncMock(side_effect=RuntimeError("venue down"))
        with pytest.raises(RuntimeError, match="venue down"):
            await clob.place_order_with_timeout(_order("FOK"))
        assert clob.place_order.await_count == 1

    async def test_resting_retry_is_sized_to_the_confirmed_unfilled_remainder(self, monkeypatch):
        # Collapse the in-flight poll sleep so the tiny 0.01s timeout elapses
        # without real waiting (justification: the sleep lives in prod code).
        real_sleep = asyncio.sleep
        monkeypatch.setattr(asyncio, "sleep", lambda _s: real_sleep(0))
        clob = _live_clob(live_order_timeout_seconds=0.01)
        first = {"status": "LIVE", "order_id": "o1", "filled_size": 20.0, "avg_price": 0.5, "raw": {}}
        retry = {"status": "LIVE", "order_id": "o2", "filled_size": 160.0, "avg_price": 0.51, "raw": {}}
        clob.place_order = AsyncMock(side_effect=[first, retry])
        clob.cancel_order = AsyncMock(return_value=True)
        clob.get_order = AsyncMock(return_value={"status": "CANCELED", "filled_size": 40.0, "avg_price": 0.5})

        result = await clob.place_order_with_timeout(_order("GTC", price=0.5, size=100.0))

        assert clob.place_order.await_count == 2
        retry_order = clob.place_order.await_args_list[1].args[0]
        # intended 200 shares; venue confirmed 40 filled → remainder 160 shares = $80 at 0.5
        assert retry_order.size_usdc == pytest.approx(160.0 * 0.5)
        # retry crosses the book at the configured wider cap
        assert clob.place_order.await_args_list[1].kwargs["slippage_override"] == pytest.approx(
            clob.config.copy_trading.live_retry_slippage_pct
        )
        # total filled = confirmed + retry fill, never more than intended
        assert result["filled_size"] == pytest.approx(200.0)

    async def test_failed_cancel_is_ambiguous_and_blocks_the_retry(self):
        clob = _live_clob(live_order_timeout_seconds=0.01)
        clob.place_order = AsyncMock(
            return_value={"status": "LIVE", "order_id": "o1", "filled_size": 0.0, "avg_price": None, "raw": {}}
        )
        clob.cancel_order = AsyncMock(return_value=False)
        await clob.place_order_with_timeout(_order("GTC"))
        assert clob.place_order.await_count == 1

    async def test_unavailable_confirm_is_ambiguous_and_blocks_the_retry(self):
        clob = _live_clob(live_order_timeout_seconds=0.01)
        clob.place_order = AsyncMock(
            return_value={"status": "LIVE", "order_id": "o1", "filled_size": 0.0, "avg_price": None, "raw": {}}
        )
        clob.cancel_order = AsyncMock(return_value=True)
        clob.get_order = AsyncMock(return_value=None)
        await clob.place_order_with_timeout(_order("GTC"))
        assert clob.place_order.await_count == 1


# ─── Paper-fill and slippage math (api/clob_client.py) ────────────────────────


class TestPaperFillMath:
    """Paper fills are price-shaped: fee = rate·p·(1−p); slippage scales only
    above the size threshold, bounded by the max multiplier (M11/H5)."""

    @given(
        price=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        rate=st.floats(min_value=0.0, max_value=0.25, allow_nan=False),
    )
    def test_taker_fee_is_price_shaped_and_vanishes_at_the_extremes(self, price, rate):
        fee = taker_fee_per_share(price, rate)
        assert fee == pytest.approx(rate * price * (1.0 - price))
        assert fee <= rate * 0.25 + 1e-12  # maximum at p=0.5
        assert taker_fee_per_share(0.0, rate) == 0.0
        assert taker_fee_per_share(1.0, rate) == 0.0

    @given(
        price=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        slip=st.floats(min_value=0.0, max_value=0.10, allow_nan=False),
        rate=st.floats(min_value=0.0, max_value=0.25, allow_nan=False),
    )
    def test_fill_prices_never_leave_the_token_range(self, price, slip, rate):
        assert 0.0 <= gross_buy_fill_price(price, slip, rate) <= 1.0
        assert 0.0 <= net_sell_fill_price(price, slip, rate) <= 1.0

    @given(size=st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False))
    def test_size_multiplier_is_identity_below_threshold_and_bounded_above(self, size):
        clob = ClobClient(AppConfig(mode="paper"))
        ct = clob.config.copy_trading
        mult = clob._size_multiplier(size)
        if size <= ct.slippage_size_threshold_usdc:
            assert mult == 1.0
        else:
            assert 1.0 <= mult <= ct.slippage_size_max_mult

    def test_paper_results_reconcile_as_a_full_fill_at_the_paper_price(self):
        """Reconciliation is a deliberate no-op for paper results — paper
        behavior must stay byte-for-byte unchanged by live-fill handling."""
        filled, avg = CopyTrader._reconcile_fill({"status": "PAPER", "fill_price": 0.51}, 100.0, 0.50)
        assert filled == 100.0
        assert avg == 0.51


class TestFeeRatePrecedence:
    """Fee-rate precedence: CLOB market info → Gamma metadata → config fallback
    (CLAUDE.md 'Money math'); absurd rates are rejected, not propagated."""

    def _market(self, fee_rate):
        return Market(condition_id="m", fee_rate=fee_rate)

    def test_clob_rate_wins_when_present(self):
        rate, source = CopyTrader._fee_rate_for_market(self._market(0.03), 0.02, 0.045)
        assert (rate, source) == (0.02, "clob_market_info")

    def test_gamma_rate_wins_when_clob_missing(self):
        rate, source = CopyTrader._fee_rate_for_market(self._market(0.03), None, 0.045)
        assert (rate, source) == (0.03, "gamma_market")

    def test_config_fallback_when_both_missing(self):
        rate, source = CopyTrader._fee_rate_for_market(self._market(None), None, 0.045)
        assert (rate, source) == (0.045, "config")

    def test_absurd_clob_rate_is_rejected_and_falls_through(self):
        rate, source = CopyTrader._fee_rate_for_market(self._market(0.03), 5.0, 0.045)
        assert (rate, source) == (0.03, "gamma_market")


# ─── Kelly sizing (core/sizing.py) ────────────────────────────────────────────


class TestKellySizing:
    """Kelly is opt-in and hard-capped; no edge means no bet."""

    @given(
        win_prob=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        price=st.floats(min_value=0.01, max_value=0.99, allow_nan=False),
        bankroll=st.floats(min_value=1.0, max_value=1_000_000, allow_nan=False),
    )
    def test_kelly_size_never_exceeds_the_hard_cap(self, win_prob, price, bankroll):
        size = kelly_size_usdc(win_prob, price, bankroll, kelly_multiplier=0.25, max_pct=0.02)
        assert 0.0 <= size <= bankroll * 0.02 + 1e-9

    @given(
        price=st.floats(min_value=0.01, max_value=0.99, allow_nan=False),
        frac=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    def test_no_edge_means_no_bet(self, price, frac):
        """win_prob at or below the market-implied probability → (near-)zero
        fraction; tolerance covers float cancellation at win_prob == price."""
        assert kelly_fraction(price * frac, price) <= 1e-9

    def test_tracker_seeded_edge_is_capped_before_sizing(self):
        """H18: one lucky sample cannot push the implied edge past max_edge."""
        capped = kelly_size_from_edge(
            10.0, 0.5, 10_000, kelly_multiplier=0.25, max_pct=0.02, edge_shrink=1.0, max_edge=0.20
        )
        at_cap = kelly_size_usdc(0.5 + 0.20, 0.5, 10_000, kelly_multiplier=0.25, max_pct=0.02)
        assert capped == pytest.approx(at_cap)


# ─── Trader scoring (core/tracker.py::TraderScorer) ───────────────────────────


def _stats(**kw) -> TraderStats:
    defaults = dict(
        address="0x" + "a" * 40,
        pseudonym="whale",
        total_pnl=50_000.0,
        trade_count=200,
        win_rate=0.9,
        pnl_per_trade=[0.05] * 200,
        last_trade_time=time.time(),
    )
    defaults.update(kw)
    return TraderStats(**defaults)


class TestTraderScoring:
    """Score = (4.0·sharpe + 3.5·consistency + 2.5·recency) / 10 — a weighted
    SUM with a Sharpe cap, small-sample shrinkage, and an expectancy gate
    (win-rate is soft). Verified at commit fc65b31; README's '×' formula is
    stale (audit DD-15)."""

    def test_score_is_a_weighted_sum_not_a_product(self):
        """A dormant trader (recency = 0) must still be scoreable — under the
        README's multiplicative formula the score would collapse to zero."""
        scorer = TraderScorer(TrackerConfig())
        scored = scorer.score(_stats(last_trade_time=0.0))
        assert scored is not None
        assert scored.recency_weight == 0.0
        assert scored.score > 0.0
        expected = (4.0 * scored.sharpe_proxy + 3.5 * scored.consistency + 2.5 * 0.0) / 10.0
        assert scored.score == pytest.approx(expected)

    def test_sharpe_is_capped_at_the_configured_cap(self):
        scorer = TraderScorer(TrackerConfig())
        scored = scorer.score(_stats())  # zero-variance returns → raw sharpe is huge
        assert scored is not None
        assert scored.sharpe_proxy == scorer.cfg.sharpe_cap

    def test_small_samples_shrink_sharpe_toward_zero(self):
        cfg = TrackerConfig()
        scorer = TraderScorer(cfg)
        stats = _stats(trade_count=10, pnl_per_trade=[0.05, 0.15, -0.02, 0.08, 0.11] * 2)
        shrunk = scorer._capped_sharpe(stats)
        assert shrunk == pytest.approx(min(stats.sharpe_proxy * (10 / cfg.sharpe_shrink_min_trades), cfg.sharpe_cap))

    def test_expectancy_gates_eligibility_but_low_win_rate_does_not(self):
        """H16: the hard eligibility gate is expectancy; a win rate below
        min_win_rate alone must NOT disqualify a trader."""
        scorer = TraderScorer(TrackerConfig())
        low_win_rate = _stats(win_rate=0.20)
        assert scorer.score(low_win_rate) is not None
        no_expectancy = _stats(pnl_per_trade=[0.0001] * 200)
        assert scorer.score(no_expectancy) is None


# ─── Monitor dedup, cold start, jitter, WS hygiene (core/monitor.py) ──────────


def _monitor(**kw) -> TradeMonitor:
    defaults = dict(tracked_wallets=["0xwallet"], on_trade=AsyncMock(), jitter_seed=42)
    defaults.update(kw)
    return TradeMonitor(**defaults)


def _trade(i: int) -> dict:
    return {"id": f"t{i}", "type": "trade", "side": "BUY", "market": "m", "asset": "a", "price": "0.5", "size": "10"}


class TestMonitorDedupAndColdStart:
    """_seen_trade_ids is an OrderedDict with FIFO eviction; the first poll per
    wallet only primes the baseline (CLAUDE.md concurrency rules)."""

    def test_first_poll_primes_the_baseline_without_emitting_trades(self):
        m = _monitor()
        out = m._filter_new_trades("0xwallet", [_trade(i) for i in range(5)], prime=True)
        assert out == []
        assert len(m._seen_trade_ids["0xwallet"]) == 5

    def test_recently_seen_trades_are_never_re_detected(self):
        m = _monitor()
        batch = [_trade(i) for i in range(50)]
        assert len(m._filter_new_trades("0xwallet", batch)) == 50
        assert m._filter_new_trades("0xwallet", batch) == []

    def test_seen_id_eviction_is_fifo_and_bounded(self):
        """Overflow must evict the OLDEST ids; evicting an arbitrary recent id
        would let the next poll re-copy a trade it already acted on."""
        m = _monitor()
        m._filter_new_trades("0xwallet", [_trade(i) for i in range(150)])
        seen = m._seen_trade_ids["0xwallet"]
        assert len(seen) == 100  # bounded at 2 × _MAX_TRADES_PER_POLL
        assert "t0" not in seen and "t49" not in seen  # oldest evicted
        assert "t50" in seen and "t149" in seen  # newest retained
        # the most recent poll window must yield nothing new
        assert m._filter_new_trades("0xwallet", [_trade(i) for i in range(100, 150)]) == []

    def test_wallet_addresses_are_lowercased_at_ingestion(self):
        m = _monitor(tracked_wallets=["0xABCDEF"])
        assert m._wallets == ["0xabcdef"]

    async def test_set_wallets_preserves_seen_ids_for_retained_wallets(self):
        m = _monitor()
        m._filter_new_trades("0xwallet", [_trade(1)])
        await m.set_wallets(["0xWALLET", "0xnew"])
        assert "t1" in m._seen_trade_ids["0xwallet"]
        assert m._seen_trade_ids["0xnew"] == {}


class TestMonitorJitter:
    """H17: poll cadence is jittered within bounds and floored — do not
    'simplify' the interval math back to a fixed period."""

    def test_poll_interval_jitter_is_bounded_and_floored(self):
        m = _monitor(poll_interval=8.0, poll_jitter=2.0)
        draws = [m._next_interval() for _ in range(500)]
        assert all(6.0 - 1e-9 <= d <= 10.0 + 1e-9 for d in draws)
        assert len(set(round(d, 6) for d in draws)) > 1  # actually varies

    def test_zero_jitter_restores_the_deterministic_interval(self):
        m = _monitor(poll_interval=8.0, poll_jitter=0.0)
        assert m._next_interval() == 8.0


class TestWebSocketTickHygiene:
    """Price ticks are emitted only for subscribed tokens with an in-range,
    numeric price. (Known gap: a MISSING price field defaults to 0.0 and passes
    — audit DD-05. These pins cover what the guard does enforce today.)"""

    async def test_out_of_range_or_non_numeric_ws_prices_are_dropped(self):
        import json

        ticks: list[PriceTick] = []

        async def on_price(t):
            ticks.append(t)

        m = _monitor(on_price=on_price)
        m.subscribe_token("tok")
        for bad in (1.5, -0.2, "abc", None):
            await m._handle_ws_message(json.dumps([{"event_type": "price_change", "asset_id": "tok", "price": bad}]))
        assert ticks == []
        await m._handle_ws_message(json.dumps([{"event_type": "price_change", "asset_id": "tok", "price": 0.42}]))
        assert [(t.token_id, t.price) for t in ticks] == [("tok", 0.42)]

    async def test_ticks_for_unsubscribed_tokens_are_ignored(self):
        import json

        ticks: list[PriceTick] = []

        async def on_price(t):
            ticks.append(t)

        m = _monitor(on_price=on_price)
        await m._handle_ws_message(json.dumps([{"event_type": "price_change", "asset_id": "other", "price": 0.4}]))
        assert ticks == []


# ─── Copier orchestration invariants (core/copier.py) ─────────────────────────


@pytest.fixture
def paper_config() -> AppConfig:
    return AppConfig(mode="paper", bankroll=10_000)


@pytest.fixture
async def paper_portfolio(tmp_path):
    pm = PortfolioManager(db_path=str(tmp_path / "invariants.db"))
    await pm.init()
    yield pm
    await pm.close()


@pytest.fixture
def paper_gamma():
    g = AsyncMock()
    g.get_market = AsyncMock(
        return_value=Market(condition_id="mkt-a", question="Q?", volume_24h=50_000, active=True, resolve_time=None)
    )
    g.get_market_price = AsyncMock(return_value=0.50)
    g.get_market_fee_rate = AsyncMock(return_value=None)
    return g


@pytest.fixture
def paper_copier(paper_config, paper_portfolio, paper_gamma) -> CopyTrader:
    risk = RiskManager(config=RiskConfig(), bankroll=paper_config.bankroll)
    return CopyTrader(risk, paper_portfolio, ClobClient(paper_config), paper_gamma, paper_config)


def _buy_event(price=0.50, size=100.0, market="mkt-a", token="tok-a", wallet="0xwhale") -> TradeEvent:
    return TradeEvent(
        event_id=f"e-{time.monotonic_ns()}",
        wallet_address=wallet,
        market_id=market,
        token_id=token,
        outcome_label="Yes",
        trade_type=TradeType.BUY,
        price=price,
        size_usdc=size,
        timestamp=time.time(),
        transaction_hash="0xhash",
    )


class TestEntryRollbackInvariants:
    """After build_position() reserves exposure, EVERY failure path must fully
    roll back: exposure (market AND trader), the position cache, and the
    pending-entry counter (CLAUDE.md failure-path rules, tag H12)."""

    async def test_failed_order_rolls_back_exposure_cache_and_pending_counter(self, paper_copier):
        paper_copier.clob.place_order_with_timeout = AsyncMock(side_effect=RuntimeError("venue down"))
        await paper_copier.handle_trade_event(_buy_event())
        assert await paper_copier.portfolio.position_count() == 0
        assert paper_copier.risk.market_exposure("mkt-a") == 0.0
        assert paper_copier.risk.trader_exposure("0xwhale") == 0.0
        assert paper_copier._pos_cache == {}
        assert paper_copier._pending_entries == 0

    async def test_zero_fill_releases_the_full_registered_notional(self, paper_copier):
        paper_copier.clob.place_order_with_timeout = AsyncMock(
            return_value={"status": "LIVE", "order_id": "o", "filled_size": 0.0, "avg_price": None, "raw": {}}
        )
        await paper_copier.handle_trade_event(_buy_event())
        assert await paper_copier.portfolio.position_count() == 0
        assert paper_copier.risk.market_exposure("mkt-a") == 0.0
        assert paper_copier.risk.trader_exposure("0xwhale") == 0.0
        assert paper_copier._pending_entries == 0

    async def test_partial_fill_releases_the_unfilled_fraction_of_registered_notional(self, paper_copier):
        intended_shares = 50.0 / gross_buy_fill_price(0.50, 0.005, 0.08)
        filled_shares = intended_shares * 0.4
        paper_copier.clob.place_order_with_timeout = AsyncMock(
            return_value={
                "status": "LIVE",
                "order_id": "o",
                "filled_size": filled_shares,
                "avg_price": 0.50,
                "raw": {},
            }
        )
        await paper_copier.handle_trade_event(_buy_event())
        positions = await paper_copier.portfolio.get_open_positions()
        assert len(positions) == 1
        assert positions[0].size_shares == pytest.approx(filled_shares)
        # A 40% fill keeps 40% of the registered $50 all-in budget.
        assert paper_copier.risk.market_exposure("mkt-a") == pytest.approx(20.0)
        assert paper_copier._pending_entries == 0

    async def test_pending_entries_are_counted_against_the_position_cap(self, paper_copier):
        """H12: positions with reserved exposure but no DB row yet must count
        toward max_concurrent_positions, or two in-flight copies double-open."""
        paper_copier._pending_entries = paper_copier.config.copy_trading.max_concurrent_positions
        await paper_copier.handle_trade_event(_buy_event())
        assert await paper_copier.portfolio.position_count() == 0

    async def test_trading_halt_blocks_the_entry_path(self, paper_copier):
        paper_copier.risk._cooldown_until = time.time() + 600
        await paper_copier.handle_trade_event(_buy_event())
        assert await paper_copier.portfolio.position_count() == 0


class TestExitInvariants:
    """Exits: up to 3 attempts; the DB row is closed ONLY after a confirmed
    non-zero fill; a permanently-failing exit leaves the position open; a
    double-trigger records exactly one close (C3/C4)."""

    async def _open_paper_position(self, copier) -> Position:
        await copier.handle_trade_event(_buy_event())
        positions = await copier.portfolio.get_open_positions()
        assert len(positions) == 1
        return positions[0]

    async def test_exits_proceed_even_while_entries_are_halted(self, paper_copier):
        pos = await self._open_paper_position(paper_copier)
        paper_copier.risk._cooldown_until = time.time() + 600  # halt entries
        await paper_copier.handle_price_tick(PriceTick(token_id=pos.token_id, price=pos.sl_price))
        assert await paper_copier.portfolio.position_count() == 0

    async def test_zero_fill_exit_retries_three_times_and_leaves_the_position_open(self, paper_copier, monkeypatch):
        pos = await self._open_paper_position(paper_copier)
        zero_fill = AsyncMock(
            return_value={"status": "LIVE", "order_id": "o", "filled_size": 0.0, "avg_price": None, "raw": {}}
        )
        paper_copier.clob.place_order_with_timeout = zero_fill
        # Collapse the exit path's 1s/2s backoff sleeps so the suite stays fast.
        real_sleep = asyncio.sleep
        monkeypatch.setattr(asyncio, "sleep", lambda _s: real_sleep(0))

        await paper_copier.handle_price_tick(PriceTick(token_id=pos.token_id, price=pos.sl_price))

        assert zero_fill.await_count == 3
        assert await paper_copier.portfolio.position_count() == 1  # still open for the next sweep

    async def test_db_close_happens_only_after_a_confirmed_fill(self, paper_copier):
        pos = await self._open_paper_position(paper_copier)
        await paper_copier.handle_price_tick(PriceTick(token_id=pos.token_id, price=pos.sl_price))
        assert await paper_copier.portfolio.position_count() == 0
        report = await paper_copier.portfolio.realized_pnl_report()
        assert report["disposals"] == 1
        # exposure fully released on close
        assert paper_copier.risk.total_exposure() == pytest.approx(0.0, abs=1e-6)


class TestDoubleCloseGuard:
    """C4: `AND status='open'` + the rowcount check make close_position a
    single-winner operation; the loser gets None and must skip record_exit."""

    async def test_second_close_returns_none_and_records_a_single_tax_lot(self, paper_portfolio):
        rm = _rm()
        pos = await rm.build_position("p1", "mkt", "tok", "0xw", entry_price=0.5, size_shares=100)
        await paper_portfolio.open_position(pos)

        first = await paper_portfolio.close_position("p1", 0.6, ExitReason.TAKE_PROFIT)
        second = await paper_portfolio.close_position("p1", 0.6, ExitReason.SOURCE_EXIT)

        assert first == pytest.approx(10.0)
        assert second is None
        report = await paper_portfolio.realized_pnl_report()
        assert report["disposals"] == 1

    async def test_conservative_unrealized_pnl_is_never_positive(self, paper_portfolio):
        rm = _rm()
        for i, entry in enumerate((0.30, 0.55, 0.80)):
            pos = await rm.build_position(f"p{i}", f"m{i}", f"t{i}", "0xw", entry_price=entry, size_shares=10)
            await paper_portfolio.open_position(pos)
        assert await paper_portfolio.get_open_unrealized_pnl_conservative() <= 0.0


# ─── Live-mode CLI override revalidation (config.py / main.py) ────────────────


class TestLiveModeCliOverrideRevalidation:
    """DD-02 (fixed upstream, commit b666acf): the --mode live CLI override
    must re-trigger the same private-key / signature_type=3-funder checks
    load_config() enforces for a YAML-declared mode: live — an override must
    never bypass load-time live-mode gating (SECURITY.md #2)."""

    async def test_cli_mode_override_to_live_revalidates_key_and_funder_checks(self, tmp_path, monkeypatch):
        monkeypatch.delenv("POLY_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("POLY_FUNDER", raising=False)
        monkeypatch.delenv("POLY_SIGNATURE_TYPE", raising=False)
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("mode: paper\nbankroll: 500\n")

        # A YAML mode of "paper" must load cleanly — the check must not fire
        # for the mode that's actually shipping.
        load_config(config_path=str(cfg_path))

        # Applying --mode live through main.run_bot's override path must raise
        # BEFORE any network I/O (aiohttp session, geoblock preflight) happens.
        from polymarket_copier.main import run_bot

        with pytest.raises(ConfigError, match="POLY_PRIVATE_KEY"):
            await run_bot(config_path=str(cfg_path), mode="live")

    async def test_cli_mode_override_to_live_revalidates_deposit_wallet_funder(self, tmp_path, monkeypatch):
        monkeypatch.setenv("POLY_PRIVATE_KEY", "0x" + "1" * 64)
        monkeypatch.setenv("POLY_SIGNATURE_TYPE", "3")
        monkeypatch.delenv("POLY_FUNDER", raising=False)
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("mode: paper\nbankroll: 500\n")

        from polymarket_copier.main import run_bot

        with pytest.raises(ConfigError, match="POLY_FUNDER"):
            await run_bot(config_path=str(cfg_path), mode="live")


# ─── Config coupling and shipped-yaml drift (config.py / config.yaml) ─────────


class TestConfigCoupling:
    """The slippage/retry fields are coupled by a model_validator — read it
    before touching any of them (CLAUDE.md config rules)."""

    def test_paper_slippage_may_never_exceed_the_live_cap(self):
        with pytest.raises(ValueError, match="max_live_slippage_pct"):
            AppConfig(
                copy_trading={
                    "paper_fill_slippage_pct": 0.02,
                    "max_live_slippage_pct": 0.01,
                    "live_retry_slippage_pct": 0.02,
                }
            )

    def test_retry_slippage_must_cross_more_of_the_book_than_the_base_cap(self):
        with pytest.raises(ValueError, match="live_retry_slippage_pct"):
            AppConfig(copy_trading={"live_retry_slippage_pct": 0.005, "max_live_slippage_pct": 0.01})

    def test_live_retries_are_bounded_to_at_most_one(self):
        with pytest.raises(ValueError, match="live_order_max_retries"):
            AppConfig(copy_trading={"live_order_max_retries": 2})


class TestShippedYamlNeverDriftsFromCodeDefaults:
    """Every value in the shipped config.yaml must equal the config.py default
    (repo convention: 'Keep them in sync'). The pre-existing
    TestShippedConfigMatchesCodeDefaults pins 4 historical fields; this pins
    the whole file so no future edit to either side ships silently (audit
    DD-22 / fact-check §3.1 overstatement)."""

    def _assert_subtree_matches(self, model, data: dict, path: str = "") -> None:
        for key, value in data.items():
            assert hasattr(model, key), f"config.yaml key '{path}{key}' does not exist on {type(model).__name__}"
            attr = getattr(model, key)
            if isinstance(value, dict):
                self._assert_subtree_matches(attr, value, path=f"{path}{key}.")
            elif isinstance(value, float) or isinstance(attr, float):
                assert attr == pytest.approx(value), f"'{path}{key}': yaml={value!r} != default={attr!r}"
            else:
                assert attr == value, f"'{path}{key}': yaml={value!r} != default={attr!r}"

    def test_every_shipped_yaml_value_matches_code_default(self):
        repo_root = Path(__file__).resolve().parent.parent
        with open(repo_root / "config.yaml") as f:
            shipped = yaml.safe_load(f)
        assert isinstance(shipped, dict) and shipped, "shipped config.yaml is missing or empty"
        self._assert_subtree_matches(AppConfig(), shipped)
