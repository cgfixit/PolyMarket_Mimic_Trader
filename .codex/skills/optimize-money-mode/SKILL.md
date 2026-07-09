---
name: optimize-money-mode
description: >-
  Live-money-readiness optimizer for PolyMarket_Mimic_Trader. Use when asked
  to review profitability docs, improve non-paper mode, verify wallet/API
  correctness, or harden the code for real-money paths without weakening safety
  rules.
---

# Optimize Money Mode

Use this skill when the user wants work aimed at real-wallet, non-paper mode.

This skill is intentionally skeptical. It can optimize for live-money
readiness. It cannot honestly certify that the bot is legal or "likely to make
money consistently" without fresh external evidence, venue-specific legal
review, and measured execution data. Do not blur that line.

## Read First

Before proposing or editing anything, read the repo's business and money-mode
docs:

- `README.md`
- `CLAUDE.md`
- `SECURITY.md`
- `PROFITABILITY_ANALYSIS_JUNE_2026.md`
- `next_steps.md`
- `INVARIANTS.md`
- `docs/PROFITABILITY_FACTCHECK_REPORT_JULY_2026.md`
- `docs/POLYMARKET_REAL_MONEY_READINESS_PR_PLAN_2026-07-03.md`
- `docs/POLYMARKET_BOT_STRATEGY_RESEARCH_2026-06-30.md`
- `docs/DUE_DILIGENCE_AUDIT_2026-07-08.md`

Treat claims in those files as inputs to verify, not facts to repeat.

## External Baseline To Verify

Re-check current official sources before making claims about live mode:

- Trading overview: `https://docs.polymarket.com/trading/overview`
- Authentication and API structure: `https://docs.polymarket.com/api-reference/authentication`
- Order creation flow: `https://docs.polymarket.com/trading/orders/create`
- Market discovery: `https://docs.polymarket.com/market-data/fetching-markets`
- User activity: `https://docs.polymarket.com/api-reference/core/get-user-activity`
- Leaderboard: `https://docs.polymarket.com/api-reference/core/get-trader-leaderboard-rankings`
- Geoblock: `https://docs.polymarket.com/api-reference/geoblock`
- Terms / venue split: `https://polymarket.com/tos`

Legal baseline to re-check before saying anything strong:

- federal UIGEA: `31 U.S.C. 5361-5367`
- federal Wire Act: `18 U.S.C. 1084`
- Georgia Constitution, Article I, Section II, Paragraph VIII

If you cannot verify a legal point from a primary or clearly authoritative
source, say so and default to "needs counsel."

## Focus Areas

Optimize only for changes that plausibly matter to live-money survivability:

- wallet/auth correctness: private key path, signature type, funder, API key derivation
- geoblock / jurisdiction gating that fails closed before order placement
- fee-aware edge preservation after spread, slippage, fill quality, rebates, and no-fills
- order lifecycle safety: timeout, cancel-confirm, partial-fill reconciliation, no double exposure
- bankroll and exposure accounting under failed entries, exits, and reconnects
- realistic market-data assumptions: activity shape, leaderboard shape, orderbook depth, tick size, fees
- operator visibility: structured logs, kill switches, paper/live mismatch warnings

Do not drift into generic cleanup, paper-mode polish, or speculative strategy
rewrites unless the user asks.

## Output Contract

Start with a `FINDINGS SUMMARY` grounded in repo facts and verified current
sources. Separate:

- verified repo fact
- verified external fact
- inference
- unknown

Then group the work into PR-sized chunks. Prefer one real change over three
invented ones.

For any profitability statement, demand one of:

- held-out backtest with net expectancy after fees and slippage
- paper/live execution comparison using real orderbook snapshots
- measured latency/no-fill evidence tied to the actual venue path

Without that, phrase it as risk reduction or readiness improvement, not alpha.

## Guardrails

- Never weaken the safety rules in `CLAUDE.md`.
- Never default the repo to live mode.
- Never claim a live-money path is legal in Georgia or federally compliant from code inspection alone.
- Never hardcode secrets, bypass geoblock checks, or add "VPN around it" logic.
- Never treat the international Polymarket venue as equivalent to `polymarket.us`.

## Execution

When the user asks you to execute this workflow:

1. Start from fresh `origin/main`.
2. Read the repo docs above.
3. Verify the current Polymarket docs and legal baseline above.
4. Produce findings and choose one high-leverage chunk.
5. Implement the smallest coherent fix.
6. Validate with the narrowest useful checks plus the repo gates if the change crosses modules.
7. Open a draft PR against `main`.
