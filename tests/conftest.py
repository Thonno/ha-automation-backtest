"""Make the engine importable without Home Assistant installed."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "automation_backtest"))

from engine import HistoryStore, StateSnapshot  # noqa: E402

UTC = timezone.utc


def ts(text: str) -> datetime:
    """'2026-11-10 07:00' -> aware UTC datetime."""
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


@pytest.fixture
def make_history():
    def _make(rows):
        """rows: (entity_id, time, state[, attributes])."""
        store = HistoryStore()
        last_state: dict[str, tuple[str, datetime]] = {}
        for row in sorted(rows, key=lambda r: ts(r[1])):
            entity_id, when, state = row[0], ts(row[1]), row[2]
            attrs = row[3] if len(row) > 3 else {}
            prev = last_state.get(entity_id)
            changed = when if prev is None or prev[0] != state else prev[1]
            last_state[entity_id] = (state, changed)
            store.add(StateSnapshot(entity_id, state, attrs, changed, when))
        return store

    return _make
