# Polymarket Copy-Trading Bot — Improvement Plan

> Expert review covering latency, trader selection, copy logic, risk math, market microstructure, async architecture, and game theory. All issues reference actual code locations found in this repo.

---

## Priority Matrix

| # | Issue | Severity | File(s) |
|---|-------|----------|---------|
| 1 | Polling loop timing drift | CRITICAL | `core/monitor.py` |
| 2 | WS subscription update is a no-op | CRITICAL | `core/monitor.py` |
| 3 | Scorer uses multiplicative formula — outlier-sensitive | CRITICAL | `core/tracker.py` |
| 4 | TP/SL math breaks at price extremes (< 0.005, > 0.995) | CRITICAL | `core/risk_manager.py` |
| 5 | Daily loss circuit breaker uses wrong clock | CRITICAL | `core/risk_manager.py` |
| 6 | RiskManager exposure dicts are not async-safe | CRITICAL | `core/risk_manager.py` |
| 7 | No graceful degradation when WebSocket dies | CRITICAL | `core/monitor.py` / `core/copier.py` |
| 8 | No dead man's switch / watchdog | CRITICAL | `main.py` |
| 9 | WS ping interval 30 s — dead connections take too long to detect | HIGH | `core/monitor.py` |
| 10 | Exit order has no retry; failed exit leaves phantom position | HIGH | `core/copier.py` |
| 11 | Mixed monotonic / wall clocks for age calculation | HIGH | `core/monitor.py` / `core/copier.py` |
| 12 | Leaderboard uses all-time window — survivorship bias | HIGH | `core/tracker.py` |
| 13 | Liquidity check computes notional instead of shares | HIGH | `api/clob_client.py` |
| 14 | All orders GTC limit — entries should be aggressive, exits FOK | HIGH | `api/clob_client.py` / `core/copier.py` |
| 15 | Trailing stop peak mutated inside evaluate() — race condition | MEDIUM | `core/risk_manager.py` / `core/copier.py` |
| 16 | No volatility-adjusted or Kelly-scaled position sizing | MEDIUM | `core/copier.py` |
| 17 | min_trades: 50 too low; rebalance_days: 7 too slow | MEDIUM | `config.yaml` / `core/tracker.py` |
| 18 | 0.5× size multiplier has no empirical basis | MEDIUM | `core/copier.py` |
| 19 | max_price_deviation 2 % too loose; no per-liquidity gate | MEDIUM | `core/copier.py` |
| 20 | Naive datetime from Gamma API not guarded to UTC | MEDIUM | `core/copier.py` |
| 21 | No slippage tracking | MEDIUM | `core/copier.py` / `core/portfolio.py` |
| 22 | _EPSILON_USDC = 1e-6 is meaninglessly small | LOW | `core/copier.py` |
| 23 | Division by current_price not epsilon-guarded | LOW | `core/copier.py` |

---

## CRITICAL Fixes

### 1 · Polling Loop Timing Drift
**File:** `core/monitor.py` — `_poll_loop()`

**Problem:** Loop computes `sleep = poll_interval - elapsed`. If a poll takes longer than the interval, sleep clamps to 0 and the next poll starts immediately — the effective interval doubles. Over 10 000 cycles the accumulated drift can exceed 9 minutes. The age-gate then rejects valid trades because they appear stale.

**Fix:** Track a fixed `next_deadline` instead of leftover time.

```python
async def _poll_loop(self) -> None:
    async with aiohttp.ClientSession(...) as session:
        next_deadline = time.monotonic() + self._poll_interval
        while not self._stop_event.is_set():
            await self._poll_all_wallets(session)
            sleep = max(0.0, next_deadline - time.monotonic())
            next_deadline += self._poll_interval          # advance regardless of slip
            if sleep > 0.001:
                try:
                    await asyncio.wait_for(
                        asyncio.shield(self._stop_event.wait()), timeout=sleep
                    )
                    break
                except asyncio.TimeoutError:
                    pass
```

---

### 2 · WebSocket Subscription Update is a No-op
**File:** `core/monitor.py` — `_maybe_update_subscription()`

**Problem:** The method body is `pass`. Any token added to `_subscribed_tokens` after the WebSocket connects is never sent to the server. Position exits driven by price ticks are silently missed forever.

**Fix:** Send a full re-subscribe message whenever the subscribed set changes.

```python
async def _maybe_update_subscription(self, ws) -> None:
    current = set(self._subscribed_tokens)
    if current != self._last_subscribed:
        if current:
            await self._ws_send_subscription(ws, list(current))
        self._last_subscribed = current
        logger.info("WS subscription updated: %d tokens", len(current))
```

