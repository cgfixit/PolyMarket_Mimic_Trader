# Real-Money Readiness — Wave 1 (July 9, 2026)

**What this is:** a small, surgical wave of fixes and one new gate, in response to feedback asking
for code changes that push toward "would this literally work as intended, legally and financially,
if run today" — while being honest that no code change makes a copy-trading strategy "75%+ likely
profitable." The bot's core edge question (documented in `PROFITABILITY_ANALYSIS_JUNE_2026.md`) is
unresolved by construction; what this wave does is close operational gaps and make the eventual
profitability answer *measurable* rather than assumed.

**Context:** by the time this wave started, `origin/main` had already independently landed a large
share of what a "wave 1" would normally cover: the geoblock startup preflight
(`_enforce_live_geoblock_preflight` in `main.py`), CLOB-market-info-driven per-market fee resolution
in the pre-copy edge gate (`CopyTrader._fee_rate_for_market`), price-shaped taker fees, and
per-trade timing telemetry logging. This doc covers only what's new on top of that.

## What landed

### 1. Mode validation gap (real bug)

`AppConfig.mode` was a plain `str`. `ClobClient` decides real-vs-simulated orders with
`mode == "paper"` (anything else takes the real-order path); every safety gate — geoblock
preflight, `validate_live_config`, the new forward-paper gate — checks `mode == "live"`. A
`config.yaml` typo or casing variant (`mode: LIVE`, `mode: prod`) matched neither comparison:
`paper_mode` becomes `False` (real orders) while every gate silently no-ops (neither `== "paper"`
nor `== "live"` matched). **Fixed:** `mode` is now `Literal["paper", "live"]`, and `load_config`
case-normalizes the raw YAML value before validation so `LIVE`/`Live` still work as intended while
a genuinely unrecognized value now raises `ConfigError` at startup instead of fail-opening.

### 2. Fee-rate under-charge + a fill/gate inconsistency

- **Default fallback rate was below every real category cap.** `paper_taker_fee_rate` defaulted to
  0.02, which (`fee = shares × rate × p × (1−p)`) gives a 0.5% peak fee at p=0.5 — below sports,
  the *cheapest* real category (~0.75% peak, rate ≈0.03), let alone crypto (~1.8% peak, rate
  ≈0.072). This fallback only fires when live CLOB/Gamma fee data is unavailable, but "unavailable"
  is exactly when the bot should be conservative, not optimistic. **Fixed:** default raised to 0.08
  (2% peak), above every published category cap.
- **The edge gate and the actual fill used different numbers.** `CopyTrader._fee_rate_for_market`
  already resolved a market-specific rate for the pre-copy edge check, but `Order` never carried
  it — so `ClobClient.place_order`'s paper-fill simulator always fell back to the flat config
  default regardless of what the edge gate just approved the trade under. A trade that passed the
  gate at a category-specific 0.03 could still be simulated (and its paper PnL recorded) at 0.08.
  **Fixed:** `Order.fee_rate` now carries the resolved rate for both entry and exit; the exit rate
  is re-resolved fresh at exit time (a direct CLOB-market-info lookup, skipping the extra
  Gamma-market fallback tier to stay off the latency-sensitive TP/SL exit path) rather than cached,
  since a market's published rate can change between entry and exit and a per-market cache keyed
  only by market_id would go stale the moment *any* other event for that market — even a
  subsequently-skipped one — resolved a different number.

### 3. Forward-paper gate (readiness-plan "PR 4" skeleton)

New: live mode refuses to start until the local database holds `forward_paper_min_trades` (default
50) closed positions **explicitly tagged `mode='paper'`** with net realized PnL greater than
`forward_paper_min_net_pnl_usd` (default $0). Config: `forward_paper_gate_enabled` (default on),
`forward_paper_min_trades`, `forward_paper_min_net_pnl_usd`. Never blocks paper mode.

Implementation note on a mistake avoided: the natural migration for tagging existing positions with
a `mode` column is `ALTER TABLE ... DEFAULT 'paper'` — but this bot has always supported live
mode, so a database that predates this column may contain real closed LIVE positions. Defaulting
them to `'paper'` would let pre-existing live evidence silently satisfy a gate whose entire point is
"prove it in paper mode first." The migration instead adds the column **without** a default; legacy
rows stay `NULL` (unknown provenance) and `get_forward_paper_stats()` only counts rows explicitly
`mode='paper'` — `NULL` and `'live'` are both excluded. Covered by
`tests/test_portfolio.py::TestModeColumnMigration`.

This is explicitly a **necessary, not sufficient** gate: paper mode still simulates fills against a
synthetic book, so a green gate is a floor on evidence, not proof of live edge. The backtest harness
(next wave) is what would make that evidence trustworthy.

## What did NOT change

- No strategy/signal changes — this wave is entirely gates and money-math correctness.
- No `py-clob-client` → `py-clob-client-v2` migration (still open; re-verify issues #70/#90 re
  `signature_type=3` before attempting it).
- No offline backtest harness / real-book paper fills — paper mode still uses a synthetic order
  book. This remains the single highest-leverage next step: even a green forward-paper gate is only
  as trustworthy as the fill simulation feeding it.
- No decision-telemetry database table. Per-trade timing/fee telemetry already exists as structured
  log events (`log_event(..., "position_opened", ...)` etc.); persisting *skip* decisions to a table
  was considered for this wave but deferred — doing it safely requires either writing outside the
  `_entry_lock` critical section or accepting a wider TOCTOU window on `_pending_entries`, and that
  tradeoff deserves its own focused change rather than being folded into this one.

## Next waves (ranked)

1. **Offline backtest harness / real-book paper fills.**
2. **`py-clob-client-v2` migration** (with the sig-type-3 issue re-verified first).
3. **De-bias trader win-rate/ROI metrics** (worthless-expiry losses aren't counted).
4. **Decision-telemetry persistence** for skip reasons, done carefully re: the lock-hold tradeoff
   noted above.
