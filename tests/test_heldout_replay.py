"""Regression tests for the paper-only R1 held-out replay evaluator."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from polymarket_copier.replay import build_heldout_report


FIXTURE = Path(__file__).parent / "fixtures" / "r1_heldout_v1.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestHeldoutReplay:
    def test_v1_fixture_reports_selection_costs_and_uncertainty(self):
        """R1 must not turn an unselected or unknown event into measured PnL."""
        report = build_heldout_report(_fixture())

        assert report.selected_wallets == ["0xalpha"]
        assert report.decision_counts == {
            "filled": 1,
            "partial_fill": 1,
            "no_fill": 1,
            "skipped": 2,
            "unknown_fill": 1,
        }
        assert report.skip_reasons == {"not_selected": 1, "stale_trade": 1}
        assert report.unknown_fills == 1
        assert report.net_pnl_usdc == pytest.approx(25.454230)
        assert report.net_expectancy_usdc == pytest.approx(5.090846)

    def test_rejects_holdout_event_at_or_before_training_cutoff(self):
        """The report must fail rather than silently score an event with look-ahead."""
        fixture = _fixture()
        fixture["heldout"][0]["source_timestamp"] = fixture["training_end_timestamp"]

        with pytest.raises(ValueError, match="strictly after training_end_timestamp"):
            build_heldout_report(fixture)

    def test_module_entrypoint_renders_the_fixture_report(self):
        """The documented paper-only command must execute the same evaluator."""
        result = subprocess.run(
            [sys.executable, "-m", "polymarket_copier.replay", str(FIXTURE)],
            check=True,
            capture_output=True,
            text=True,
        )

        rendered = json.loads(result.stdout)
        assert rendered["unknown_fills"] == 1
        assert rendered["skip_reasons"] == {"not_selected": 1, "stale_trade": 1}
