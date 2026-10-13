# Ponytail Audit — 2026-10-13

Read-only simplification audit per `.codex/commands/ponytail.md`: delete duplicate helpers,
remove speculative abstractions, replace custom glue with stdlib, keep async trading paths
boring and explicit — **without** simplifying away risk controls, exposure accounting, async
correctness, or secret handling.

| Field | Value |
|---|---|
| Audited commit | `5a7f1041b6044c6dd51fe95f4d294d72500eaf3c` (`origin/main`, branch level: 0 ahead / 0 behind) |
| Scope | `polymarket_copier/` (6,088 lines) and `tests/` (8,997 lines); every package module read in full |
| Open PRs at audit time | none (`list_pull_requests state=open` → `[]`) |
| Local Python | 3.13.16 (CI also runs 3.12) |

Claim types used below: **repo fact** (anchored `file::symbol`), **measured** (command + output),
**inference** (my judgement, marked). No profitability or performance claims are made.

## Baseline gates (measured)

| Gate | Command | Result |
|---|---|---|
| ruff lint | `ruff check .` | PASS (exit 0) |
| ruff format | `ruff format --check .` | PASS (`76 files already formatted`) |
| mypy | `mypy polymarket_copier --ignore-missing-imports --no-strict-optional` | PASS (`no issues found in 22 source files`) |
| pytest | `pytest -m "not integration" -q` | PASS (`672 passed in 12.32s`) |

Extended scans (not CI gates; used only to find candidates):

```
ruff check polymarket_copier --select SIM,UP,C4,RET,PIE,PERF,FURB,RUF,PLR,PLW,T20,ARG,ERA --statistics
vulture polymarket_copier --min-confidence 60
```

## Verdict

The package is already lean where it matters: the trading paths are explicit, the retry
matrix is deliberate, and nothing in `core/risk_manager.py` or `api/clob_client.py` is
over-abstracted. What Ponytail *does* find is **duplicated glue at the edges**: three
hand-rolled timestamp parsers, two fee-rate coercers with a duplicated constant, nine
hand-rolled fake HTTP sessions in tests, one rollback sequence pasted three times, and a
handful of stdlib-replaceable try/except blocks. Total deletable without touching trading
math: roughly 60 package lines and 150+ test lines (inference from the diffs below).

Nothing here is a bug. Nothing here should be bundled into one PR.

## Findings — Tier 1 (proceed via single-concern draft PR)

Ranked by lines-deleted-per-unit-risk. All of these leave trading math, sizing, TP/SL,
exposure accounting, and retry semantics byte-for-byte unchanged.

### P1 — Three copies of ISO/epoch timestamp parsing

**Type:** repo fact.
**Anchors:** `core/monitor.py::_parse_trade_event` (inline, lines 645–659),
`core/tracker.py::_parse_timestamp`, `api/gamma_client.py::_parse_resolve_time`.

All three do `datetime.fromisoformat(raw.replace("Z", "+00:00"))`, the same
`> 1e12 → milliseconds` heuristic, and (monitor + tracker) the same naive-datetime → UTC fix,
each with its own copy of the explanatory comment. Monitor and tracker each carry a
**function-local** `from datetime import datetime, timezone` instead of a module import.

Behavioral difference to preserve: tracker returns `0.0` on any failure (L4 — pinned by
`tests/test_tracker.py` and `tests/test_timestamps.py::TestTrackerParseTimestamp`); monitor
drops the event on a malformed string (the `ValueError` propagates to the outer `except`) but
substitutes `time.time()` when the field is absent.

**Ponytail action:** one `parse_activity_timestamp(raw) -> float | None` in
`utils/activity.py` (already the home of the Data API accessor helpers) that raises
`ValueError` on a malformed string and returns `None` for absent/unknown types. Monitor keeps
its drop-on-malformed / now-on-absent semantics; tracker wraps it to `0.0`. Gamma's
datetime-returning variant can call the same helper then `fromtimestamp(..., tz=utc)`.
Existing tests cover every branch. Net: about 20 lines deleted, two local imports gone.

### P2 — Nine hand-rolled fake HTTP session classes in tests

**Type:** measured.

```
$ grep -rn "class _Fake\|class Fake" tests/ | awk -F: '{print $3}' | sort | uniq -c | sort -rn
      5 class _FakeSession
      5 class _FakeResp
      1 class _FakeSessionMonitor / _FakeRespMonitor / _FakeClientSession / _FakeActivitySession / _FakeActivityResponse (one each)
```

The five `_FakeResp` constructors differ only in which optional knobs they accept
(`status`, `reason`, `exc`). `tests/conftest.py` currently holds two data fixtures and no
session helper. CLAUDE.md "New conventions" already mandates: *"use a shared conftest helper
once one exists — don't add a 7th copy."* There is no 7th copy yet because there is no helper.

