"""Small parsing helpers shared by the engine (no Home Assistant imports)."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any


class UnsupportedFeature(Exception):
    """Raised when a trigger/condition/template feature cannot be simulated."""


def as_list(value: Any) -> list:
    """Return value as a list (None -> [])."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def norm_state(value: Any) -> str:
    """YAML 1.1 turns unquoted on/off into booleans; HA users mean states."""
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def parse_duration(value: Any) -> timedelta | None:
    """Parse HA-style durations: seconds, 'HH:MM[:SS]', or {hours: .., minutes: ..}."""
    if value is None:
        return None
    if isinstance(value, timedelta):
        return value
    if isinstance(value, (int, float)):
        return timedelta(seconds=value)
    if isinstance(value, dict):
        keys = {"days", "hours", "minutes", "seconds", "milliseconds"}
        unknown = set(value) - keys
        if unknown:
            raise UnsupportedFeature(f"Unknown duration keys: {sorted(unknown)}")
        return timedelta(**{k: float(v) for k, v in value.items()})
    if isinstance(value, str):
        text = value.strip()
        if "{{" in text:
            raise UnsupportedFeature("Templated durations are not supported yet")
        sign = -1 if text.startswith("-") else 1
        text = text.lstrip("-")
        parts = text.split(":")
        try:
            if len(parts) == 1:
                return sign * timedelta(seconds=float(parts[0]))
            if len(parts) == 2:
                return sign * timedelta(hours=int(parts[0]), minutes=float(parts[1]))
            if len(parts) == 3:
                return sign * timedelta(
                    hours=int(parts[0]), minutes=int(parts[1]), seconds=float(parts[2])
                )
        except ValueError as err:
            raise UnsupportedFeature(f"Invalid duration: {value!r}") from err
    raise UnsupportedFeature(f"Invalid duration: {value!r}")


def parse_time_of_day(value: str) -> time:
    """Parse 'HH:MM' or 'HH:MM:SS' into a time."""
    parts = [int(p) for p in str(value).strip().split(":")]
    while len(parts) < 3:
        parts.append(0)
    return time(parts[0], parts[1], parts[2])


def to_float(value: Any) -> float | None:
    """Convert a state value to float, or None when not numeric."""
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:  # NaN
        return None
    return result


def iso(dt: datetime) -> str:
    """ISO string without microseconds."""
    return dt.replace(microsecond=0).isoformat()