Also reduce `ping_interval` from 30 s → 15 s and `ping_timeout` from 10 s → 5 s.

---

### 3 · Trader Scorer — Multiplicative Formula Amplifies Outliers
**File:** `core/tracker.py` — `score()`

**Problem:** `score = sharpe * consistency * recency`. Because the three axes are multiplied:
- A single lucky run inflates Sharpe → score 3-4× higher than a consistent trader
- A 50% higher Sharpe drives 50% of the final score
- Half-life 14 days means a 28-day-old trader still has 0.25× weight

**Fix:** Use a weighted average instead of multiplication; cap Sharpe; shorten half-life.

```python
def score(self, stats: TraderStats) -> Optional[ScoredTrader]:
    sharpe_norm = min(stats.sharpe_proxy, 2.0) / 2.0          # cap outliers
    consistency = stats.win_rate ** 1.2                         # power curve
    recency = self._recency_weight(stats.last_trade_time, half_life_days=7)

    score = 0.40 * sharpe_norm + 0.40 * consistency + 0.20 * recency
    return ScoredTrader(stats=stats, score=score, ...)
```

Also add a post-selection **decorrelation pass**: measure market overlap between the top-N selected traders and drop any pair with > 30 % overlap, replacing them with the next ranked trader.

---

### 4 · TP/SL Math Breaks at Price Extremes
**File:** `core/risk_manager.py` — `_compute_thresholds()`

**Problem:**
- Entry 0.001: `sl_raw = 0.001 - max(0.001×0.25, 0.02) = -0.019` → clamped to 0.0. Position can lose 100 %.
- Entry 0.90: TP gain = 0.063, SL risk = 0.225 — risk/reward 3.6:1 against you.
- After clamping, `tp <= sl` is possible but never checked.

**Fix:**
```python
def _compute_thresholds(self, entry: float) -> Tuple[float, float]:
    dist_ceil  = 1.0 - entry
    dist_floor = entry

    min_tp = max(self.cfg.min_tp_abs, dist_ceil  * 0.5 if entry > 0.98 else self.cfg.min_tp_abs)
    min_sl = max(self.cfg.min_sl_abs, entry * 0.5        if entry < 0.02 else self.cfg.min_sl_abs)

    tp = min(entry + max(dist_ceil  * self.cfg.tp_range_fraction, min_tp), 1.0)
    sl = max(entry - max(dist_floor * self.cfg.sl_range_fraction, min_sl), 0.0)

    if tp <= sl:
        raise InvalidPriceError(
            f"Entry {entry:.4f} produces TP={tp:.4f} ≤ SL={sl:.4f}. "
            "Reject this trade."
        )
    return round(tp, 6), round(sl, 6)
```

Also add an **entry price guard** in `build_position()`: reject entries outside `[0.005, 0.995]`.

---

### 5 · Daily Loss Circuit Breaker Uses Local Clock for UTC Midnight
**File:** `core/risk_manager.py` — `_midnight_utc()`

**Problem:** `time.mktime()` interprets its argument as **local** time, not UTC. A deployment in UTC+5 resets the daily window 5 hours late. `time.gmtime()` returns UTC fields, but `time.mktime()` converts them as if they were local — the offset is wrong.

**Fix:**
```python
from datetime import datetime, timezone

def _midnight_utc() -> float:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

def _maybe_reset_daily_window(self) -> None:
    now_utc = datetime.fromtimestamp(time.time(), tz=timezone.utc)
    start_utc = datetime.fromtimestamp(self._day_start_ts, tz=timezone.utc)
    if now_utc.date() != start_utc.date():
        logger.info("Daily PnL reset. previous=%.2f", self._daily_pnl)
        self._daily_pnl = 0.0
        self._day_start_ts = _midnight_utc()
```

---

### 6 · RiskManager Exposure Dicts Have a Race Condition
**File:** `core/risk_manager.py` — `build_position()`, `record_exit()`

**Problem:** Two coroutines can both read `_market_exposure["X"] = 200`, both pass the cap check (200 + 100 < 800), then both write, leaving total exposure at 350 instead of the correct 450. The cap is silently breached.

**Fix:** Wrap both dicts with an `asyncio.Lock` and make `build_position` / `record_exit` async.

```python
self._exposure_lock = asyncio.Lock()

async def build_position(self, ...) -> Position:
    async with self._exposure_lock:
        self._assert_exposure_cap(market_id, position_value)
        self._market_exposure[market_id] = (
            self._market_exposure.get(market_id, 0.0) + position_value
        )
        ...
```

