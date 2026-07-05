# Profitability Fact-Check & Remediation Report — July 2026

**Scope:** This report reconciles the profitability/feasibility claims made across PR #75 (merged,
`PROFITABILITY_ANALYSIS_JUNE_2026.md`), PR #76 (open, `docs/POLYMARKET_BOT_STRATEGY_RESEARCH_2026-06-30.md`),
and PR #77 (merged; duplicate root copy now removed) against (a) this repo's actual code and
(b) an independent deep-research fact-check against primary sources (Polymarket docs, CFTC/PR Newswire, SSRN,
ICE IR, StepSecurity, CoinDesk, WSJ). It closes with the fixes applied on this branch and what's still open.

Full claim-by-claim ledger: `docs/PR_75_76_77_CLAIMS_NOTEPAD.md`. Methodology caveat: the fact-check's adversarial
3-vote verification step hit an infrastructure rate limit and did not run; findings below are single-pass
extraction with direct quotes from primary sources, not cross-verified by independent skeptic votes. Confidence
is noted per finding.

**Current main update, 2026-07-05:** after this report was written, `origin/main` also landed fee-curve realism,
CLOB fee metadata, live geoblock preflight, profitability timing telemetry, documented WebSocket heartbeat,
`usdcSize` activity notional parsing, and canonical `paper_taker_fee_rate` cleanup. The original conditional-NO
profitability verdict still holds, but several implementation blockers listed below are now fixed or partially
fixed on main.

---

## 1. Bottom line

**The original verdict holds, and the fact-check makes it slightly more pessimistic, not less.**

PR #75's core thesis — the engineering is strong, the edge is real for a ~3% skilled minority, but that edge is
a speed/first-reaction edge this bot's copy mechanism cannot inherit at 2–13s of latency, and total round-trip
friction (spread + slippage, not fees) likely erases what's left — was independently corroborated against the
actual SSRN paper, not just PR #75's summary of it. Every headline number PR #75 cited from that paper (3.14%
skilled, 44% out-of-sample persistence vs. ~10% for mutual funds, ~12% top-earner/skill overlap, ~1,950 suspected
insiders moving prices 7–12× harder) matches the paper as published. Multiple independent secondary sources
(The Block, CoinDesk, Bitcoin.com News, Yale's own write-up) repeat the same figures.

Two new findings from this fact-check make the picture *worse* than either PR described:

1. **The CFTC opened a new investigation into Polymarket in June 2026** (per a CNBC follow-up), after the
   July-2025 closure both PRs describe as the end of regulatory risk. The "regulatory all-clear" framing in
   PR #75 §5 is no longer current.
2. **Wallet profit concentration is starker than PR #75 cited.** PR #75 quoted "<1% of wallets take ~half the
   profits" as one Solidus Labs/WSJ statistic. It's actually two different studies with two different numbers:
   Solidus Labs (politics markets only, Dec 2025–Feb 2026: 0.55%/0.26% of wallets take ~50% of gains) and WSJ
   (venue-wide: **0.1% of accounts captured 67% of all profits**, and **>70% of users lose money**). The WSJ
   figure is the stronger and more representative one, and it's more concentrated than what was quoted.
   Separately, a 2.5M-wallet on-chain analysis found **84.1% of traders lost money**.

Everything else checked out close to as described, with a handful of precision corrections (below) and one
operational risk neither PR flagged: **py-clob-client-v2's open GitHub issues indicate `signature_type=3` (the
deposit-wallet auth path both PRs recommend adding config for) has known breakage** — the API key can bind to the
wrong wallet. That's now surfaced in this repo's config validation (see §3).

---

## 2. Corrections to the original PR claims

