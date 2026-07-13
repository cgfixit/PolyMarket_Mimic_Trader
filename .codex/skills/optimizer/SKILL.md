---
name: optimizer
description: >-
  Codex-native PolyMarket_Mimic_Trader optimization workflow. Use when working
  in cgfixit/PolyMarket_Mimic_Trader and the user asks Codex to optimize the
  repo, harden CI, audit code, security, or financial-risk assumptions, propose
  focused improvements, or open optimization PRs against main. Read-only for
  review requests; edit, commit, and PR steps require an explicit execution request.
---

# Optimizer

Use this skill to scan the PolyMarket_Mimic_Trader `main` branch for concrete
optimization, security, reliability, financial-risk, auditability, and
maintainability opportunities, then turn the best findings into focused draft
pull requests.

This is the Codex-native optimizer workflow for this repo. Treat the
instructions below as authoritative for Codex here.

## Codex Operating Rules

- Run command steps only when the user clearly asks Codex to execute the
  workflow, make changes, or open PRs. For read-back, explanation, or review
  requests, inspect only.
- All shell, network, git, and GitHub actions remain governed by the active
  Codex sandbox, approval, and authentication rules.
- Use the native Git bootstrap below. `bootstrap.sh` remains optional for POSIX callers; do not require Bash on Windows.
- Use local `git` for branch creation, commits, and pushes.
- Prefer the GitHub app or plugin for PR and issue data when available. Use
  `gh` as fallback for listing PRs, checking auth, and creating draft PRs.
- Do not rely on legacy agent tool names or hard-coded MCP function names. Use
  Codex tools, `rg`, shell file reads, GitHub plugin tools, or `gh`
  equivalents.
- Do the initial scan directly in Codex. A separate read-only pass is optional,
  not required.

## PolyMarket_Mimic_Trader Context

PolyMarket_Mimic_Trader is an async copy-trading bot for Polymarket. Core areas
include:

- `polymarket_copier/main.py`: startup, supervision loops, shutdown flow
- `polymarket_copier/core/`: copier, monitor, risk, sizing, portfolio, tracker
- `polymarket_copier/api/`: Data API, Gamma API, and CLOB clients
- `polymarket_copier/config.py` and `config.yaml`: runtime config and defaults
- `tests/`: unit, integration, metrics, and chaos coverage

Read code for leverage:

- performance
- security
- financial-risk and oversight assumptions
- auditability
- maintainability

## Step 0 - Bootstrap

From the repo root, require a clean tree and start the work branch from fresh
`origin/main`:

```bash
git status --porcelain   # must print nothing
git fetch origin main
git switch -c codex/polymarket-optimize-<topic> origin/main
```

If the branch already exists, use `git switch <branch>` and do not reset it.
For POSIX callers, `bash .codex/skills/optimizer/bootstrap.sh <branch>` is an
optional equivalent; it does not force a Git identity.

For a read-only inventory, omit the branch creation and inspect the current
clean checkout.

## Step 1 - Read-Only Scan

Spend a short, time-boxed pass on concrete findings. Keep the scan read-only:
do not edit files while discovering candidates.

Sweep these areas:

- `.github/workflows/*.yml`: caching, action SHA pinning, concurrency,
  `cancel-in-progress`, matrix gaps, and license or secret-free hardening
- `tests/`: coverage gaps, brittle fixtures, logic errors, missing assertions,
  async regressions
- `polymarket_copier/main.py` and `polymarket_copier/core/`: inefficient
  loops, redundant logic, blocking I/O, shutdown bugs, and risk-control drift
- `polymarket_copier/api/`: timeout, retry, rate-limit, and error-context gaps
- `polymarket_copier/core/portfolio.py` and DB-touching code: unnecessary
  writes, transaction safety, and durability issues
- `polymarket_copier/config.py`, `config.yaml`, `requirements.txt`, and
  `pyproject.toml`: risky defaults, tooling drift, missing dependencies
- readability and auditability issues anywhere in the repo

Return 6-10 distinct findings. Each finding must include:

- title
- file path and line number
- one-line description
- category
- effort: small or medium

End the scan with a suggested grouping into about five PR-sized chunks. Cite
real code only. Do not invent findings.

## Step 2 - Deduplicate Against Open PRs

Before choosing focus areas, list open PRs and drop candidate areas already
covered by an open PR.

Use the best available GitHub path:

```bash
gh pr list --repo cgfixit/PolyMarket_Mimic_Trader --state open --json number,title
```

If using a GitHub connector, request only `number` and `title` when possible.
Do not dump large raw PR payloads into context.

## Step 3 - Select Focus Areas

