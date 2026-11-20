"""Sun events for triggers and conditions.

Inside Home Assistant the adapter precomputes the events with HA's own astral
helpers (so times match HA to the second) and passes them in as a table.
The NOAA fallback below is only used by the stand-alone test-suite.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Callable

# event name -> datetime (aware) or None (polar day/night)
SunProvider = Callable[[str, date], "datetime | None"]

EVENTS = ("sunrise", "sunset", "dawn", "dusk", "noon", "midnight")


def table_provider(table: dict[str, dict[str, datetime | None]]) -> SunProvider:
    """Provider backed by {iso_date: {event: datetime}} precomputed by the adapter."""

    def get(event: str, day: date) -> datetime | None:
        return table.get(day.isoformat(), {}).get(event)

    return get


def noaa_provider(latitude: float, longitude: float, tz: tzinfo, elevation: float = 0.0) -> SunProvider:
    """Sunrise equation (accurate to about a minute). Test fallback only."""

    def get(event: str, day: date) -> datetime | None:
        noon_local = datetime(day.year, day.month, day.day, 12, tzinfo=tz)
        jd = noon_local.astimezone(timezone.utc).timestamp() / 86400.0 + 2440587.5
        n = math.ceil(jd - 2451545.0 + 0.0008)
        j_star = n - longitude / 360.0
        m = math.radians((357.5291 + 0.98560028 * j_star) % 360)
        c = 1.9148 * math.sin(m) + 0.0200 * math.sin(2 * m) + 0.0003 * math.sin(3 * m)
        lam = math.radians((math.degrees(m) + c + 180 + 102.9372) % 360)
        transit = 2451545.0 + j_star + 0.0053 * math.sin(m) - 0.0069 * math.sin(2 * lam)
        if event in ("noon", "midnight"):
            jd_event = transit if event == "noon" else transit - 0.5
        else:
            decl = math.asin(math.sin(lam) * math.sin(math.radians(23.4397)))
            depression = 6.0 if event in ("dawn", "dusk") else 0.833 + 2.076 * math.sqrt(max(elevation, 0)) / 60
            lat = math.radians(latitude)
            cos_h = (math.sin(math.radians(-depression)) - math.sin(lat) * math.sin(decl)) / (
                math.cos(lat) * math.cos(decl)
            )
            if not -1 <= cos_h <= 1:
                return None
            hour_angle = math.degrees(math.acos(cos_h)) / 360.0
            jd_event = transit - hour_angle if event in ("sunrise", "dawn") else transit + hour_angle
        ts = (jd_event - 2440587.5) * 86400.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)

    return get


def days_between(start: datetime, end: datetime, tz: tzinfo, pad: int = 1):
    day = start.astimezone(tz).date() - timedelta(days=pad)
    last = end.astimezone(tz).date() + timedelta(days=pad)
    while day <= last:
        yield day
        day += timedelta(days=1)
