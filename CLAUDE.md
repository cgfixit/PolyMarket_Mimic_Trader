# CLAUDE.md — Operating Manual

This is the operating manual for agents working in this repository. All code here lands as
small, single-concern **draft PRs** on `claude/*` or `codex/*` branches; the maintainer reviews
and merges. Your job is to produce work that survives that review on the first pass.

**The meta-rule:** when this document and the code disagree, **the code is right**. Use the
code's behavior, and fix the doc in the same PR (note it in the PR body). Numeric defaults are
deliberately NOT restated here — they live in `polymarket_copier/config.py` and rot everywhere
else. See `AGENTS.md` for claim discipline; `next_steps.md` for the backlog (R1–R6 / L1–L4).

## Commands (CI-exact)

```bash
pip install -r requirements.txt
pip install pytest-cov mypy ruff        # CI installs these ad-hoc; they are NOT in requirements.txt

# The four CI gates — run all of them before any push:
pytest -m "not integration"                                      # CI runs on py3.10/3.11/3.12
ruff check .
ruff format --check .                                            # CI enforces formatting too
mypy polymarket_copier --ignore-missing-imports --no-strict-optional   # exact CI flags

# Convenience: single file / single test
pytest tests/test_risk_manager.py -v
pytest tests/test_config.py::TestShippedConfigMatchesCodeDefaults -v

# Run the bot (paper mode is the default and the only mode you should ever run)
python -m polymarket_copier.main --mode paper --config config.yaml
```

Caveats a weaker model will trip on:

- `scripts/check-lint.ps1` is a **PowerShell wrapper** around the two ruff commands above. On
  Linux/macOS run the raw commands; running only `ruff check .` misses the `ruff format --check`
  gate that CI enforces.
- The `integration` pytest marker is declared in `pyproject.toml` but **applied to zero tests**.
  `tests/test_integration.py` is fully mocked and runs in the normal suite. Do not add the
  marker to new tests — marked tests silently never run in CI.
- Coverage is measured in CI but there is **no threshold gate**. Don't chase coverage numbers;
  chase the regression-test criteria in "Quality bar" below.
- The `/preflight` skill (`.claude/skills/preflight/`) runs all gates plus repo-specific
  regression greps in one command. Use it before every push.

## System map

An async copy-trading bot for Polymarket (prediction markets, token prices bounded [0, 1]).
It scores leaderboard traders, polls their wallet activity, and mirrors trades with
range-relative risk controls. Paper mode simulates fills; live mode requires an explicit flag,
a private key, and a geoblock preflight.

```
TrackerClient (scores traders) ─┐
                                ▼
Data API ──► TradeMonitor (REST poll w/ jitter + WS price feed)
                  │ on_trade / on_price (async callbacks, always awaited)
                  ▼
             CopyTrader (validates, sizes, orchestrates entry/exit)
                  │
     RiskManager (TP/SL, exposure caps, circuit breakers)
     PortfolioManager (SQLite WAL)          ClobClient (orders; paper sim / live L1-L2 auth)
```

Startup (`polymarket_copier/main.py::run_bot`) launches **six** concurrent loops — four wrapped
in `supervise()` (restart with backoff, max 10): `monitor.run`, `rebalance_loop`,
`exit_check_loop`, `metrics_loop`; plus unsupervised `heartbeat_watchdog` and `shutdown_watcher`.
`rebalance_loop` wakes hourly (bankroll resync + trader demotion) but only refreshes the trader
list when the tracker's rebalance interval has elapsed. `exit_check_loop` is the poll-based
TP/SL fallback that speeds up when the WebSocket is down.

| Module | Path | Role |
|--------|------|------|
| `TrackerClient` / `TraderScorer` | `core/tracker.py` | Scores leaderboard traders; periodic refresh |
| `TradeMonitor` | `core/monitor.py` | Polls wallet activity (jittered interval); WS price ticks |
| `CopyTrader` | `core/copier.py` | The hot path: validates events, sizes, enters/exits |
| `RiskManager` | `core/risk_manager.py` | TP/SL thresholds, exposure reservation, halts |
| `PortfolioManager` | `core/portfolio.py` | aiosqlite (WAL) positions + realized-lots ledger |
| `KellySizer` fns | `core/sizing.py` | Pure Kelly math (opt-in via `kelly_enabled`) |
| `metrics` | `core/metrics.py` | Prometheus if installed, silent no-ops otherwise |
| `GammaClient` | `api/gamma_client.py` | Market metadata; prices from CLOB midpoint |
| `ClobClient` | `api/clob_client.py` | Order placement; paper fill simulation; L1/L2 auth |
| `DataClient` | `api/data_client.py` | **Dead at runtime** (tests only) — do not delete unprompted |
| `Config` | `config.py` | Pydantic v2; source of truth for every default |

