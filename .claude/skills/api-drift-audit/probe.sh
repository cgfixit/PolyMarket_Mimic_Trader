#!/usr/bin/env bash
# probe.sh — read-only Polymarket API probe for the api-drift-audit skill.
# Fetches each REST endpoint the bot depends on exactly once, with sleeps between calls
# to stay far under the Data API rate budget, and saves raw JSON to an output directory.
#
# STRICTLY read-only: GET requests only, no auth, no order placement, no mutation.
#
# Usage: bash .claude/skills/api-drift-audit/probe.sh [output_dir]
# Exit code: 0 if every probe returned HTTP 200, 1 otherwise (partial captures are kept).

set -u

OUT="${1:-/tmp/api-drift-probes}"
mkdir -p "$OUT"
SLEEP_SECS=3
FAIL=0

DATA_API="https://data-api.polymarket.com"
GAMMA_API="https://gamma-api.polymarket.com"
CLOB_API="https://clob.polymarket.com"
GEOBLOCK="https://polymarket.com/api/geoblock"

probe() {
  # probe <name> <url>
  local name="$1" url="$2"
  local code
  code="$(curl -sS -o "$OUT/$name.json" -w '%{http_code}' --max-time 15 "$url" 2>"$OUT/$name.err" || echo "000")"
  echo "PROBE|$name|$code|$url"
  if [ "$code" != "200" ]; then
    FAIL=1
  fi
  sleep "$SLEEP_SECS"
}

# Helper: first string value for a JSON key (crude but dependency-free; audit uses raw files).
first_json_value() {
  # first_json_value <file> <key>
  grep -oE "\"$2\"[[:space:]]*:[[:space:]]*\"[^\"]+\"" "$1" 2>/dev/null \
    | head -1 | sed -E 's/.*:[[:space:]]*"([^"]+)"/\1/'
}

echo "== api-drift probe → $OUT =="
date -u +"probe started %Y-%m-%dT%H:%M:%SZ"

# 1. Leaderboard (tracker.py) — also the source of a live wallet for the activity probe.
probe "leaderboard" "$DATA_API/v1/leaderboard?window=30d&limit=5"

WALLET="$(first_json_value "$OUT/leaderboard.json" proxyWallet)"
[ -z "$WALLET" ] && WALLET="$(first_json_value "$OUT/leaderboard.json" wallet)"
[ -z "$WALLET" ] && WALLET="$(first_json_value "$OUT/leaderboard.json" address)"

# 2. Wallet activity (monitor.py / tracker.py / utils/activity.py).
if [ -n "$WALLET" ]; then
  probe "activity" "$DATA_API/activity?user=$WALLET&limit=10"
else
  echo "PROBE|activity|SKIPPED|no wallet extractable from leaderboard response — inspect $OUT/leaderboard.json"
  FAIL=1
fi

# 3. Gamma markets list (gamma_client.py::_parse_market) — also sources condition/token ids.
probe "gamma_markets" "$GAMMA_API/markets?limit=3&active=true&closed=false"

CONDITION_ID="$(first_json_value "$OUT/gamma_markets.json" conditionId)"
# clobTokenIds is usually a JSON-encoded string of a list; grab the first hex-ish token id.
TOKEN_ID="$(grep -oE '"clobTokenIds"[^]]*' "$OUT/gamma_markets.json" 2>/dev/null \
  | grep -oE '[0-9]{20,}' | head -1)"

# 4. Single market by condition id (gamma_client.py::get_market).
if [ -n "$CONDITION_ID" ]; then
  probe "gamma_market_single" "$GAMMA_API/markets/$CONDITION_ID"
else
  echo "PROBE|gamma_market_single|SKIPPED|no conditionId in gamma_markets response"
  FAIL=1
fi

# 5. CLOB midpoint (gamma_client.py::get_market_price).
if [ -n "$TOKEN_ID" ]; then
  probe "clob_midpoint" "$CLOB_API/midpoint?token_id=$TOKEN_ID"
else
  echo "PROBE|clob_midpoint|SKIPPED|no token id extractable from gamma_markets response"
  FAIL=1
fi

# 6. CLOB market info / fee rate (gamma_client.py::get_market_fee_rate).
if [ -n "$CONDITION_ID" ]; then
  probe "clob_market" "$CLOB_API/clob-markets/$CONDITION_ID"
fi

# 7. Geoblock preflight (main.py::_enforce_live_geoblock_preflight).
probe "geoblock" "$GEOBLOCK"

date -u +"probe finished %Y-%m-%dT%H:%M:%SZ"
echo "raw responses in $OUT — diff their keys against the parsing code per SKILL.md Step 3"
echo "note: the WS endpoint (wss://ws-subscriptions-clob.polymarket.com/ws/market) is not"
echo "covered here; probe it with a short python-websockets snippet per SKILL.md Step 2."

exit "$FAIL"
