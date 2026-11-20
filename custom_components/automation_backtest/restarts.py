"""Find when Home Assistant was not running automations (restarts, crashes).

Automations only attach their triggers on `homeassistant_started`, so anything
between `homeassistant_stop` (or `homeassistant_start` after a crash) and the
next `homeassistant_started` must not fire in the simulation.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

from .engine.downtime import STARTED, START, STOP, windows_from_events
from .engine.triggers import RecordedEvent

MAX_EVENTS = 50_000


async def async_get_events(
    hass: HomeAssistant, event_types: set[str], start: datetime, end: datetime
) -> list[RecordedEvent] | None:
    """Recorded events of the given types in [start, end], with their data."""
    from homeassistant.components.recorder import get_instance

    def _query() -> list[RecordedEvent]:
        from sqlalchemy import select

        from homeassistant.components.recorder.db_schema import EventData, Events, EventTypes
        from homeassistant.components.recorder.util import session_scope

        stmt = (
            select(EventTypes.event_type, Events.time_fired_ts, EventData.shared_data)
            .join(EventTypes, Events.event_type_id == EventTypes.event_type_id)
            .outerjoin(EventData, Events.data_id == EventData.data_id)
            .where(EventTypes.event_type.in_(sorted(event_types)))
            .where(Events.time_fired_ts > start.timestamp())
            .where(Events.time_fired_ts <= end.timestamp())
            .order_by(Events.time_fired_ts)
            .limit(MAX_EVENTS)
        )
        out: list[RecordedEvent] = []
        with session_scope(hass=hass, read_only=True) as session:
            for etype, ts, raw in session.execute(stmt).all():
                try:
                    data = json.loads(raw) if raw else {}
                except ValueError:
                    data = {}
                out.append(RecordedEvent(datetime.fromtimestamp(ts, tz=timezone.utc), etype, data))
        return out

    try:
        return await get_instance(hass).async_add_executor_job(_query)
    except Exception:  # noqa: BLE001 - schema differences must never break a backtest
        _LOGGER.debug("Could not read events from the recorder", exc_info=True)
        return None


async def async_get_downtime(
    hass: HomeAssistant, start: datetime, end: datetime
) -> list[tuple[datetime, datetime]] | None:
    """Downtime windows overlapping [start, end], or None if they can't be read."""
    from homeassistant.components.recorder import get_instance

    def _query() -> list[tuple[str, datetime]]:
        from sqlalchemy import select

        from homeassistant.components.recorder.db_schema import Events, EventTypes
        from homeassistant.components.recorder.util import session_scope

        lookback = (start - timedelta(days=1)).timestamp()
        stmt = (
            select(EventTypes.event_type, Events.time_fired_ts)
            .join(EventTypes, Events.event_type_id == EventTypes.event_type_id)
            .where(EventTypes.event_type.in_([STOP, START, STARTED]))
            .where(Events.time_fired_ts >= lookback)
            .where(Events.time_fired_ts <= end.timestamp())
            .order_by(Events.time_fired_ts)
        )
        with session_scope(hass=hass, read_only=True) as session:
            return [
                (row[0], datetime.fromtimestamp(row[1], tz=timezone.utc))
                for row in session.execute(stmt).all()
            ]

    try:
        events = await get_instance(hass).async_add_executor_job(_query)
    except Exception:  # noqa: BLE001 - schema differences must never break a backtest
        _LOGGER.debug("Could not read restart events from the recorder", exc_info=True)
        return None
    return [(a, b) for a, b in windows_from_events(events) if b > start and a <= end]
