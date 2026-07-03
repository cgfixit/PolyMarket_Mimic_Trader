# Polymarket Real-Money Readiness PR Plan

## Verdict

This bot should be modernized as a realistic paper/research demo first. Real-money use stays blocked until forward paper results prove net edge after spread, slippage, fees, latency, and jurisdiction checks.

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
- Update paper fill tests at low, mid, and high prices so fee shape is verified.
- Update the pre-copy edge gate to compare expected TP against spread + fee + exit cost, not a flat multiplier.

Acceptance:

- Paper fill at $0.50 should match the fee-rate table.
- Paper fill near $0.05 and $0.95 should charge materially less fee than $0.50.
- Edge gate should skip trades only when expected bounded upside is consumed by realistic costs.

## PR 3: Live Auth/SDK Compatibility

Do this only after deciding whether live mode remains in scope.

Required changes:

- Evaluate migration from `py-clob-client` to `py-clob-client-v2`.
- Add explicit config for signature type and funder/deposit wallet.
- Derive or load L2 API credentials without logging secrets.
- Add a startup geoblock check before any live order path.
- Keep paper mode as the default.

Acceptance:

- Live mode refuses to start without private key, signature type, funder when required, and successful geoblock eligibility.
- Unit tests cover config validation without real credentials.

## PR 4: Profitability Evidence

This is not solved by code cleanup.

Required changes:

- Persist source trade timestamp, detection timestamp, submit timestamp, fill timestamp, source price, observed price, fill price, spread, fee, size, skip reason, and realized PnL.
- Add a daily report grouped by source wallet, category, market, and skip reason.
- Add a forward-paper gate: no live mode until a configured minimum sample shows positive net expectancy.

Acceptance:

- 30+ days of forward paper data.
- Net expectancy remains positive after realistic costs.
- Drawdown and daily loss controls are exercised in paper mode.

## Non-Goals

- No claim of profitability.
- No auto-bypass of geographic restrictions.
- No new strategy abstraction before measured edge exists.
