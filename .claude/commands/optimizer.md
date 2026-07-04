# /optimizer

Use `.codex/skills/optimizer/SKILL.md` as the source of truth for the
PolyMarket_Mimic_Trader optimizer workflow.

For read-only audit requests:

- inspect CI, tests, `polymarket_copier/`, config, and API or SQLite choke points
- return ranked findings first with file and line references
- prefer small safe fixes over broad rewrites

For execute or PR-opening requests:

- run `bash .codex/skills/optimizer/bootstrap.sh [branch-name]`
- deduplicate against open PRs before selecting work
- group findings into focused draft-PR chunks
- verify with the narrowest useful lint, mypy, pytest, or paper-mode check

Guardrails:

- never commit directly to `main`
- preserve range-relative TP/SL, exposure rollback, cold-start guards, awaited async callbacks, and paper mode as default
- do not change live-trading behavior, secrets handling, or risk math without explicit user direction

Optional: `/optimizer --focus=async` to bias the scan toward async safety and event-loop choke points.
