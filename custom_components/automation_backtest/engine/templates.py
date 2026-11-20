"""Render HA-style Jinja templates against the *historical* state machine.

Only a well-defined subset of Home Assistant's template API is implemented.
Anything else raises UnsupportedFeature, so the run is reported as
'uncertain' instead of silently giving a wrong answer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from jinja2 import StrictUndefined, UndefinedError
from jinja2.sandbox import ImmutableSandboxedEnvironment

from .history import SimulatedStates, StateSnapshot
from .util import UnsupportedFeature, to_float

_NO_DEFAULT = object()
# Attributes the jinja sandbox probes for; must not resolve to entity lookups.
_SANDBOX_PROBES = {"unsafe_callable", "alters_data"}


class _DomainStates:
    def __init__(self, states: SimulatedStates, domain: str) -> None:
        self._states = states
        self._domain = domain

    def __getattr__(self, object_id: str) -> StateSnapshot | None:
        if object_id.startswith("_") or object_id in _SANDBOX_PROBES:
            raise AttributeError(object_id)
        return self._states.get(f"{self._domain}.{object_id}")

    def __iter__(self):
        return iter(sorted(self._states.all(self._domain), key=lambda s: s.entity_id))


class _StatesProxy:
    """Supports both states('light.x') and states.light.x.state."""

    def __init__(self, states: SimulatedStates) -> None:
        self._states = states

    def __call__(self, entity_id: str, rounded: bool = False, with_unit: bool = False) -> str:
        snap = self._states.get(entity_id)
        return snap.state if snap else "unknown"

    def __getattr__(self, domain: str) -> _DomainStates:
        if domain.startswith("_") or domain in _SANDBOX_PROBES:
            raise AttributeError(domain)
        return _DomainStates(self._states, domain)

    def __iter__(self):
        return iter(sorted(self._states.all(), key=lambda s: s.entity_id))


def _num(cast: Callable[[Any], Any]):
    def convert(value: Any, default: Any = _NO_DEFAULT) -> Any:
        try:
            return cast(float(value)) if cast is int else cast(value)
        except (TypeError, ValueError):
            if default is _NO_DEFAULT:
                raise UnsupportedFeature(
                    f"Template could not convert {value!r} and no default was given"
                ) from None
            return default

    return convert


def _bool(value: Any, default: Any = _NO_DEFAULT) -> Any:
    text = str(value).strip().lower()
    if text in ("true", "on", "yes", "1", "enable"):
        return True
    if text in ("false", "off", "no", "0", "disable", "none"):
        return False
    if default is _NO_DEFAULT:
        raise UnsupportedFeature(f"Template could not convert {value!r} to bool")
    return default


def _as_timestamp_filter(value: Any, default: Any = _NO_DEFAULT) -> Any:
    if isinstance(value, datetime):
        return value.timestamp()
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        if default is _NO_DEFAULT:
            raise UnsupportedFeature(f"as_timestamp could not parse {value!r}") from None
        return default


class TemplateRenderer:
    """Renders templates for one simulated instant."""

    def __init__(self) -> None:
        self._env = ImmutableSandboxedEnvironment(undefined=StrictUndefined)
        self._env.filters.update(
            {
                "float": _num(float),
                "int": _num(int),
                "bool": _bool,
                "as_timestamp": _as_timestamp_filter,
                "is_defined": lambda v: v,
            }
        )
        self._cache: dict[str, Any] = {}

    def render(
        self,
        template: str,
        states: SimulatedStates,
        now: datetime,
        variables: dict[str, Any] | None = None,
    ) -> str:
        compiled = self._cache.get(template)
        if compiled is None:
            try:
                compiled = self._env.from_string(template)
            except Exception as err:  # noqa: BLE001 - jinja syntax errors
                raise UnsupportedFeature(f"Template error: {err}") from err
            self._cache[template] = compiled

        def state_attr(entity_id: str, name: str) -> Any:
            snap = states.get(entity_id)
            return snap.attributes.get(name) if snap else None

        def is_state(entity_id: str, value: Any) -> bool:
            snap = states.get(entity_id)
            if snap is None:
                return False
            if isinstance(value, (list, tuple)):
                return snap.state in value
            return snap.state == value

        def is_state_attr(entity_id: str, name: str, value: Any) -> bool:
            return state_attr(entity_id, name) == value

        def has_value(entity_id: str) -> bool:
            snap = states.get(entity_id)
            return snap is not None and snap.state not in ("unknown", "unavailable")

        def today_at(value: str = "00:00") -> datetime:
            hh, mm, *ss = (int(p) for p in value.split(":"))
            return now.replace(hour=hh, minute=mm, second=ss[0] if ss else 0, microsecond=0)

        def as_timestamp(value: Any, default: Any = _NO_DEFAULT) -> Any:
            if isinstance(value, datetime):
                return value.timestamp()
            try:
                return datetime.fromisoformat(str(value)).timestamp()
            except ValueError:
                if default is _NO_DEFAULT:
                    raise UnsupportedFeature(f"as_timestamp could not parse {value!r}") from None
                return default

        def as_datetime(value: Any, default: Any = _NO_DEFAULT) -> Any:
            if isinstance(value, datetime):
                return value
            try:
                return datetime.fromisoformat(str(value))
            except ValueError:
                if default is _NO_DEFAULT:
                    raise UnsupportedFeature(f"as_datetime could not parse {value!r}") from None
                return default

        def iif(cond: Any, if_true: Any = True, if_false: Any = False, if_none: Any = _NO_DEFAULT) -> Any:
            if cond is None and if_none is not _NO_DEFAULT:
                return if_none
            return if_true if cond else if_false

        context: dict[str, Any] = {
            "states": _StatesProxy(states),
            "state_attr": state_attr,
            "is_state": is_state,
            "is_state_attr": is_state_attr,
            "has_value": has_value,
            "now": lambda: now,
            "utcnow": lambda: now.astimezone(timezone.utc),
            "today_at": today_at,
            "as_timestamp": as_timestamp,
            "as_datetime": as_datetime,
            "timedelta": timedelta,
            "float": _num(float),
            "int": _num(int),
            "bool": _bool,
            "iif": iif,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
        }
        context.update(variables or {})
        try:
            return compiled.render(context)
        except UnsupportedFeature:
            raise
        except UndefinedError as err:
            raise UnsupportedFeature(f"Template uses something not available in simulation: {err}") from err
        except Exception as err:  # noqa: BLE001
            raise UnsupportedFeature(f"Template failed: {err}") from err

    def render_bool(self, template: str, states, now, variables=None) -> bool:
        result = self.render(template, states, now, variables).strip().lower()
        if result in ("true", "on", "yes", "1"):
            return True
        number = to_float(result)
        if number is not None:
            return number != 0
        return False


def template_uses_now(template: str) -> bool:
    return "now()" in template or "utcnow()" in template or "today_at" in template
