# PolyMarket_Mimic_Trader Real-Money Feasibility

Formerly `PROFITABILITY_ANALYSIS_JUNE_2026.md`.

**Original analysis updated:** 2026-07-20
**Repo snapshot rechecked:** 2026-09-15, `origin/main` at `5bb13afe294fb55d309b5c1e8348fa7d67fe9239`. Prior rechecks: 2026-09-11 at `d603c16` (PR #149); 2026-08-21 at `13b6563` / `de8eaf8` (PR #143); 2026-08-08 at `24321e8`.

## Verdict

**Still conditional NO for non-paper real-money mode.**

The 2026-09-11 `origin/main` tree is a better paper runtime than the August recheck: shutdown now joins background loops before closing SQLite and API clients, replacement Data/Gamma sessions are owned, timed-out poll waiters are released, portfolio init failures close the connection, and copier latency tests compare clocks that actually match the metrics. Those changes improve evidence quality. They do **not** prove the strategy is profitable, and they do **not** make the targeted international CLOB a legal or practical real-money venue for a US or Georgia-based operator.

Live mode still fails closed before order-session creation while the client remains on unsupported CLOB V1. Official new-project Python is still unified `polymarket-client`. Data API v2 shipped 2026-09-04; this tree still reads frozen v1 `/v1/leaderboard` and legacy `/activity`.

## 2026-09-15 R1 First Slice

**Source:** `225dfc217407678e631ba19945bcdb869289a1f7` on `cx/r1-heldout-paper-replay`, based on the `origin/main` snapshot above. This is paper-only research code; it does not enter `main.py`, create an order client, or change trading/risk configuration.

- **[verified branch fact]** `polymarket_copier/replay.py::build_heldout_report` scores the recorded v1 all-time/recent leaderboard intersection through `tracker.py::TraderScorer`, derives v1 activity statistics through `_compute_trader_stats`, and rejects a held-out event at or before `training_end_timestamp`.
- **[verified branch fact]** Known filled and partial-filled records use `clob_client.py::gross_buy_fill_price` / `net_sell_fill_price`; skipped and no-fill records contribute zero realized PnL; `unknown_fill` records remain separately counted and are excluded from the net-expectancy denominator.
- **[measured fixture result]** `pytest tests/test_heldout_replay.py -q` passed 3 tests locally on 2026-09-15. `python -m polymarket_copier.replay tests/fixtures/r1_heldout_v1.json` rendered 1 full fill, 1 partial fill, 1 no-fill, 2 skips, and 1 unknown fill; its synthetic fixture result was `$25.454230` net PnL and `$5.090846` per known decision. This verifies evaluator accounting only, not market performance.
- **[unknown]** The repository still lacks captured real source activity paired with decision-time quotes, orders, and historical depth. This first slice consumes a captured-decision schema rather than re-implementing the async `CopyTrader` gate chain; R2/R4 remain required before treating results as execution evidence.

## Current-Source Recheck (2026-09-11)

- **[verified external fact]** Polymarket migrated production trading to CLOB V2 on 2026-04-28. Legacy V1 SDKs and V1-signed orders are no longer supported. Official Python docs for new work still recommend unified `polymarket-client` (`from polymarket import PublicClient, AsyncPublicClient, SecureClient, AsyncSecureClient`; GitHub `Polymarket/py-sdk`).
- **[verified external fact]** The international API lists the United States as **close-only on both the frontend and API**: existing positions may be closed, but new positions cannot be opened. Polymarket US is a separate CFTC-designated contract market operated by QCX LLC, with a separate API and API-key authentication model.
- **[verified external fact]** Data API v2 is live at `https://data-api.polymarket.com/v2` as of 2026-09-04. v2 wraps payloads in `data`, paginates with opaque cursors (no offset), and encodes money/size as JSON numbers. `/v1` still serves unchanged but is **frozen**; new fields and endpoints land on v2 only.
- **[verified repo fact]** This tree still pins `py-clob-client>=0.34.0,<1.0` (`constraints.txt` `==0.34.6`) and imports `py_clob_client`. `run_bot` still raises `ConfigError` on `mode == "live"` before any order session (`polymarket_copier/main.py::run_bot`). Tracker and DataClient still call `/v1/leaderboard` and `/activity`.
- **[verified repo fact]** The tracker requests `TRADE,REDEEM`; non-directional `REWARD` rows and current blank-asset redemptions are excluded from directional scoring. The legacy token-attributed redemption path still assumes a $1 payout when price is absent, while worthless expiries and unredeemed outcomes can be missing.
- **[inference]** The international live path remains a venue mismatch for a Georgia operator. A future live adapter, if ever approved after counsel, should target `polymarket-client` and plan a Data API v2 cutover; neither is a request to change the running client in this recheck.
- **[unknown]** The cited federal and Georgia text does not by itself classify every event contract or automation pattern. Venue-specific counsel is still required. Exact Data API v2 field parity with this bot's v1 parsers is unprobed in this tree.

## What Is Fixed In The Current Tree

- Current Data API **v1** leaderboard path and schema are handled. v2 is documented upstream and unused here.
- Market WebSocket connectivity, application-level `PING`, immediate subscription refresh, and the current nested `price_changes` event shape are handled.
- Activity rows can use `usdcSize` for copied trade notional.
- Paper fills use Polymarket's price-shaped taker fee curve: `fee_rate * price * (1 - price)`.
- Market fee metadata is pulled from CLOB/Gamma data when available.
- Live mode is hard-disabled before order-session creation while the repo uses CLOB V1. The geoblock and forward-paper guards remain readiness code, not an enabled live path.
- Invalid mode values fail closed during configuration loading.
- Deposit-wallet signing config exists: `POLY_SIGNATURE_TYPE` and `POLY_FUNDER`.
- Timing telemetry exists for profitability analysis. Copier latency tests now assert against the metric's own clock origin (PR #144).
- `config.yaml` uses the canonical `paper_taker_fee_rate` key.
- Partial exit fills retain and account for the open remainder.
- BUY shares are sized against conservative all-in entry cost so slippage and fees cannot push a configured dollar budget above its ceiling.
- Tracker activity is normalized chronologically before FIFO matching. `REWARD` and current blank-asset redemption rows are excluded from directional scoring; legacy token-attributed claims still use the documented $1 payout assumption.
- Re-added wallets must seed a fresh cold-start baseline before emitting trades.
- **2026-09-11 runtime hygiene (not expectancy proof):** timed-out monitor poll waiters are released (PR #145); internally created replacement Data/Gamma sessions are closed (PR #146); disabled log events are skipped and exception context is retained (PR #147); portfolio init failures close SQLite (PR #148); `run_bot` cancels and joins background loops before closing the database and API clients (PR #149).

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

## 2026-09-11 FINDINGS SUMMARY

**Repo base:** `origin/main` at `d603c16e554e8b62161c4cd6832607a0430cae80`. Open PRs at recheck: none. Merged since the 2026-08-21 pin: MIT license (`1e874c2`) and PRs #144–#149 (runtime/test hygiene). Verdict is unchanged: **conditional NO**. Live mode stays hard-disabled. Open `INVARIANTS.md` divergences DD-03, DD-04, DD-05, DD-09, DD-10, DD-11, and DD-14 are documented, not fixed here.

- **[verified repo fact]** PRs #144–#149 do not change TP/SL math, sizing, fee curve, trader scoring, fill reconciliation, or the live-mode raise. They make paper runs less leaky (poll waiters, aiohttp sessions, SQLite init, shutdown join) and make latency assertions deterministic.
- **[verified external fact]** As of 2026-09-11, official Python docs still recommend unified `polymarket-client`. Geoblock docs still list the United States as close-only on frontend and API.
- **[verified external fact]** Data API v2 shipped 2026-09-04. v1 remains frozen. This bot's leaderboard/activity clients still speak v1/`/activity`. Paper mode can keep using frozen v1 until it 404s or silently drops fields; a backtest harness should record the v1 shape it actually consumed and treat a v2 cutover as a separate, tested adapter change.
- **[verified repo fact]** `data_client.py::get_leaderboard` already unwraps `data` if the payload is not a list, so a v2-style envelope would not immediately crash that one helper. Tracker `_fetch_leaderboard_window` does the same. That is not a v2 migration: parameters still use offset pagination and v1 path `/v1/leaderboard`. Official v2 examples use snake_case row keys (`proxy_wallet`, `realized_pnl`); this tree's v1 parsers still read camelCase (`proxyWallet`, `pnl`).
- **[inference]** Runtime hygiene raises confidence that a future paper log or backtest is not poisoned by leaked waiters or half-closed SQLite. It is not a substitute for held-out net-expectancy evidence.
- **[unknown]** Live Data API v2 field names versus this repo's `.get("pnl")` / `usdcSize` / `proxyWallet` parsers were not probed in this recheck. Use `/polymarket-api-drift` (GET only) before treating v2 as drop-in.

## Why Real-Money Mode Is Still Blocked

1. **Venue and legal mismatch.** The code targets the international crypto CLOB, whose official geoblock lists the United States as close-only on both the frontend and API, prohibiting new orders from US IP space. Polymarket US is a separate CFTC-designated venue with a separate API, but this repo has no adapter for it. The geoblock preflight is a safety check, not permission to trade.
2. **No profitability proof.** There is still no held-out offline backtest that measures selected traders forward, net of spread, slippage, taker fees, latency, skipped fills, no-fills, and market impact.
3. **Paper mode is not a go-live signal.** Paper mode is useful for plumbing and telemetry, but it still cannot prove live fill quality, partial/no-fill selection bias, or thin-book market impact. 2026-09-11 shutdown and session fixes do not close this gap.
4. **The copied signal is delayed and public.** The bot copies after public activity appears. Skilled Polymarket traders appear to earn much of their edge by reacting first; a delayed copier may buy after the source trade has already moved the book.
5. **Trader metrics remain incomplete.** `REWARD` and current blank-asset redemptions are now excluded from directional scoring. Legacy token-attributed claims still assume a $1 payout when price is absent, and worthless-expiry losses or unredeemed outcomes can be missing, so historical ROI/win-rate inputs remain incomplete.
6. **Live fill accounting is optimistic when the venue response is incomplete.** `_reconcile_fill` defaults missing fill fields to a full fill at the current quote (open DD-10). Any future live path must obtain authoritative order/trade state or keep the result unknown; it must not manufacture a position, exposure release, or PnL.
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

## Trader scoring and Kelly bias

This is the section README points at. It is not a profitability proof.

- **[verified repo fact]** Trader score is the weighted **sum** `(4.0 · sharpe + 3.5 · consistency + 2.5 · recency) / 10` in `tracker.py::TraderScorer.score`, not a product and not raw PnL. Dual-window rank (all-time and trailing 30-day) is an eligibility filter. Expectancy gates eligibility; a low win rate alone does not.
- **[verified repo fact]** Default copy size is `size_multiplier` 0.5 of the source, hard-capped at `max_trade_pct` 0.02 of bankroll (`config.py`). `kelly_enabled` defaults **false**. When enabled, sizing uses the bot's own closed-trade win rate after `kelly_min_trades` (50); before that sample, `kelly_seed_from_tracker` (default true) can seed from tracker mean ROI with time decay.
- **[inference]** Both Kelly paths inherit measurement bias from incomplete realizations (missing worthless expiries, legacy $1-redemption assumption, delayed public fills). The 2% cap bounds the damage; it does not create edge. Leave Kelly off until R1/R3 exist.
- **[unknown]** No held-out measurement in this repo shows that the scored wallets remain profitable after this bot's skip rules, fees, and latency.

## What to do next, and how

IDs match `next_steps.md`. Nothing below authorizes live mode. Do not silently fix open DD items. Operator decision first, then the first code slice.

### 1. R6 — Venue decision (ask, do not code)

**Why:** SDK migration and a US adapter are different products. Coding either before a written venue choice wastes the next PR.

**How:**

1. Write down one of: stay paper-only; later international CLOB via `polymarket-client` (CLOB V2 / pUSD) after counsel; or a separate Polymarket US adapter (different API, CFTC DCM).
2. Venue-specific counsel for operator location, automation, and funding path. Geoblock passing is not permission.
3. Do not start R5 until this is written. Engineering default until then: paper only.

### 2. R1 — Offline backtest harness (highest-value code next)

**Why:** Only this can falsify “copying scored wallets has positive net expectancy.” Plumbing PRs cannot.

**How (first slice, one draft PR):**

1. After this docs PR merges, run `/next-chunk R1` (or branch `grok/polymarket-r1-backtest` from `origin/main`).
2. Add a paper-only replay module plus fixtures under `tests/` (recorded JSON, never live orders, never `mode == live`).
3. Window A: score traders with current `TraderScorer` on recorded Data API leaderboard + activity (the v1 shape this tree actually consumes). Window B: held-out copy using current skip rules, price-shaped taker fee `rate · p · (1 − p)`, detection latency, and explicit no-fill/partial-fill outcomes.
4. Report net expectancy, skip reasons, and unknown fills separately. Do not count synthetic full fills as live evidence.
5. First failing test on main: “replay fixture X yields a report object with net expectancy and skip histogram.” Implement the smallest harness that makes that pass.
6. **Do not** rewrite TP/SL, scoring weights, or retry matrix in the same PR. If the harness needs to change those, stop — that is Tier 2.

### 3. R2 — Execution parity report

**Why:** Timing telemetry exists (PR #86) and the clocks are now test-honest (PR #144), but there is still no operator report that joins detection, quote, fee, skip, and fill certainty.

**How:** Persist detection/submit/fill timestamps, source vs observed price, spread, fee, skip reason, and authoritative order/trade status. Label unknown fills. Build on existing `log_event` fields; do not invent a second log pipeline. Paper-only.

### 4. R4 — Paper fill realism

**Why:** Paper still synthesizes full fills at the quote. That inflates fill quality.

**How:** Replay recorded order-book snapshots for size-aware VWAP, partial fill, and no-fill. A shallow book must not report a full fill. Keep `clob_client.py` paper reconciliation byte-stable except at the new snapshot-replay path (the invariant test pins the synthetic full-fill behavior).

### 5. R3 — Trader metric de-bias (Tier 2 — ask before coding)

**Why:** Scoring still under-counts worthless expiries and unredeemed losses, so Kelly and eligibility can look better than the book.

**How:** Represent worthless expiries and unredeemed outcomes; keep `REWARD` / blank-asset `REDEEM` out of directional PnL. Touches `tracker.py` math → ask first. Do not “fix” DD-23’s remaining $1 payout assumption without a maintainer decision.

### 6. R5 — Live auth proof (last, and only after R6 + counsel)

**Why:** V1 cannot place production orders. A V1 proof is not a V2 proof.

**How:** If R6 chose international CLOB: migrate the unreachable live adapter to current official `polymarket-client`, pUSD, V2 order structure, current auth/signing; minimal-funds test; redacted logs. Treat `py-clob-client-v2` as previous-generation, not the new-project path. Include a Data API v2 read adapter in that design, not as a drive-by in R1. If R6 chose Polymarket US, that is a different adapter and a different PR series.

### Not on the real-money critical path

`next_steps.md` L1–L3 (seen-id cap, signer thread count, per-wallet poll circuit) are operational polish. Do them after R1 exists, not instead of it.

## Planning Sources Rechecked (accessed 2026-09-11)

- [Polymarket Python SDK](https://docs.polymarket.com/getting-started/python) — unified `polymarket-client` is still the documented new-project path.
- [Polymarket geographic restrictions](https://docs.polymarket.com/api-reference/geoblock) — United States remains close-only on frontend and API.
- [Polymarket changelog](https://docs.polymarket.com/changelog/predictions) — 2026-09-04 Data API v2; 2026-08-10 per-outcome `REDEEM`; 2026-07-24 FAK/FOK `tradeIDs` vs `transactionHashes`.
- [Data API overview / v2](https://docs.polymarket.com/api-reference/data-api/overview) — v2 host path; v1 frozen.

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

This is not financial or legal advice. It is the repo-level engineering status after the latest `origin/main` changes. Paper mode remains the only supported runtime.
