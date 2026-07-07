# AGENTS.md

Repository: `PolyMarket_Mimic_Trader`
Stack: Python 3.10+, asyncio trading bot

Start here:

- Read `CLAUDE.md` before changing trading logic, risk rules, async orchestration, or live-mode behavior.
- Read `.codex/README.md` for the repo-local Codex workflow.
- Use `.codex/skills/refactor/SKILL.md` when asked to refactor structure or run an iterative speed/refactor loop.
- Use `.codex/commands/optimizer.md` for read-only audit and quality-review passes.
- Use Ponytail when the user asks for the shortest safe fix or when deleting over-engineering.
- Claude-side skills live in `.claude/skills/`: `preflight` (local CI parity gate), `fact-check` (claims ledger), `next-chunk` (backlog → draft PR), `api-drift-audit` (read-only Polymarket API drift probe).

Behavioral baseline:

- Preserve the safety rules in `CLAUDE.md`, especially range-relative TP/SL, exposure rollback, cold-start guards, and the order retry matrix (FOK entries are never retried; resting GTC/GTD orders retry once for the confirmed-unfilled remainder; exit orders retry up to 3 times — see `CLAUDE.md` "Money math").
- Use async-safe patterns. Avoid blocking calls, unbounded polling, or sync I/O in hot event-loop paths.
- Do not alter trading math, position sizing, exchange assumptions, or live-trading behavior without explicit follow-up.
- Prefer small diffs at the shared choke point instead of patching symptoms in multiple callers.
- Never hardcode secrets. Keep `.env` local and out of repo.
- Use parameterized SQL or safe library APIs when touching SQLite reads or writes.
- Keep paper mode as the default unless the maintainer explicitly requests live-mode work.

Validation commands:

- `pip install -r requirements.txt` (plus `pip install pytest-cov mypy ruff` — CI installs these ad-hoc; they are not in requirements.txt)
- `pytest -v -m "not integration"` (what CI runs; the `integration` marker is applied to zero tests)
- `pytest tests/test_risk_manager.py -v`
- `ruff check .` and `ruff format --check .` (both are CI gates; `scripts/check-lint.ps1` is a Windows PowerShell wrapper around the same two commands)
- `mypy polymarket_copier --ignore-missing-imports --no-strict-optional` (exact CI flags)
- `python -m polymarket_copier.main --mode paper --config config.yaml`
- Or run everything at once: `bash .claude/skills/preflight/preflight.sh`

Repo facts:

- Line length is 120 in `pyproject.toml`.
- Tests use `asyncio_mode = "auto"` with shared fixtures in `tests/conftest.py`.
- Prometheus metrics exist when enabled in `config.yaml`, but do not assume a metrics endpoint is available in ordinary local runs.
- Existing Claude-side audit notes live in `.claude/commands/optimizer.md`; keep Codex guidance repo-native and tool-agnostic.

Code map:

- `polymarket_copier/main.py` - startup, supervision loops, shutdown flow
- `polymarket_copier/config.py` - env and YAML configuration
- `polymarket_copier/core/copier.py` - trade validation and copy decisions
- `polymarket_copier/core/monitor.py` - polling and price-stream monitoring
- `polymarket_copier/core/risk_manager.py` - TP/SL, exposure, and circuit-breaker logic
- `polymarket_copier/core/portfolio.py` - SQLite-backed position persistence
- `polymarket_copier/core/sizing.py` - Kelly sizing logic
- `polymarket_copier/api/*.py` - Polymarket API clients
- `config.yaml` - runtime parameters
- `tests/` - unit, integration, metrics, and chaos coverage

Claim discipline:

- Separate repo-backed facts, measured runtime results, market signals, and inference when editing docs or strategy notes.
- Do not turn README or profitability docs into performance or PMF claims without current evidence.
- Prefer paper-mode verification and measured logs over narrative claims about trading edge.
