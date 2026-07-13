# Optimizer

Use `.codex/skills/optimizer/SKILL.md` as the source of truth for the
PolyMarket_Mimic_Trader optimizer workflow.

When the user asks to optimize, harden, audit, or open focused improvement PRs:

- inspect only for read-back or review requests
- for execution, require a clean tree, run `git fetch origin main`, and create a `codex/polymarket-optimize-<topic>` branch from `origin/main`; switch to an existing branch without resetting it
- scan CI, tests, `polymarket_copier/`, config, and API or SQLite choke points
- deduplicate against open PRs before choosing focus areas
- group work into small draft-PR chunks instead of one broad rewrite

Verification bias:

- `powershell -File scripts/check-lint.ps1`
- `python -m mypy polymarket_copier`
- `pytest -v -m "not integration"`
- narrower tests or paper-mode runs when the touched area justifies them

Guardrails:

- never commit directly to `main`
- preserve range-relative TP/SL, exposure rollback, cold-start guards, awaited async callbacks, and paper mode as default
- do not change live-trading behavior, secrets handling, or risk math without explicit user direction

For over-engineering cleanup, pair this with Ponytail instead of inventing new abstractions.
