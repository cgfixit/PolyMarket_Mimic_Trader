"""Summarize paper-mode decision telemetry from structured JSON logs."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
from typing import Any, Iterable

_WALL_AGE_BUCKETS = (1, 3, 6, 12, 30, 60)


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _percentile(values: list[float], percentile: float) -> float:
    """Return the nearest-rank percentile from a non-empty list."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percentile) - 1)]


def summarize(log_paths: Iterable[Path]) -> tuple[dict[str, Any], int]:
    """Collect paper decision events, ignoring malformed or non-paper records."""
    opened = skipped = breaker_trips = malformed_lines = 0
    skip_reasons: Counter[str] = Counter()
    wall_ages: list[float] = []

    for path in log_paths:
        with path.open(encoding="utf-8") as log_file:
            for line in log_file:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    malformed_lines += 1
                    continue
                data = record.get("data") if isinstance(record, dict) else None
                if not isinstance(data, dict) or data.get("mode") != "paper":
                    continue

                event = data.get("event")
                if event == "position_opened":
                    opened += 1
                elif event == "copy_skipped":
                    skipped += 1
                    reason = data.get("reason")
                    if isinstance(reason, str):
                        skip_reasons[reason] += 1
                elif event == "circuit_breaker_tripped":
                    breaker_trips += 1
                else:
                    continue

                wall_age = _number(data.get("wall_age_seconds"))
                if wall_age is not None:
                    wall_ages.append(wall_age)

    return {
        "opened": opened,
        "skipped": skipped,
        "breaker_trips": breaker_trips,
        "skip_reasons": skip_reasons,
        "wall_ages": wall_ages,
    }, malformed_lines


def render(summary: dict[str, Any], malformed_lines: int) -> str:
    """Render a compact, human-readable paper telemetry report."""
    opened = summary["opened"]
    skipped = summary["skipped"]
    decisions = opened + skipped
    wall_ages: list[float] = summary["wall_ages"]
    lines = [
        "Paper decision telemetry",
        "Synthetic paper fills are not execution-adjusted expectancy.",
        f"Decisions: {decisions} | opened: {opened} | skipped: {skipped} | breaker trips: {summary['breaker_trips']}",
    ]

    if wall_ages:
        lines.extend(("Wall-age CDF:",))
        for bucket in _WALL_AGE_BUCKETS:
            count = sum(age <= bucket for age in wall_ages)
            lines.append(f"  <= {bucket:>2}s: {count}/{len(wall_ages)} ({count / len(wall_ages):.1%})")
        lines.append(
            f"  p50/p95/max: {_percentile(wall_ages, 0.50):.3f}s / "
            f"{_percentile(wall_ages, 0.95):.3f}s / {max(wall_ages):.3f}s"
        )
    else:
        lines.append("Wall-age CDF: no paper decision records with wall_age_seconds.")

    reasons: Counter[str] = summary["skip_reasons"]
    if reasons:
        lines.append("Skip reasons:")
        lines.extend(f"  {reason}: {count}" for reason, count in reasons.most_common())
    if malformed_lines:
        lines.append(f"Ignored malformed JSON lines: {malformed_lines}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path, help="Structured JSON log file(s) from paper-mode runs.")
    args = parser.parse_args()
    summary, malformed_lines = summarize(args.logs)
    print(render(summary, malformed_lines))


if __name__ == "__main__":
    main()
