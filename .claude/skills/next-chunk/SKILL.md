---
name: next-chunk
description: >
  Select the highest-value unclaimed item from next_steps.md, implement it with tests on a
  fresh branch, pass preflight, and open a single-concern draft PR. Use when asked for "the
  next improvement", "/next-chunk", or to make autonomous progress on the backlog. Optional
  argument: a backlog item ID (e.g. "R2" or "L1") to target a specific item.
---

# /next-chunk — Implement the Next Improvement

One backlog item → one branch → one draft PR. The maintainer merges; you never do.

## Step 0 — Read the backlog FRESH

Read `next_steps.md` top to bottom **every time**. Do not trust any cached memory of its
structure — a previous version of this command referenced a "Tier A/B/C" scheme long after the
backlog had been rewritten (currently it is R1–R6 real-money gates + L1–L4 low-level items,
but that too will change). The file on disk is the only source of truth for what the items are
and how they are prioritized.

If an item ID was passed as an argument and it doesn't exist in the current file, say so and
show what IDs do exist — don't guess at a mapping.

## Step 1 — Dedupe against in-flight work

```bash
git fetch origin main --quiet
git log origin/main --oneline -20
```

List open PRs (GitHub MCP `list_pull_requests`, or `gh pr list --state open --json
number,title,headRefName` where the CLI exists). If an open PR already covers an item, skip
that item and say which PR claimed it. Also check the "Completed Recent Fixes" section of
`next_steps.md` — items sometimes land without being crossed off.

## Step 2 — Select, and escalate if needed

Selection rules, in order:
1. Respect the file's own priority ordering (R-items before L-items unless the file says
   otherwise, or the user named an ID).
2. Prefer the highest-priority item that fits in a single-concern PR. If the top item is too
   large, propose a scoped first slice of it and say so — do not silently implement a fragment.
3. **Tier-2 escalation check (CLAUDE.md ladder):** if the item requires changing trading math,
   sizing, TP/SL structure, retry semantics, order-placement flow, config defaults, or anything
   live-mode adjacent — STOP and ask before implementing, presenting the item and your intended
   approach. Many R-items are in this category by design; asking first is the expected path,
   not a failure.
4. If nothing qualifies (everything claimed, too large, or Tier-2 with no answer), **"nothing
   worth doing" is a valid outcome** — report that instead of manufacturing low-value work.

State your selection rationale: the item chosen, the items skipped and why, and the dedup
evidence.

## Step 3 — Branch before the first edit

```bash
git checkout -b claude/<short-topic> origin/main
```

Branch FIRST — the repo's Stop hook force-commits-and-pushes whatever branch is checked out at
the end of a turn.

## Step 4 — Implement against the quality bar

Implement with tests. Hold the work to the matching checklist in CLAUDE.md "Quality bar per
deliverable" (bug-fix / feature-config / test-only) — those criteria are what review checks.
The non-negotiables from the mistakes table apply in full; when in doubt, re-read the relevant
rows before writing code.

## Step 5 — Gate with preflight

Run the `/preflight` skill (`bash .claude/skills/preflight/preflight.sh`). Do not push on
`READY TO PUSH: no`. Pre-existing failures on main get reported in the PR body, not fixed in
this PR.

## Step 6 — Draft PR

Commit (loose conventional style: `fix:`/`feat:`/`test:`/`docs:` + optional scope, body says
*why*), push with `git push -u origin claude/<short-topic>`, and open a **draft** PR:

```markdown
## What
<one paragraph: the backlog item and what changed>

## Why
<the item ID from next_steps.md and the problem it addresses>

## Validation
<preflight summary block; the regression-test command and its fails-on-main/passes-here result>

## Risk to monitor
<what could go wrong in paper mode; what log_event/metric would show it>
```

If the item is now fully done, update `next_steps.md` in the same PR (move it to the completed
section with the PR number). If only a slice was done, note the remainder in the PR body
instead — don't edit the backlog for partial work.

## Guardrails

- Never commit to `main`. Draft PRs only. One concern per PR.
- Do not bundle opportunistic refactors, doc sweeps, or "while I was here" fixes — file them as
  observations in your reply instead.
- Do not start a second chunk in the same session unless asked.
