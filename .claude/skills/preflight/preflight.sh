#!/usr/bin/env bash
# preflight.sh — local CI parity gate for PolyMarket_Mimic_Trader.
# Runs the exact CI gate commands plus repo-specific regression greps and prints a
# machine-readable PASS/FAIL block. Read-only: never edits code, requirements, or config.
#
# Usage: bash .claude/skills/preflight/preflight.sh
# Exit code: 0 if READY TO PUSH, 1 otherwise.

set -u

cd "$(git rev-parse --show-toplevel)" || exit 1

PASS=1
declare -a ROWS

run_gate() {
  # run_gate <label> <command...>
  local label="$1"; shift
  local out
  if out="$("$@" 2>&1)"; then
    ROWS+=("GATE|${label}|PASS")
  else
    ROWS+=("GATE|${label}|FAIL")
    PASS=0
    printf '\n===== %s FAILED =====\n%s\n' "$label" "$out" | tail -n 40
  fi
}

echo "== preflight: environment =="
python --version
for tool in ruff mypy pytest; do
  if ! python -m "$tool" --version >/dev/null 2>&1; then
    echo "MISSING: $tool (CI installs it ad-hoc; run: pip install pytest pytest-asyncio pytest-cov ruff mypy)"
    ROWS+=("GATE|env:${tool}|FAIL")
    PASS=0
  fi
done

echo "== preflight: CI drift self-check =="
# This script hardcodes CI's commands; warn if the CI definitions no longer contain them.
# The ruff gates run via scripts/check-lint.ps1 (invoked by ci.yml's lint job), so the
# format-check needle is verified against that script, not ci.yml itself.
for needle in 'not integration' 'check-lint.ps1' 'mypy polymarket_copier --ignore-missing-imports --no-strict-optional'; do
  if ! grep -qF "$needle" .github/workflows/ci.yml; then
    echo "WARN: '.github/workflows/ci.yml' no longer contains '${needle}' — CI is the source of truth; update the preflight skill."
    ROWS+=("GATE|ci-drift:${needle}|WARN")
  fi
done
if ! grep -qF '"format", "--check"' scripts/check-lint.ps1; then
  echo "WARN: 'scripts/check-lint.ps1' no longer runs ruff format --check — CI is the source of truth; update the preflight skill."
  ROWS+=("GATE|ci-drift:ruff-format|WARN")
fi

echo "== preflight: gates =="
run_gate "ruff-lint"   python -m ruff check .
run_gate "ruff-format" python -m ruff format --check .
run_gate "mypy"        python -m mypy polymarket_copier --ignore-missing-imports --no-strict-optional
run_gate "pytest"      python -m pytest -m "not integration" --tb=short -q

echo "== preflight: regression greps (diff vs origin/main, added lines only) =="
git fetch origin main --quiet 2>/dev/null || echo "WARN: could not fetch origin/main; grepping against local origin/main ref"
DIFF="$(git diff origin/main -- '*.py' 2>/dev/null | grep '^+' | grep -v '^+++' || true)"

check_grep() {
  # check_grep <label> <pattern> <explanation>
  local label="$1" pattern="$2" why="$3"
  local hits
  hits="$(printf '%s\n' "$DIFF" | grep -En "$pattern" || true)"
  if [ -n "$hits" ]; then
    ROWS+=("GREP|${label}|HIT")
    PASS=0
    printf '\n===== grep %s HIT (%s) =====\n%s\n' "$label" "$why" "$hits"
  else
    ROWS+=("GREP|${label}|CLEAN")
  fi
}

check_grep "async-blocking"    'time\.sleep|requests\.|urllib\.request' \
  "blocking call in diff — if inside async def, route through _run_blocking/ThreadPoolExecutor"
check_grep ":memory:"          ':memory:' \
  "tests must use tmp_path on-disk SQLite, never :memory:"
check_grep "integration-mark"  'mark\.integration' \
  "the integration marker silently excludes tests from CI — do not apply it"

# release_exposure without trader_address: flag calls that close the parens without the kwarg.
RELEASE_HITS="$(printf '%s\n' "$DIFF" | grep -E 'release_exposure\(' | grep -v 'trader_address' || true)"
if [ -n "$RELEASE_HITS" ]; then
  ROWS+=("GREP|release_exposure|HIT")
  PASS=0
  printf '\n===== grep release_exposure HIT (must pass trader_address= or the per-trader cap leaks) =====\n%s\n' "$RELEASE_HITS"
else
  ROWS+=("GREP|release_exposure|CLEAN")
fi

# Config drift: only when the diff touches config files.
if git diff origin/main --name-only 2>/dev/null | grep -qE '^(polymarket_copier/config\.py|config\.yaml)$'; then
  run_gate "config-drift" python -m pytest "tests/test_config.py::TestShippedConfigMatchesCodeDefaults" -q
else
  ROWS+=("GATE|config-drift|N/A")
fi

echo
echo "== preflight: summary =="
for row in "${ROWS[@]}"; do
  echo "$row"
done
echo
if [ "$PASS" -eq 1 ]; then
  echo "READY TO PUSH: yes"
  exit 0
else
  echo "READY TO PUSH: no"
  exit 1
fi