| Claim (PR #75/#76/#77) | Fact-check verdict | Correct version |
|---|---|---|
| Category taker fee caps: 0.75/1.00/1.25/1.80 sports/politics/culture/crypto | ⚠️ One number off | Economics is **1.50%**, not 1.25% — 1.25% belongs to culture/weather |
| US DCM maker rebate = flat −$0.31/100 contracts | ❌ Unconfirmed | The only documented rebate mechanism is a **revenue-share pool** (makers split 25% of taker fees, 20% for crypto) on the *global* CLOB — no primary source confirms a flat per-contract US DCM figure |
| ICE invested "$2B–2.6B" | ⚠️ Overstated | ICE announced **up to $2B** (Oct 2025, $8B pre-money valuation). The "$2.6B" figure double-counts a 2026 follow-on raise that was part of the same original commitment, not additive |
| SSRN paper described as a "Yale study" | ⚠️ Imprecise | 3 of 4 authors (Gómez-Cram, Guo, Kung) are London Business School; only Jensen is Yale SOM. Yale's own site published a write-up (likely the source of the label), but "Yale study" overstates Yale's role |
| "~$3M in related phishing losses" tied to the malicious GitHub copy-bot repos | ❌ Conflates two incidents | The StepSecurity-documented hijacked-org/copy-bot-repo campaign (real, confirmed) and the $3M (revised $3.1M) loss are **separate incidents** — the $3M came from a June 25, 2026 compromise of a third-party front-end vendor injecting malicious JS into Polymarket's own website, unrelated to the GitHub repos |
| "<1% of wallets take ~half the profits" | ⚠️ Conflates two studies | Solidus Labs (politics markets, defined window) says this; WSJ's venue-wide analysis found a starker **0.1% take 67%**, >70% of users lose money overall |
| DOJ/CFTC investigations "ended" (regulatory risk resolved) | ⚠️ Stale as of July 2026 | True for the 2022–2025 probes, but the **CFTC opened a new investigation in June 2026** — not mentioned in either PR |

Everything else — the concave fee formula, the QCEX acquisition and $112M figure, the CFTC Amended Order of
Designation (~Nov 25, 2025) enabling *intermediated* (not international-CLOB) US access, the international CLOB's
continued server-side geoblocking of the US, the `/v1/leaderboard` endpoint migration and schema, the WebSocket
`/ws/market` + 10s text PING/PONG requirement, and the `py-clob-client-v2` + `signature_type=3` + `funder` auth
guidance — checked out against primary sources essentially as both PRs described.

---

## 3. Code changes now landed on main

Mechanical, low-risk fixes have continued after the original branch. Current `origin/main` includes the earlier
leaderboard/API drift work plus later real-money-readiness fixes:

1. **Config drift fix, three instances** (`config.yaml`) — `trailing_stop_fraction` (0.15 → 0.40) and
   `half_life_days` (14 → 7) already matched `config.py`'s documented post-fix defaults but the shipped YAML
   silently overrode them. A **third, previously unflagged instance** was found during this pass: `min_trades`
   (50 in `config.yaml` vs. `150` in `config.py`, raised via commit M12 specifically to fix a winner's-curse
   statistical bias in trader selection at small sample sizes) had the same silent-override problem. All three
   now match. A new regression test class, `TestShippedConfigMatchesCodeDefaults`, loads the actual repo-root
   `config.yaml` and asserts it against `AppConfig()`'s code defaults, so a future edit to either file that
   reintroduces this class of drift fails CI instead of shipping silently.
2. **Deposit-wallet auth config** (`config.py`, `api/clob_client.py`, `.env.example`) — added `signature_type`
   and `funder` config fields (env vars `POLY_SIGNATURE_TYPE` / `POLY_FUNDER`), wired through to the live
   `py-clob-client` constructor, with a fail-closed validation: live mode + `signature_type=3` without `funder`
   set now raises `ConfigError` at startup instead of silently misconfiguring the deposit-wallet flow. This is a
   partial implementation of "PR 3: Live Auth/SDK Compatibility" from
   `docs/POLYMARKET_REAL_MONEY_READINESS_PR_PLAN_2026-07-03.md`; the later live-geoblock preflight is also now
   on main, while the `py-clob-client-v2` migration/proof remains open.
3. **README accuracy** — corrected the "mirrors entries via fractional Kelly" framing (Kelly is opt-in, off by
   default; the actual default is a flat 50%-of-source-size multiplier) and added a caveat to the "Why This
   Exists" pitch that leaderboard rank is a candidate filter, not a proven copyable edge, per the SSRN findings.
   Also corrected a stale `trailing_stop_fraction` value in the parameter table.
4. **Fee-curve and market-fee metadata** — paper fills and copy gates now use Polymarket's price-shaped taker-fee
   curve (`fee_rate * price * (1 - price)`), with CLOB/Gamma market fee metadata when available.
5. **Live geoblock preflight** — live mode now checks Polymarket's geoblock endpoint before entering the live order
   path. This is a safety guard, not a legal approval.
6. **Profitability telemetry and API drift follow-ups** — timing telemetry, documented WebSocket `PING`, `usdcSize`
   activity notional parsing, and canonical `paper_taker_fee_rate` docs/config cleanup have landed.

---

## 4. What's still open (highest leverage, ranked)

Not fixed in this pass. `docs/POLYMARKET_REAL_MONEY_READINESS_PR_PLAN_2026-07-03.md` already tracks most of this
as a 4-PR roadmap (fee realism, live auth/SDK, profitability telemetry) — this fact-check confirms that roadmap's
priorities are the right ones and adds a couple of items it doesn't cover:

1. **Build the offline backtest harness (readiness plan "PR 4").** The "30 days green paper PnL" go-live gate is
   non-predictive. Paper mode is now better on fees, but it still cannot prove live fill/no-fill behavior or
   adverse selection. This remains the single highest-leverage next step before any real capital.
2. **Execution parity reporting.** Persist detection latency, submit latency, fill latency, source price, observed
   spread, book VWAP, fee, size, skip reason, and realized PnL by source wallet and market type.
3. **`py-clob-client-v2` migration and live auth proof.** Deposit-wallet config exists and geoblock preflight exists,
   but the exact SDK/signature/funder live order path still needs minimal-fund proof. Track the open
   `py-clob-client-v2` issues (#70, #90) before using `signature_type=3`.
4. **De-bias trader win-rate/ROI metrics** — worthless-expiry losses aren't counted (no redeem record), inflating
   the tracker's selection metrics and the (currently-disabled) Kelly edge seed.
5. **Regulatory re-check** — the new June 2026 CFTC investigation (finding #1 above) should be tracked; it wasn't
   in scope for either prior PR or the readiness plan.

---

## 5. Recommendation

Do not increase live sizing or exit paper mode based on this fact-check alone. Later main-branch fixes remove more
implementation drift, but nothing yet proves net expectancy after spread, slippage, fees, latency, skipped fills,
and legal/venue constraints. Paper-mode results still are not a valid go-live signal until the backtest harness and
execution parity reports exist.
