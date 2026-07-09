---
name: add-enhance-tests
description: >-
  Tests-only improvement workflow for PolyMarket_Mimic_Trader. Use when asked
  to refactor, update, or add realistic unit or mocked integration tests for
  CI without depending on live network calls.
---

# Add Enhance Tests

Use this skill when the user wants the `tests/` suite strengthened.

The goal is realism without flake. Prefer current official payload shapes,
existing fixtures, and deterministic checks. Do not turn CI into a live API
probe.

## Read First

- `AGENTS.md`
- `CLAUDE.md`
- `INVARIANTS.md`
- `tests/conftest.py`
- touched test files near the target

Current API-shape sources to mirror in fixtures when useful:

- activity: `https://docs.polymarket.com/api-reference/core/get-user-activity`
- leaderboard: `https://docs.polymarket.com/api-reference/core/get-trader-leaderboard-rankings`
- market discovery: `https://docs.polymarket.com/market-data/fetching-markets`
- auth/order flow: `https://docs.polymarket.com/api-reference/authentication`
- geoblock: `https://docs.polymarket.com/api-reference/geoblock`

## Rules

- Reuse existing fake sessions, helpers, and fixture patterns before adding new ones.
- Prefer one focused regression test in the shared choke point over duplicate caller tests.
- Keep integration tests mocked and deterministic; no real Polymarket network traffic in CI.
- If a payload shape changed upstream, update the existing tests that own that path before adding another suite.
- Do not add new dependencies unless the repo already needs them for the test path.

## Good Targets

- live-mode auth and funder validation
- geoblock fail-closed startup behavior
- activity / leaderboard / market response-shape drift
- order timeout / partial-fill / cancel-confirm safety
- exposure and bankroll accounting after failures
- CI drift between docs, requirements, and actual test imports

## Bad Targets

- broad coverage chasing with no failure mode behind it
- slow snapshot dumps of entire APIs
- real-money or real-network tests
- duplicate fixtures when a local fake session already exists

## Execution

When the user asks you to execute:

1. Start from fresh `origin/main`.
2. Scan `tests/` and the target production path for the smallest real gap.
3. Add or update the minimum test that fails without the fix.
4. Run targeted tests first.
5. Run:
   - `powershell -File scripts/check-lint.ps1`
   - `python -m pytest -v -m "not integration"`
6. Open a draft PR if changes were justified.
