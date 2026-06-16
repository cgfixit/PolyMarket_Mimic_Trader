# Contributing to PolyMarket_Mimic_Trader

Thanks for your interest in contributing! This project is a Polymarket copy-trading bot with range-relative risk management. Contributions that improve correctness, safety, or test coverage are especially welcome.

## Getting Started

### 1. Fork and clone

```bash
git clone https://github.com/<your-username>/PolyMarket_Mimic_Trader.git
cd PolyMarket_Mimic_Trader
```

### 2. Set up a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run the test suite

```bash
pytest -v
```

All 144+ tests must pass before submitting a PR. Tests run fully offline with mocked API responses.

### 4. Run the linter

```bash
pip install ruff
ruff check .
```

## Development Workflow

1. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the guidelines below.

3. **Add or update tests** — every bug fix should include a regression test; every new feature should include unit tests. Integration tests in `tests/test_integration.py` are required for changes to the monitor-copier wiring.

4. **Verify locally:**
   ```bash
   pytest -v              # All tests pass
   ruff check .           # No lint errors
   ```

5. **Commit with a clear message** describing *why*, not just *what*:
   ```bash
   git commit -m "Fix trailing stop never persisting peak to SQLite

   evaluate() mutates pos.peak_price in-place, so the subsequent
   comparison was always False. Capture prev_peak before the call."
   ```

6. **Open a PR** against `main` with a description of what changed and why.

## Code Guidelines

### Architecture rules

- **Never place a live order without calling `RiskManager.build_position()` first.** It enforces the exposure cap. Bypassing it will breach market concentration limits.
- **Never use flat-percentage TP/SL.** The `_compute_thresholds()` method in `risk_manager.py` is the only acceptable way to compute take-profit and stop-loss prices.
- **Never enter a market resolving within 24 hours.** Liquidity collapses near resolution.
- **Never retry failed order placements.** Log and skip. Retrying on a stale market can create double positions.
- **Paper mode must be the default.** Live mode requires explicit `--mode live`.

### Style

- **Python 3.9+** compatibility required (use `from __future__ import annotations`)
- **Ruff** for linting — the project config is in `pyproject.toml`
- **No comments explaining *what*** — use clear names instead. Only comment *why* when it's non-obvious.
- **Async/await correctness** — if a callback is `async def`, the caller must `await` it. The integration tests in `test_integration.py` exist specifically to catch un-awaited coroutine regressions.

### Testing

| Test type | Location | When to add |
|-----------|----------|-------------|
| Unit tests | `tests/test_<module>.py` | Every change |
| Integration tests | `tests/test_integration.py` | Changes to monitor/copier/portfolio wiring |
| Risk manager tests | `tests/test_risk_manager.py` | Changes to TP/SL/trailing/exposure logic |

All external API calls must be mocked. Tests must run offline and complete in under 5 seconds.

### Project layout

```
polymarket_copier/
├── api/           # API client wrappers (Data, Gamma, CLOB)
├── core/          # Business logic (tracker, monitor, copier, risk, portfolio)
├── models/        # Pydantic data models
├── utils/         # Logging
├── config.py      # Configuration loading
└── main.py        # CLI entrypoint
tests/             # Pytest test suite
```

## What We're Looking For

High-impact contributions:

- **Bug fixes** with regression tests (see the "Remaining Known Issues" section in recent PRs)
- **Tracker accuracy** — improving the `_build_trader_stats` field-name mapping against the live Polymarket Data API
- **Rate limiting** — consolidating `TrackerClient`'s fetch logic to use `DataClient` (and its `AsyncLimiter`)
- **UTC correctness** — `_midnight_utc()` in `risk_manager.py` has a known `time.mktime`/`gmtime` mismatch
- **Additional risk controls** — e.g. correlation-aware position sizing across related markets

## Code of Conduct

Be respectful, constructive, and focused on the code. This is a small project — keep discussions on-topic and PRs focused on a single concern.

## Questions?

Open an issue or reach out to [contact@cgfixit.com](mailto:contact@cgfixit.com).