Update all call sites in `copier.py` to `await self.risk.build_position(...)`.

---

### 7 · No Graceful Degradation When WebSocket Dies
**File:** `core/monitor.py`, `core/copier.py`

**Problem:** After the WS reconnect budget is exhausted, the task exits quietly. The poll loop keeps running but price ticks stop arriving. Positions never exit until the 48 h time limit.

**Fix:** Add `ws_healthy: bool` property to monitor. In `copier.check_all_exits()`, if WS is unhealthy, fetch current prices via the REST Gamma client for every open position and evaluate exits:

```python
async def check_all_exits(self) -> None:
    if self.monitor and not self.monitor.ws_healthy:
        logger.warning("WS down — running REST-based exit sweep")
        for pos in await self.portfolio.get_open_positions():
            price = await self.gamma.get_market_price(pos.token_id)
            if price is not None:
                reason = self.risk.evaluate(pos, price)
                if reason != ExitReason.HOLD:
                    await self._exit_position(pos, price, reason)
```

---

### 8 · No Dead Man's Switch
**File:** `main.py`

**Problem:** If all tasks die silently, open positions sit unmanaged indefinitely.

**Fix:** Add a watchdog coroutine that checks every 30 minutes whether the poll task is alive. If not, liquidate all open positions at market price and call `shutdown_event.set()`.

---

## HIGH Priority Fixes

### 9 · Exit Orders Have No Retry; Failed Exit Leaves Phantom Position
**File:** `core/copier.py` — `_exit_position()`

```python
async def _exit_position(self, pos, price, reason):
    for attempt in range(3):
        try:
            await self.clob.place_order(exit_order)
            break
        except Exception as e:
            if attempt == 2:
                logger.error("Exit permanently failed for %s — manual intervention required", pos.position_id)
                return
            await asyncio.sleep(2 ** attempt)

    await self.portfolio.close_position(pos.position_id, price, reason)
```

Only call `portfolio.close_position` after the order succeeds.

---

### 10 · Mixed Monotonic / Wall Clocks for Age Calculation
**File:** `core/monitor.py` (line 93 uses `time.monotonic` for `detected_at`), `core/copier.py` (subtracts `time.time()` from `event.timestamp`)

`event.timestamp` is a Unix wall-clock time from the API; `event.detected_at` is monotonic. Subtracting them is undefined. NTP adjustments can make `age` negative or enormous.

**Fix:** Compute wall-clock age from `event.timestamp` separately from monotonic detection latency. Add a sanity bound: if `wall_age < 0` treat as fresh; if `wall_age > 3600` treat as stale.

---

### 11 · Leaderboard Uses All-Time Window — Survivorship Bias
**File:** `core/tracker.py` — `_fetch_leaderboard()`

Change `"window": "all"` → `"window": "90d"`. Add a filter: if `lastTradeTime` is more than 30 days ago, skip. This removes retired traders and de-weights regime-specific winners.

---

### 12 · Liquidity Check Computes Notional Instead of Shares
**File:** `api/clob_client.py` — `_check_liquidity()`

```python
# WRONG
available += level_price * level_size   # notional

# CORRECT
needed_shares = size_usdc / max(price, 1e-6)
available_shares += level_size          # shares on the ask
if available_shares < needed_shares:
    raise InsufficientLiquidityError(...)
```

The existing logic rejects ~30 % of valid orders that would actually fill.

---

### 13 · All Orders Are GTC Limit — Wrong for Entries and Exits
**File:** `api/clob_client.py`, `core/copier.py`

- **Entry orders** should be aggressive (market order or limit crossed slightly above ask by ~0.5 %) to guarantee fill.
- **Exit orders** (TP/SL) should be FOK — fill immediately or cancel — not sit in the book for hours.

Add `order_type: Literal["GTC", "FOK"] = "GTC"` and `is_market_order: bool = False` to the `Order` model and thread it through `place_order`.

---

## MEDIUM Priority Fixes

### 14 · Trailing Stop — Peak Mutated Inside `evaluate()`
**File:** `core/risk_manager.py`, `core/copier.py`

`evaluate()` mutates `pos.peak_price` in place. If two price ticks arrive before the DB write completes, an out-of-order write can roll the peak back, loosening the trailing stop.

**Fix:** Remove the mutation from `evaluate()`. Return the new peak as part of the result tuple and let the caller write it to the DB atomically:

```python
# evaluate() returns (ExitReason, new_peak: float)
reason, new_peak = self.risk.evaluate(pos, tick.price)
if new_peak > pos.peak_price:
    await self.portfolio.update_peak_price(pos.position_id, new_peak)
```

---