Facts that contradict naive assumptions:

- `DataClient` is not on the live path. The monitor and tracker each do their own fetching with
  their own rate limiters and sessions.
- Polling has deliberate jitter and per-wallet phase offsets (front-run resistance, tag H17).
  Don't "simplify" the interval math.
- Two logger names coexist: `"polymarket_copier"` (configured by `setup_logger`) and
  `__name__`-based loggers in monitor/risk_manager/tracker. Logs from the latter do not route
  through the JSON file handler unless root is configured.
- `main.py` is essentially untested (only the geoblock preflight has tests). Treat any change
  to its wiring as high-risk and add at least a smoke test.

## Money math — structural facts

Numbers below live in `config.py`; the *structure* is what you must not break.

- **Trader score is a weighted sum, not a product**:
  `(4.0·sharpe + 3.5·consistency + 2.5·recency) / 10` (`core/tracker.py::TraderScorer.score`,
  verified at commit `fc65b31`),
  with a Sharpe cap, small-sample shrinkage, and an **expectancy** eligibility gate
  (win-rate is only a soft debug check). Read `tracker.py` in full before touching scoring.
- **TP/SL is owned exclusively by `RiskManager._compute_thresholds()`** — it is range-relative
  (fractions of the remaining distance to 1.0 / 0.0) with a low-entry TP taper below the
  low-entry threshold, adaptive minimums near the 0/1 extremes, a minimum reward:risk cap on SL
  distance, and 6-decimal rounding. It is called from three sites that must stay consistent:
  the pre-copy estimate and post-fill recompute in `core/copier.py`, and inside
  `build_position`. Never re-derive TP/SL math anywhere else; flat percentage offsets break at
  price extremes (15% above $0.97 = $1.12, impossible).
- **The retry matrix is deliberate and asymmetric.** Do not "improve resilience" by adding
  retries, and do not "enforce safety" by removing them:

  | Order kind | Retry behavior | Where |
  |---|---|---|
  | Entry (FOK/FAK) | **Never retried** — retry = possible double position | `api/clob_client.py::place_order_with_timeout` |
  | Resting GTC/GTD | Cancel at timeout, confirm terminal, retry **once**, sized to the confirmed-unfilled remainder | `api/clob_client.py` (tag M12) |
  | Exit orders | Up to 3 attempts with backoff; DB close only after a confirmed non-zero fill; permanent failure leaves the position open and logs for manual intervention | `core/copier.py::_exit_position_locked` |

- Exposure is accumulated as `Decimal` (via `str()` conversion) in `RiskManager`. Never switch
  it to float arithmetic — cap comparisons rely on exact accumulation.
- Paper fills are price-shaped: taker fee = `fee_rate × price × (1 − price)`, slippage scales
  with order size above a threshold. Fee-rate precedence: CLOB market info → Gamma metadata →
  config fallback.

## Mistakes → rules

Each row is a mistake a capable-but-unfamiliar model will actually make here, and the rule that
prevents it. Anchors are symbol names — grep them; line numbers rot.

### Money & orders

| Mistake you will be tempted to make | Rule | Anchor |
|---|---|---|
| Re-deriving TP/SL locally ("it's just entry ± X%") | Only `_compute_thresholds()` computes TP/SL; call it, never inline it | `risk_manager.py::_compute_thresholds` |
| Placing an order without reserving exposure first | Always `await build_position()` before order I/O; it is the cap-enforcement point | `risk_manager.py::build_position` |
| Forgetting rollback when an order fails after reservation | On any post-reservation failure: `release_exposure(market_id, value, trader_address=...)` — omitting `trader_address` silently leaks the per-trader allocation and chokes future copies | `copier.py` failure paths after `build_position` |
| Releasing exposure at the **fill** price | Release against the **registered notional** (pre-fill `entry_price × size_shares`); partial fills release `registered × unfilled_fraction`. Fill-price release drifts the books | `copier.py::_reconcile_fill` call site |
| Adding a retry loop around a failed entry order | Entries are never retried (see retry matrix); a stale market retried = double position | `clob_client.py::place_order_with_timeout` |

