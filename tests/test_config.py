"""Tests for v2 configuration loading."""

from __future__ import annotations

import pytest
import yaml

from polymarket_copier.config import AppConfig, ConfigError, load_config


class TestAppConfig:
    def test_defaults(self):
        config = AppConfig()
        assert config.mode == "paper"
        assert config.polling_interval_seconds == 8
        assert config.max_tracked_traders == 5
        assert config.bankroll == 500
        # v2 range-relative risk defaults
        assert config.risk_management.tp_range_fraction == 0.40
        assert config.risk_management.sl_range_fraction == 0.25
        assert config.risk_management.min_tp_abs == 0.03
        assert config.risk_management.min_sl_abs == 0.02
        assert config.risk_management.max_market_exposure_pct == 0.08
        assert config.risk_management.resolution_blackout_hours == 24.0
        assert config.copy_trading.size_multiplier == 0.5

    def test_custom_values(self):
        config = AppConfig(
            mode="live",
            bankroll=50000,
            risk_management={"tp_range_fraction": 0.50, "sl_range_fraction": 0.20},
        )
        assert config.mode == "live"
        assert config.bankroll == 50000
        assert config.risk_management.tp_range_fraction == 0.50
        assert config.risk_management.sl_range_fraction == 0.20
        # Other defaults preserved
        assert config.risk_management.min_tp_abs == 0.03

    def test_load_config_from_yaml(self, tmp_path):
        yaml_content = {
            "mode": "paper",
            "polling_interval_seconds": 12,
            "max_tracked_traders": 3,
            "copy_trading": {"size_multiplier": 0.3},
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(yaml_content))

        config = load_config(config_path=str(config_file))
        assert config.mode == "paper"
        assert config.polling_interval_seconds == 12
        assert config.max_tracked_traders == 3
        assert config.copy_trading.size_multiplier == 0.3

    def test_load_config_env_override(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"mode": "paper"}))

        monkeypatch.setenv("BANKROLL", "25000")
        monkeypatch.setenv("POLY_PRIVATE_KEY", "0xdeadbeef")

        config = load_config(config_path=str(config_file))
        assert config.bankroll == 25000
        assert config.private_key == "0xdeadbeef"

    def test_load_config_missing_yaml(self, tmp_path):
        config = load_config(config_path=str(tmp_path / "nonexistent.yaml"))
        assert config.mode == "paper"
        assert config.bankroll == 500

    def test_load_config_invalid_bankroll_raises(self, tmp_path, monkeypatch):
        # A non-numeric BANKROLL env value must fail fast with a typed,
        # catchable ConfigError — not a SystemExit, and not a raw ValueError
        # deep in load_config. This keeps load_config importable/testable.
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"mode": "paper"}))
        monkeypatch.setenv("BANKROLL", "not-a-number")
        with pytest.raises(ConfigError, match="BANKROLL must be a number"):
            load_config(config_path=str(config_file))

    def test_load_config_negative_bankroll_raises(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"mode": "paper"}))
        monkeypatch.setenv("BANKROLL", "-100")
        with pytest.raises(ConfigError, match="must be positive"):
            load_config(config_path=str(config_file))

    def test_load_config_live_mode_requires_private_key(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"mode": "live"}))
        monkeypatch.delenv("POLY_PRIVATE_KEY", raising=False)
        with pytest.raises(ConfigError, match="POLY_PRIVATE_KEY required"):
            load_config(config_path=str(config_file))

    def test_signature_type_and_funder_default_unset(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"mode": "paper"}))
        monkeypatch.delenv("POLY_SIGNATURE_TYPE", raising=False)
        monkeypatch.delenv("POLY_FUNDER", raising=False)
        config = load_config(config_path=str(config_file))
        assert config.signature_type == 0
        assert config.funder == ""

    def test_signature_type_and_funder_env_override(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"mode": "paper"}))
        monkeypatch.setenv("POLY_SIGNATURE_TYPE", "3")
        monkeypatch.setenv("POLY_FUNDER", "0xfunder")
        config = load_config(config_path=str(config_file))
        assert config.signature_type == 3
        assert config.funder == "0xfunder"

    def test_invalid_signature_type_raises(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"mode": "paper"}))
        monkeypatch.setenv("POLY_SIGNATURE_TYPE", "not-a-number")
        with pytest.raises(ConfigError, match="POLY_SIGNATURE_TYPE must be an integer"):
            load_config(config_path=str(config_file))

    def test_live_mode_signature_type_3_requires_funder(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"mode": "live"}))
        monkeypatch.setenv("POLY_PRIVATE_KEY", "0xdeadbeef")
        monkeypatch.setenv("POLY_SIGNATURE_TYPE", "3")
        monkeypatch.delenv("POLY_FUNDER", raising=False)
        with pytest.raises(ConfigError, match="POLY_FUNDER required"):
            load_config(config_path=str(config_file))

    def test_live_mode_signature_type_3_with_funder_succeeds(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"mode": "live"}))
        monkeypatch.setenv("POLY_PRIVATE_KEY", "0xdeadbeef")
        monkeypatch.setenv("POLY_SIGNATURE_TYPE", "3")
        monkeypatch.setenv("POLY_FUNDER", "0xfunder")
        config = load_config(config_path=str(config_file))
        assert config.signature_type == 3
        assert config.funder == "0xfunder"

    def test_config_error_is_value_error(self):
        # Subclassing ValueError keeps any existing `except ValueError` callers
        # working while allowing precise `except ConfigError` handling.
        assert issubclass(ConfigError, ValueError)

    def test_trader_selection_v2_fields(self):
        config = AppConfig()
        assert config.trader_selection.min_pnl == 10000
        assert config.trader_selection.min_win_rate == 0.55
        assert config.trader_selection.min_trades == 150  # M12: raised from 50
        assert config.trader_selection.half_life_days == 7.0  # L4: faster recency decay
        assert config.trader_selection.max_top_traders == 5
        # Chunk 2 (H14/H15/H16) trader-selection quality knobs
        assert config.trader_selection.sharpe_cap == 3.0
        assert config.trader_selection.sharpe_shrink_min_trades == 20
        assert config.trader_selection.min_expectancy == 0.01
        assert config.trader_selection.recent_window_days == 30

    def test_chunk3_risk_refinement_fields(self):
        # Chunk 3 (M9/L5) risk-refinement knobs
        config = AppConfig()
        assert config.copy_trading.max_positions_per_token == 3  # M9
        assert config.risk_management.low_entry_threshold == 0.20  # L5
        assert config.risk_management.low_entry_tp_fraction == 0.25  # L5

    def test_chunk4_execution_quality_fields(self):
        # Chunk 4 (H17/M1/M5) execution-quality knobs
        config = AppConfig()
        assert config.poll_jitter_seconds == 2.0  # H17
        assert config.copy_trading.revalidate_edge_before_order is True  # M1
        assert config.copy_trading.entry_order_type == "FOK"  # M5
        assert config.copy_trading.exit_order_type == "FAK"  # M5

    def test_invalid_order_type_rejected(self):
        # M5: order types are typed as the CLOB's Literal set; bad values are rejected.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AppConfig(copy_trading={"entry_order_type": "BOGUS"})

    def test_chunk6_kelly_execution_fields(self):
        # Chunk 6 (H18/M3/M4/M11/M12) knobs and their new defaults.
        config = AppConfig()
        assert config.copy_trading.kelly_min_trades == 50  # M3
        assert config.copy_trading.kelly_edge_shrink == 0.5  # H18
        assert config.copy_trading.kelly_max_edge == 0.20  # H18
        assert config.copy_trading.tracker_prior_decay_enabled is True  # M4
        assert config.copy_trading.slippage_size_threshold_usdc == 500.0  # M11
        assert config.copy_trading.slippage_size_coeff == 0.5  # M11
        assert config.copy_trading.slippage_size_max_mult == 3.0  # M11
        assert config.copy_trading.live_order_timeout_seconds == 8.0  # M12
        assert config.copy_trading.live_retry_slippage_pct == 0.02  # M12
        assert config.copy_trading.live_order_max_retries == 1  # M12

    def test_slippage_parity_validator_raises_when_paper_exceeds_live(self):
        # PR2: paper_fill_slippage_pct > max_live_slippage_pct must fail; otherwise
        # paper simulation is penalised more than live, making back-test PnL optimistic.
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="max_live_slippage_pct must be"):
            AppConfig(copy_trading={"paper_fill_slippage_pct": 0.02, "max_live_slippage_pct": 0.01})

    def test_slippage_parity_validator_passes_when_equal(self):
        # Exact parity is valid — paper and live share identical slippage budgets.
        config = AppConfig(copy_trading={"paper_fill_slippage_pct": 0.01, "max_live_slippage_pct": 0.01})
        assert config.copy_trading.paper_fill_slippage_pct == pytest.approx(0.01)
        assert config.copy_trading.max_live_slippage_pct == pytest.approx(0.01)

    def test_live_retry_slippage_validator(self):
        # M12: retry slippage must be >= base cap and <= 0.05 ceiling; retries in {0,1}.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AppConfig(copy_trading={"max_live_slippage_pct": 0.03, "live_retry_slippage_pct": 0.01})
        with pytest.raises(ValidationError):
            AppConfig(copy_trading={"live_retry_slippage_pct": 0.10})  # > 0.05 ceiling
        with pytest.raises(ValidationError):
            AppConfig(copy_trading={"live_order_max_retries": 2})

    def test_taker_fee_rate_supports_new_key(self):
        config = AppConfig(copy_trading={"paper_taker_fee_rate": 0.03})
        assert config.copy_trading.taker_fee_rate() == pytest.approx(0.03)

    def test_taker_fee_rate_supports_legacy_alias(self):
        config = AppConfig(copy_trading={"paper_taker_fee_pct": 0.03})
        assert config.copy_trading.taker_fee_rate() == pytest.approx(0.03)