### 15 · No Volatility-Adjusted or Kelly-Scaled Position Sizing
**File:** `core/copier.py`

The fixed `size_multiplier = 0.5` and `max_trade_pct = 0.02` ignore:
- Source trader's leverage relative to their bankroll (unknown, but can be proxied by trade size vs. market volume)
- Market daily volatility (proxy: `std(price[-24h])`)
- Kelly criterion: `f = (p·w − q·l) / w` → 0.25× fractional Kelly for safety

Add a `_kelly_fraction(win_rate, mean_win, mean_loss) -> float` helper and multiply the result by a volatility scalar (baseline 0.02 daily vol → scale 1.0; higher vol → scale down).

---

### 16 · Calibration: `min_trades`, `rebalance_days`, `half_life_days`

| Parameter | Current | Recommended | Reason |
|-----------|---------|-------------|--------|
| `min_trades` | 50 | 150 | At 50 trades, 95 % CI on win rate is ±14 % — too wide |
| `rebalance_days` | 7 | 2 | Detect downswings in 2 days instead of 7 |
| `half_life_days` | 14 | 7 | Inactive traders decay to 0.5× in 7 days instead of 14 |

---

### 17 · Size Multiplier Has No Empirical Basis
**File:** `core/copier.py`, `config.yaml`

Proxy the source trader's aggressiveness by `trade_size / market_volume_24h`. If they're taking > 1 % of daily volume they're aggressive; scale your multiplier down proportionally. Cap at 0.3× for aggressive sources, 0.7× for conservative ones.

---

### 18 · Price Deviation Gate Too Loose
**File:** `core/copier.py`, `config.yaml`

`max_price_deviation = 0.02` (2 %) uses the trade price as denominator, creating inconsistency across the price range. Use absolute delta instead (`abs(current - trade_price)`), and use tighter thresholds for liquid markets (volume > $50 k → 0.015) and looser for thin markets (< $50 k → 0.04).

---

### 19 · Naive Datetime from Gamma API Not Guarded to UTC
**File:** `core/copier.py`

```python
if market.resolve_time.tzinfo is None:
    resolve_ts = market.resolve_time.replace(tzinfo=timezone.utc).timestamp()
else:
    resolve_ts = market.resolve_time.timestamp()
```

---

### 20 · No Slippage Tracking
**File:** `core/copier.py`, `core/portfolio.py`

Capture `fill_price` from the CLOB response, store it alongside `exit_price` in the position record, and log `realized_slippage = |fill - requested| / requested` on every exit. Aggregate in a periodic performance report.

---

## LOW Priority

### 21 · `_EPSILON_USDC = 1e-6` Is Meaninglessly Small
Change to `0.01` — a $0.01 floor on order size is the practical minimum.

### 22 · Missing Epsilon Guard on Division by `current_price`
```python
size_shares = copy_size_usdc / max(current_price, 1e-6)
```

---

## Game Theory & Psychology Notes

These don't map to specific bugs but inform configuration choices:

1. **Adverse selection risk.** Top traders know they're on a public leaderboard. They may dump positions into copy-bot order flow. Mitigate by tightening the staleness gate and adding a minimum market-volume filter (don't copy trades in markets with < $10 k 24 h volume).

2. **Information cascade.** Multiple copy bots watching the same leaderboard creates correlated order flow. Your orders will move thin markets against you. Use the market-volume-relative size proxy (issue 17) and hard-cap per-market exposure at 5 % (down from 8 %).

3. **Timing in the trade lifecycle.** You see the leader's filled order, not their intent. By the time you detect a fill, the easy alpha has been captured. Consider only copying when the leader's trade constitutes evidence of information (e.g., size > 1 % of 24 h volume) rather than noise.

4. **Regime awareness.** A 90-day leaderboard still rewards bull-market bias. Add a regime flag (e.g., overall prediction market resolution rate vs. historical base rate) and scale down all position sizes when overall market volatility is high.

---

## Suggested Implementation Order

**Week 1 (critical stability):**
- Issues 1, 5, 6 — timing and concurrency correctness
- Issues 4, 8 — safety rails

**Week 2 (correctness of exit path):**
- Issues 2, 7, 9 — WebSocket and exit reliability
- Issue 13 — liquidity check bug

**Week 3 (alpha quality):**
- Issues 3, 11, 12, 16 — trader selection overhaul
- Issues 10, 14 — order type discipline

**Week 4 (sizing and polish):**
- Issues 15, 17, 18, 19, 20, 21 — position sizing and edge calibration

---

*Review generated via deep static analysis of all core modules. Each recommendation references actual code behavior, not assumptions.*
