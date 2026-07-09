# Optimize Money Mode

Use `.codex/skills/optimize-money-mode/SKILL.md` as the source of truth for
live-money-readiness work in `PolyMarket_Mimic_Trader`.

When the user asks to improve non-paper mode:

- start from fresh `origin/main`
- read the repo's profitability, strategy, readiness, and audit `.md` files first
- verify current Polymarket docs, geoblock behavior, and legal constraints before asserting anything
- optimize for execution correctness, fee-aware edge preservation, wallet/auth correctness, and fail-closed compliance
- do not claim "likely profitable" or "legal" without fresh evidence and an explicit caveat

Validation bias:

- `powershell -File scripts/check-lint.ps1`
- `python -m mypy polymarket_copier --ignore-missing-imports --no-strict-optional`
- `pytest -v -m "not integration"`
- the narrowest live-path tests justified by the touched code
