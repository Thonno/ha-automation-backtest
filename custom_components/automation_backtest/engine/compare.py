"""Diff two backtests of the same window (e.g. current vs. edited automation)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .simulator import EXECUTED, BacktestResult, Run
from .util import iso

TOLERANCE = timedelta(seconds=1)


def _executed(result: BacktestResult) -> list[Run]:
    return [r for r in result.runs if r.status == EXECUTED]


def compare(a: BacktestResult, b: BacktestResult) -> dict[str, Any]:
    """Which executions happen only in A, only in B, or in both."""
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

    def brief(run: Run) -> dict[str, Any]:
        return {"time": iso(run.time.astimezone(tz)), "trigger": run.description}

    return {
        "summary": {
            "a_executed": len(runs_a),
            "b_executed": len(runs_b),
            "both": len(both),
            "only_a": len(only_a),
            "only_b": len(only_b),
        },
        "only_a": [brief(r) for r in only_a],
        "only_b": [brief(r) for r in only_b],
    }
