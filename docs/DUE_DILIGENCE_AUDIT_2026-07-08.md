# Due-Diligence Audit — Doc/Claim vs. Code Behavior Divergences

**Date:** 2026-07-08
**Commit audited:** `05ef1cd` (`origin/main` at audit time); re-verified against `6c6bd94`
(`origin/main` at push time — see DD-02, fixed upstream between the two commits, and DD-23,
introduced upstream between them)
**Method:** full-source read of `polymarket_copier/` plus claim extraction from README.md,
SECURITY.md, CLAUDE.md, AGENTS.md, config.yaml comments, module docstrings, and the docs/
reports; every code-behavior claim was checked against source, and the highest-impact findings
were reproduced with executable snippets (outputs pasted inline).

**Claim typing** (per AGENTS.md discipline): every finding's REALITY is a **repo fact** with a
`file::symbol` anchor; items marked **[measured]** include command output reproduced in this
environment; items marked **[inference]** depend on live-API behavior not verifiable offline.

Severity: **S1** = money-losing / safety-property failure, **S2** = wrong behavior or silent
failure mode, **S3** = doc rot that will cause a wrong operational decision.

---

## S1 — Safety-property divergences

### DD-01. A `mode` typo routes orders down the LIVE path while every live safety gate stays off

- **Claim** (CLAUDE.md "System map"; SECURITY.md #2; README "Real-Money Status"): *"live mode
  requires an explicit flag, a private key, and a geoblock preflight"* / *"Paper mode is the
  supported default"*.
- **Reality:** the paper/live decision is made by **two different, inconsistent string
  comparisons**. `api/clob_client.py::ClobClient.__init__` sets
  `paper_mode = config.mode == "paper"`, while every safety gate checks `config.mode == "live"`
  (`config.py::load_config` private-key check, `main.py::_enforce_live_geoblock_preflight`,
  `main.py::rebalance_loop` bankroll resync, `copier.py` paper-slippage selection).
  `AppConfig.mode` is a plain `str` (`config.py::AppConfig`), so any third value — `"PAPER"`,
  `"Paper"`, `"papr"`, `"prod"` — yields a hybrid: **not paper** for order placement, **not
  live** for gating.
- **Evidence [measured]:**
  ```
  mode='PAPER' -> ClobClient.paper_mode = False | geoblock gate would run: False | load-time key check would run: False
  ```
- **Scenario:** an operator who keeps `POLY_PRIVATE_KEY` in `.env` (e.g. for occasional live
  tests) edits `config.yaml` to `mode: PAPER`. Load succeeds (no key check — mode ≠ "live"),
  geoblock preflight is skipped (mode ≠ "live"), and `ClobClient` signs and submits **real
  orders** on the first copied trade. The single most load-bearing safety property in the repo
  is enforced by exact-string luck, not by construction.

### DD-02. `--mode live` CLI flag bypasses the load-time private-key AND funder checks — **FIXED upstream, commit `b666acf` (2026-07-08, after this audit's source read)**

- **Claim** (SECURITY.md #2: live trading requires the flag *"and a configured
  POLY_PRIVATE_KEY"*; docs/PROFITABILITY_FACTCHECK_REPORT_JULY_2026.md §3.2: live +
  `signature_type=3` without funder *"now raises ConfigError at startup"*).
- **Original reality (at audit commit `05ef1cd`):** both checks lived in
  `config.py::load_config` and fired only if the YAML/env mode was already `"live"`.
  `main.py::run_bot` applied the CLI override **after** load, so with the shipped
  `mode: paper` neither check ever ran for `--mode live`.
- **Current reality [measured against `origin/main` @ `3b18ca2`]:** `config.py` now exposes
  `validate_live_config(config)`, called both at the end of `load_config()` **and** again by
  `main.py::run_bot` immediately after applying the CLI override
  (`config.mode = mode; validate_live_config(config)`). Reproduced:
  ```
  ConfigError raised as expected: POLY_PRIVATE_KEY required for live mode
  ```
  Both the missing-key and missing-funder cases now raise the clean `ConfigError` regardless
  of whether `"live"` came from YAML or `--mode`. **This closes the gap; SECURITY.md and the
  fact-check report's claims are accurate again.** No further action needed — flagged here so
  the fix has a record and isn't rediscovered as "new."

### DD-03. `record_exit` releases exposure at the fill-mutated entry price — the books drift

- **Claim** (CLAUDE.md "Mistakes → rules": *"Release against the **registered notional**
  (pre-fill entry_price × size_shares) … Fill-price release drifts the books"*).
- **Reality:** the failure paths in `copier.py::handle_trade_event` honor this (they release
  `registered_notional`), but the **successful-exit path does not**: after fill reconciliation
  mutates `pos.entry_price = fill_price` (`copier.py::handle_trade_event`, H5 block),
  `risk_manager.py::RiskManager.record_exit` releases
  `pos.entry_price * pos.size_shares` — the **fill** notional, not the registered one. In
  paper mode the buy fill price is always above the quoted price (slippage + fee), so every
  close over-releases; `max(_ZERO, …)` clamps per-key at zero, which means the over-release
  silently eats *other* positions' registered exposure in the same market/trader bucket.
- **Evidence [measured]:** two positions registered at $50 each in one market; close the first
  after mutating its entry 0.50 → 0.55 (fill):
  ```
  registered market exposure: 100.0
  after exit of p1: market exposure = 44.99999999999999 (p2 alone should still be 50.0)
  ```
- **Scenario:** with adverse fills the market/trader exposure understates reality → the
  8%/5%/30% caps admit more risk than configured. With favorable fills the release is too
  small → phantom exposure accumulates and silently chokes off copies in that market/trader
  ("bot stopped copying X" with no log). Either direction, the documented invariant that cap
  math is exact (`Decimal` accumulation) is defeated by a float-times-wrong-price at the top.

### DD-04. The `min_reward_risk` floor is violated near the price ceiling

- **Claim** (`risk_manager.py::RiskManager._compute_thresholds` H2 comment: *"so the floor R:R
  is always respected"*; `RiskConfig.min_reward_risk` docstring: *"Caps the SL distance so R:R
  never inverts below this floor"*).
- **Reality:** the SL cap is computed from the **unclamped** `tp_raw`; TP is clamped to 1.0
  *afterwards*. For entries where `entry + min_tp_abs > 1.0` (i.e. entry > 0.97 with the
  default `min_tp_abs=0.03`), the realized TP distance shrinks below the distance the SL cap
  was computed from, and the floor inverts.
- **Evidence [measured]:**
  ```
  entry=0.971 tp=1.0 sl=0.941 R:R=0.967  <-- FLOOR VIOLATED
  entry=0.975 tp=1.0 sl=0.945 R:R=0.833  <-- FLOOR VIOLATED
  entry=0.985 tp=1.0 sl=0.955 R:R=0.500  <-- FLOOR VIOLATED
  ```
- **Scenario:** latent under shipped defaults (the `max_entry_price=0.95` band gate keeps the
  copy path out of this region), but any operator who raises `max_entry_price` — or any future
  code path that recomputes thresholds at a post-slippage fill price above 0.97 — gets
  structurally negative-EV positions that the config promises are impossible.
  `tests/test_invariants.py::test_reward_risk_floor_holds_across_default_entry_band` pins the
  region where the floor actually holds.

### DD-05. WS price message without a `price` field emits a 0.0 tick → stop-loss cascade

- **Claim** (`monitor.py::TradeMonitor._handle_ws_message` guards: out-of-range prices are
  logged and ignored; the api-drift posture elsewhere in the repo is fail-closed).
- **Reality:** `float(event.get("price", 0))` supplies its own sentinel `0` for a **missing**
  key, and `0.0` passes the `0.0 <= price <= 1.0` range check — so a `price_change` event that
  carries `asset_id` but no top-level `price` (the current Polymarket drift direction is a
  nested `changes` array) becomes a **valid-looking tick at $0.00**.
- **Evidence [measured]:**
  ```
  ticks emitted: [('tokX', 0.0)]
  ```
- **Scenario:** one drifted WS payload per token → `RiskManager.evaluate` sees
  `current_price <= sl_price` → STOP_LOSS on **every open position** on that token → live FAK
  sell into the book at whatever the real bid is. A single silent API shape change becomes an
  unattended full liquidation. This is the exact class of event `.claude/skills/api-drift-audit`
  exists to catch, but nothing at runtime fails closed.

### DD-06. The cache-eviction double-SELL guard holds only for *concurrent* triggers

- **Claim** (`copier.py` C4 comment: the per-position lock *"stops us placing two live SELL
  orders for one position"*; CLAUDE.md: the DB `AND status='open'` guard is the belt, the lock
  the suspenders).
- **Reality:** poll-path exits (`copier.py::CopyTrader.check_all_exits`) evaluate **fresh
  `Position` objects loaded from the DB**, while eviction from the in-memory cache
  (`copier.py::CopyTrader._remove_pos_from_cache`) uses `list.remove(pos)` — dataclass
  **value** equality. Peak-price updates are debounced (`_peak_dirty`, default 30 s flush), so
  the DB copy routinely differs from the cached object in `peak_price`; eviction then fails
  (the code's own "cache desync" warning), and the closed position **stays in the cache**.
  Every subsequent tick re-triggers `_exit_position` for the phantom, which places a real SELL
  **before** `close_position` returns `None` — the DB guard prevents double *accounting*, not
  double *orders*, and the per-position lock only serializes concurrent triggers.
- **Evidence [measured]:**
  ```
  Position p1 not found in cache for token tok — may indicate cache desync
  cache after eviction attempt: [Position(id='p1', ... peak=0.6200)]
  phantom position still cached: True
  ```
- **Scenario:** WS tick raises the cached peak at t+0; poll sweep exits the position from the
  DB copy at t+5 (peaks differ) → eviction fails → for as long as ticks arrive on that token,
  the bot re-sends SELL orders for shares it no longer holds (live: naked sells / venue
  rejections at best).

---

## S2 — Silent failure modes & unenforced invariants

### DD-07. `supervise()` cannot restart the monitor: `monitor.run()` swallows child crashes

- **Claim** (CLAUDE.md "System map": four loops *"wrapped in supervise() (restart with
  backoff, max 10)"* including `monitor.run`).
- **Reality:** `monitor.py::TradeMonitor.run` ends with
  `await asyncio.gather(*tasks, return_exceptions=True)`. If the poll loop dies of an
  unhandled exception, the exception is **captured, not raised**; `run()` keeps awaiting the
  WS task indefinitely, so `supervise("monitor", …)` never observes a crash and never
  restarts anything. The `heartbeat_watchdog` logs a stall error but restarts nothing.
- **Scenario:** any bug or environment change that kills `_poll_loop` (not the per-wallet
  fetches, which are individually caught) produces a bot that holds positions, manages exits
  via WS, **and silently never detects another trade** — logging only periodic WATCHDOG lines
  that nothing acts on. The advertised supervision ("max 10 restarts") is inert for the one
  loop that matters most.

### DD-08. WS subscription updates depend on unrelated inbound traffic

- **Claim** (`monitor.py` module docstring flow: *"Position registered → token_id added to
  WebSocket subscription"*; README: *"sub-second latency for exits"*).
- **Reality:** `subscribe_token()` only mutates a set. The subscription message is sent by
  `_maybe_update_subscription`, which is called **only inside the `async for raw_msg in ws`
  loop** — i.e. only when *some* message arrives. With zero active subscriptions the market
  channel sends nothing; the only traffic is the server's `PONG` reply to the app-level
  `PING` heartbeat every 10 s (`_ws_heartbeat`). The first position's price feed therefore
  starts up to ~10 s late, **and only because the PONG happens to arrive as a text frame** —
  an invariant held by server convention, not by code.
- **Scenario:** if Polymarket ever answers pings at the protocol level only (or drops PONG
  frames), token subscriptions stop being sent whenever the subscribed set was empty at
  connect; positions opened after a reconnect get **no WS ticks at all** and are managed only
  by the slower poll fallback. Nothing logs the difference.

### DD-09. Trader demotion is undone by the next rebalance; `_demoted_traders` is write-only

- **Claim** (`copier.py` H13 comment: *"tracks demoted traders so Kelly sizing stops using
  them"*; README Observability: *"trader_demoted — trader removed from pool"*).
- **Reality:** `copier.py::CopyTrader.check_trader_demotion` adds to `_demoted_traders`, but
  **no code reads that set** (grep: one write site, zero read sites). The actual demotion
  effect is popping the tracker priors and `main.py::rebalance_loop` shrinking the wallet
  list — and the next `tracker.refresh()` (7-day cycle) **wholesale replaces** both the
  wallet list and the priors from the leaderboard, silently re-promoting any demoted trader
  who still ranks. Re-demotion then needs another hourly cycle, during which the trader is
  copied again.
- **Scenario:** a wallet the bot demonstrably loses money copying (Wilson upper bound below
  `min_win_rate`) re-enters the pool every rebalance and gets fresh copies for up to an hour,
  forever. The "removed from pool" claim describes at most a 7-day suspension.

### DD-10. Live fill reconciliation degrades to "assume fully filled at the quoted price"

- **Claim** (`copier.py` step 10b comment / CLAUDE.md: *"Reconcile against the ACTUAL fill …
  assuming a full fill would overstate pos.size_shares (corrupting PnL …)"*).
- **Reality:** `copier.py::CopyTrader._reconcile_fill` falls back to a **full fill at
  `current_price`** whenever the result dict lacks `filled_size`/`matched_amount` (the code
  comment admits this). `clob_client.py::place_order` populates those keys from
  `_extract_live_fields(signed_order)` — but py-clob-client's immediate `POST /order` response
  does not reliably carry a fill-size field **[inference — depends on live API shape]**; the
  reliable source (`get_order`) is only consulted on the resting-order timeout path, never for
  FOK entries or FAK exits.
- **Scenario:** a live FOK entry that the venue *kills* (no fill) but reports without a fill
  field is recorded as a full position at the quoted price: DB position with zero real shares,
  exposure reserved, TP/SL later "exits" it and books fake PnL against real bankroll numbers.
  The reconciliation safety story is only as strong as an undocumented venue field name.
  **Partial hardening upstream (commit `a0a0505`):** the retry-confirm `get_order` calls in
  `place_order_with_timeout` are now wrapped in `_get_order_with_timeout` (bounded by
  `asyncio.wait_for`), so a stuck status call degrades to "ambiguous → no retry" instead of
  hanging the copy path forever. This fixes a liveness risk but does not touch the fallback
  described above, which applies to the FOK/FAK entry and exit paths `place_order_with_timeout`
  never reaches.

### DD-11. The tax-lot "same transaction" atomicity holds only by convention

- **Claim** (`portfolio.py::PortfolioManager.close_position` comment: *"Record an immutable
  tax lot in the SAME transaction as the close, so the ledger can never drift from the
  positions table"*).
- **Reality:** all writers share one `aiosqlite` connection in autocommit-off implicit
  transactions. Between `close_position`'s UPDATE and its lot INSERT there are awaits; a
  concurrently scheduled `batch_update_peak_prices` (the debounced H11 flush) issues its own
  `COMMIT` on the **same connection**, committing the half-done close. A crash in that window
  persists a closed position with no tax lot. Nothing (e.g. `BEGIN IMMEDIATE`, a write lock)
  enforces the claimed atomicity.
- **Scenario:** power-loss during a busy tick → `realized_lots` disagrees with `positions` —
  precisely the drift the comment declares impossible; year-end reporting silently
  under-counts disposals.

### DD-12. Wallets re-added after removal skip the cold-start guard

- **Claim** (`monitor.py` `_primed_wallets` comment / CLAUDE.md: first poll per wallet only
  seeds the baseline).
- **Reality:** `set_wallets()` retains `_seen_trade_ids` for *all* wallets ever tracked and
  never removes anyone from `_primed_wallets`. A wallet dropped at rebalance and re-added
  weeks later is still "primed", with a stale seen-set — its entire visible backlog (up to 50
  trades) is emitted as live events on the first poll. Only the `max_trade_age_seconds`
  staleness gate (12 s default) stands between that replay and real orders; an operator who
  sets it to 0 ("disable the gate", per the config comment) re-enables the cold-start bug the
  guard exists to prevent.

### DD-13. `activity_notional_usdc` falls back to share count as if it were USDC

- **Claim** (`utils/activity.py::activity_notional_usdc` docstring: *"Return activity notional
  in USDC"*).
- **Reality:** `float(raw.get("usdcSize", raw.get("size", 0)))` — the legacy fallback `size`
  is a **share count** on the current Data API. If `usdcSize` is ever absent, sizing treats
  shares as dollars (`event.size_usdc`), inflating `copy_size_usdc` by 1/price (20× at a $0.05
  token) before the `max_trade_pct` cap truncates it — every copy silently maxes out at the
  cap, and the tracker's ROI stats (same helper) corrupt in the same direction.

### DD-14. "Daily loss limit halts trading" actually force-liquidates the whole portfolio

- **Claim** (README Risk Controls #6: *"halts all trading after 3% daily loss"*;
  `risk_manager.py::RiskManager.is_trading_halted` docstring: gates **entries**).
- **Reality:** breach also makes `evaluate()` return `DAILY_LOSS_LIMIT` for **every open
  position on every tick** (priority 0, before any position-level logic), and
  `copier.handle_price_tick`/`check_all_exits` treat any non-HOLD reason as "exit now" — so
  the breach **sells every open position at market** (FAK into the bid), realizing maximum
  slippage at the worst moment, then re-arms at UTC midnight. That may be a defensible design,
  but no doc says "liquidate"; two docs say "halt".

---

## S3 — Doc rot that will cause wrong decisions

### DD-15. README describes the *old multiplicative* scoring formula

README ("Sharpe ratio × Consistency × Recency", twice) vs
`tracker.py::TraderScorer.score`: `(4.0·sharpe + 3.5·consistency + 2.5·recency) / 10` — a
weighted **sum**, deliberately (H14). Under a product a dormant trader (recency≈0) can never
be selected; under the sum they can. Anyone modeling selection off the README predicts a
different top-5. Pinned by `test_score_is_weighted_sum_not_product`.

### DD-16. TP/SL example tables (README + `risk_manager.py` docstring) predate the H2 cap

Both tables claim entry $0.82 → SL $0.615 and entry $0.97 → SL $0.727. Actual
(`_compute_thresholds` with defaults): **0.82 → SL 0.748; 0.97 → SL 0.94** — the
`min_reward_risk` cap tightens high-entry stops up to 4×. Operators sizing mental risk off
the tables will misread every high-entry stop-out. (Same docstring also omits the L5
low-entry TP taper: entry $0.02 → TP is ≈0.28, not the documented $0.412.)

### DD-17. Trailing-stop parameter description documents the removed formula

README: "Trail 40% below peak-to-SL gap". Code (`_compute_trail_sl`, H1):
`trail = peak − (peak − entry) × fraction`, floored at hard SL — run-up-from-entry, not
peak-to-SL. Doc formula mispredicts every trailing exit by several cents.

### DD-18. Kelly narrative wrong on both activation and input

README: "activates only once the trader has ≥50 closed trades — until then it falls back to
the flat multiplier" and "derived from … mean ROI (not raw win rate)". Code
(`copier.py::handle_trade_event` step 6): below 50 trades the **tracker-seeded Kelly path**
(on by default via `kelly_seed_from_tracker`) sizes from trade #1; **at ≥50 trades sizing
switches to the raw portfolio win rate** (`kelly_size_usdc(win_rate, …)`) — the H18
demonstrated-edge debiasing applies only to the warm-up branch, so the favorite-buyer bias
the doc says was engineered out returns at steady state.

### DD-19. "Fee-aware sizing" does not exist; `round_trip_fee_pct` is a dead knob

README Risk Control #19: "expected round-trip fee deducted from edge before Kelly sizing".
No sizing function takes a fee input (`core/sizing.py`, all call sites). Fees exist only in
the separate binary `post_fee_edge` skip gate, which never adjusts size. And
`config.py::CopyTradingConfig.round_trip_fee_pct` — whose own comment says it is "used for
the pre-copy edge check" — has **zero use sites** (grep: definition + one docs mention).
Tuning it changes nothing.

### DD-20. Every documented Prometheus metric name is wrong; one doesn't exist

README Observability lists `polymarket_bankroll_usdc`, `polymarket_daily_pnl_usdc`,
`polymarket_open_positions`, `polymarket_copies_skipped_total`, `polymarket_orders_placed_total`.
Actual (`core/metrics.py`): prefix `copybot_`, suffix `_usd`, and **no orders-placed-by-side
counter exists at all**. Alerts built from the README match nothing — a daily-loss alert that
never fires is indistinguishable from health.

### DD-21. README documents a config key that pydantic silently ignores

README parameter table: `kelly_fraction | 0.25`. The field is `kelly_fraction_multiplier`.
`AppConfig` does not set `extra="forbid"`, so `kelly_fraction: 0.5` in config.yaml is
accepted and discarded. **[measured]**: `kelly_fraction_multiplier` stays 0.25. Same trap
class as CLAUDE.md's unwired-field warning, but triggered by the README itself.

### DD-22. Assorted decorative/dead surface presented as functional

- `config.py::AppConfig.max_tracked_traders` — read once, for a startup **log line**
  (`main.py::run_bot`); the real limit is `trader_selection.max_top_traders`.
- `models/types.py::Market.fees_enabled` — parsed by `gamma_client.py::_parse_market`,
  consumed nowhere.
- `clob_client.py::ClobClient.close` — docstring says "call on bot shutdown";
  `main.py::run_bot`'s `finally` closes portfolio/gamma/session but never the CLOB executor.
- `clob_client.py::InsufficientLiquidityError` docstring: "within 1% of price" — the cap is
  config-driven and size-scaled (M11), not 1%.
- README "Run all tests (453 tests)" — 510 collected **[measured]**.
- README startup sequence lists 4 concurrent tasks; `run_bot` gathers 6.
- README "Shared aiohttp.ClientSession … across all API clients" — the CLOB client (the
  latency-critical order path) uses py-clob-client's own blocking `requests` stack.
- README Risk Control #9 "per-trader … session loss" — `get_trader_pnl` sums **all-time**
  realized PnL from the persistent DB; threshold is 8% of *bankroll*, not allocation; and it
  blocks new copies without emitting `trader_demoted` (that event is Wilson-bound demotion).
- README step 3 "Skip if price moved >2%" — the H6 gate is **directional** (adverse only);
  favorable moves are copied down to −15%.
- CLAUDE.md "Two logger names coexist … [child] logs do not route through the JSON file
  handler unless root is configured" — **false [measured]**: `__name__` loggers in
  monitor/risk_manager/tracker are *children* of `polymarket_copier` and propagate to its
  JSON handlers (fixed in CLAUDE.md in this PR).
- docs/PROFITABILITY_FACTCHECK_REPORT_JULY_2026.md §3.1 claims
  `TestShippedConfigMatchesCodeDefaults` prevents "this class of drift"; it pins exactly 4
  fields. Every other config.yaml value could drift silently (all 50 currently match).
  Closed by `test_invariants.py::test_every_shipped_yaml_value_matches_code_default`.

### DD-23. Tracker's documented "resolution awareness" was silently disconnected by the `type=TRADE` fetch filter (introduced upstream `a024771`, 2026-07-08)

- **Claim** (`tracker.py::_compute_trader_stats` docstring, "RESOLUTION AWARENESS"): *"We
  treat redemption/claim records as realizing events so held-to-resolution outcomes are
  counted, not silently dropped"* — implemented by the `_REDEEM_TYPES = ("redeem", "claim",
  "reward")` branch.
- **Reality:** commit `a024771` changed `tracker.py::TrackerClient._fetch_activity` to
  request `type=TRADE` (matching the monitor's poll). The Data API's `type` filter excludes
  REDEEM/reward rows **[inference — API filter semantics not verifiable offline]**, so the
  only call path feeding `_compute_trader_stats` can no longer deliver the records the
  redemption branch exists to handle — the branch is dead at runtime, and the docstring's
  honest-accounting story is now inverted: held-to-resolution **wins** are the ones silently
  dropped (their SELL-less round trips never close), while the docstring claims the opposite
  bias direction.
- **Scenario:** a tracked trader whose alpha is buy-and-hold-to-resolution loses every
  winning round-trip from their stats; their win rate and expectancy collapse and they are
  scored out of the pool — the exact trader archetype the redemption logic was added to keep.
  Anyone reading the docstring to reason about win-rate bias now reasons in the wrong
  direction. (Flagged only — restoring redeem visibility is a fetch/scoring change, Tier 2.)

---

## Summary

| # | Severity | One-line |
|---|----------|----------|
| DD-01 | S1 | `mode` typo → live order path with all live gates off |
| DD-02 | ~~S1~~ | **FIXED upstream (`b666acf`)** — `--mode live` now revalidates key+funder |
| DD-03 | S1 | Exposure released at fill price, not registered notional — books drift |
| DD-04 | S1 | `min_reward_risk` floor violated above entry ≈0.97 |
| DD-05 | S1 | Missing WS `price` field → 0.0 tick → SL cascade |
| DD-06 | S1 | Phantom cached position re-sends SELLs; equality-based eviction fails |
| DD-07 | S2 | Monitor crash swallowed; supervise() restart inert |
| DD-08 | S2 | WS subscriptions depend on PONG traffic arriving as messages |
| DD-09 | S2 | Demotion undone by rebalance; `_demoted_traders` never read |
| DD-10 | S2 | Live reconcile degrades to assume-full-fill at quote (get_order calls now bounded — `a0a0505` — but the FOK/FAK fallback itself is unchanged) |
| DD-11 | S2 | Tax-lot atomicity by convention only (shared-connection commits) |
| DD-12 | S2 | Re-added wallets skip cold-start priming |
| DD-13 | S2 | Notional helper falls back to shares-as-USDC |
| DD-14 | S2 | "Halt" on daily loss is actually full liquidation |
| DD-15–22 | S3 | Doc rot: scoring formula, TP/SL tables, trailing formula, Kelly story, fee-aware sizing, metric names, `kelly_fraction`, misc |
| DD-23 | S2 | `type=TRADE` fetch filter (`a024771`) makes the tracker's documented redemption-awareness dead code; hold-to-resolution wins now silently dropped |

**Dispositions.** Everything above (excluding the now-fixed DD-02) is *reported, not fixed*:
per CLAUDE.md's escalation ladder, DD-01, DD-03…DD-06, and DD-10…DD-14 touch trading math,
order flow, or live-mode gating (Tier 2/3 — ask first). What this PR does ship:
`tests/test_invariants.py` pins every invariant that currently holds (so a weaker model can't
regress the parts that work, including a regression pin for the DD-02 fix), `INVARIANTS.md`
makes the contract explicit for future sessions, and the one doc-truth fix this PR is allowed
to make (CLAUDE.md logger claim) is applied.