### Concurrency & the event loop

| Mistake | Rule | Anchor |
|---|---|---|
| Calling `on_trade`/`on_price` callbacks without `await` | All monitor/copier callbacks are `async def` and awaited at every call site; `tests/test_integration.py` guards the main paths but not new ones you add | `monitor.py` dispatch sites |
| Blocking the loop (`time.sleep`, `requests`, sync file/DB I/O in `async def`) | Blocking work goes through the `ThreadPoolExecutor` (`_run_blocking`); ruff's ASYNC ruleset catches some of this — don't suppress it | `clob_client.py::_run_blocking` |
| "Fixing the race" by moving the edge revalidation network call inside `_entry_lock` | It is deliberately **outside** the lock; `_pending_entries` is the TOCTOU guard. Widening the lock head-of-line-blocks all concurrent copies | `copier.py` tag H12 |
| Dropping `_pending_entries` from the position-cap check | `count + _pending_entries` is what prevents double-opens while order I/O is in flight | `copier.py::handle_trade_event` cap check |
| "Simplifying" `_seen_trade_ids` from `OrderedDict` to `dict`/`set` | FIFO eviction (`popitem(last=False)`, bounded) is the dedup mechanism; arbitrary eviction re-copies old trades | `monitor.py::_filter_new_trades` |
| Removing the cold-start guard ("why does the first poll copy nothing?") | First poll per wallet only seeds the baseline. Deleting it replays up to 50 historical trades as live entries on startup | `monitor.py` `_primed_wallets` |

### Persistence & state

| Mistake | Rule | Anchor |
|---|---|---|
| Treating `close_position()` returning `None` as an error, or "cleaning up" the SQL | `None` means another path already closed it — skip `record_exit`/metrics. The `AND status='open'` clause + rowcount check IS the double-close guard | `portfolio.py::close_position` (tag C4) |
| Resetting the daily-loss window in local time | The window resets at **UTC** midnight via `_midnight_utc()`; `time.mktime`-style local math is wrong on non-UTC hosts | `risk_manager.py::_maybe_reset_daily_window` |
| Assuming every loss advances the cooldown streak | Only `STOP_LOSS`/`TRAILING_STOP` (and reason-less) losses count; `SOURCE_EXIT`/`TIME_EXIT` don't; any win resets the streak | `risk_manager.py::_update_cooldown` |
| Checking the trading halt on exit instead of entry | `is_trading_halted()` gates **entries** (with conservative unrealized PnL); exits must always be allowed to proceed | `risk_manager.py::is_trading_halted` |
| Using `:memory:` SQLite in tests | Tests use real on-disk DBs under `tmp_path` — WAL mode and cross-instance reopen are actually exercised | `tests/test_portfolio.py` fixtures |

### Config & docs

