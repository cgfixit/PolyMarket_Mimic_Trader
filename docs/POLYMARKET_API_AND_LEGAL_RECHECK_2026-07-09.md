# Polymarket API And Legal Recheck (2026-07-09)

Repo snapshot: `aa3b552` on `codex/research-polymarket-api-20260709`

This was a current-source recheck against official Polymarket docs plus current federal and Georgia legal text for non-paper mode assumptions. Claim labels below use the repo's own discipline: external fact, repo fact, inference, open question.

## Assumption Ledger

| assumption | repo location | current source | status | action |
| --- | --- | --- | --- | --- |
| Live-mode auth broadly matches the current official Polymarket trading flow. | `requirements.txt:1`, `polymarket_copier/api/clob_client.py:121-155`, `polymarket_copier/config.py:251-267`, `README.md:11-15` | Polymarket Trading Overview and Authentication docs say current Python client is `py-clob-client-v2`, L1 derives L2 creds, and new API users should use deposit-wallet `signature_type=3` plus funder/deposit-wallet address. | drifted | Keep live mode documented as not ready; stop short of code changes in this run. |
| Leaderboard discovery uses the current official endpoint and core schema. | `polymarket_copier/core/tracker.py:474-499`, `README.md:20-24,264-267` | Polymarket leaderboard docs still show `GET https://data-api.polymarket.com/v1/leaderboard` with fields including `proxyWallet`, `userName`, `vol`, `pnl`, `xUsername`, `verifiedBadge`. | confirmed | No doc correction needed beyond the research note. |
| Wallet activity parsing is grounded on the current endpoint and current notional field. | `polymarket_copier/core/tracker.py:550-583`, `polymarket_copier/utils/activity.py:44-46`, `README.md:13` | Polymarket activity docs still show `GET https://data-api.polymarket.com/activity` and include `usdcSize` on activity rows. | confirmed | No doc correction needed in this pass. |
| Market discovery assumptions still fit the current official market-data docs. | `README.md:264-267`, `polymarket_copier/api/gamma_client.py:16-18` | Polymarket market-data docs still direct builders to `gamma-api.polymarket.com/events` and `/markets` for discovery. | confirmed | No doc correction needed in this pass. |
| Geoblock should be treated as a hard live-trading gate, not a cosmetic frontend rule. | `polymarket_copier/main.py:25,36-56,88`, `README.md:13-15`, `PROFITABILITY_ANALYSIS_JUNE_2026.md:28` | Polymarket geoblock docs say builders should check `GET https://polymarket.com/api/geoblock`, orders from blocked regions will be rejected, and `US` is listed as close-only on frontend and API. | confirmed | Keep the fail-closed geoblock warning strong. |
| For a Georgia-based operator, the international CLOB remains a legal/compliance blocker rather than a config problem. | `README.md:15`, `PROFITABILITY_ANALYSIS_JUNE_2026.md:28,42-43` | Polymarket geoblock docs list `US` as close-only on frontend and API; 31 U.S.C. Sec. 5363 still prohibits payment acceptance tied to unlawful internet gambling; 18 U.S.C. Sec. 1084 still reaches interstate or foreign wire transmission of bets/wagers or assisting information on sporting events/contests; Georgia Constitution Art. I, Sec. II, Para. VIII still prohibits lotteries, pari-mutuel betting, and casino gambling except specific carveouts. | confirmed | Keep the repo's conditional-NO legal warning. Counsel is still required before any non-paper path. |
| Passing geoblock or seeing working API examples would itself answer the federal/state legality question. | implied risk boundary in `README.md:15` and `PROFITABILITY_ANALYSIS_JUNE_2026.md:28,42` | The official docs only describe API and geoblock behavior; they do not grant legal clearance. The federal statutes and Georgia constitution do not yield a clean venue-specific clearance answer by themselves. | unclear | Treat legality as counsel-only, not as an engineering checklist item. |

## Legal Risk Note

Not legal advice.

- **[verified external fact]** Polymarket's current geoblock docs list `US` as close-only on both the frontend and the API. A Georgia-based operator should expect the international CLOB order path to be blocked for opening trades from US IP space.
- **[verified external fact]** Georgia's constitution still prohibits lotteries, pari-mutuel betting, and casino gambling except narrow carveouts such as the state lottery, nonprofit bingo, and raffles.
- **[verified external fact]** 31 U.S.C. Sec. 5363 still targets payment acceptance tied to unlawful internet gambling. 18 U.S.C. Sec. 1084 still covers interstate or foreign wire transmission of bets or wagers, or assisting information, on sporting events or contests.
- **[inference]** Even before resolving the harder federal classification questions, the combination of Polymarket's own US API restriction and Georgia's anti-gambling baseline keeps the international CLOB in the legal/compliance-risk bucket for a Georgia-based operator.
- **[open question]** The bare federal statutes do not, by themselves, answer every prediction-market or non-sports edge case. Venue, product type, funding path, and automation method still need counsel.

## Source Notes

- Official Polymarket docs were checked on 2026-07-09:
  - Trading Overview
  - Authentication
  - Get trader leaderboard rankings
  - Get user activity
  - Fetching Markets
  - Geographic Restrictions
- Federal statutory text was checked from the current US Code pages on 2026-07-09:
  - `31 U.S.C. Sec. 5363`
  - `18 U.S.C. Sec. 1084`
- The Georgia General Assembly constitution page was reachable only as a JavaScript loading shell during this pass. The constitution text used for the legal note came from an accessible current web copy surfaced during the same research pass, and should be rechecked against the legislature site or counsel before relying on it for anything higher-stakes than doc risk labeling.
