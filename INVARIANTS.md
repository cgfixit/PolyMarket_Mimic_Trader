# INVARIANTS.md — Read this before touching any code file

This file lists the behavioral invariants of this bot that **must never change silently**,
the test that proves each one, and the known divergences you must not "fix" without asking.
It complements CLAUDE.md (how to work here) and AGENTS.md (claim discipline); where those
documents disagree with code, **the code is right** — but where a test below disagrees with
your change, **the test is right** until a maintainer explicitly retires the invariant.

Provenance: 2026-07-08 due-diligence audit at commit `05ef1cd`
(`docs/DUE_DILIGENCE_AUDIT_2026-07-08.md` — claim/reality/exploit for every finding).
Unless stated otherwise, "test" means `tests/test_invariants.py::<name>`.

**Rules of engagement**

1. If your change makes any test below fail, the change is wrong until proven otherwise —
   present the failure to the maintainer; do not weaken or delete the test to get green.
2. Open entries in "Known divergences" are *documented, not fixed*. Fixing an open entry
   touches trading math, order flow, or live gating → **Tier 2, ask first** (CLAUDE.md
   escalation ladder). Fixed entries remain only as historical anchors. Never pin a known
   bug with a new test.
3. Adding a new invariant? Add the test in `tests/test_invariants.py`, named after the
   invariant, and add a row here in the same PR.

---

## 1. Money math

| Invariant | Enforced at | Proven by |
|---|---|---|
| TP is strictly above SL for every valid entry price | `risk_manager.py::_compute_thresholds` | `test_tp_is_strictly_above_sl_for_every_entry` |
| TP/SL always stay inside the token's [0, 1] range | same | `test_thresholds_stay_inside_token_bounds` |
| Thresholds are rounded to exactly 6 decimals | same | `test_thresholds_are_rounded_to_six_decimals` |
| Reward:risk ≥ `min_reward_risk` **inside the default entry band [0.05, 0.95]** (see DD-04 for why not beyond) | same (H2) | `test_reward_risk_floor_holds_across_default_entry_band` |
| Low entries (< `low_entry_threshold`) get a tapered TP fraction, never the full 40 % | same (L5) | `test_low_entry_tp_taper_targets_less_than_full_fraction` |
| Only `_compute_thresholds()` computes TP/SL — its three call sites in `copier.py` must stay consistent; never re-derive locally | CLAUDE.md rule | structure pins above; grep `_compute_thresholds` before changing call sites |
| Trailing stop = `peak − (peak − entry) × fraction`, floored at hard SL (H1 — NOT the old peak-to-SL-gap formula) | `risk_manager.py::_compute_trail_sl` | `test_trailing_stop_formula_is_run_up_from_entry_not_peak_to_sl_gap`, `test_trailing_stop_never_drops_below_hard_sl` |
| Trader score is a weighted **sum** `(4.0·sharpe + 3.5·consistency + 2.5·recency)/10` — not a product | `tracker.py::TraderScorer.score` (H14) | `test_score_is_a_weighted_sum_not_a_product` |
| Sharpe proxy is capped at `sharpe_cap` and shrunk for samples < `sharpe_shrink_min_trades` | `tracker.py::TraderScorer._capped_sharpe` | `test_sharpe_is_capped_at_the_configured_cap`, `test_small_samples_shrink_sharpe_toward_zero` |
| Expectancy is the hard eligibility gate; low win rate alone never disqualifies | `tracker.py::TraderScorer._is_eligible` (H16) | `test_expectancy_gates_eligibility_but_low_win_rate_does_not` |
| Paper taker fee is price-shaped: `rate · p · (1 − p)`, zero at both extremes | `clob_client.py::taker_fee_per_share` | `test_taker_fee_is_price_shaped_and_vanishes_at_the_extremes` |
| Simulated fill prices never leave [0, 1] | `clob_client.py::gross_buy_fill_price` / `net_sell_fill_price` | `test_fill_prices_never_leave_the_token_range` |
| Slippage size-scaling is identity at/below the threshold and bounded by `slippage_size_max_mult` above it (M11) | `clob_client.py::_size_multiplier` | `test_size_multiplier_is_identity_below_threshold_and_bounded_above` |
| Fee-rate precedence: CLOB market info → Gamma metadata → config fallback; absurd rates rejected | `copier.py::_fee_rate_for_market` | `TestFeeRatePrecedence` (4 tests) |
| Kelly size never exceeds `bankroll × max_trade_pct`; no edge → no bet; seeded edge capped at `max_edge` | `sizing.py` | `test_kelly_size_never_exceeds_the_hard_cap`, `test_no_edge_means_no_bet`, `test_tracker_seeded_edge_is_capped_before_sizing` |

