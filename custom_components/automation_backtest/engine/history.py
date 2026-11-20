"""Historical state storage and the live 'simulated state machine'."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable


@dataclass(frozen=True)
class StateSnapshot:
    """A recorded state, shaped like a (very small) Home Assistant State."""

    entity_id: str
    state: str
    attributes: dict[str, Any] = field(default_factory=dict)
    last_changed: datetime | None = None
    last_updated: datetime | None = None

    @property
    def domain(self) -> str:
        return self.entity_id.split(".", 1)[0]

    @property
    def object_id(self) -> str:
        return self.entity_id.split(".", 1)[1]

    @property
    def name(self) -> str:
        return str(self.attributes.get("friendly_name", self.object_id))

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "state": self.state,
            "attributes": dict(self.attributes),
            "last_changed": self.last_changed.isoformat() if self.last_changed else None,
        }


@dataclass(frozen=True)
class StateChange:
    """One change event: old -> new for an entity at a given time."""

    time: datetime
    entity_id: str
    old: StateSnapshot | None
    new: StateSnapshot | None


class HistoryStore:
    """Holds recorded states per entity, sorted by last_updated."""

    def __init__(self) -> None:
        self._states: dict[str, list[StateSnapshot]] = {}
        self._times: dict[str, list[datetime]] = {}

    def add(self, snapshot: StateSnapshot) -> None:
        when = snapshot.last_updated or snapshot.last_changed
        if when is None:
            raise ValueError(f"Snapshot for {snapshot.entity_id} has no timestamp")
        if snapshot.last_updated is None or snapshot.last_changed is None:
            snapshot = StateSnapshot(
                snapshot.entity_id,
                snapshot.state,
                snapshot.attributes,
                snapshot.last_changed or when,
                snapshot.last_updated or when,
            )
        times = self._times.setdefault(snapshot.entity_id, [])
        states = self._states.setdefault(snapshot.entity_id, [])
        idx = bisect.bisect_right(times, when)
        times.insert(idx, when)
        states.insert(idx, snapshot)

    def add_many(self, snapshots: Iterable[StateSnapshot]) -> None:
        for snap in snapshots:
            self.add(snap)

    @property
    def entity_ids(self) -> list[str]:
        return sorted(self._states)

    def state_at(self, entity_id: str, when: datetime) -> StateSnapshot | None:
        """Last known state at or before `when`."""
        times = self._times.get(entity_id)
        if not times:
            return None
        idx = bisect.bisect_right(times, when) - 1
        if idx < 0:
            return None
        return self._states[entity_id][idx]

    def changes_between(self, start: datetime, end: datetime) -> list[StateChange]:
        """All changes with start < time <= end, ordered by time (stable per entity)."""
        out: list[StateChange] = []
        for entity_id, times in self._times.items():
            states = self._states[entity_id]
            lo = bisect.bisect_right(times, start)
            hi = bisect.bisect_right(times, end)
            prev = states[lo - 1] if lo > 0 else None
            for i in range(lo, hi):
                cur = states[i]
                if prev is not None and _same(prev, cur):
                    continue
                out.append(StateChange(times[i], entity_id, prev, cur))
                prev = cur
        out.sort(key=lambda c: c.time)
        return out


def _same(a: StateSnapshot, b: StateSnapshot) -> bool:
    return a.state == b.state and a.attributes == b.attributes


class SimulatedStates:
    """The state machine as it looked at the current point of the replay."""

    def __init__(self, store: HistoryStore, start: datetime) -> None:
        self._current: dict[str, StateSnapshot] = {}
        for entity_id in store.entity_ids:
            snap = store.state_at(entity_id, start)
            if snap is not None:
                self._current[entity_id] = snap

    def get(self, entity_id: str) -> StateSnapshot | None:
        return self._current.get(entity_id)

    def apply(self, change: StateChange) -> None:
        if change.new is None:
            self._current.pop(change.entity_id, None)
        else:
            self._current[change.entity_id] = change.new

    def all(self, domain: str | None = None) -> list[StateSnapshot]:
        return [
            s for s in self._current.values() if domain is None or s.domain == domain
        ]
