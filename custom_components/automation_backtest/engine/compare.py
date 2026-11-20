"""Diff two backtests of the same window (e.g. current vs. edited automation)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .simulator import EXECUTED, BacktestResult, Run
from .util import iso

TOLERANCE = timedelta(seconds=1)
SHIFT_WINDOW = timedelta(hours=6)


def _origin(run: Run) -> str:
    """The event that caused the run, without the 'held for' suffix of for: triggers."""
    return run.description.split(" (held ")[0]


def _executed(result: BacktestResult) -> list[Run]:
    return [r for r in result.runs if r.status == EXECUTED]


def compare(a: BacktestResult, b: BacktestResult) -> dict[str, Any]:
    """Which executions happen only in A, only in B, in both, or in both but at another time."""
    tz = a.tz
    runs_a, runs_b = _executed(a), _executed(b)
    used_b: set[int] = set()
    both, only_a = [], []
    for run in runs_a:
        match = next(
            (i for i, other in enumerate(runs_b)
             if i not in used_b and abs(other.time - run.time) <= TOLERANCE),
            None,
        )
        if match is None:
            only_a.append(run)
        else:
            used_b.add(match)
            both.append(run)
    only_b = [r for i, r in enumerate(runs_b) if i not in used_b]

    # Same originating event, different time (e.g. a changed `for:`): report as shifted.
    shifted: list[tuple[Run, Run]] = []
    remaining_b = list(only_b)
    for run in list(only_a):
        candidates = [
            other for other in remaining_b
            if _origin(other) == _origin(run) and abs(other.time - run.time) <= SHIFT_WINDOW
        ]
        if candidates:
            best = min(candidates, key=lambda o: abs(o.time - run.time))
            remaining_b.remove(best)
            only_a.remove(run)
            shifted.append((run, best))
    only_b = remaining_b

    def brief(run: Run) -> dict[str, Any]:
        return {"time": iso(run.time.astimezone(tz)), "trigger": run.description}

    return {
        "summary": {
            "a_executed": len(runs_a),
            "b_executed": len(runs_b),
            "both": len(both),
            "only_a": len(only_a),
            "only_b": len(only_b),
            "shifted": len(shifted),
        },
        "only_a": [brief(r) for r in only_a],
        "only_b": [brief(r) for r in only_b],
        "shifted": [
            {
                "a_time": iso(ra.time.astimezone(tz)),
                "b_time": iso(rb.time.astimezone(tz)),
                "delta_seconds": int((rb.time - ra.time).total_seconds()),
                "trigger": _origin(ra),
            }
            for ra, rb in shifted
        ],
    }
