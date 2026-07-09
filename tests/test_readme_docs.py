"""README drift checks for operator-facing code facts."""

from __future__ import annotations

from pathlib import Path


README = Path(__file__).resolve().parents[1] / "README.md"


class TestReadmeCodeFacts:
    def test_readme_uses_current_scoring_shape(self):
        text = README.read_text(encoding="utf-8")

        assert "Sharpe ratio \u00d7 Consistency \u00d7 Recency" not in text
        assert "Sharpe_proxy \u00d7 Consistency \u00d7 Recency_weight" not in text
        assert "(4.0 * Sharpe_proxy + 3.5 * Consistency + 2.5 * Recency_weight) / 10" in text

    def test_readme_uses_current_kelly_and_trailing_names(self):
        text = README.read_text(encoding="utf-8")

        assert "`kelly_fraction_multiplier`" in text
        assert "`kelly_fraction` |" not in text
        assert "peak-to-SL gap" not in text
        assert "run-up from entry" in text

    def test_readme_uses_declared_metric_names(self):
        text = README.read_text(encoding="utf-8")

        assert "polymarket_bankroll_usdc" not in text
        assert "polymarket_orders_placed_total" not in text
        for metric in (
            "copybot_bankroll_usd",
            "copybot_daily_pnl_usd",
            "copybot_open_positions",
            "copybot_copies_skipped_total",
            "copybot_exits_total",
        ):
            assert metric in text
