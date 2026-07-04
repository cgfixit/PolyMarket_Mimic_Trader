---
name: refactor
description: >-
  Iterative architecture and speed refactor loop for PolyMarket_Mimic_Trader.
  Use when asked to refactor structure, clean up code organization, or run an
  autonomous measured optimization loop with verification, review, commits, and
  tracker updates.
---

# Refactor

Use this skill for `PolyMarket_Mimic_Trader` when the user asks for a refactor,
architecture cleanup, or iterative speed work.

This skill combines the architecture loop and speed loop into one measured
workflow. It is Codex-native and always runs with Ponytail bias: reuse existing
code, prefer stdlib, delete dead structure before adding new structure, and fix
the shared choke point instead of patching every caller.

## Rules

- Never weaken trading safety rules from `CLAUDE.md`.
- Never use live trading as a speed benchmark. Use deterministic local paths.
- One targeted change per loop. Do not mix unrelated refactors in one commit.
- After every significant step: measure, verify, autoreview, commit, update the
  tracker.
- Keep progress in `/tmp/refactor-${PROJNAME}.md`.

## Setup

From the repo root:

```bash
PROJNAME=$(basename "$PWD")
TRACKER="/tmp/refactor-${PROJNAME}.md"
```

Initialize the tracker if needed:

```bash
[ -f "$TRACKER" ] || cat > "$TRACKER" <<EOF
# Refactor Loop - $PROJNAME
Started: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
Target: architecture cleaned up and deterministic hot paths under 50 ms where feasible
## Goals
- Clean, modular architecture
- No duplicated trading logic or scattered safety checks
- Deterministic local hot paths measured after each change
- Ponytail defaults: delete, simplify, reuse
## Baseline
(record first measurements before editing)
## Progress
EOF
```

## Measurement Protocol

This repo is not a web app. Treat "page/module under 50 ms" as deterministic
local hot paths that matter to operator feedback and module load cost.

Keep measurement conditions fixed for every iteration:

- same Python version
- same dependency set
- same warm/cold approach each run
- five runs per measurement
- median, not mean

Suggested baseline set:

```bash
python -m pytest tests/test_config.py -q
python -m pytest tests/test_risk_manager.py -q
python -m pytest tests/test_monitor.py -q
python -c "import time; t=time.perf_counter(); import polymarket_copier.config; print(int((time.perf_counter()-t)*1000))"
python -c "import time; t=time.perf_counter(); import polymarket_copier.core.risk_manager; print(int((time.perf_counter()-t)*1000))"
```

If the change targets a different hot path, swap in the matching targeted test
or import probe and record why.

Record the results under `### Step N - Measurement`.

Pass/fail gate:

- A step passes when the measured hot paths improve and the targeted paths you
  own are under 50 ms, or when the remaining floor is clearly interpreter or
  external-I/O bound and you document that ceiling in the tracker.
- If any owned path is still slower, target the slowest one next.

## Loop

Repeat until the stop criteria are met:

1. Assess
   - Look for god modules, duplicated logic, tangled async flow, repeated config
     loads, repeated DB work, redundant API shaping, or docs/CI drift.
   - Record the highest-leverage finding in the tracker under
     `### Step N - Assessment`.
2. Pick one change
   - Prefer deleting dead code, extracting one bounded helper, collapsing
     duplicated checks, caching repeated local work, or removing a needless
     abstraction.
   - State the target path, expected speedup, and risk.
3. Execute
   - Make one focused change.
4. Measure
   - Re-run the full measurement set under the same conditions.
5. Live-test correctness
   - Run the narrowest useful checks:
   - `pytest tests/test_risk_manager.py -v` for trading-threshold changes
   - `pytest tests/test_monitor.py -v` for polling/stream logic
   - `pytest tests/test_integration.py -v` when orchestration behavior changed
   - `pytest -v -m "not integration"` when the change crosses multiple modules
6. Autoreview
   - Review the diff in REVIEW MODE.
   - Findings first. Fix correctness or safety regressions before committing.
   - Bias toward findings Claude-style broad scans often miss here:
     - shared async choke points
     - unnecessary config or DB reloads
     - import/startup cost in operator paths
     - CI/test drift versus actual runtime behavior
     - code that can be deleted instead of abstracted
7. Commit
   - `git add -p`
   - `git commit -m "refactor: <what changed and why>"`
   - Use `perf:` when the step is mainly a measured speed gain.
8. Update tracker
   - Add `### Step N - Done` with:
     - target
     - change
     - measurement result
     - tests run
     - autoreview outcome
     - commit hash

## Stop Criteria

Stop when all are true:

- No module in scope is doing multiple unrelated jobs without a good reason.
- Shared trading safety rules live in one obvious place.
- Imports and async flow are coherent enough to follow without jumping through
  duplicate wrappers.
- Deterministic owned hot paths are under 50 ms for two consecutive runs, or a
  documented runtime floor is the remaining limit.
- The latest targeted tests pass.
- The latest autoreview finds no correctness issues worth fixing before handoff.

Append:

```md
## Final State
Completed: <timestamp>
Summary: <what improved>
Ceilings: <anything still above target and why>
```