## 2. Exposure accounting

| Invariant | Enforced at | Proven by |
|---|---|---|
| Exposure accumulates as `Decimal` via `str()` — exact, never float | `risk_manager.py` (`_to_dec`) | `test_exposure_accumulates_exactly_as_decimal_not_float` |
| `build_position()` is the single cap-enforcement point: per-market, per-trader, and total caps all raise before any state is written | `risk_manager.py::build_position` | `test_build_position_enforces_per_market_cap` / `_per_trader_allocation_cap` / `_total_exposure_cap` |
| Every post-reservation failure fully rolls back: exposure (market **and** trader), position cache, pending counter | `copier.py::handle_trade_event` failure paths | `test_failed_order_rolls_back_exposure_cache_and_pending_counter`, `test_zero_fill_releases_the_full_registered_notional` |
| Partial fills release `registered_notional × unfilled_fraction` (registered = pre-fill price × intended shares) | `copier.py` (10b) | `test_partial_fill_releases_the_unfilled_fraction_of_registered_notional` |
| `release_exposure()` without `trader_address` leaks the per-trader allocation — every rollback call site MUST pass it | `risk_manager.py::release_exposure` | `test_release_without_trader_address_leaves_trader_allocation_reserved` |
| Exposure never goes negative (over-release clamps at zero) | same | `test_exposure_never_goes_negative_on_over_release` |
| A `Position` cannot exist without TP/SL — construct only via `build_position()` | `risk_manager.py::Position.__post_init__` | `test_positions_cannot_be_constructed_without_thresholds` |

## 3. The retry matrix (deliberate and asymmetric — do not "improve")

| Invariant | Enforced at | Proven by |
|---|---|---|
| Entry FOK/FAK orders are **never** retried (retry = possible double position) | `clob_client.py::place_order_with_timeout` fast path | `test_fok_entry_is_placed_exactly_once_even_on_zero_fill`, `test_fok_entry_failure_propagates_without_retry` |
| Resting GTC/GTD: cancel at timeout → confirm terminal → retry **once**, sized to the confirmed-unfilled remainder, at the wider retry cap | same (M12) | `test_resting_retry_is_sized_to_the_confirmed_unfilled_remainder` |
| Any ambiguity (cancel failed, confirm unavailable) degrades to NO retry | same | `test_failed_cancel_is_ambiguous_and_blocks_the_retry`, `test_unavailable_confirm_is_ambiguous_and_blocks_the_retry` |
| Exit orders: up to 3 attempts; DB close **only** after a confirmed non-zero fill; permanent failure leaves the position open | `copier.py::_exit_position_locked` | `test_zero_fill_exit_retries_three_times_and_leaves_the_position_open`, `test_db_close_happens_only_after_a_confirmed_fill` |
| Paper reconciliation is a no-op full fill at the paper price (paper behavior byte-for-byte stable) | `copier.py::_reconcile_fill` | `test_paper_results_reconcile_as_a_full_fill_at_the_paper_price` |

## 4. Circuit breakers & halts

