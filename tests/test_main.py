"""Tests for startup preflight behavior in main.py."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from polymarket_copier.config import AppConfig, ConfigError
from polymarket_copier.main import POLYMARKET_GEOBLOCK_URL, _enforce_live_geoblock_preflight, run_bot


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
