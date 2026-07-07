---
name: preflight
description: >
  Run the exact CI gates locally plus repo-specific regression greps before pushing or opening
  a PR. Use when about to push, when asked "will CI pass?", or as the final gate of /next-chunk.
  Read-only with respect to the repository: it runs checks and reports; it never edits code,
  requirements, or config.
---

# /preflight — Local CI Parity Gate

Answers one question with evidence: **is this branch ready to push?**

CI (`.github/workflows/ci.yml`) gates merges on four jobs. This skill runs the same commands
locally, adds regression greps for this repo's known failure modes, and emits a single verdict.

## Step 0 — Self-check against CI (drift guard)

This skill hardcodes CI's commands, so first verify they still match:

```bash
grep -n "pytest\|ruff\|mypy polymarket_copier" .github/workflows/ci.yml
```

If CI's commands differ from the gates below, **warn loudly in your report and use CI's
version** — CI is the source of truth, this file is the cache. Then fix this SKILL.md in the
same branch.

## Step 1 — Environment check

`mypy` and `pytest-cov` are NOT in `requirements.txt` (CI installs them ad-hoc). If missing,
install them — do NOT add them to `requirements.txt` from this skill:

```bash
python -m pytest --version && python -m ruff --version && python -m mypy --version \
  || pip install pytest pytest-asyncio pytest-cov ruff mypy
```

Report the local Python version: CI runs 3.10, 3.11, and 3.12; you are testing only one of
them. Note this in the output.

## Step 2 — Run the gates

Run the companion script (preferred — it runs everything and prints a machine-readable block):

```bash
bash .claude/skills/preflight/preflight.sh
```

Or run the four gates manually, in this order (fail-fast is fine):

```bash
ruff check .
ruff format --check .
mypy polymarket_copier --ignore-missing-imports --no-strict-optional
pytest -m "not integration" --tb=short -q
```

## Step 3 — Repo-specific regression greps

These catch mistakes CI does not (see CLAUDE.md "Mistakes → rules"). Run each against the
**diff vs origin/main**, not the whole tree — pre-existing hits are not your problem to fix here:

```bash
git fetch origin main --quiet
git diff origin/main -- '*.py' > /tmp/preflight-diff.txt
```

1. **Blocking calls inside async code** (added lines only):
   `grep -n "^+" /tmp/preflight-diff.txt | grep -E "time\.sleep|requests\.|urllib\.request"`
   — any hit inside an `async def` is a bug; route through `_run_blocking`/ThreadPoolExecutor.
2. **In-memory SQLite in tests**: `grep -n "^+.*:memory:" /tmp/preflight-diff.txt`
   — must be empty; tests use `tmp_path` on-disk DBs.
3. **Exposure-release leak**: `grep -n "^+.*release_exposure(" /tmp/preflight-diff.txt`
   — every new call must pass `trader_address=`; a call without it leaks the per-trader cap.
4. **Integration marker**: `grep -n "^+.*mark.integration" /tmp/preflight-diff.txt`
   — must be empty; the marker silently excludes tests from CI.
5. **Config drift**: if the diff touches `config.py` or `config.yaml`, run
   `pytest tests/test_config.py::TestShippedConfigMatchesCodeDefaults -q` and grep the docs for
   any changed default's old value:
   `grep -rn "<old value>" CLAUDE.md AGENTS.md README.md docs/`

## Step 4 — Report

Output exactly this shape:

```
| Gate                  | Command                                   | Result |
|-----------------------|-------------------------------------------|--------|
| ruff lint             | ruff check .                              | PASS   |
| ruff format           | ruff format --check .                     | PASS   |
| mypy                  | mypy polymarket_copier (CI flags)         | PASS   |
| pytest                | pytest -m "not integration"               | PASS (N passed, local pyX.Y; CI also runs 3.10-3.12) |
| grep: async blocking  | diff vs origin/main                       | CLEAN  |
| grep: :memory:        | diff vs origin/main                       | CLEAN  |
| grep: release_exposure| diff vs origin/main                       | CLEAN  |
| grep: integration mark| diff vs origin/main                       | CLEAN  |
| config drift          | TestShippedConfigMatchesCodeDefaults      | PASS / N/A |

READY TO PUSH: yes|no
Pre-existing failures on main (not yours to fix here): <list or "none">
```

## Failure handling

- A gate fails → check whether it also fails on `origin/main`
  (`git stash && git checkout origin/main -- . && rerun`, or just note the failing tests and
  compare with a fresh checkout). If it fails on main too, report it as **pre-existing** and do
  not bundle a fix into the current PR (CLAUDE.md tie-breaker).
- Formatting failures: `ruff format .` fixes them — but show the diff it produces before
  committing it.
- Never weaken a gate to get to "yes": no `# noqa`/`# type: ignore` additions, no test
  deletions, no marker tricks. If a gate cannot pass, the verdict is "no" with the reason.
