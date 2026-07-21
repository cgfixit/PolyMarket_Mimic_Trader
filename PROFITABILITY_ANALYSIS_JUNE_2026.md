# PolyMarket_Mimic_Trader Real-Money Feasibility

**Updated:** 2026-07-20
**Repo snapshot inspected for this recheck:** `origin/main` at `c4c6e1b`.

## Verdict

**Still conditional NO for non-paper real-money mode.**

The latest main branch is materially better than the June review: it now handles price-shaped taker fees, CLOB fee metadata, strict mode validation, current nested WebSocket price changes, resolution activity, `usdcSize` activity notional, timing telemetry, partial exits, conservative all-in BUY sizing, and cold-start re-priming for re-added wallets. Live mode now fails closed before order-session creation while the client remains on unsupported CLOB V1.

Those fixes remove several stale implementation blockers. They do **not** prove the strategy is profitable, and they do **not** make the targeted international CLOB a legal or practical real-money venue for a US or Georgia-based operator.

## Current-Source Recheck (2026-07-20)

- **[verified external fact]** Polymarket migrated production trading to CLOB V2 on 2026-04-28. Legacy V1 SDKs and V1-signed orders are no longer supported; the supported Python path is `py-clob-client-v2`, with pUSD collateral and the V2 order structure.
- **[verified external fact]** The international API lists the United States as **blocked**, not close-only. Polymarket US is a separate CFTC-designated contract market operated by QCX LLC, with a separate API and API-key authentication model.
- **[verified external fact]** The Data API activity endpoint supports `TRADE`, `REDEEM`, and `REWARD` filters. The federal UIGEA definition depends on applicable federal and state law, the Wire Act addresses specified interstate or foreign wagering transmissions, and Georgia's constitution prohibits listed gambling forms except authorized exceptions.
- **[repo fact]** This repo still pins `py-clob-client>=0.34,<1.0` and uses the legacy `py_clob_client` adapter and order structures. The tracker now requests `TRADE,REDEEM,REWARD`, so redemption payouts reach its resolution-aware scorer; worthless expiries and unredeemed outcomes can still be absent.
- **[inference]** The international live path remains a venue mismatch for a Georgia operator, while the separate Polymarket US venue would require a different, currently absent adapter and its own eligibility/API review.
- **[unknown]** The cited federal and Georgia text does not by itself classify every event contract or automation pattern. Venue-specific counsel is still required.

## What Is Fixed In The Current Tree

- Current Data API leaderboard path and schema are handled.
- Market WebSocket connectivity, application-level `PING`, immediate subscription refresh, and the current nested `price_changes` event shape are handled.
- Activity rows can use `usdcSize` for copied trade notional.
- Paper fills use Polymarket's price-shaped taker fee curve: `fee_rate * price * (1 - price)`.
- Market fee metadata is pulled from CLOB/Gamma data when available.
- Live mode is hard-disabled before order-session creation while the repo uses CLOB V1. The geoblock and forward-paper guards remain readiness code, not an enabled live path.
- Invalid mode values fail closed during configuration loading.
- Deposit-wallet signing config exists: `POLY_SIGNATURE_TYPE` and `POLY_FUNDER`.
- Timing telemetry exists for profitability analysis.
- `config.yaml` uses the canonical `paper_taker_fee_rate` key.
- Partial exit fills retain and account for the open remainder.
- BUY shares are sized against conservative all-in entry cost so slippage and fees cannot push a configured dollar budget above its ceiling.
- Tracker activity includes `TRADE`, `REDEEM`, and `REWARD`, reconnecting held-to-resolution payouts to the scorer.
- Re-added wallets must seed a fresh cold-start baseline before emitting trades.

## Why Real-Money Mode Is Still Blocked

