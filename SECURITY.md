# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.2.x   | :white_check_mark: |
| < 0.2   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in PolyMarket_Mimic_Trader, **do not open a public issue**. Instead, please report it privately:

1. **Email:** [contact@cgfixit.com](mailto:contact@cgfixit.com)
2. **Subject line:** `[SECURITY] PolyMarket_Mimic_Trader — <brief description>`
3. Include:
   - A description of the vulnerability and its potential impact
   - Steps to reproduce or a proof-of-concept
   - The affected file(s) and line number(s) if known
   - Your suggested fix, if any

You should receive an acknowledgment within **48 hours**. We aim to release a patch within **7 days** of confirmation for critical issues.

## Scope

The following are in scope for security reports:

| Area | Examples |
|------|----------|
| **Private key handling** | Key leakage via logs, env mishandling, or error messages |
| **Order placement logic** | Conditions where the bot could place unintended live orders |
| **SQLite injection** | Unsanitized input reaching portfolio DB queries |
| **Dependency vulnerabilities** | Known CVEs in `py-clob-client`, `aiohttp`, `pydantic`, `aiosqlite`, `websockets` |
| **Configuration bypass** | Ways to force live trading when `mode: paper` is set |
| **Exposure cap bypass** | Code paths that skip `RiskManager.build_position()` or `_assert_exposure_cap()` |

The following are **out of scope**:

- Polymarket API or smart contract vulnerabilities (report those to [Polymarket](https://polymarket.com))
- Financial losses from using the bot as intended (see Disclaimer in README)
- Social engineering attacks

## Security Design Principles

This project follows these security practices:

1. **No hardcoded secrets** — All credentials are loaded from environment variables via `.env` (never committed)
2. **Paper mode by default** — `config.yaml` ships with `mode: paper`; live trading requires explicit `--mode live` CLI flag *and* a configured `POLY_PRIVATE_KEY`
3. **No automatic order retries** — Failed order placements are logged and skipped, never retried (retrying on a stale market can create double positions)
4. **Parameterized SQL** — All SQLite queries in `portfolio.py` use parameterized statements (`?` placeholders), not string interpolation
5. **Input validation** — All prices are validated against `[0.0, 1.0]` range via `_assert_valid_price()`; the `Order` model enforces `price=Field(ge=0, le=1)` and `size_usdc=Field(gt=0)` at the Pydantic layer
6. **Exposure caps** — `RiskManager._assert_exposure_cap()` is called on every position entry; `release_exposure()` rolls back on failure paths

## Dependency Auditing

We recommend periodically auditing dependencies:

```bash
pip install pip-audit
pip-audit -r requirements.txt
```
