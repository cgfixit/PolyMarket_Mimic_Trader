# Next Steps

The original June 2026 implementation backlog is complete enough that it should no longer drive real-money decisions. Current `origin/main` has fixed the main API drift, fee-curve, live-geoblock, WebSocket heartbeat, activity-notional, and fee-key issues.

The remaining question is narrower: can this bot prove a net edge outside paper mode? Today the answer is still **no**.

## Real-Money Blockers

- **Venue/legal:** the bot targets the international Polymarket CLOB. US/Georgia real-money use needs a current venue-specific legal review and likely a separate regulated venue path.
- **Backtesting:** no held-out offline backtest proves selected traders remain profitable after spread, slippage, fees, latency, skipped fills, and no-fills.
- **Paper/live gap:** paper mode remains useful for plumbing, but it cannot prove live execution quality or fill selection bias.
- **Trader metric bias:** worthless-expiry losses and unredeemed positions can still inflate ROI/win-rate inputs.
- **SDK/auth:** deposit-wallet config exists, but the exact live order path still needs minimal-fund proof before any sizing.

## Highest-Value Work

| ID | Work | Why it matters |
|----|------|----------------|
| R1 | Offline backtest harness | Replays historical leaderboard/activity and market data to measure forward net expectancy. |
| R2 | Execution parity report | Records detection latency, spread, book VWAP, fee, skip reason, simulated fill, and realized PnL. |
| R3 | Trader metric de-biasing | Accounts for unresolved/worthless outcomes so selection does not chase inflated winners. |
| R4 | Paper fill realism | Uses real order-book snapshots for size-aware paper VWAP and no-fill/partial-fill modeling. |
| R5 | Live auth proof | Verifies the configured SDK/signature/funder path with minimal funds and redacted logs. |
| R6 | Venue adapter decision | Decide whether live mode targets the international CLOB, Polymarket US, Kalshi, or remains paper-only. |

## Operational Checklist Before Any Live Test

- [ ] Legal/venue review completed for operator location, venue, automation, and funding path.
- [ ] Backtest shows positive net expectancy on held-out data.
- [ ] Paper reports show positive expectancy with realistic book-depth simulation.
- [ ] Live auth path tested with minimal funds and no secret leakage in logs.
- [ ] Daily loss stop, alerts, and rollback plan exercised in paper mode.
- [ ] Bankroll limited to a disposable test amount.

## Low-Level Follow-Ups

These are not real-money blockers, but still worth keeping on the backlog:

| ID | Area | Follow-up |
|----|------|-----------|
| L1 | Monitor | Revisit `_seen_trade_ids` cap if tracked wallets become very high frequency. |
| L2 | CLOB client | Consider making signer thread count configurable if live order throughput grows. |
| L3 | Monitor | Add per-wallet circuit breaking for persistent polling failures. |
| L4 | CLOB client | Add an explicit outer timeout around order-status polling for defensive depth. |

## Completed Recent Fixes

- Price-shaped taker fees and fee-aware copy gating landed in PR #82.
- Live geoblock preflight landed in PR #84.
- CLOB fee metadata fallback/use landed in PR #85.
- Profitability timing telemetry landed in PR #86.
- Documented WebSocket heartbeat landed in PR #87.
- `usdcSize` activity notional parsing landed in PR #88.
- Canonical `paper_taker_fee_rate` docs/config cleanup landed in PR #89.
