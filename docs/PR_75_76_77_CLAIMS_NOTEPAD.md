# Claims Notepad — PRs #75, #76, #77 (profitability of this bot with real money)

**Purpose:** working catalog of every profitability / feasibility claim made across the three research PRs,
with (a) code-verification status against this repo and (b) external fact-check status from deep research.
Compiled 2026-07-03/07-04 on branch `claude/polymarket-profitability-review-9ovgmb`.

**Note on branch history:** this notepad and its companion report were originally drafted against `main` at
commit `e11ef8c`. Before this PR was opened, `main` moved forward via PR #76/#79 (commit `2e98738`, "Fix
Polymarket API drift and readiness gates"), which independently fixed the leaderboard-endpoint and
WebSocket-heartbeat bugs PR #76/#77 had identified — the same bugs this branch had also fixed. This branch was
rebased onto the new `main`; the duplicate fix was dropped in favor of the already-merged one, and this notepad
keeps only the claim-verification content, which is unaffected by which commit did the fixing.

**Sources:**
- **PR #75** (merged) — `PROFITABILITY_ANALYSIS_JUNE_2026.md` — "can this strategy make money" (edge / cost / regulatory)
- **PR #76** (open) — `docs/POLYMARKET_BOT_STRATEGY_RESEARCH_2026-06-30.md` — Codex strategy report (content ≡ PR #77's doc)
- **PR #77** (merged) — duplicate root copy of `docs/POLYMARKET_BOT_STRATEGY_RESEARCH_2026-06-30.md` — "is the integration current against the live API"

Note: PR #76 and PR #77 carried the **same 399-line report**. The root duplicate was later removed; the retained copy is under `docs/`.

Verification key: ✅ confirmed · ⚠️ partially confirmed / nuance needed · ❓ unverifiable from here · ❌ refuted

---

## A. Headline verdicts

| # | Claim | Source | Code check | External check |
|---|-------|--------|-----------|----------------|
| A1 | **Conditional NO** — as written, run live with real USDC, the bot is unlikely to be net-profitable; most likely outcome is a slow bleed (≈ break-even minus friction), ~15–25% chance of small sustained profit, and even then ~$10–30/month on $500 | #75 | n/a (judgment) | see `PROFITABILITY_FACTCHECK_REPORT_JULY_2026.md` §1 |
| A2 | Engineering/risk plumbing is strong; the **edge is structurally weak** because the signal is public, delayed, and decays faster than an 8s poller can act on it | #75 | ✅ 8s poll + 2s jitter confirmed (`config.yaml`, `monitor.py`) | ✅ confirmed — see B3 below |
| A3 | Trader discovery is **broken today**: legacy `GET /leaderboard?window=...` returns HTTP 404 (live-checked 2026-06-30); current API is `GET /v1/leaderboard` with a different schema | #76/#77 | ✅ confirmed at the time; **now fixed on `main`** via commit `2e98738` (PR #76/#79), independent of this branch | ✅ confirmed against docs.polymarket.com |
| A4 | Both reports agree: fix known issues + add measurement **before** any real capital / increased live sizing | all | n/a | n/a |

## B. Edge / alpha claims (PR #75 §1)

