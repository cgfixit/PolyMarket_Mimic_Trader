# Add Enhance Tests

Use `.codex/skills/add-enhance-tests/SKILL.md` as the source of truth for
tests-only work in this repo.

When the user asks to improve `tests/`:

- prefer existing fixtures, fake sessions, and invariant patterns before adding new scaffolding
- add realistic API payload shapes from current Polymarket docs without making CI depend on live network calls
- keep test PRs deterministic and small
- run the same repo validation gates used elsewhere after edits

Validation bias:

- `powershell -File scripts/check-lint.ps1`
- `python -m pytest -v -m "not integration"`
- narrower targeted test files first when the touched area is local
