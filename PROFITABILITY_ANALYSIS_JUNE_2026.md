# PolyMarket_Mimic_Trader Real-Money Feasibility

**Original analysis updated:** 2026-07-20
**Repo snapshot rechecked:** 2026-08-21, `origin/main` at `13b6563` (prior recheck 2026-08-08 at `24321e8`).

## Verdict

**Still conditional NO for non-paper real-money mode.**

The latest main branch is materially better than the June review: it now handles price-shaped taker fees, CLOB fee metadata, strict mode validation, current nested WebSocket price changes, resolution activity, `usdcSize` activity notional, timing telemetry, partial exits, conservative all-in BUY sizing, and cold-start re-priming for re-added wallets. Live mode now fails closed before order-session creation while the client remains on unsupported CLOB V1.

Those fixes remove several stale implementation blockers. They do **not** prove the strategy is profitable, and they do **not** make the targeted international CLOB a legal or practical real-money venue for a US or Georgia-based operator.

## Current-Source Recheck (2026-07-20)

- **[verified external fact]** Polymarket migrated production trading to CLOB V2 on 2026-04-28. Legacy V1 SDKs and V1-signed orders are no longer supported. As of the 2026-07-20 recheck, official docs named `py-clob-client-v2` as the supported Python path, with pUSD collateral and the V2 order structure. **Superseded for new work by the 2026-08-21 findings:** official docs now recommend unified `polymarket-client`.
- **[verified external fact]** The international API lists the United States as **close-only on both the frontend and API**: existing positions may be closed, but new positions cannot be opened. Polymarket US is a separate CFTC-designated contract market operated by QCX LLC, with a separate API and API-key authentication model.
- **[verified external fact]** The Data API activity endpoint supports `TRADE`, `REDEEM`, and `REWARD` filters. The federal UIGEA definition depends on applicable federal and state law, the Wire Act addresses specified interstate or foreign wagering transmissions, and Georgia's constitution prohibits listed gambling forms except authorized exceptions.
- **[verified branch fact]** This repo still pins `py-clob-client>=0.34,<1.0` and uses the legacy `py_clob_client` adapter and order structures. The tracker requests `TRADE,REDEEM`; non-directional `REWARD` rows and current blank-asset redemptions are excluded from directional scoring. The legacy token-attributed redemption path still assumes a $1 payout when price is absent, while worthless expiries and unredeemed outcomes can be missing.
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
- Tracker activity is normalized chronologically before FIFO matching. `REWARD` and current blank-asset redemption rows are excluded from directional scoring; legacy token-attributed claims still use the documented $1 payout assumption.
- Re-added wallets must seed a fresh cold-start baseline before emitting trades.

## 2026-08-08 FINDINGS SUMMARY

**Repo base:** `origin/main` at `24321e86be0ebe0326274cd82f3d940650f70dcf`; branch findings include the remediation below.

- **[verified branch fact]** `tracker.py::_compute_trader_stats` chronologically normalizes the newest-first activity response, excludes `REWARD` from position realizations, and skips rows without market/token attribution. Legacy token-attributed claims with no price still assume the documented $1 payout. Directional metrics remain candidate signals rather than profitability proof.
- **[verified repo fact]** `copier.py::CopyTrader._reconcile_fill` assumes a full fill at the quoted price when a live response has no concrete fill size. Current order documentation distinguishes an accepted/matched order from a later confirmed or failed trade. A future live path must represent an absent fill as unknown rather than create a position or PnL from it.
- **[verified repo fact]** Paper fills remain synthetic full fills. This is useful plumbing, not execution evidence; realistic evidence requires recorded order-book snapshots with size-aware VWAP plus partial-fill and no-fill replay.
- **[verified external fact]** As of 2026-08-08, official docs still named `py-clob-client-v2` as the supported Python CLOB client, while this tree pinned legacy `py-clob-client`. **Superseded by the 2026-08-21 findings** (unified `polymarket-client`). The runtime hard-disable of live mode is unchanged, so this remains a planning blocker rather than a request to change the running client.
- **[inference]** Separating directional PnL from non-directional income and unknown fills reduces false evidence of copy-trading edge; it does not establish profitability.
- **[unknown]** No repository or public-doc review can establish venue eligibility or legal permission. Counsel remains required.

