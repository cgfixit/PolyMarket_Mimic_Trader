---
name: research-polymarket-api
description: >-
  Fact-check PolyMarket_Mimic_Trader assumptions against the latest official
  Polymarket docs plus current federal and Georgia legal constraints for
  non-paper mode.
---

# Research Polymarket API

Use this skill when the user asks whether the repo's non-paper assumptions
still match current Polymarket docs or current U.S./Georgia constraints.

This is a research and fact-check workflow first. Code changes come second.

## Source Priority

Use sources in this order:

1. Official Polymarket docs and terms
2. Primary legal text or regulator material
3. High-quality current reporting only when primary text is unavailable
4. Repo docs last

Current Polymarket pages to start from:

- `https://docs.polymarket.com/trading/overview`
- `https://docs.polymarket.com/api-reference/authentication`
- `https://docs.polymarket.com/trading/orders/create`
- `https://docs.polymarket.com/market-data/fetching-markets`
- `https://docs.polymarket.com/api-reference/core/get-user-activity`
- `https://docs.polymarket.com/api-reference/core/get-trader-leaderboard-rankings`
- `https://docs.polymarket.com/api-reference/geoblock`
- `https://polymarket.com/tos`

Legal baseline to verify fresh:

- `31 U.S.C. 5361-5367` (UIGEA)
- `18 U.S.C. 1084` (Wire Act)
- Georgia Constitution, Article I, Section II, Paragraph VIII

## Questions To Answer

Produce a tight answer to these:

1. Does the repo's live-mode auth path match the current official Polymarket trading flow?
2. Do the repo's market-data assumptions still match the current activity, leaderboard, and market-discovery endpoints?
3. Does the repo correctly treat geoblock and jurisdiction restrictions as blocking conditions?
4. Are there current federal or Georgia constraints that make the international venue a legal/compliance risk for a Georgia-based operator?

## Output Contract

Return an assumption ledger with these columns:

- assumption
- repo location
- current source
- status: confirmed / drifted / unclear
- action

Then give a short `LEGAL RISK NOTE`:

- not legal advice
- what is clearly blocked or risky
- what needs counsel

If the verified source picture materially changes the repo's profitability or
live-mode claims, update `PROFITABILITY_ANALYSIS_JUNE_2026.md` in the same run.
Keep the update evidence-tagged: verified external fact, repo fact, inference,
or open question.

## Guardrails

- Do not infer legality from the API working.
- Do not equate `polymarket.com` with `polymarket.us`.
- Do not cite stale repo docs over current official docs.
- If primary legal text is missing or ambiguous, say `unclear` and stop short of a definitive legal conclusion.

## Follow-On Work

If the user wants changes after the research pass:

- route live-money code hardening to `.codex/skills/optimize-money-mode/SKILL.md`
- route tests work to `.codex/skills/add-enhance-tests/SKILL.md`