| # | Claim | Code check | External check |
|---|-------|-----------|----------------|
| B1 | Yale/SSRN study (Gómez-Cram, Guo, Jensen, Kung, SSRN #6617059, Apr 2026; 98,906 events / 210k markets / $13.76B volume): ~3.14% of accounts are "skilled winners"; **44%** of in-sample skilled stay skilled out-of-sample vs ~10% for mutual-fund managers | n/a | ✅ **confirmed** — paper exists at exactly this abstract ID with these figures (5 independent sources) |
| B2 | Only ~12% of top *earners* overlap with genuinely skilled accounts; ~60% of "lucky winners" become losers out-of-sample; ~40% top-20 rank retention at 90 days | n/a | ✅ **confirmed** (SSRN Blog "A Closer Look", The Block) |
| B3 | The skill is a **speed/first-reaction** edge that a copier cannot inherit; ~1,950 suspected insider accounts move prices 7–12× harder per dollar; insider edge uncopyable | n/a | ✅ **confirmed** — multiple sources restate this exact mechanism |
| B4 | Signal age at fill ≈ **2–13s** (on-chain settle + Data-API indexing ~1–3s → 8s poll + ≤2s jitter → 0.1–0.5s decision) → systematic adverse selection (buys post-impact price) | ✅ latency stack matches code (8s poll, jitter 2.0, revalidate-then-order) | ⚠️ the Data-API indexing latency component is architecturally plausible but wasn't independently timed |
| B5 | `max_trade_age_seconds: 12` staleness gate is nearly self-defeating (tighten → starve; loosen → adverse selection) | ✅ value confirmed in `config.yaml` | n/a (analytic) |
| B6 | **Holding-period mismatch**: much Polymarket alpha is hold-to-resolution, but `resolution_blackout_hours: 24` + `time_exit_hours: 48` force early exit — bot copies the entry but not the strategy | ✅ both values confirmed in `config.yaml` | n/a (not directly addressed by the SSRN paper) |
| B7 | An 8s REST poller sits at the back of the queue behind mempool/indexer watchers on the same public wallets | ✅ architecture confirmed (REST polling for wallet activity; WS only for held-position prices) | n/a (no direct evidence found either way) |

## C. Cost / fee claims (PR #75 §2, #76/#77 finding 8)

| # | Claim | Code check | External check |
|---|-------|-----------|----------------|
| C1 | Polymarket was historically 0% fee; **2026 introduced fees**; real fee is concave `feeRate·p·(1−p)` — peaks near p=0.50, ~0 at extremes; makers ~free / rebated | n/a | ✅ **confirmed** against docs.polymarket.com/trading/fees |
| C2 | Polymarket US (DCM): taker Θ=0.05, max ≈ $1.25/100 contracts at $0.50, maker rebate ≈ −$0.31/100, effective Apr 3 2026 | n/a | ❌ **unconfirmed** — only a revenue-share maker-rebate pool (not a flat −$0.31 figure) is documented, and only for the global CLOB |
| C3 | Global CLOB category taker caps ≈ $0.75 sports / $1.00 politics-finance-tech / $1.25 economics-culture-weather / $1.80 crypto per 100 shares; geopolitics free; sells not charged | ✅ originally open; now partially addressed on `main` via CLOB/Gamma fee metadata parsing and fallback | ⚠️ **one number off**: economics is 1.50%, not 1.25% (1.25% is culture/weather) |
| C4 | Bot's old flat `paper_taker_fee_pct: 0.02` / `round_trip_fee_pct: 0.045` model had the **curve shape inverted** — H7 "extremes are expensive" mental model was backwards | ✅ now addressed on `main`: `paper_taker_fee_rate` plus `fee_rate * price * (1 - price)` paper/copy-gate math | ✅ confirmed real fee curve is the opposite shape |
| C5 | Dominant taker cost is **spread + slippage**, not fees; realistic round-trip friction ≈ 3–6%+ (spread <1¢ liquid, ~5¢ mid-tier, 10¢+ thin; Kaiko Feb-2026: single Deribit BTC strikes exceed total Polymarket depth 20–40×) | n/a | ⚠️ qualitatively supported (a live taker-strategy writeup shows execution assumptions dominate outcomes); the specific 3–6% figure wasn't independently confirmed |
| C6 | Gamma live sample: liquid markets show spread 0.001 and `feeRate 0.03`; some markets `feeSchedule=null`, others `takerOnly=true`; volume-only market filter passes closed/stale/`acceptingOrders=false` markets | ✅ **now addressed on `main`** — commit `2e98738` added `closed`/`archived`/`restricted`/`accepting_orders`/`enable_order_book` parsing to `Market` and gates copies on them | n/a |
| C7 | Polygon gas ≈ 0 for users (relayer-subsidized) — the one cost the bot can ignore | n/a | not independently re-checked (low priority) |

## D. Capital / ROI claims (PR #75 §3)

| # | Claim | Code check | External check |
|---|-------|-----------|----------------|
| D1 | $500 bankroll → $10 max/position (2%), $25/trader (5%), $40/market (8%), $150 total (30%), ≈$100–150 deployed | ✅ caps confirmed in `config.yaml` | n/a (arithmetic) |
| D2 | ~100 round-trips/month at ~$10 → optimistic +$15/mo (+3%), base ~$0, pessimistic −$20/mo (−4%) | n/a (model) | n/a (no independent way to check a hypothetical model) |
| D3 | Strategy does not scale: M11 sqrt-impact slippage kicks in above $500 notional; thin books punish size | ✅ `slippage_size_threshold_usdc: 500` confirmed | n/a |

## E. Code-level assumption audit (PR #75 §4)

| # | Claim | Code check | External check |
|---|-------|-----------|----------------|
| E1 | (4.2) `win_rate`/`mean_roi` biased UP: winners emit redeem records (counted), worthless expiries emit nothing (uncounted) → inflated selection metrics and Kelly seed | ⚠️ acknowledged in `tracker.py` comments; still unaddressed (see readiness plan PR 4) | n/a |
| E2 | (4.3) Kelly chain math sound but input poisoned; 2% hard cap makes Kelly mostly decorative; correctly off by default | ✅ `kelly_enabled: false`, caps confirmed | n/a (analytic) |
| E3 | (4.4) Four competing exit logics (TP/SL, trailing, time, source-mirror) override the pure mirror → negative skew (cut winners, keep stop-outs); 40/25 fractions arbitrary | ✅ all four exits exist in `risk_manager.py`/`copier.py` | n/a (needs backtest, not literature) |
| E4 | (4.5) Paper-mode go-live gate non-predictive: synthetic book (bid 0.50/ask 0.51, size 10000), always-full FOK fills, flat fee curve, no no-fill/partial-fill modeling | ✅ **confirmed** — still true; `clob_client.py` returns a fixed synthetic book, paper `place_order` always fills, depth gate skipped in paper mode | n/a (code fact) |
| E5 | (4.6) Self-measurement circular; only an offline backtest on held-out history breaks the loop | n/a (methodological) | n/a |
| E6 | (4.7) **Config drift**: `config.yaml` shipped `trailing_stop_fraction: 0.15` and `half_life_days: 14`, silently overriding post-fix code defaults (0.40 / 7.0) → running bot used pre-fix behavior. **A third instance was found during this pass**: `min_trades: 50` vs. the code's `150` (raised via commit M12 to fix a winner's-curse statistical bias) | ✅ **fixed in this PR** — all three now match `config.py`, plus a regression test (`TestShippedConfigMatchesCodeDefaults`) that loads the shipped `config.yaml` and asserts it against code defaults | n/a (code fact) |
| E7 | (#76/#77 f.4) README says fractional-Kelly sizing but `kelly_enabled: false` — docs/config/code disagree | ✅ **fixed in this PR** — README now states Kelly is opt-in/off-by-default | n/a |

## F. Integration-drift claims (PR #76/#77)

| # | Claim | Code check | External check |
|---|-------|-----------|----------------|
| F1 | Leaderboard endpoint dead (404); current is `/v1/leaderboard` with `category`/`timePeriod`/`orderBy` and `proxyWallet`/`userName`/`vol`/`pnl` fields | ✅ **fixed on `main`** via commit `2e98738`, independent of this branch | ✅ confirmed against docs.polymarket.com |
| F2 | `py-clob-client>=0.34,<1.0` pin stale; docs now recommend `py-clob-client-v2`; missing `signature_type` / `funder` config for deposit-wallet users | ⚠️ **partially fixed in this PR** — `signature_type`/`funder` config added with fail-closed validation; the `py-clob-client-v2` migration itself is still open (see readiness plan PR 3) | ✅ confirmed against docs.polymarket.com/api-reference/authentication; **new finding**: py-clob-client-v2's open GitHub issues (#70, #90) report `signature_type=3` binds the API key to the EOA instead of the deposit wallet — a known auth-path bug neither PR flagged |
| F3 | WebSocket drift: repo used `/ws/` + protocol-level ping every 15s + `"type": "Market"`; docs specify `/ws/market` (or `/ws/user`) + **application-level text `PING` every 10s**; silent mismatch degrades exit feeds to REST polling | ✅ **fixed on `main`** via commit `2e98738`, independent of this branch | ✅ confirmed, with a nuance neither PR caught: the *sports* channel differs — server-initiated 5s ping, client must pong within 10s |
| F4 | Data API rate limits now much higher than repo assumes (1,000 req/10s general; `/trades` 200/10s; CLOB book/price/midpoint 1,500/10s; POST /order 5,000/10s burst) — repo's 30 req/60s budget overconservative | ⚠️ repo budget confirmed conservative; unchanged (deliberately not touched — safer to stay conservative) | not independently re-checked |
| F5 | Leaderboard `xUsername`/`verifiedBadge` are metadata, not alpha | n/a | n/a (judgment; agree) |
| F6 | Live Gamma sample (2026-06-30): top all-time PnL Theo4 $22.05M, Fredi9999 $16.6M, swisstony $13.7M…; monthly leaders ~$7.6–9.2M | n/a | not independently re-checked (point-in-time sample, expected to be stale by now) |

## G. Regulatory / access / security claims (PR #75 §5)

| # | Claim | Code check | External check |
|---|-------|-----------|----------------|
| G1 | DOJ/CFTC investigations ended Jul 2025; Polymarket acquired CFTC-licensed **QCEX** ($112M); launched **Polymarket US** (DCM); CFTC amended Order of Designation Nov 25 2025; ICE invested up to ~$2.6B | n/a | ✅ **confirmed** for the 2025 timeline, with corrections — see `PROFITABILITY_FACTCHECK_REPORT_JULY_2026.md` §2. **New finding**: the CFTC opened a *new* investigation into Polymarket in June 2026 |
| G2 | US persons can now legally trade — but via the regulated DCM, in permitted states (reported exclusions: AZ, IL, MA, MD, MI, MT, NJ, NV, OH); Kalshi is the cleaner regulated alternative | n/a | ⚠️ the intermediated-access mechanism (via FCMs) is confirmed; the specific excluded-state list wasn't independently re-verified |
| G3 | **Venue mismatch**: bot hardcodes the international CLOB (`clob.polymarket.com` etc.), which still geoblocks US IPs and checks before every order; Polymarket US is a separate exchange (own books/markets/fees/auth) → US real-money port is a rewrite, not a config change | ✅ endpoints hardcoded in repo | ✅ **confirmed** — docs.polymarket.com/api-reference/geoblock documents server-side rejection at order placement, tiered restriction categories |
| G4 | Whether **automated** trading on the intl CLOB is permitted for a US person is an open compliance question | n/a | not resolved either way by this pass |
| G5 | Security: hijacked verified GitHub org distributed 20+ malicious Polymarket copy-bot repos that exfiltrate `.env` private keys (StepSecurity); ~$3M related phishing losses; keep `POLY_PRIVATE_KEY` on a low-balance wallet | n/a | ✅ **confirmed** the hijacked-org campaign is real; ❌ **refuted** the $3M figure — that's from a separate June 2026 supply-chain attack on Polymarket's own website, unrelated to the GitHub repos |

## H. Paper-mode vs live differences (cross-cutting; both PRs)

| # | Claim | Code check | External check |
|---|-------|-----------|----------------|
| H1 | Paper fills are always full FOK fills against a synthetic 0.50/0.51 book → paper never observes no-fill/partial-fill, which in live systematically removes the *best* trades (fast markets) | ✅ confirmed, still unaddressed | n/a |
| H2 | Paper applies configured slippage plus price-shaped taker fee — better than midpoint-optimistic, but still not a discontinuous, size-sensitive real book | ✅ fee curve addressed; real-book VWAP/no-fill modeling still open | ⚠️ qualitatively supported, see C5 |
| H3 | Paper mode skips the live depth gate entirely | ✅ confirmed, still true | n/a |
| H4 | "30 days green paper PnL" as go-live gate is non-predictive; backtest on held-out history is the honest arbiter | ✅ gate documented in `next_steps.md` | n/a (methodological; agree — matches readiness plan PR 4's forward-paper gate) |

---

## Deep-research verification results

Ran 2026-07-03. **Caveat on methodology:** the harness's 3-vote adversarial-verification pass errored out entirely
(session rate limit), so nothing below carries the workflow's normal "2/3 refuted → killed" cross-check. What
follows is single-pass extraction from live web search hitting primary/near-primary sources (docs.polymarket.com,
CFTC/PR Newswire, SSRN, ICE IR, StepSecurity, CoinDesk, WSJ-via-Yahoo) with direct quotes — treat as well-sourced
but not adversarially stress-tested. Full synthesis in `PROFITABILITY_FACTCHECK_REPORT_JULY_2026.md`.

| Claim area | Verdict | Correction |
|---|---|---|
| C1 concave fee formula, makers free | ✅ **CONFIRMED** (docs.polymarket.com/trading/fees) | Exact form is `C × rate × p × (1−p)`, symmetric, near-zero at extremes |
| C3 category taker caps | ⚠️ **MOSTLY CONFIRMED, one number off** | Correct global-CLOB caps: ~0.75% sports, 1.00% politics/finance/tech, 1.25% culture/weather, **1.50% economics (not 1.25% as PR #75 stated)**, 1.80% crypto, geopolitics free |
| C2 US DCM Θ=0.05/$1.25 cap/−$0.31 maker rebate | ❌ **UNCONFIRMED / likely wrong framing** | Only the *global* CLOB rebate mechanism is documented: makers pay nothing and split a **revenue-share pool** (25% of taker fees, 20% for crypto), not a flat −$0.31/100 figure. No primary source surfaced for that being the *US DCM's* specific rate |
| G1 DOJ/CFTC ended investigations July 2025 | ✅ **CONFIRMED** (CNBC, primary quote) | Both civil + criminal probes closed with no charges; centered on US-user access despite 2022 promises |
| G1 QCEX acquisition ~$112M | ✅ **CONFIRMED** (PR Newswire, primary) | Closed July 21, 2025; QCX LLC + QC Clearing LLC |
| G1 CFTC amended Order of Designation ~Nov 25 2025 | ✅ **CONFIRMED** (PR Newswire + CFTC doc) | Enables *intermediated* access via FCMs/brokerages — separate regulated DCM, not the international CLOB |
| G1 ICE invested ~$2B–2.6B | ⚠️ **PARTIALLY CONFIRMED, figure corrected** | ICE announced **up to $2B** (Oct 7 2025, $8B pre-money valuation) — the "$2.6B" figure double-counts a later 2026 $600M raise that was part of the same commitment, not additive |
| G3 international CLOB still geoblocks US, order-level enforcement | ✅ **CONFIRMED** (docs.polymarket.com/api-reference/geoblock, primary) | Server-side rejection at order placement, not just frontend; tiered "block completely" vs "close-only" categories |
| **NEW nuance not in either PR** | ⚠️ | A CNBC follow-up (June 26, 2026) reports the **CFTC opened a NEW investigation into Polymarket** — regulatory status is *not* fully settled as of July 2026 despite the July-2025 closure |
| B1 SSRN #6617059 exists with claimed findings | ✅ **CONFIRMED** (SSRN abstract page, SSRN Blog, The Block, CoinDesk, Bitcoin.com — 5 independent sources) | Posted Apr 20 2026 (rev. Apr 25); 3.14% skilled, 44% OOS persistence vs ~10% mutual funds, ~12% top-earner/skill overlap, ~1,950 suspected insiders moving prices 7–12× harder, skill = first-reaction/speed edge — **all numbers match exactly** |
| "Yale study" framing | ⚠️ **IMPRECISE** | 3 of 4 authors (Gómez-Cram, Guo, Kung) are London Business School; only Jensen is Yale SOM. Yale's own site ran a write-up, which is likely the source of the "Yale study" label, but it's not accurate to call it a Yale study |
| D2/G5-adjacent: ~7.6% of wallets profitable (Dune) | ⚠️ **ORDER-OF-MAGNITUDE CONFIRMED, not primary-verified** | A secondary trading-guide article cites this Dune figure (~120k winners vs 1.5M+ losers); the raw Dune dashboard itself wasn't independently checked |
| <1% of wallets take ~half the profits (Solidus/WSJ) | ⚠️ **CONFIRMED BUT CONFLATES TWO STUDIES** | Solidus Labs (Apr 2026, politics markets only, Dec2025–Feb2026 window): 0.55% of profitable maker wallets + 0.26% of taker wallets each capture ~50% of gains. **WSJ's separate analysis found a starker number**: 0.1% of accounts captured 67% of all profits, >70% of users lose money overall. PR text blends these as one stat; they're two different studies/samples |
| Broader wallet loss-rate | ✅ new data point | An April-2026 on-chain analysis of 2.5M wallets found **84.1% lost money**, only 2% ever made >$1,000, 0.033% (840 addresses) cleared $100K |
| Solidus caveat (new, not in either PR) | ⚠️ | Solidus's report also flags **wash trading and suspected POLY-airdrop farming** on leaderboard-adjacent wallets — top-wallet PnL can be manipulated, independent of the skill/luck question |
| B3 skill = speed/first-reaction edge, uncopyable | ✅ **CONFIRMED**, directly relevant to PR #75's core thesis | Multiple sources restate: skilled traders react first to public news; a bot mirroring 2–13s later buys post-impact price (adverse selection) — this inference about copy-bots specifically is the fact-checkers' extension of the paper's finding, not a stated result of the paper itself |
| F1 legacy `/leaderboard` 404, `/v1/leaderboard` replacement | ✅ **CONFIRMED** (docs.polymarket.com API reference) | Params/response fields (`category`, `timePeriod`, `orderBy`, `proxyWallet`, `userName`, `vol`, `pnl`, `xUsername`, `verifiedBadge`) match exactly. Already fixed on `main` (see F1 in the table above) |
| F3 WS `/ws/market` + 10s text PING/PONG | ✅ **CONFIRMED**, with a nuance PR #76/#77 missed | docs.polymarket.com/developers/CLOB/websocket/wss-overview confirms 10s app-level PING for market/user channels — **but the sports channel is different**: server-initiated ping every 5s, client must pong within 10s or the connection closes. Already fixed on `main` (see F3 in the table above) |
| F2 py-clob-client-v2 recommended, signature_type 3 + funder | ✅ **CONFIRMED**, with an important operational caveat neither PR flagged | signature_type 3 = `POLY_1271` (deposit-wallet flow); **open GitHub issues (#70, #90) on py-clob-client-v2 report L1 auth binds the API key to the EOA rather than the deposit wallet under signature_type=3** — i.e., this exact auth path has known breakage for programmatic order placement as of the research date |
| H2/C5 paper trading overstates live taker performance | ⚠️ **QUALITATIVELY SUPPORTED, not quantitatively confirmed** | A rare live (non-simulated) taker-strategy writeup shows execution assumptions dominate outcomes, consistent with the thesis; no independent source confirmed the specific "3–6% round-trip" friction number |
| G5 security: StepSecurity hijacked-org report, 20+ malicious repos | ✅ **CONFIRMED** (StepSecurity primary write-up + GitHub repo evidence + Cryptopolitan follow-up) | `dev-protocol` (verified GitHub org, 568 followers) hijacked ~Feb 26 2026; 20+ scam copy-bot repos; typosquatted npm deps exfiltrate `.env` private keys to attacker Vercel endpoints + open an SSH backdoor |
| G5 "$3M in related phishing losses" | ❌ **REFUTED — conflates two distinct incidents** | The $3M (revised to $3.1M) loss is from a **separate** June 25 2026 supply-chain compromise of a third-party front-end vendor injecting malicious JS into Polymarket's own website — draining ~11 user wallets, unrelated to the GitHub copy-bot repos. The security lesson (never fund a bot wallet you didn't audit) still stands; the dollar figure attribution in PR #75 is factually wrong |

**Bottom line on the fact-check:** PR #75 and #76/#77's factual claims hold up well overall — the SSRN paper, regulatory
timeline, fee-curve shape, API/WebSocket migration, and security-risk category are all real and substantially as
described. The errors found are in **precision, not direction**: one fee-category number, the maker-rebate figure,
the ICE total, the "Yale study" label, and the security-incident dollar figure all need small corrections. One
materially new finding not in either PR: **the CFTC opened a new investigation into Polymarket in June 2026**,
meaning the regulatory "all clear" the PRs describe is not the final word.
