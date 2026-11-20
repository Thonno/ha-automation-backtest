"""ha-automation-backtest simulation engine.

Pure Python (only depends on jinja2), so it can be unit-tested without
Home Assistant installed.
"""

from .compare import compare
from .history import HistoryStore, StateSnapshot
from .references import extract_entities
from .simulator import BLOCKED, EXECUTED, UNCERTAIN, BacktestResult, backtest

__all__ = [
    "BLOCKED",
    "EXECUTED",
    "UNCERTAIN",
    "BacktestResult",
    "HistoryStore",
    "StateSnapshot",
    "backtest",
    "compare",
    "extract_entities",
]
