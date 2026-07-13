# PolyMarket_Mimic_Trader project notes

This repository is a Polymarket copy-trading bot (Python/asyncio) with:

- Configured runtime: `polymarket_copier/main.py`
- Trading logic modules:
  - `polymarket_copier/core/copier.py`
  - `polymarket_copier/core/monitor.py`
  - `polymarket_copier/core/risk_manager.py`
  - `polymarket_copier/core/portfolio.py`
  - `polymarket_copier/core/tracker.py`
- Exchange/API clients in `polymarket_copier/api/*`
- Config in `config.yaml` and secrets via `.env`

Testing and checks:
- `pip install -r requirements.txt`
- `pytest -v`
- `pytest -v -m "not integration"`
- `powershell -File scripts/check-lint.ps1`
- `powershell -File scripts/check-lint.ps1 -Fix`
- `python -m mypy polymarket_copier`

Baseline architecture from initial inspection:
- `run_bot()` initializes config, logger, shared aiohttp session, risk manager, portfolio, clients.
- Tracker selects traders; monitor streams events and price ticks.
- CopyTrader validates events, applies risk checks, places/cancels mirrored orders.
- RiskManager enforces range-relative TP/SL and exposure/circuit-breaker rules.
- Portfolio manager persists open/closed positions in SQLite.

Notes:
- This repo contains `CLAUDE.md` with detailed operational rules.
- Canonical Codex repo instructions live in root `AGENTS.md`.
- Repo-local Codex workflow notes live in `.codex/commands/`.
- Reusable Codex skills live in `.codex/skills/`.
- Keep the split simple: repo facts in `AGENTS.md`, reusable playbooks in `.codex/`.
- `.codex/skills/optimizer/SKILL.md` is the Codex-native optimizer workflow.
- `.codex/commands/optimizer.md` is the short entrypoint that points at that skill.
- `.codex/commands/ponytail.md` documents how to apply Ponytail safely in this trading repo.
- `.codex/skills/refactor/SKILL.md` is the Codex-native iterative refactor and speed loop.
- `.codex/skills/optimizer/SKILL.md` is the repo-specific optimizer workflow.
- `.codex/skills/optimize-money-mode/SKILL.md` is the live-money-readiness optimizer for real-wallet paths, profitability docs, and legal gating.
- `.codex/skills/research-polymarket-api/SKILL.md` is the current-docs/current-law fact-check workflow for non-paper mode assumptions.
- `.codex/skills/add-enhance-tests/SKILL.md` is the realistic-tests workflow for CI-safe unit/integration coverage upgrades.
- `.codex/skills/fable-protocol/SKILL.md` is the evidence-first reasoning and security-discipline layer for substantive technical work.
- `.codex/commands/optimize-money-mode.md`, `research-polymarket-api.md`, and `add-enhance-tests.md` are the repo-local wrappers for those skills.

Codex optimization bias:

- Prefer measurable hot-path findings over generic code-style nits.
- Hunt for unique issues a broad Claude-style optimizer often repeats past: shared async choke points, repeated config or DB loads, import/startup latency, CI/runtime drift, and code that should be deleted instead of abstracted.
