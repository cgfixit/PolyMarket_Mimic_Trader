"""Regression tests for the paper decision telemetry report."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


_SCRIPT = Path(__file__).parents[1] / "scripts" / "paper_metrics_report.py"


def test_report_summarizes_paper_decisions_and_ignores_other_records(tmp_path):
    log = tmp_path / "trades.log"
    records = [
        {"data": {"event": "position_opened", "mode": "paper", "wall_age_seconds": 1.0}},
        {"data": {"event": "copy_skipped", "mode": "paper", "reason": "stale_trade", "wall_age_seconds": 12.0}},
        {"data": {"event": "circuit_breaker_tripped", "mode": "paper", "wall_age_seconds": 2.0}},
        {"data": {"event": "copy_skipped", "mode": "live", "reason": "must_ignore", "wall_age_seconds": 99}},
        {"message": "not telemetry"},
    ]
    log.write_text("\n".join(json.dumps(record) for record in records) + "\nnot json\n")

    result = subprocess.run(
        [sys.executable, str(_SCRIPT), str(log)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Decisions: 2 | opened: 1 | skipped: 1 | breaker trips: 1" in result.stdout
    assert "<= 12s: 3/3 (100.0%)" in result.stdout
    assert "stale_trade: 1" in result.stdout
    assert "must_ignore" not in result.stdout
    assert "Ignored malformed JSON lines: 1" in result.stdout