Choose about five deduplicated chunks. Each chunk should be independently
reviewable:

- one or two major concepts, or
- three to five closely related minor tasks

For each chunk, state one line covering the files touched and why the change has
leverage: performance, security, financial-risk, auditability, or
maintainability.

If no clear opportunities remain after deduplication, say so and stop. Do not
manufacture low-value PRs.

## Step 3.5 - Plan Shared Files

Before creating implementation branches, build a file-to-chunks map and find
files touched by multiple chunks. Common shared files are
`.github/workflows/*.yml`, `config.yaml`, `requirements.txt`, `pyproject.toml`,
`CLAUDE.md`, and `.codex/README.md`.

For each shared file, choose one strategy:

- Consolidate all edits to that file in one chunk or a dedicated wiring PR.
- Stack later branches on earlier branches and set the child PR base to the
  parent branch.

If two branches edit the same shared file, trial-merge them locally before
opening PRs. Confirm both edits survive, no conflict markers exist, and any
structured file still parses.

Example checks:

```bash
git checkout -B _trial origin/main
git merge --no-ff origin/<branch-a>
git merge --no-ff origin/<branch-b>
grep -q '<a-marker>' <shared-file>
grep -q '<b-marker>' <shared-file>
grep -rc '<<<<<<<' <shared-file>
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
git checkout main
git branch -D _trial
```

## Step 4 - Implement One Draft PR Per Chunk

For each chunk:

1. Create a focused branch. Default branch names should look like
   `codex/polymarket-optimize-<topic>`.
2. Make the smallest coherent change set for the chunk.
3. Verify the touched area.
4. Stage only intended files.
5. Commit with a clear message.
6. Push the branch.
7. Open a draft PR against `main`, unless Step 3.5 requires a stacked base.

Draft PR bodies should include:

- what changed
- why it helps
- validation performed
- risk to monitor

With `gh`, a typical fallback is:

```bash
gh pr create --repo cgfixit/PolyMarket_Mimic_Trader --base main --head <branch> --draft \
  --title "<concise title>" --body-file <body-file>
```

On network failure during push, retry up to four times with exponential backoff:
2s, 4s, 8s, and 16s.

## Verification

Prefer the narrowest meaningful check for the touched area. The documented
PolyMarket_Mimic_Trader gates are:

```bash
powershell -File scripts/check-lint.ps1
python -m mypy polymarket_copier --ignore-missing-imports --no-strict-optional
pytest -v -m "not integration"
```

Use a narrower check when appropriate, for example:

```bash
pytest tests/test_risk_manager.py -v
python -m polymarket_copier.main --mode paper --config config.yaml
```

Fresh clones may not have Python dependencies installed. If dependencies are
missing, install them only when the task requires runtime validation and the
active approval rules allow it. For docs, skill, or workflow-only PRs, prefer
static validation such as markdown review or shell syntax checks.

## Guardrails

- Never commit directly to `main`.
- Open draft PRs; the human decides when to merge or close them.
- Keep each PR reviewable and restorable.
- Do not re-open work already covered by an open PR.
- Do not alter trading math, position sizing, or live-trading behavior without
  explicit follow-up.
- Preserve the repo safety invariants: range-relative TP/SL, exposure rollback
  on failed orders, the deliberate order retry matrix (FOK entries never retried;
  GTC/GTD remainder retried once; exits up to 3 times — see CLAUDE.md), awaited
  async callbacks, cold-start wallet baselines, and paper mode as the default.
- Workflow enhancements must not require a new license, secret, or key.
- Never hardcode secrets or put `.env` values in logs, docs, tests, or commits.

## Gotchas

- Large PR-list payloads waste context; reduce to PR number and title.
- Largest file does not mean worst file. Confirm a real defect before proposing
  refactors of `polymarket_copier/main.py`, `core/copier.py`,
  `core/monitor.py`, `core/risk_manager.py`, or `core/portfolio.py`.
- Shared-file PRs can conflict even when each change is valid. Use the
  consolidate-or-stack plan before opening PRs.
- A broken `main` poisons child PR CI. Check whether failures reproduce on
  `main` before attributing them to a child PR.

## Example Finding Groups

This example shows the desired shape only. Re-scan current `main` instead of
reusing these findings blindly.

1. CI wiring drift across lint, mypy, and test commands.
2. Async monitor and shutdown-loop efficiency in `main.py` and `core/monitor.py`.
3. API client timeout, retry, and error-context hardening.
4. Portfolio or SQLite durability plus exposure rollback checks.
5. Config and docs hardening around paper-mode defaults and live-mode safety.
