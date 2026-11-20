"""Find when Home Assistant was not running automations (restarts, crashes).

Automations only attach their triggers on `homeassistant_started`, so anything
between `homeassistant_stop` (or `homeassistant_start` after a crash) and the
next `homeassistant_started` must not fire in the simulation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

from .engine.downtime import STARTED, START, STOP, windows_from_events


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
