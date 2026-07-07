---
name: fact-check
description: >
  Build a claims ledger for a PR, doc, or report: extract every claim, verify each with BOTH a
  code check (file::symbol anchor) and an external check (URL + access date), and emit the
  repo-standard verdict table. Use when asked to fact-check, verify claims, audit a PR or doc,
  or reassess real-money readiness. Argument: a PR number (e.g. "77"), a file path
  (e.g. "docs/PROFITABILITY_ANALYSIS_JUNE_2026.md"), or "readiness".
---

# /fact-check — Claims Ledger

This repo's core discipline: **no claim is trusted until it has been checked twice** — once
against the code in this repository, once against primary external sources. That applies to
claims written by the maintainer's own agents. Exemplars of the output shape:
`docs/PR_75_76_77_CLAIMS_NOTEPAD.md` and `docs/PROFITABILITY_FACTCHECK_REPORT_JULY_2026.md`.

## Step 1 — Load the target

- **PR number** → fetch the PR body, description, and diff (GitHub MCP tools, or `gh pr view
  <n> --json title,body` + `gh pr diff <n>` where the CLI exists).
- **File path** → read the file.
- **"readiness"** → target `docs/POLYMARKET_REAL_MONEY_READINESS_PR_PLAN_2026-07-03.md` plus
  the "Real-Money Status" section of `README.md`, and pin the ledger to the current
  `git rev-parse --short HEAD`.

## Step 2 — Extract claims

A claim is any sentence a skeptical reviewer could ask "how do you know?" about. Extract ALL of
them — including ones that look obviously true. Type each using the `AGENTS.md` taxonomy:

| Type | Meaning | Verification that counts |
|---|---|---|
| repo fact | "the code does X" | reading the actual code |
| measured result | "we observed X when running" | a command + its output |
| market signal | "Polymarket/the market does X" | primary source: official docs, API probe, filing |
| inference | "therefore X" | logic check: do the premises (verified above) support it? |

Skip pure opinions and stylistic statements. Do not skip numbers — numbers are where this
repo's docs have historically rotted (trailing stop, Kelly threshold, scoring formula).

## Step 3 — Verify: every claim gets BOTH columns

**Code check** — find the actual behavior in this repo:
- Cite `path.py::symbol` (greppable — line numbers rot) and quote the decisive line(s).
- For measured-result claims, re-run the command if it's cheap and safe (tests, greps,
  paper-mode dry runs). Never place live orders or spend money to verify anything.
- If the claim is about external reality, write exactly: `N/A — not a repo claim`.

**External check** — verify against sources outside the repo:
- Primary sources only: official Polymarket docs, exchange/regulator filings, the paper itself
  (not a blog about the paper). Record URL + access date.
- A read-only API probe counts (GET endpoints, respect rate limits; never authenticated
  mutation). Save raw responses if used as evidence.
- If the claim is repo-internal, write exactly: `N/A — repo-internal`.
- If you cannot reach a source, the verdict is ❓ — **never** silently upgrade to ✅.

## Step 4 — Verdicts

Repo-standard key (these emoji are reserved for claims ledgers — don't use them elsewhere):

- ✅ **confirmed** — both applicable checks support the claim as written.
- ⚠️ **partially confirmed / nuance needed** — directionally right but imprecise (wrong number,
  overbroad wording, missing caveat). State the corrected version.
- ❓ **unverifiable from here** — source unreachable, data not available, or would require
  live-mode/spending to test. State what WOULD verify it.
- ❌ **refuted** — a check contradicts the claim. Quote the contradicting evidence.

State your confidence honestly. If any verification step was skipped or degraded (rate limit,
missing tool), say so in a "Methodology limits" note — the exemplar reports do exactly this.

## Step 5 — Output

Write `docs/<TARGET>_CLAIMS_<YYYY-MM-DD>.md` on the current working branch (never `main`):

```markdown
# Claims Ledger: <target> — <date>

Pinned to commit `<short sha>`. Verdicts: N ✅ · N ⚠️ · N ❓ · N ❌

| # | Claim | Type | Code check | External check | Verdict |
|---|-------|------|------------|----------------|---------|
| 1 | "<claim as written>" | repo fact | `copier.py::handle_trade_event` — quote | N/A — repo-internal | ✅ |

## Corrections required (⚠️/❌ items)
- #N: <what the claim should say instead, with evidence>

## Methodology limits
- <anything skipped or degraded, or "none">
```

Then:
- If the target was a PR: post the ⚠️/❌ items as PR comments (one comment, itemized) so the
  author can respond. **Never silently edit the target to "fix" its claims** — the ledger is
  the deliverable; corrections go through review.
- Report the verdict counts and the single most consequential finding in your reply.

## Guardrails

- Verify the claim **as written** — if it says 1.25% and the source says 1.50%, that is ⚠️ with
  a correction, not ✅ because "it's close".
- One ledger per target. Re-running against a moved target = new ledger with a new date, not an
  edit that erases the old verdicts.
- No live orders, no authenticated mutation, no spending, ever — a claim that needs those to
  verify is ❓ by definition (that is itself useful information for the readiness decision).