| Invariant | Enforced at | Proven by |
|---|---|---|
| `is_trading_halted()` gates **entries only**; position evaluation/exits keep working while halted | `risk_manager.py::is_trading_halted`, `copier.py` 2a | `test_halt_gates_entries_only_never_position_evaluation_exits`, `test_exits_proceed_even_while_entries_are_halted`, `test_trading_halt_blocks_the_entry_path` |
| Only STOP_LOSS / TRAILING_STOP (and reason-less) losses advance the cooldown streak; SOURCE_EXIT / TIME_EXIT don't; any win resets it | `risk_manager.py::_update_cooldown` (L5) | `TestCooldownAndHalt` (5 tests) |
| Conservative unrealized PnL counts toward the daily halt (H3) | `risk_manager.py::is_trading_halted` | `test_unrealized_losses_count_toward_the_daily_halt` |
| The daily-loss window resets at **UTC** midnight regardless of host timezone | `risk_manager.py::_midnight_utc` | `test_daily_window_resets_at_utc_midnight_not_local_midnight` |
| A daily-loss breach flags **every** open position for exit (full liquidation — current design; docs say "halt", see DD-14 before changing either) | `risk_manager.py::evaluate` priority 0 | `test_daily_loss_breach_flags_every_open_position_for_exit` |
| `evaluate()` never mutates the position (peak persistence is the caller's job) | `risk_manager.py::evaluate` | `test_evaluate_never_mutates_the_position` |
| Stale-but-profitable positions are spared the time exit (M8) | same | `test_time_exit_spares_profitable_positions` |

## 5. Monitor: dedup, cold start, jitter

| Invariant | Enforced at | Proven by |
|---|---|---|
| First poll per wallet only primes the baseline — nothing is copied | `monitor.py` `_primed_wallets` | `test_first_poll_primes_the_baseline_without_emitting_trades` |
| `_seen_trade_ids` evicts FIFO (`popitem(last=False)`), bounded at 2× poll size; a recently-seen id can never be re-detected | `monitor.py::_filter_new_trades` | `test_seen_id_eviction_is_fifo_and_bounded`, `test_recently_seen_trades_are_never_re_detected` |
| Poll cadence is jittered within ±`poll_jitter` and floored (H17 front-run resistance) — do not simplify to a fixed period | `monitor.py::_next_interval` | `TestMonitorJitter` (2 tests) |
| Wallet addresses are lowercased at every ingestion boundary | `monitor.py::__init__`/`set_wallets`, `utils/addresses.py` | `test_wallet_addresses_are_lowercased_at_ingestion`, `tests/test_addresses.py` |
| `set_wallets()` keeps seen-id state for retained wallets | `monitor.py::set_wallets` | `test_set_wallets_preserves_seen_ids_for_retained_wallets` |
| WS ticks: only subscribed tokens, only numeric in-range prices | `monitor.py::_handle_ws_message` | `TestWebSocketTickHygiene` (2 tests) |
| All monitor→copier callbacks are `async` and awaited at every call site | `monitor.py` dispatch | `tests/test_integration.py` |

## 6. Persistence

| Invariant | Enforced at | Proven by |
|---|---|---|
| `close_position()` is single-winner: `AND status='open'` + rowcount; the loser gets `None` and must skip `record_exit`/metrics | `portfolio.py::close_position` (C4) | `test_second_close_returns_none_and_records_a_single_tax_lot`; also `tests/test_portfolio.py` |
| Exactly one tax lot per close | same | `test_second_close_returns_none_and_records_a_single_tax_lot` |
| Conservative unrealized PnL is never positive | `portfolio.py::get_open_unrealized_pnl_conservative` | `test_conservative_unrealized_pnl_is_never_positive` |
| Tests use real on-disk SQLite under `tmp_path`, never `:memory:` | test convention | preflight grep |

## 7. Config

| Invariant | Enforced at | Proven by |
|---|---|---|
| The coupled slippage/retry group is validator-enforced: retry cap ≥ live cap, ≤ 0.05 hard ceiling, retries ∈ {0, 1}, paper slip ≤ live cap | `config.py` `@model_validator` | `TestConfigCoupling` (3 tests); `tests/test_config.py` |
| **Every** value in the shipped `config.yaml` equals its `config.py` default | repo convention | `test_every_shipped_yaml_value_matches_code_default` (whole-file pin; supersedes the 4-field `TestShippedConfigMatchesCodeDefaults`) |
| A new risk/copy config field must be wired in `main.py::run_bot`'s `RiskConfig(...)` or read directly off `config.*` at the use site — an unwired field is silently ignored | CLAUDE.md rule | no automated pin; verify by grep before shipping |
| `--mode live` CLI override re-triggers the private-key and `signature_type=3`/funder checks (`validate_live_config()`), not just the YAML/env path (fixed `b666acf`, formerly DD-02) | `config.py::validate_live_config`, `main.py::run_bot` | `test_cli_mode_override_to_live_revalidates_key_and_funder_checks` |

---

## Known divergences — open items remain Tier 2+

Full detail with reproduction output: `docs/DUE_DILIGENCE_AUDIT_2026-07-08.md`.
Fixed entries remain below as historical anchors; do not reopen them without a new failing reproduction.

- ~~**DD-01**~~ **FIXED** (commit `2a383b1`) — `AppConfig.mode` is a validated literal and
  `load_config()` normalizes case before validation. Pinned by `TestModeValidation`.
- ~~**DD-02**~~ **FIXED** (commit `b666acf`) — `--mode live` now calls
  `config.py::validate_live_config()` again after the CLI override applies, so the
  private-key and `signature_type=3`/funder checks both fire regardless of whether `"live"`
  came from YAML or `--mode`. Pinned by
  `test_cli_mode_override_to_live_revalidates_key_and_funder_checks`.
- **DD-03** `record_exit` releases exposure at the fill-mutated `entry_price`, not the
  registered notional — books drift on every reconciled fill.
- **DD-04** `min_reward_risk` floor violated for entries ≳ 0.97 (post-cap TP clamp). The
  invariant test deliberately covers only [0.05, 0.95]; do not widen `max_entry_price`
  without fixing this.
- **DD-05** WS message with a missing `price` field emits a 0.0 tick (would stop-loss every
  position on that token).
- ~~**DD-06**~~ **FIXED** (commit `f6fb2a0`) — cache eviction matches the stable
  `position_id`, so a DB copy with a different debounced peak still removes the live cache row.
- ~~**DD-07**~~ **FIXED** (commit `5c13152`) — `monitor.run()` propagates child failures.
  Pinned by `test_run_propagates_poll_loop_exception`.
- ~~**DD-08**~~ **FIXED** (commit `5c13152`) — subscription changes wake the heartbeat task
  and are pushed without waiting for inbound traffic. Pinned by
  `test_ws_heartbeat_pushes_subscription_update`.
- **DD-09** Tracker rebalance re-adds demoted wallets to `TradeMonitor`; `_demoted_traders`
  filters Kelly priors but does not gate flat-size copies.
- **DD-10** Live fill reconciliation degrades to "assume full fill at quoted price" when the
  venue response lacks fill fields.
- **DD-11** close-plus-tax-lot atomicity holds only by convention (shared connection,
  interleavable commits).
- ~~**DD-12**~~ **FIXED** (commit `d516586`) — `set_wallets()` clears priming for removed
  wallets, so a re-add seeds a fresh baseline. Pinned by
  `test_set_wallets_readded_wallet_is_unprimed`.
- **DD-14** Daily-loss "halt" actually liquidates all open positions (pinned as current
  behavior by `test_daily_loss_breach_flags_every_open_position_for_exit`; docs disagree).
- ~~**DD-23**~~ **FIXED** (commit `99c4ae1`) — tracker activity requests
  `TRADE,REDEEM,REWARD`, reconnecting resolution payouts to the scorer. Pinned by
  `test_fetch_activity_includes_realizations_and_sort`.

Doc-rot items (safe to fix as doc-truth PRs, one concern each): README scoring formula,
TP/SL tables (README + `risk_manager.py` docstring), trailing-stop description, Kelly
narrative, "fee-aware sizing" claim + dead `round_trip_fee_pct`, Prometheus metric names,
`kelly_fraction` key name, SECURITY.md "never retried" wording — see audit DD-15…DD-22.