**Ponytail action:** one `FakeResp(data=None, *, status=200, reason="OK", exc=None)` and one
`FakeSession(routes_or_responses)` in `conftest.py` supporting the union of the existing
signatures; migrate the five identical-shape files first (`test_api_session`, `test_chaos`,
`test_gamma_client`, `test_integration`, `test_main`), leave the monitor/activity variants for
a second pass if their shape genuinely differs. Test-only PR; the inversion check is simply
that the suite still passes with the duplicates deleted.

### P3 — Shadowed `import math` inside a method

**Type:** repo fact. **Anchor:** `core/copier.py::CopyTrader.check_trader_demotion` line 1086
(`import math`) while `math` is already imported at module scope (line 7). Delete one line.

### P4 — Unused `websockets.exceptions` import

**Type:** measured. `grep -rn "websockets.exceptions" polymarket_copier tests` returns only
the import itself (`core/monitor.py` line 58, carrying a `# noqa: F401`). Nothing references
the submodule; `websockets` (line 57) is what the code uses. Delete the line and its noqa.

### P5 — Stdlib-replaceable glue already half-adopted

**Type:** repo fact + measured (ruff dry-run diff).

| Site | Today | Ponytail |
|---|---|---|
| `core/monitor.py::TradeMonitor.stop` | `try: await task / except CancelledError: pass` | `with suppress(asyncio.CancelledError)` — `suppress` is **already imported** (line 32) and used 100 lines later in `_ws_connect_and_listen`; the module disagrees with itself |
| `main.py::_install_shutdown_handlers` | same try/except/pass on `(ValueError, OSError)` | `contextlib.suppress` |
| `core/monitor.py::_poll_wallet` | nested `async with limiter:` / `async with session.get(...)` | single `async with a, b:` (SIM117) |
| `api/clob_client.py::place_order` `_place_sync` | `dict(token_id=..., ...)` | dict literal (C408) |
| `replay.py::build_heldout_report` | `{o: 0 for o in _OUTCOMES}` | `dict.fromkeys(_OUTCOMES, 0)` (C420) |
| `api/gamma_client.py::_parse_resolve_time` | `elif` after `return` | `if` (RET505) |
| `core/tracker.py::_compute_trader_stats` | `while key in open_buys and open_buys[key]` | `while open_buys.get(key)` (RUF019) |

All seven are `ruff --fix`-able and the dry-run diff was inspected line by line; none change
control flow. One mechanical commit.

### P6 — Two annotation dialects coexist (optional, large-but-safe)

**Type:** measured. `ruff check polymarket_copier --select UP006,UP035,UP045,UP037 --fix --diff`
touches **184 lines in 12 files**. `copier.py`, `replay.py`, `sizing.py`, and `utils/*` already
use `list[str]` / `X | None`; `monitor.py`, `tracker.py`, `risk_manager.py`, `portfolio.py`,
`config.py`, `types.py` still import `List`, `Dict`, `Tuple`, `Optional` from `typing`.
Every module has `from __future__ import annotations`, and `requires-python >= 3.10`, so the
rewrite is runtime-neutral. **Inference:** worth doing only as its own noise-only PR, and only
after the pydantic models in `config.py` / `models/types.py` are confirmed by the existing
`tests/test_config.py` run (string annotations with `|` are evaluated by pydantic at class
creation). Lowest priority in this list; skip if review bandwidth is scarce.

### P7 — `main.py::run_bot` repeats itself

**Type:** repo fact. Two duplications:

1. The tracker → copier propagation block appears at startup (lines 192–194) and inside
   `rebalance_loop` (lines 283–285): `update_tracker_win_rates`, `update_tracker_mean_pnl`,
   `_update_tracker_metrics`, same three calls, same dict comprehensions.
2. Four resource-cleanup ladders (`portfolio.close()` / `gamma_client.close()` /
   `clob_client.close()` / `shared_session.close()`) at lines 119–123, 150–155, 180–186, and
   the `finally` at 353–356, each a hand-written subset of the same list.

**Ponytail action:** a module-level `_apply_tracker_refresh(tracker, copier, traders)` for (1);
`contextlib.AsyncExitStack` with `push_async_callback` for (2) so each resource registers its
own close once. CLAUDE.md flags `main.py` wiring as high-risk and requires a smoke test;
`tests/test_main.py::TestBotShutdown` covers one shutdown path and `TestRiskConfigWiring`
covers the `RiskConfig(...)` block, so the new helper needs at minimum a test that the
rebalance path still pushes win rates and mean PnL into the copier.

### P8 — `_EPSILON_USDC` is defined after the class that uses it

**Type:** repo fact. `core/copier.py` line 1131–1133 defines the constant *below*
`class CopyTrader`; it works only because the name is resolved at call time. Move it next to
`_MAX_REASONABLE_TAKER_FEE_RATE` at the top. Zero behavior change.