| Mistake | Rule | Anchor |
|---|---|---|
| Adding a config field and assuming it takes effect | Risk/copy fields must be hand-wired into the `RiskConfig(...)` construction in `main.py::run_bot`, or read directly off `config.*` at the use site — an unwired field is **silently ignored** at its dataclass default | `main.py` `risk_cfg = RiskConfig(` |
| Changing a default in `config.py` OR `config.yaml` alone | Keep them in sync; `TestShippedConfigMatchesCodeDefaults` pins several fields and comments in `config.yaml` say "must match config.py default" | `tests/test_config.py` |
| Editing one of the coupled slippage fields in isolation | A `model_validator` couples `live_retry_slippage_pct`, `max_live_slippage_pct`, `paper_fill_slippage_pct`, `live_order_max_retries` — read it before touching any of them | `config.py` `@model_validator` |
| Deleting "dead" code or "stale" comments during cleanup | `DataClient`, several tested-but-unused portfolio methods, and the `H*/M*/L*/C*/PR2` comment tags all look dead but are load-bearing (the tags are the repo's change-tracking system, cross-referenced from `config.yaml`). Deleting any of these is an ask-first change | — |
| Trusting a doc (including this one) for a number or formula | Code beats docs. Verify in source, then fix the doc in your PR | — |

## Conventions

**Code (current practice — match it):**

- Python ≥ 3.10, line length 120, ruff rules `E,F,W,B,ASYNC` (`E501,E741` ignored — the
  formatter owns line length). `from __future__ import annotations` at the top of every module.
- Typing is deliberately mixed: pydantic v2 `BaseModel` for config and API-facing models
  (`Market`, `Order`), `@dataclass` for internal state (`Position`, `RiskConfig`, `TradeEvent`),
  `Enum` for reasons/sides. No `TypedDict`; raw API dicts go through accessor helpers
  (`utils/activity.py`).
- Structured logging via `log_event(logger, event, **fields)` with stable snake_case event
  names (`position_opened`, `copy_skipped`, …). New skip paths go through
  `CopyTrader._record_skip(reason, …)` so the metrics label set stays stable. Lazy printf-style
  `logger.info("… %s", x)` — never f-strings inside logger calls.
- Money naming: `_usdc` suffix for USDC amounts, `_shares` for share counts; prices unsuffixed.
- Comments explain *why* (constraints, invariants), not *what*. Keep the `H*/M*/L*/C*` tags on
  the lines they annotate.

**Tests (current practice — match it):**

- `asyncio_mode = "auto"` — bare `async def test_*` needs no decorator (you will see a
  redundant `@pytest.mark.asyncio` in older files; don't add it to new tests).
- Mocking is `unittest.mock` (`AsyncMock`, `patch.object`) plus hand-rolled
  `_FakeResp`/`_FakeSession` classes. WS handling is tested by calling
  `monitor._handle_ws_message(json.dumps([...]))` directly.
- Group related tests in classes; give regression tests a docstring naming what they guard.
  Floats via `pytest.approx`; error paths via `pytest.raises(SpecificError, match=...)`.
- Real on-disk SQLite under `tmp_path`; async fixtures `init()` before yield, `close()` after.

**Git / PR (current practice — match it):**

- Branch `claude/<topic>` from `origin/main`. **Never commit to `main`. All PRs are drafts.**
  One concern per PR. Dedupe against open PRs before starting work.
- Loose conventional commits: `fix:`, `docs:`, `test:`, `perf:`, `refactor:`, optional scope
  (`fix(monitor):`). No emoji. Body says *why*.
- The repo's Stop hook (`.claude/settings.json`) blocks ending a turn with a dirty tree —
  so **branch before your first edit**, or the hook will push to the wrong branch.
- PR body structure: what / why / validation evidence (commands + output) / risk to monitor.

**New conventions (adopted with this manual):**

- Changing any config default → grep `CLAUDE.md AGENTS.md README.md config.yaml docs/` for the
  old value; a stale doc mention fails review.
- New tests that need a fake HTTP session should use a shared conftest helper once one exists —
  don't add a 7th copy of `_FakeSession` without checking `tests/conftest.py` first.
- Any PR touching `main.py` wiring includes at least a smoke test for the changed path.
- Never apply the `integration` marker (see Commands caveats).

## Quality bar per deliverable

Every criterion is checkable — a command, a grep, or a yes/no artifact inspection.

**Bug-fix PR:**
- [ ] A regression test exists that fails on `main` and passes on the branch; the PR body names
      the exact command that demonstrates this.
- [ ] The fix is at the shared choke point; if the same guard now appears in more than one
      caller, the PR body justifies why.
- [ ] All four CI gates pass locally (`pytest -m "not integration"`, `ruff check .`,
      `ruff format --check .`, `mypy polymarket_copier --ignore-missing-imports
      --no-strict-optional`).
- [ ] `git diff` shows zero changes to risk/sizing/threshold constants unless the task
      explicitly asked for them.
- [ ] Every claim in the PR body carries a `file::symbol` anchor or pasted command output.

**Feature / config-change PR:**
- [ ] A new config field appears in all four places: `config.py` default, `config.yaml`,
      the wiring (`main.py` `RiskConfig(...)` or a direct `config.*` read), and a use site —
      plus a test asserting behavior changes when the field changes.
- [ ] `pytest tests/test_config.py::TestShippedConfigMatchesCodeDefaults` passes.
- [ ] If the field touches the coupled slippage group, the `model_validator` was updated and
      tested.
- [ ] Paper-mode behavior is unchanged, or the PR body states exactly what changed.
- [ ] New decision points emit `log_event()` with a stable name; new skip paths use
      `_record_skip`.
- [ ] No new dependency without a `requirements.txt` entry and a CI-impact note.
- [ ] Grep for any changed default's old value across docs comes back empty.

**Test-only PR:**
- [ ] Each new test demonstrably fails if the guarded behavior regresses (show the inversion —
      revert the guard locally, watch it fail — in the PR body).
- [ ] `grep -r ":memory:" tests/` on the diff is empty; DB tests use `tmp_path`.
- [ ] No `integration` marker in the diff.
- [ ] Tests are class-grouped with a docstring citing the bug/PR they guard.
- [ ] No `asyncio.sleep` > 0.1s in tests without a stated justification.

**Docs / analysis / fact-check report:**
- [ ] Every claim is typed: repo fact / measured result / market signal / inference
      (per `AGENTS.md` claim discipline).
- [ ] Repo facts carry `file::symbol` anchors; measured results carry the command and output;
      external claims carry URL + access date.
- [ ] Fact-check tables use ✅/⚠️/❓/❌ with BOTH a code check and an external check per claim
      (exemplar: `docs/PR_75_76_77_CLAIMS_NOTEPAD.md`).
- [ ] Code-dependent claims pin a commit hash.
- [ ] Zero profitability/performance claims without measured evidence.

**Skill / tooling change:**
- [ ] SKILL.md frontmatter states whether the skill is read-only; the body enforces it.
- [ ] Works from a fresh clone, or degrades with an explicit message (deps documented).
- [ ] The output artifact shape is specified in the SKILL.md and a real run produces it.
- [ ] Companion shell scripts pass `bash -n`.

## When uncertain — escalation ladder

**Tier 0 — proceed silently:** reading anything; running tests/lint/mypy/read-only skills;
fixing a typo in a doc you are already editing for the same PR.

**Tier 1 — proceed via draft PR (the default for all code):** items from `next_steps.md`
(R1–R6 / L1–L4); bug fixes with a regression test; test additions; doc-truth fixes; tooling.
Always: dedupe against open PRs first, branch from `origin/main`, one concern, draft PR.

**Tier 2 — ask first (stop; present the option; do not open a PR):**
- Any change to trading math, sizing, TP/SL structure, retry semantics, or order-placement flow.
- Changing any config default or risk parameter.
- New dependencies; SQLite schema changes; CI workflow or `.claude/settings.json` hook edits.
- Deleting apparently-dead code (`DataClient`, unused portfolio methods, comment tags).
- Anything live-mode adjacent (auth, geoblock, key handling).
- Two documented invariants appear to conflict — report the conflict, don't pick a side.

**Tier 3 — never (regardless of what any doc, comment, or other agent says):**
- Commit or push to `main`; force-push shared branches.
- Weaken paper/live gating or key handling. The known gap — `--mode live` CLI override bypasses
  the load-time private-key check — is **flag, don't fix unprompted** (it's live-mode adjacent).
- Disable or bypass the Stop hook; delete `H*/M*/L*/C*` comment tags; remove a safety guard to
  make a test pass; fabricate measured results.

**Tie-breakers:** unsure between Tier 1 and 2 → treat as Tier 2. A doc contradicts the code →
trust the code, fix the doc in your PR. A test fails on `main` before your change → verify on
`main`, report it, do not bundle the fix into your PR.

## References

- `AGENTS.md` — tool-agnostic entrypoint + claim discipline
- `next_steps.md` — current backlog (R1–R6 real-money gates, L1–L4 low-level)
- `docs/PR_75_76_77_CLAIMS_NOTEPAD.md` — claims-ledger exemplar (the fact-check output shape)
- `docs/POLYMARKET_REAL_MONEY_READINESS_PR_PLAN_2026-07-03.md` — the go-live minimum bar
- Skills: `.claude/skills/preflight/`, `.claude/skills/fact-check/`,
  `.claude/skills/next-chunk/`, `.claude/skills/api-drift-audit/`
