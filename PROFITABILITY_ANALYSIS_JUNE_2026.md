# PolyMarket_Mimic_Trader Real-Money Feasibility

**Updated:** 2026-07-12
**Repo snapshot inspected for this recheck:** `origin/main` at `c286279` plus the current money-mode branch.

## Verdict

**Still conditional NO for non-paper real-money mode.**

The latest main branch is materially better than the June review: it now handles current Polymarket API shapes, price-shaped taker fees, CLOB fee metadata, strict mode validation, live geoblock and forward-paper startup gates, WebSocket heartbeat behavior, `usdcSize` activity notional, timing telemetry, and partial exits.

Those fixes remove several stale implementation blockers. They do **not** prove the strategy is profitable, and they do **not** make the targeted international CLOB a legal or practical real-money venue for a US or Georgia-based operator.

## Current-Source Recheck (2026-07-12)

- **[verified external fact]** Current Polymarket trading docs still recommend `py-clob-client-v2`, L1-to-L2 auth, and deposit-wallet `signature_type=3` plus funder/deposit-wallet address for new API users.
- **[verified external fact]** The international API lists the United States as close-only for both frontend and API order entry. Polymarket US is a separate CFTC-designated contract market operated by QCX LLC.
- **[verified external fact]** The Data API activity endpoint supports `TRADE`, `REDEEM`, and `REWARD` filters. The federal UIGEA definition depends on applicable federal and state law, the Wire Act addresses specified interstate or foreign wagering transmissions, and Georgia's constitution prohibits listed gambling forms except authorized exceptions.
- **[repo fact]** This repo still pins `py-clob-client>=0.34,<1.0`, initializes the international CLOB client, and requests tracker activity with `type=TRADE` even though its scorer contains redemption handling.
- **[inference]** The international live path remains a venue mismatch for a Georgia operator, while the separate Polymarket US venue would require a different, currently absent adapter and its own eligibility/API review.
- **[unknown]** The cited federal and Georgia text does not by itself classify every event contract or automation pattern. Venue-specific counsel is still required.

## What Is Fixed In The Current Tree

- Current Data API leaderboard path and schema are handled.
- Market WebSocket path and application-level `PING` heartbeat are handled.
- Activity rows can use `usdcSize` for copied trade notional.
- Paper fills use Polymarket's price-shaped taker fee curve: `fee_rate * price * (1 - price)`.
- Market fee metadata is pulled from CLOB/Gamma data when available.
- Live mode has a startup geoblock preflight.
- Live mode fail-closes on invalid mode values and requires forward-paper evidence by default.
- Deposit-wallet signing config exists: `POLY_SIGNATURE_TYPE` and `POLY_FUNDER`.
- Timing telemetry exists for profitability analysis.
- `config.yaml` uses the canonical `paper_taker_fee_rate` key.
- Partial exit fills retain and account for the open remainder.
- This branch sizes BUY shares against conservative all-in entry cost so slippage and fees cannot push a configured dollar budget above its ceiling.

## Why Real-Money Mode Is Still Blocked

1. **Venue and legal mismatch.** The code targets the international crypto CLOB, whose official geoblock lists the United States as close-only. Polymarket US is a separate CFTC-designated venue, but this repo has no adapter for it. The geoblock preflight is a safety check, not permission to trade.
2. **No profitability proof.** There is still no held-out offline backtest that measures selected traders forward, net of spread, slippage, taker fees, latency, skipped fills, no-fills, and market impact.
3. **Paper mode is not a go-live signal.** Paper mode is useful for plumbing and telemetry, but it still cannot prove live fill quality, partial/no-fill selection bias, or thin-book market impact.
4. **The copied signal is delayed and public.** The bot copies after public activity appears. Skilled Polymarket traders appear to earn much of their edge by reacting first; a delayed copier may buy after the source trade has already moved the book.
5. **Trader metrics remain biased.** The scorer can process redemptions, but its only activity fetch asks for `type=TRADE`, so held-to-resolution results are disconnected. Worthless-expiry losses can still be absent entirely. Historical ROI/win-rate inputs therefore remain biased.
6. **SDK/auth risk remains.** The repo has deposit-wallet config, but the official current-doc path is still `py-clob-client-v2` plus `signature_type=3` for new API users, while this repo's live client remains on `py-clob-client`; migration and real deposit-wallet order-path proof remain open work.
7. **Breaker persistence is incomplete.** Daily PnL, consecutive-loss cooldown, and cooldown expiry remain in-memory state, and the shipped `drawdown_stop_pct` setting is not wired into the runtime risk configuration.

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
3. Restore redemption visibility and de-bias trader metrics for unresolved or worthless outcomes.
4. Re-verify the Polymarket SDK/auth path and decide whether live mode remains in scope.
5. Scope a Polymarket US adapter separately if US real-money trading is a goal.

## Primary Sources Rechecked

- [Polymarket trading overview](https://docs.polymarket.com/trading/overview)
- [Polymarket user activity API](https://docs.polymarket.com/api-reference/core/get-user-activity)
- [Polymarket geographic restrictions](https://docs.polymarket.com/api-reference/geoblock)
- [CFTC designation for QCX LLC d/b/a Polymarket US](https://www.cftc.gov/IndustryOversight/IndustryFilings/TradingOrganizations/49571)
- [31 U.S.C. 5362](https://uscode.house.gov/view.xhtml?edition=prelim&num=0&req=granuleid%3AUSC-prelim-title31-section5362)
- [18 U.S.C. 1084](https://uscode.house.gov/view.xhtml?edition=prelim&num=0&req=granuleid%3AUSC-prelim-title18-section1084)
- [Georgia Secretary of State constitution publications](https://sos.ga.gov/search?query=constitution)

This is not financial or legal advice. It is the repo-level engineering status after the latest `origin/main` changes.