### P9 — Two near-identical cache scans with two spellings of the same warning

**Type:** repo fact. `core/copier.py::_remove_pos_from_cache` and `::_update_pos_size_in_cache`
both linear-scan `self._pos_cache[token_id]` for a matching `position_id` and both log
"Position %s not found in cache for token %s — may indicate cache desync", one with an em
dash and one with a hyphen. A private `_find_cached(pos) -> Position | None` collapses both
to three lines each. H11 tag comments stay on their lines. Cache bookkeeping only, not trading
math — **inference:** Tier 1, but I'd still pair it with `tests/test_copier.py` cache tests
in the PR body.

## Findings — Tier 2 (ask first; touches order flow or risk accounting)

These are the *highest-value* Ponytail targets in the repo, and exactly the ones the
escalation ladder says not to open a PR for unprompted. Presented as options.

### P10 — Entry rollback sequence pasted three times (the real choke point)

**Type:** repo fact. **Anchor:** `core/copier.py::handle_trade_event` lines 634–637, 641–644,
659–661. Each failure path after `build_position()` does the same three things:
`_remove_pos_from_cache(pos)` → `await self.risk.release_exposure(pos.market_id,
pos.entry_price * pos.size_shares, pos.trader_address)` → `metrics.EXPOSURE_RELEASED.labels(
cause=...).inc()`. CLAUDE.md's rule *"every rollback call site MUST pass `trader_address`"*
exists precisely because this is copy-pasted; a single `async def _rollback_entry(self, pos,
cause: str)` makes the rule structural instead of a review checklist item.

Pinned by `tests/test_invariants.py::test_failed_order_rolls_back_exposure_cache_and_pending_counter`
and `::test_zero_fill_releases_the_full_registered_notional`. The partial-fill branch
(lines 670–674) releases a *fraction* and keeps the position, so it stays separate.

**Why Tier 2:** it is the order-placement failure path. Diff would be ~12 lines deleted,
~8 added, with the invariant tests as the proof. Recommend approving this one.

### P11 — Unreachable rollback around an integer increment

**Type:** repo fact. **Anchor:** `core/copier.py::handle_trade_event` lines 595–605:

```python
try:
    self._pending_entries += 1
except Exception:
    self._remove_pos_from_cache(pos)
    await self.risk.release_exposure(...)
    raise
```

`_pending_entries` is a plain `int` attribute; `+= 1` cannot raise. The ten-line `except`
branch is dead code that *looks* like a safety guard. Ponytail says delete it; the escalation
ladder says a diff that removes a `release_exposure` call from the reservation critical section
needs a human to agree it was never live. The H12 comment on line 593 is unaffected.

### P12 — Two fee-rate coercers and a duplicated constant

**Type:** repo fact + measured.

```
api/gamma_client.py:27   _MAX_REASONABLE_TAKER_FEE_RATE = 0.25
core/copier.py:32        _MAX_REASONABLE_TAKER_FEE_RATE = 0.25
api/gamma_client.py:164  def _coerce_fee_rate(value) -> Optional[float]
core/copier.py:193       def _coerce_fee_rate(value) -> float | None   (staticmethod)
```

They are **not** interchangeable: Gamma's converts basis points (`> 1.0 → / 10_000`) and
has no `isfinite` check; the copier's rejects non-finite and `> 0.25` with no bps conversion.
Unifying them changes which `Market.fee_rate` values survive (e.g. `5.0` → `None` today,
`0.0005` after), and `tests/test_invariants.py::TestFeeRatePrecedence` pins the copier side.

**Split action:** importing the constant from one module is Tier 1 (one line, no semantic
change). Unifying the functions is fee math → Tier 2; recommend leaving both and adding a
one-line comment in each pointing at the other, which is cheaper than the abstraction.

### P13 — Four copies of `max(_ZERO, dict.get(k, _ZERO) - d)` in the exposure ledger

**Type:** repo fact. **Anchor:** `core/risk_manager.py::record_exit` (lines 432–439) and
`::release_exposure` (lines 530–534) each subtract from both `_market_exposure` and
`_trader_exposure` with the same clamp; `_assert_exposure_cap` and `_assert_trader_allocation`
are the same function with different dict / cap / label. A single lock-held
`_release_locked(market_id, trader_address, value_d)` would make the open divergence
**DD-03** (release at fill-mutated price vs registered notional) a one-site fix when the
maintainer decides to take it. Exposure accounting is invariant-pinned (`test_exposure_*`),
so this is ask-first; **inference:** worth doing *together with* DD-03 rather than before it.

### P14 — Second-layer field fallbacks in `_reconcile_fill`

