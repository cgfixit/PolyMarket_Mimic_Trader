# PolyMarket_Mimic_Trader Real-Money Feasibility

**Updated:** 2026-07-05
**Code baseline:** `origin/main` at `bc5f107` after PRs #82, #84, #85, #86, #87, #88, and #89.

## Verdict

**Still conditional NO for non-paper real-money mode.**

The latest main branch is materially better than the June review: the bot now uses current Polymarket API shapes, price-shaped taker-fee math, CLOB fee metadata, live geoblock preflight, documented WebSocket heartbeat behavior, `usdcSize` activity notional parsing, timing telemetry, and the canonical `paper_taker_fee_rate` config key.

Those fixes remove several stale implementation blockers. They do **not** prove the strategy is profitable, and they do **not** make the targeted international CLOB a legal or practical real-money venue for a US or Georgia-based operator.

## What Is Fixed On Main

- Current Data API leaderboard path and schema are handled.
- Market WebSocket path and application-level `PING` heartbeat are handled.
- Activity rows can use `usdcSize` for copied trade notional.
- Paper fills use Polymarket's price-shaped taker fee curve: `fee_rate * price * (1 - price)`.
- Market fee metadata is pulled from CLOB/Gamma data when available.
- Live mode has a startup geoblock preflight.
- Deposit-wallet signing config exists: `POLY_SIGNATURE_TYPE` and `POLY_FUNDER`.
- Timing telemetry exists for profitability analysis.
- `config.yaml` uses the canonical `paper_taker_fee_rate` key.

## Why Real-Money Mode Is Still Blocked

1. **Venue and legal mismatch.** The code targets the international crypto CLOB endpoints. For a US/Georgia operator, real-money use needs a current venue-specific legal review and likely a different regulated venue path. The repo's geoblock preflight is a safety check, not permission to trade.
2. **No profitability proof.** There is still no held-out offline backtest that measures selected traders forward, net of spread, slippage, taker fees, latency, skipped fills, no-fills, and market impact.
3. **Paper mode is not a go-live signal.** Paper mode is useful for plumbing and telemetry, but it still cannot prove live fill quality, partial/no-fill selection bias, or thin-book market impact.
4. **The copied signal is delayed and public.** The bot copies after public activity appears. Skilled Polymarket traders appear to earn much of their edge by reacting first; a delayed copier may buy after the source trade has already moved the book.
5. **Trader metrics remain biased.** Worthless-expiry losses and unredeemed positions are still hard to reconstruct from the current activity stream, so historical ROI/win-rate inputs can be inflated.
6. **SDK/auth risk remains.** The repo has deposit-wallet config, but the `py-clob-client-v2` migration and real deposit-wallet order-path proof remain open work.

## Minimum Bar Before Real Money

Do not fund live mode until all of these are true:

- A held-out offline backtest shows positive net expectancy after fees, spread, slippage, latency, and skipped/no-fill modeling.
- Paper mode reports include detection latency, submit latency, observed spread, simulated VWAP, fee, skip reason, and realized PnL by trader and market type.
- Trader scoring is de-biased for missing worthless-expiry losses or explicitly excludes strategies where that bias dominates.
- A venue-specific legal review confirms the operator, state, venue, automation method, and funding path are allowed.
- The exact live auth path is tested with minimal funds and redacted logs, including deposit-wallet behavior if `signature_type=3` is used.
- There is a rollback plan: tiny bankroll, daily loss stop, alerts, no reused hot wallet, and paper mode remains the default.

## Current Next Best Work

1. Build the offline backtest harness and make it the real go-live gate.
2. Add paper/live execution parity reports from real order-book snapshots.
3. De-bias trader metrics for unresolved or worthless outcomes.
4. Re-verify the Polymarket SDK/auth path and decide whether live mode remains in scope.
5. Scope a regulated US venue adapter separately if US real-money trading is a goal.

This is not financial or legal advice. It is the repo-level engineering status after the latest `origin/main` changes.