## 2026-08-21 FINDINGS SUMMARY

**Repo base:** `origin/main` at `13b656365b2ad0fce2a45cee65170bfa4e96241d`. Docs-only recheck of official Python client naming. Verdict is unchanged: **conditional NO**. Live mode stays hard-disabled. This is not a request to migrate the runtime client.

- **[verified external fact]** Official Python docs for new work now recommend unified `polymarket-client` (`from polymarket import PublicClient, AsyncPublicClient, SecureClient, AsyncSecureClient`; GitHub `Polymarket/py-sdk`). See [Python SDK](https://docs.polymarket.com/getting-started/python) and [SDKs & APIs](https://docs.polymarket.com/getting-started/sdks-apis).
- **[verified external fact]** `py-clob-client-v2` is still published as the previous-generation CLOB V2 client. Its README points new projects to `Polymarket/py-sdk`. The [CLOB V2 migration](https://docs.polymarket.com/v2-migration) page still mentions `pip install py-clob-client-v2`. Treat that package as interim/legacy-V2, not as the current new-project path.
- **[verified external fact]** `py-clob-client` (V1) remains unsupported on production; the upstream GitHub repo was archived 2026-05-25.
- **[verified repo fact]** This tree still pins `py-clob-client>=0.34.0,<1.0` (`constraints.txt` `==0.34.6`) and imports `py_clob_client`. `run_bot` still raises on `mode == "live"` before any order session.
- **[verified external fact]** Gamma market listing docs prefer `GET /markets/keyset`; legacy `GET /markets` still exists but is marked for future deprecation. Paper discovery still uses `/markets`. Not a live-mode blocker.
- **[verified external fact]** Data API `REDEEM` rows are per-outcome (changelog 2026-08-10). Successful FAK/FOK `POST /order` no longer returns `transactionHashes` (changelog 2026-07-24); poll `tradeIDs` instead. That feeds the existing open DD-10 fill-accounting gap for any future live path; do not unprompted-fix DD-10.
- **[inference]** A future international live adapter, if ever approved after counsel and a V2/pUSD design, should target `polymarket-client` rather than upgrading only as far as `py-clob-client-v2`.
- **[unknown]** Unified SDK is documented as beta. Exact feature parity with a dedicated CLOB V2 client for copy-trading (FOK/FAK/GTC/GTD, heartbeats, closed-only) is not proven in this tree.

## Why Real-Money Mode Is Still Blocked

1. **Venue and legal mismatch.** The code targets the international crypto CLOB, whose official geoblock lists the United States as close-only on both the frontend and API, prohibiting new orders from US IP space. Polymarket US is a separate CFTC-designated venue with a separate API, but this repo has no adapter for it. The geoblock preflight is a safety check, not permission to trade.
2. **No profitability proof.** There is still no held-out offline backtest that measures selected traders forward, net of spread, slippage, taker fees, latency, skipped fills, no-fills, and market impact.
3. **Paper mode is not a go-live signal.** Paper mode is useful for plumbing and telemetry, but it still cannot prove live fill quality, partial/no-fill selection bias, or thin-book market impact.
4. **The copied signal is delayed and public.** The bot copies after public activity appears. Skilled Polymarket traders appear to earn much of their edge by reacting first; a delayed copier may buy after the source trade has already moved the book.
5. **Trader metrics remain incomplete.** `REWARD` and current blank-asset redemptions are now excluded from directional scoring. Legacy token-attributed claims still assume a $1 payout when price is absent, and worthless-expiry losses or unredeemed outcomes can be missing, so historical ROI/win-rate inputs remain incomplete.
6. **Live fill accounting is optimistic when the venue response is incomplete.** `_reconcile_fill` defaults missing fill fields to a full fill at the current quote. Any future live path must obtain authoritative order/trade state or keep the result unknown; it must not manufacture a position, exposure release, or PnL.
7. **The live client is on an unsupported protocol.** Production trading moved to CLOB V2, while this repo still uses the legacy V1 package and order structures. Official new-project Python is now unified `polymarket-client`; `py-clob-client-v2` is previous-generation. Deposit-wallet configuration does not make the V1 adapter compatible. A current-SDK migration and minimal-funds order-path proof are prerequisites, not optional hardening.
8. **Breaker persistence is incomplete.** Daily PnL, consecutive-loss cooldown, cooldown expiry, and the peak-equity mark behind `drawdown_stop_pct` remain in-memory state, so every breaker forgets its history on process restart. (`drawdown_stop_pct` itself is now wired into the runtime risk configuration as a peak-equity entry halt; the restart-persistence gap is what remains.)

## Minimum Bar Before Real Money

Do not fund live mode until all of these are true:

- A held-out offline backtest shows positive net expectancy after fees, spread, slippage, latency, and skipped/no-fill modeling.
- Paper mode reports include detection latency, submit latency, observed spread, simulated VWAP, fee, skip reason, and realized PnL by trader and market type.
- Trader scoring is de-biased for missing worthless-expiry losses and segregates directional PnL from redemption, reward, rebate, and referral activity; unknown activity remains unscored.
- An absent concrete fill size or price creates no position, exposure release, or PnL in any future live path.
- A venue-specific legal review confirms the operator, state, venue, automation method, and funding path are allowed.
- The live adapter uses the current official Python SDK (`polymarket-client`), pUSD collateral model, V2 order structure, and current auth/signing flow. `py-clob-client-v2` is previous-generation, not the new-project path.
- The exact live auth and order path is tested with minimal funds and redacted logs.
- There is a rollback plan: tiny bankroll, daily loss stop, alerts, no reused hot wallet, and paper mode remains the default.

## Current Next Best Work

1. Decide whether to migrate the international live path to current official `polymarket-client` (CLOB V2 / pUSD), treat `py-clob-client-v2` only as an explicit interim, or remove that live path; scope a Polymarket US adapter separately for US real-money trading.
2. Build the offline backtest harness and make it the real go-live gate.
3. Add paper/live execution parity reports from recorded order-book snapshots, including VWAP, partial-fill, and no-fill replay.
4. De-bias trader metrics for worthless expiries and unredeemed outcomes, and separate directional PnL from reward/rebate/referral income.
5. After the V2 migration decision, reconcile positions only from authoritative order/trade state; missing fill data remains unknown.

## Planning Sources Rechecked (accessed 2026-08-21)

- [Polymarket Python SDK](https://docs.polymarket.com/getting-started/python) — unified `polymarket-client` is the documented new-project path (beta).
- [Polymarket SDKs & APIs](https://docs.polymarket.com/getting-started/sdks-apis)
- [Polymarket CLOB V2 migration](https://docs.polymarket.com/v2-migration) — still documents `py-clob-client-v2` as the dedicated V2 CLOB client.
- [py-clob-client-v2](https://github.com/Polymarket/py-clob-client-v2) — README points new projects to `Polymarket/py-sdk`.
- [py-clob-client](https://github.com/Polymarket/py-clob-client) — archived; V1 not functional on production.
- [Polymarket discover markets](https://docs.polymarket.com/market-data/discover-markets) — `/markets/keyset` preferred; `/markets` still present.
- [Polymarket changelog](https://docs.polymarket.com/changelog/predictions) — 2026-08-10 per-outcome `REDEEM`; 2026-07-24 FAK/FOK `tradeIDs` vs `transactionHashes`.

## Planning Sources Rechecked (accessed 2026-08-08)

- [Polymarket activity API](https://docs.polymarket.com/api-reference/core/get-user-activity) — distinct `REDEEM`, `REWARD`, and rebate/referral activity types.
- [Polymarket order lifecycle](https://docs.polymarket.com/concepts/order-lifecycle) — order acceptance/match and trade confirmation are separate states.
- [Polymarket CLOB V2 migration](https://docs.polymarket.com/v2-migration) — legacy Python CLOB client is V1-only; current production work requires V2.

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
