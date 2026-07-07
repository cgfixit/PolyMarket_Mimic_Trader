---
name: api-drift-audit
description: >
  Read-only audit of Polymarket API drift: probe the Data/Gamma/CLOB REST endpoints and the
  market WebSocket the bot actually uses, diff the observed response shapes against the fields
  the code parses, and report severity-rated findings. Use when asked to check for API drift,
  after unexplained parsing failures or empty polls, or as periodic maintenance. STRICTLY
  read-only: never places orders, never authenticates, never mutates anything remote.
---

# /api-drift-audit — Polymarket API Drift Audit

API drift is this repo's #1 recurring bug source (dead `/leaderboard` endpoint, WS heartbeat
format, `usdcSize` notional parsing — all real incidents). This skill catches the next one
before it silently breaks trade detection.

## Hard rules

- **GET requests only.** No auth headers, no POST/PUT/DELETE, no order placement, no
  `py_clob_client` calls that sign anything. If a check would require auth, record it as
  UNVERIFIABLE instead.
- Respect the Data API budget (~30 req/60s assumed; the bot's own limiter uses 25/60):
  the probe script sleeps between calls. Do not parallelize probes.
- Findings become **proposed PR chunks**, not fixes applied in this pass.

## Step 1 — Build the assumption inventory from the code (works offline)

This table is the audit's backbone. Re-derive it from the code each run (don't trust this copy
if the code moved); each row = endpoint → where it's parsed → fields the code reads:

| # | Endpoint | Consumer | Fields the code depends on |
|---|----------|----------|---------------------------|
| 1 | `GET data-api.polymarket.com/v1/leaderboard` | `core/tracker.py` (leaderboard fetch) | wallet/address + window/ranking params it sends |
| 2 | `GET data-api.polymarket.com/activity?user=<wallet>` | `core/monitor.py::_poll_wallet` and `core/tracker.py` (trader history), via `utils/activity.py` accessors | the accessor keys in `utils/activity.py` (trade id, type, side, price, size, usdcSize, market/conditionId, asset/token, timestamp) |
| 3 | `GET gamma-api.polymarket.com/markets` / `markets/<condition_id>` | `api/gamma_client.py::get_market` → `_parse_market` | the keys `_parse_market` reads (tokens, active/closed/archived/restricted flags, accepting_orders, enable_order_book, volume, end date, fee fields) |
| 4 | `GET clob.polymarket.com/midpoint?token_id=<id>` | `api/gamma_client.py::get_market_price` | `mid` value, [0,1] validity |
| 5 | `GET clob.polymarket.com/clob-markets/<condition_id>` | `api/gamma_client.py::get_market_fee_rate` | fee-rate field + basis-points normalization (÷10,000 when >1.0) |
| 6 | `wss://ws-subscriptions-clob.polymarket.com/ws/market` | `core/monitor.py` (`_handle_ws_message`, heartbeat, subscribe payload) | message envelope (list of events), `event_type`, `price_change` fields, PING/heartbeat contract |
| 7 | `GET polymarket.com/api/geoblock` | `main.py::_enforce_live_geoblock_preflight` | the blocked/allowed field the preflight reads |

For each row, open the consumer and list the exact keys accessed (grep for `.get(` and dict
subscripts in the parsing function). That list is what you diff against.

## Step 2 — Probe (network required)

Run the companion script — it fetches each REST endpoint once, rate-limit-safely, into the
scratchpad:

```bash
bash .claude/skills/api-drift-audit/probe.sh /tmp/api-drift-probes
```

It needs one real wallet address and one active condition_id/token_id to probe rows 2–5
meaningfully; take them from the leaderboard response (row 1) — the script does this
automatically. The WS (row 6) can be probed with a short `python -c` snippet using the
`websockets` lib from requirements: connect, subscribe with the same payload
`monitor.py::_ws_loop` sends, capture ~10s of messages, disconnect. If the environment has no
network, STOP here and deliver Step 1's inventory labeled **"static audit only — network
unavailable"**; that is still a valid (degraded) result.

## Step 3 — Diff shapes

For each endpoint: compare the keys the code reads (Step 1) against the keys observed in the
captured JSON (Step 2). Classify every mismatch:

- **S1 — breaks parsing:** a key the code requires is missing/renamed/moved, an endpoint 404s,
  the WS rejects the subscribe payload. The bot silently detects nothing or crashes.
- **S2 — silently wrong values:** key exists but semantics changed (units, basis points vs
  fraction, string vs number, timestamp format, side encoding). The bot trades on bad data —
  worse than S1.
- **S3 — cosmetic:** new keys the code ignores, doc-only drift, deprecation notices.

Also check the reverse direction: response fields that look load-bearing (fees, sizes, status
flags) that the code does NOT read — candidate S2s in waiting; list them as observations.

## Step 4 — Report

Findings table, most severe first:

```
| Endpoint | Field/behavior | Code expects | Observed | Severity | Anchor |
```

- Any S1/S2 → also write `docs/API_DRIFT_<YYYY-MM-DD>.md` on the current branch: the table,
  raw-response excerpts as evidence, probe timestamp, and a "Proposed chunks" section (one
  single-concern PR per finding, per repo convention). Do not fix in this pass.
- All clear → report "no drift detected", the probe timestamp, and which rows were verified
  live vs statically. Write no doc.
- Always state coverage honestly: which endpoints were probed, which were UNVERIFIABLE (auth
  required, geoblocked, no network) — an unprobed endpoint is not a passing endpoint.