class TestShippedConfigMatchesCodeDefaults:
    """config.yaml has repeatedly drifted from config.py's post-fix defaults
    (trailing_stop_fraction, half_life_days, min_trades all silently reverted
    to pre-fix values because nothing checked the shipped file against the
    code). Load the actual repo-root config.yaml and assert the intentionally
    "fixed" fields still hold their fixed values, so a future edit to either
    file that reintroduces drift fails CI instead of shipping silently.
    """

    @pytest.fixture
    def shipped_config(self):
        return load_config(config_path="config.yaml")

    def test_trailing_stop_fraction_matches_code_default(self, shipped_config):
        assert (
            shipped_config.risk_management.trailing_stop_fraction == AppConfig().risk_management.trailing_stop_fraction
        )

    def test_half_life_days_matches_code_default(self, shipped_config):
        assert shipped_config.trader_selection.half_life_days == AppConfig().trader_selection.half_life_days

    def test_min_trades_matches_code_default(self, shipped_config):
        assert shipped_config.trader_selection.min_trades == AppConfig().trader_selection.min_trades

    def test_shipped_config_uses_canonical_taker_fee_rate_key(self, shipped_config):
        assert shipped_config.copy_trading.paper_taker_fee_pct is None
        assert shipped_config.copy_trading.paper_taker_fee_rate == AppConfig().copy_trading.paper_taker_fee_rate
