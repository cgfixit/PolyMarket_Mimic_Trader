# Polymarket Real-Money Readiness PR Plan

## Verdict

This bot should be modernized as a realistic paper/research demo first. Real-money use stays blocked until forward paper results prove net edge after spread, slippage, fees, latency, and jurisdiction checks.

## Status As Of 2026-09-21

**Repo snapshot:** `origin/main` at `120d7893cb6417a93da6f9fbd8f6a746a05f688b`.

- PR 1 is implemented on main: current leaderboard/API shape, tradability gates, and documented WebSocket heartbeat are handled.
- PR 2 is mostly implemented on main: paper fills/copy gates use the price-shaped fee curve and CLOB fee metadata where available. Remaining work is recorded-book replay with size-aware VWAP, partial fills, and no-fills.
- PR 3 is partially implemented on main: legacy `signature_type`/`funder` config and live geoblock preflight exist. Remaining work is migration to the current official `polymarket-client`, exact Deposit Wallet/Relayer and L1/L2 contract tests, minimal-fund live auth testing, and venue/legal sign-off.
- PR 4 remains the real go-live gate. Initial paper-only slices now exist: a synthetic-fixture held-out evaluator (`75d33e4`) and a decision timing/skip summary (`6db5fef`). They do not supply real captured inputs, book-depth replay, income-classified trader metrics, authoritative fill reconciliation, or profitability evidence.

## PR 1: API Drift And Tradability Fixes

Implemented scope:

- Use the current Data API leaderboard path: `GET /v1/leaderboard`.
- Map internal leaderboard windows to Polymarket's current `DAY`, `WEEK`, `MONTH`, `ALL` enum.
- Read current leaderboard wallet/user fields: `proxyWallet`, `userName`.
- Use the current public market WebSocket URL and subscription schema.
- Send Polymarket's application-level WebSocket heartbeat payload.
- Parse Gamma market tradability fields.
- Skip copies when a market is inactive, closed, archived, restricted, not accepting orders, or has no enabled order book.

Validation target:

- `python -m ruff check .`
- `python -m pytest -v --tb=short`

## PR 2: Fee And Slippage Realism

Do this as a separate money-math PR.

Required changes:

- Replace flat `paper_taker_fee_pct` math with Polymarket's formula: `fee = shares * fee_rate * price * (1 - price)`.
- Rename config to `paper_taker_fee_rate` or keep a backward-compatible alias with a deprecation note.
- Pull market fee parameters from CLOB market info when available.
- Keep spread/slippage separate from fees. Do not bundle them into one percentage.
- Replay recorded order-book snapshots and retain the decision-time depth, VWAP, partial-fill, and no-fill outcome.
- Update paper fill tests at low, mid, and high prices so fee shape is verified.
- Update the pre-copy edge gate to compare expected TP against spread + fee + exit cost, not a flat multiplier.

Acceptance:

- Paper fill at $0.50 should match the fee-rate table.
- Paper fill near $0.05 and $0.95 should charge materially less fee than $0.50.
- Edge gate should skip trades only when expected bounded upside is consumed by realistic costs.
- A shallow-book replay must not report a synthetic full fill when the recorded depth supports only a partial fill or no fill.

## PR 3: Live Auth/SDK Compatibility

Do this only after deciding whether live mode remains in scope.

Required changes:

- Migrate from legacy `py-clob-client` V1 to the current official `polymarket-client`, or remove the international live path; legacy `signature_type`/`funder` config is not production compatibility proof.
- Model the current Secure Client inputs explicitly: signer, account wallet, and Relayer credentials where required.
- Create or derive CLOB L2 credentials through the supported L1 flow without logging secrets.
- Add a startup geoblock check before any live order path.
- Keep paper mode as the default.

Acceptance:

- Live mode refuses to start without the exact signer, account-wallet, Relayer/L1/L2 credentials required by the selected account type, plus successful geoblock eligibility.
- Unit tests cover config validation without real credentials.
- Adapter contract tests cover V2 order creation, order-status lookup, and redacted error handling without real credentials.

## PR 4: Profitability Evidence

This is not solved by code cleanup.

Implemented first slices:

- `polymarket_copier/replay.py` enforces training/hold-out separation, reuses the existing fee/slippage helpers for known outcomes, and keeps unknown fills out of net-expectancy arithmetic. Its bundled input is synthetic and does not exercise a historical order book.
- `scripts/paper_metrics_report.py` summarizes paper opens/skips, breaker trips, skip reasons, and wall-age timing from existing structured logs. It explicitly does not report execution-adjusted expectancy.

Remaining changes:

- Join the existing open/skip timestamps, prices, fee, size, and reason fields with close PnL; add decision-time spread, book VWAP, and authoritative fill state instead of treating synthetic paper fills as execution evidence.
- Persist source activity type and separate directional PnL from redemption, reward, rebate, referral, and unknown activity.
- For a future live path, obtain authoritative order/trade state before changing a position or PnL; absent concrete fill data remains unknown.
- Add a daily report grouped by source wallet, category, market, and skip reason.
- Add a forward-paper gate: no live mode until a configured minimum sample shows positive net expectancy.

Acceptance:

- 30+ days of forward paper data.
- Net expectancy remains positive after realistic costs.
- Fixtures prove that reward/rebate rows do not close a directional position and that unknown fills create no position or realized PnL.
- Drawdown and daily loss controls are exercised in paper mode.

## Non-Goals

- No claim of profitability.
- No auto-bypass of geographic restrictions.
- No new strategy abstraction before measured edge exists.
