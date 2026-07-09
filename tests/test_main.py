"""Tests for startup preflight behavior in main.py."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from polymarket_copier.config import AppConfig, ConfigError
from polymarket_copier.core.portfolio import PortfolioManager
from polymarket_copier.core.risk_manager import ExitReason, RiskConfig, RiskManager
from polymarket_copier.main import (
    POLYMARKET_GEOBLOCK_URL,
    _enforce_live_geoblock_preflight,
    _install_shutdown_handlers,
    enforce_forward_paper_gate,
    run_bot,
)


class _FakeResp:
    def __init__(self, data=None, exc: Exception | None = None):
        self._data = data
        self._exc = exc

    async def __aenter__(self):
        if self._exc:
            raise self._exc
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        return None

    async def json(self):
        return self._data


class _FakeSession:
    def __init__(self, data=None, exc: Exception | None = None):
        self.data = data
        self.exc = exc
        self.urls: list[str] = []

    def get(self, url):
        self.urls.append(url)
        return _FakeResp(self.data, self.exc)


@pytest.fixture
def logger():
    return SimpleNamespace(info=lambda *args, **kwargs: None)


@pytest.mark.asyncio
async def test_geoblock_preflight_skips_paper_mode(logger):
    session = _FakeSession({"blocked": True, "country": "US", "region": "GA"})

    await _enforce_live_geoblock_preflight(AppConfig(mode="paper"), session, logger)

    assert session.urls == []


@pytest.mark.asyncio
async def test_geoblock_preflight_passes_allowed_live_region(logger):
    session = _FakeSession({"blocked": False, "country": "IE", "region": ""})

    await _enforce_live_geoblock_preflight(AppConfig(mode="live"), session, logger)

    assert session.urls == [POLYMARKET_GEOBLOCK_URL]


@pytest.mark.asyncio
async def test_geoblock_preflight_blocks_live_region(logger):
    session = _FakeSession({"blocked": True, "country": "US", "region": "GA"})

    with pytest.raises(ConfigError, match="US-GA"):
        await _enforce_live_geoblock_preflight(AppConfig(mode="live"), session, logger)


@pytest.mark.asyncio
async def test_geoblock_preflight_fails_closed_on_invalid_response(logger):
    session = _FakeSession({"country": "US"})

    with pytest.raises(ConfigError, match="invalid response"):
        await _enforce_live_geoblock_preflight(AppConfig(mode="live"), session, logger)


@pytest.mark.asyncio
async def test_geoblock_preflight_fails_closed_on_request_error(logger):
    session = _FakeSession(exc=TimeoutError("slow"))

    with pytest.raises(ConfigError, match="failed"):
        await _enforce_live_geoblock_preflight(AppConfig(mode="live"), session, logger)


@pytest.mark.asyncio
async def test_cli_live_override_revalidates_live_credentials(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("mode: paper\n")
    monkeypatch.delenv("POLY_PRIVATE_KEY", raising=False)

    with pytest.raises(ConfigError, match="POLY_PRIVATE_KEY required"):
        await run_bot(config_path=str(config_file), mode="live")


def test_install_shutdown_handlers_falls_back_when_add_signal_handler_missing(monkeypatch):
    """Windows ProactorEventLoop raises NotImplementedError — must not crash."""
    calls: list[str] = []

    class _Loop:
        def add_signal_handler(self, sig, callback):  # noqa: ARG002
            raise NotImplementedError("not supported on this platform")

    import signal as signal_mod

    registered: list[int] = []

    def _fake_signal(sig, handler):  # noqa: ARG002
        registered.append(sig)
        return None

    monkeypatch.setattr(signal_mod, "signal", _fake_signal)
    _install_shutdown_handlers(_Loop(), lambda: calls.append("stop"))

    assert signal_mod.SIGINT in registered
    # SIGTERM may or may not be registered depending on platform; at least one ok.
    assert registered


class TestForwardPaperGate:
    @pytest.fixture
    async def portfolio(self, tmp_path):
        pm = PortfolioManager(db_path=str(tmp_path / "gate_test.db"))
        await pm.init()
        yield pm
        await pm.close()

    async def _close_paper_trades(self, portfolio, n: int, exit_price: float):
        rm = RiskManager(config=RiskConfig(max_trader_allocation=1.0), bankroll=10_000.0)
        for i in range(n):
            pos = await rm.build_position(
                position_id=f"p{i}",
                market_id=f"m{i}",
                token_id=f"t{i}",
                trader_address="0xw",
                entry_price=0.50,
                size_shares=100.0,
            )
            await portfolio.open_position(pos, mode="paper")
            await portfolio.close_position(pos.position_id, exit_price, ExitReason.TAKE_PROFIT)

    @pytest.mark.asyncio
    async def test_paper_mode_never_gated(self, portfolio, logger):
        config = AppConfig(mode="paper")
        await enforce_forward_paper_gate(config, portfolio, logger)  # no raise

    @pytest.mark.asyncio
    async def test_live_with_no_evidence_refused(self, portfolio, logger):
        config = AppConfig(mode="live")
        with pytest.raises(ConfigError, match="Forward-paper gate"):
            await enforce_forward_paper_gate(config, portfolio, logger)

    @pytest.mark.asyncio
    async def test_live_with_enough_profitable_paper_trades_passes(self, portfolio, logger):
        config = AppConfig(mode="live", forward_paper_min_trades=3)
        await self._close_paper_trades(portfolio, 3, exit_price=0.60)  # +$10 each
        await enforce_forward_paper_gate(config, portfolio, logger)  # no raise

    @pytest.mark.asyncio
    async def test_live_with_losing_paper_record_refused(self, portfolio, logger):
        config = AppConfig(mode="live", forward_paper_min_trades=3)
        await self._close_paper_trades(portfolio, 3, exit_price=0.40)  # -$10 each
        with pytest.raises(ConfigError, match="Forward-paper gate"):
            await enforce_forward_paper_gate(config, portfolio, logger)

    @pytest.mark.asyncio
    async def test_disabled_gate_passes_with_no_evidence(self, portfolio, logger):
        config = AppConfig(mode="live", forward_paper_gate_enabled=False)
        await enforce_forward_paper_gate(config, portfolio, logger)  # no raise
