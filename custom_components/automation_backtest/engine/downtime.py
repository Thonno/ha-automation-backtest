"""Turn recorded start/stop events into Home Assistant downtime windows."""

from __future__ import annotations

from datetime import datetime

STOP, START, STARTED = "homeassistant_stop", "homeassistant_start", "homeassistant_started"


def windows_from_events(events: list[tuple[str, datetime]]) -> list[tuple[datetime, datetime]]:
    """Turn an ordered list of (event_type, time) into (down, up) intervals."""
    windows: list[tuple[datetime, datetime]] = []
    down: datetime | None = None
    last_start: datetime | None = None
    for event_type, when in events:
        if event_type == STOP:
            if down is None:
                down = when
        elif event_type == START:
            last_start = when
            if down is None:  # crash or power loss: no stop event was written
                down = when
        elif event_type == STARTED and down is not None:
            windows.append((down, when))
            down, last_start = None, None
    if down is not None and last_start is not None:
        windows.append((down, last_start))
    return windows