1. **Venue and legal mismatch.** The code targets the international crypto CLOB, whose official geoblock lists the United States as blocked. Polymarket US is a separate CFTC-designated venue with a separate API, but this repo has no adapter for it. The geoblock preflight is a safety check, not permission to trade.
2. **No profitability proof.** There is still no held-out offline backtest that measures selected traders forward, net of spread, slippage, taker fees, latency, skipped fills, no-fills, and market impact.
3. **Paper mode is not a go-live signal.** Paper mode is useful for plumbing and telemetry, but it still cannot prove live fill quality, partial/no-fill selection bias, or thin-book market impact.
4. **The copied signal is delayed and public.** The bot copies after public activity appears. Skilled Polymarket traders appear to earn much of their edge by reacting first; a delayed copier may buy after the source trade has already moved the book.
5. **Trader metrics remain biased.** Redemption and reward rows now reach the scorer, but worthless-expiry losses and unredeemed outcomes can still be absent. Historical ROI/win-rate inputs therefore remain incomplete even though the earlier resolution-fetch disconnect is fixed.
6. **The live client is on an unsupported protocol.** Production trading moved to CLOB V2, while this repo still uses the legacy V1 package and order structures. Deposit-wallet configuration does not make that adapter compatible. A V2 migration and minimal-funds order-path proof are prerequisites, not optional hardening.
7. **Breaker persistence is incomplete.** Daily PnL, consecutive-loss cooldown, and cooldown expiry remain in-memory state, and the shipped `drawdown_stop_pct` setting is not wired into the runtime risk configuration.

## Minimum Bar Before Real Money

Do not fund live mode until all of these are true:

- A held-out offline backtest shows positive net expectancy after fees, spread, slippage, latency, and skipped/no-fill modeling.
- Paper mode reports include detection latency, submit latency, observed spread, simulated VWAP, fee, skip reason, and realized PnL by trader and market type.
- Trader scoring is de-biased for missing worthless-expiry losses or explicitly excludes strategies where that bias dominates.
- A venue-specific legal review confirms the operator, state, venue, automation method, and funding path are allowed.
- The live adapter uses the supported CLOB V2 SDK, pUSD collateral model, V2 order structure, and current auth/signing flow.
- The exact live auth and order path is tested with minimal funds and redacted logs.
- There is a rollback plan: tiny bankroll, daily loss stop, alerts, no reused hot wallet, and paper mode remains the default.

## Current Next Best Work

1. Decide whether to migrate to international CLOB V2 or remove that live path; scope a Polymarket US adapter separately for US real-money trading.
2. Build the offline backtest harness and make it the real go-live gate.
3. Add paper/live execution parity reports from real order-book snapshots.
4. De-bias trader metrics for worthless expiries and unredeemed outcomes.

## Primary Sources Rechecked (accessed 2026-07-20)

- [Polymarket trading overview](https://docs.polymarket.com/trading/overview)
- [Polymarket CLOB V2 migration guide](https://docs.polymarket.com/v2-migration)
- [Polymarket changelog](https://docs.polymarket.com/changelog)
- [Polymarket user activity API](https://docs.polymarket.com/api-reference/core/get-user-activity)
- [Polymarket geographic restrictions](https://docs.polymarket.com/api-reference/geoblock)
- [Polymarket US API introduction](https://docs.polymarket.us/api-reference/introduction)
- [CFTC designation for QCX LLC d/b/a Polymarket US](https://www.cftc.gov/IndustryOversight/IndustryFilings/TradingOrganizations/49571)
- [31 U.S.C. 5362](https://uscode.house.gov/view.xhtml?edition=prelim&num=0&req=granuleid%3AUSC-prelim-title31-section5362)
- [18 U.S.C. 1084](https://uscode.house.gov/view.xhtml?edition=prelim&num=0&req=granuleid%3AUSC-prelim-title18-section1084)
- [Georgia Constitution, revised 2025](https://sos.ga.gov/georgia-constitution-revised-2025)

This is not financial or legal advice. It is the repo-level engineering status after the latest `origin/main` changes.