**Type:** repo fact. `api/clob_client.py::place_order` already normalises every live result to
top-level `filled_size` / `avg_price` via `_extract_live_fields`, so the `matched_amount`,
`fill_price`, `price` fallbacks in `core/copier.py::_reconcile_fill` only fire for a result
dict that did not come from `place_order`. Also `"k" in d and d["k"] is not None` is
`d.get("k") is not None`. Invariant-pinned (`test_paper_results_reconcile_as_a_full_fill_at_the_paper_price`).
Low value; report-only unless DD-10 (unknown-fill state) is being worked, at which point this
function gets rewritten anyway.

### P15 — Symbols vulture reports unused (frozen by CLAUDE.md, listed for one-pass triage)

**Type:** measured (`vulture --min-confidence 60`) cross-checked with grep.

| Symbol | Runtime refs | Test refs | Note |
|---|---|---|---|
| `api/data_client.py::DataClient` (whole class) | 0 | 7 | CLAUDE.md: dead at runtime, do not delete unprompted. Its `_get_session` / `close` / `_get` are byte-identical to `GammaClient`'s; a mixin would be an abstraction for dead code — Ponytail says no |
| `api/gamma_client.py::GammaClient.get_active_markets` | 0 | 2 | |
| `core/risk_manager.py::RiskManager.market_exposure`, `.trader_exposure` | 0 | 22 / 16 | heavily used as test oracles |
| `core/portfolio.py::get_position_by_token`, `get_positions_by_token`, `update_peak_price`, `get_trader_pnl` | 0 | 3 / 8 / 4 / 2 | CLAUDE.md: tested-but-unused, ask-first |
| `core/tracker.py::TrackerClient.invalidate_stats_cache` | 0 | 2 | |
| `core/metrics.py::prometheus_available` | 0 | 3 | |
| `core/monitor.py::TradeType.SIZE_UP`, `.SIZE_DOWN` | 0 | 0 | never produced by `_parse_trade_event`; the only "unused with no test" items in the list |
| `core/monitor.py::TradeEvent.outcome_label`, `.transaction_hash` | 0 (set, never read) | 0 | populated by the parser, consumed by nothing |
| `models/types.py::Market.question`, `.fees_enabled` | 0 (set, never read) | 2 | |
| `config.py::round_trip_fee_pct` | 0 | — | documented as RETIRED; schema change to remove |

No action recommended in this audit. `SIZE_UP` / `SIZE_DOWN` / `outcome_label` /
`transaction_hash` are the only candidates with zero coverage on either side; everything else
has tests that would need deleting with it.

## Non-targets (look like Ponytail bait; are not)

- `core/copier.py::handle_trade_event` at 525 lines / 23 returns / 44 branches
  (`PLR0911/0912/0915`). Ponytail's rule is *keep async trading paths boring and explicit*;
  splitting this is the refactor skill's job, not a simplification, and every early return is
  a `_record_skip` site with a stable metrics label.
- `monitor.py` jitter arithmetic, `_seen_trade_ids` as `OrderedDict`, `_primed_wallets`
  cold-start guard, the retry matrix, `_to_dec` Decimal accumulation — all invariants.
- `monitor.py` / `tracker.py` hand-rolled `session.get` + `data if isinstance(data, list) else
  data.get("activity", data.get("data", []))` vs the dead `DataClient`: CLAUDE.md states the
  separate limiters/sessions are deliberate.
- `core/metrics.py::_NoopMetric` could be a 3-line `__getattr__`; the explicit methods are what
  keep mypy happy at every call site. Leave.
- `config.py::_FiniteConfigModel`, `taker_fee_rate()` legacy alias: config-schema
  compatibility, not speculation.
- ruff `ERA001` at `monitor.py:187` is a `# Formula: …` comment, false positive.
- ruff `FURB157` `Decimal("0")` → `Decimal(0)`: equal values, but `_ZERO` is the seed of the
  invariant-pinned Decimal path; no gain, skip.
- `T201` `print` in `main.py::main` and `replay.py::main`: CLI entrypoints, correct.

## Recommended sequence

| PR | Items | Risk | Proof |
|---|---|---|---|
| A | P3 + P4 + P5 + P8 (mechanical) | none | four gates + `ruff --fix` diff pasted in body |
| B | P1 timestamp helper | low | `tests/test_timestamps.py`, `tests/test_tracker.py` unchanged and green |
| C | P2 conftest fakes (five identical-shape files) | none (test-only) | suite green with duplicates deleted |
| D | P9 cache scan helper | low | `tests/test_copier.py` cache tests |
| E | P7 `main.py` helpers + smoke test | medium (wiring) | new rebalance-propagation test |
| F | P6 annotation dialect (optional) | none | four gates |
| ask | P10, P11, P12-unify, P13 | order flow / exposure | invariant tests named above |

Each PR is one concern, branches from `origin/main`, draft, with the four gates and the
`/preflight` greps in the body.
