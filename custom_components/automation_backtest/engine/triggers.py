"""Trigger simulation, mirroring Home Assistant semantics as closely as possible.

Each trigger reacts to:
  * on_start(ctx)            – initialise internal state at the start of the window
  * on_change(change, ctx)   – a recorded state change
  * on_tick(ctx)             – a scheduled moment it asked for (time, pattern, 'for')
and returns a list of Firing objects (plus Timer requests for 'for:').
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo
from itertools import product
from typing import Any

from .conditions import EvalContext, numeric_matches
from .devices import device_trigger_to_state
from .history import StateChange, StateSnapshot
from .templates import template_uses_now
from .util import (
    UnsupportedFeature,
    as_list,
    norm_state,
    parse_duration,
    parse_time_of_day,
    to_float,
)

_MISSING = object()
MAX_PATTERN_TICKS = 500_000


@dataclass
class Firing:
    time: datetime
    variables: dict[str, Any]
    description: str


@dataclass
class TimerRequest:
    time: datetime
    key: Any
    token: int


@dataclass
class TriggerOutput:
    firings: list[Firing] = field(default_factory=list)
    timers: list[TimerRequest] = field(default_factory=list)


_norm = norm_state


def _snap_dict(snap: StateSnapshot | None) -> dict[str, Any] | None:
    return snap.as_dict() if snap else None


class BaseTrigger:
    platform = "?"

    def __init__(self, config: dict[str, Any], index: int) -> None:
        self.config = config
        self.index = index
        self.trigger_id = str(config.get("id", index))
        self._token = 0

    def variables(self, **extra: Any) -> dict[str, Any]:
        base = {"platform": self.platform, "id": self.trigger_id, "idx": str(self.index)}
        base.update(extra)
        return {"trigger": base}

    def next_token(self) -> int:
        self._token += 1
        return self._token

    # Hooks -----------------------------------------------------------------
    def on_start(self, ctx: EvalContext) -> None:  # pragma: no cover - default
        return None

    def scheduled_times(self, start: datetime, end: datetime, tz: tzinfo) -> list[datetime]:
        return []

    def on_change(self, change: StateChange, ctx: EvalContext) -> TriggerOutput:
        return TriggerOutput()

    def on_scheduled(self, ctx: EvalContext) -> TriggerOutput:
        return TriggerOutput()

    def on_timer(self, key: Any, token: int, ctx: EvalContext) -> TriggerOutput:
        return TriggerOutput()


# --- state ------------------------------------------------------------------


class StateTrigger(BaseTrigger):
    platform = "state"

    def __init__(self, config: dict[str, Any], index: int) -> None:
        super().__init__(config, index)
        self.entity_ids = as_list(config.get("entity_id"))
        if not self.entity_ids:
            raise UnsupportedFeature("State trigger without entity_id")
        self.attribute = config.get("attribute")
        self.from_ = config.get("from", _MISSING)
        self.to = config.get("to", _MISSING)
        self.not_from = as_list(config.get("not_from"))
        self.not_to = as_list(config.get("not_to"))
        self.duration = parse_duration(config.get("for"))
        # HA: with none of from/to/not_from/not_to, attribute-only changes also fire.
        self.any_change = (
            self.from_ is _MISSING and self.to is _MISSING
            and not self.not_from and not self.not_to
        )
        self._pending: dict[str, tuple[int, Any, dict, str]] = {}

    def _value(self, snap: StateSnapshot | None) -> Any:
        if snap is None:
            return None
        return snap.attributes.get(self.attribute) if self.attribute else snap.state

    @staticmethod
    def _match(value: Any, spec: Any) -> bool:
        if spec is _MISSING or spec is None:
            return True
        return _norm(value) in [_norm(v) for v in as_list(spec)]

    def _excluded(self, value: Any, specs: list) -> bool:
        return _norm(value) in [_norm(v) for v in specs]

    def _matches(self, change: StateChange) -> bool:
        old_v, new_v = self._value(change.old), self._value(change.new)
        if self.attribute:
            if old_v == new_v:
                return False
        elif not self.any_change and old_v == new_v:
            return False  # attribute-only change
        if change.old is None and self.from_ is not _MISSING and self.from_ is not None:
            return False
        if not self._match(old_v, self.from_) or not self._match(new_v, self.to):
            return False
        if self._excluded(old_v, self.not_from) or self._excluded(new_v, self.not_to):
            return False
        return True

    def _holds(self, entity_id: str, held_value: Any, ctx: EvalContext) -> bool:
        current = self._value(ctx.states.get(entity_id))
        if self.to is _MISSING or self.to is None:
            return current == held_value
        return self._match(current, self.to) and not self._excluded(current, self.not_to)

    def on_change(self, change: StateChange, ctx: EvalContext) -> TriggerOutput:
        out = TriggerOutput()
        if change.entity_id not in self.entity_ids:
            return out
        pending = self._pending.get(change.entity_id)
        if pending is not None:
            if self._holds(change.entity_id, pending[1], ctx):
                return out  # still holding, keep the original timer
            del self._pending[change.entity_id]
        if not self._matches(change):
            return out
        new_v = self._value(change.new)
        old_v = self._value(change.old)
        desc = f"{change.entity_id}{'.' + self.attribute if self.attribute else ''}: {old_v} → {new_v}"
        variables = self.variables(
            entity_id=change.entity_id,
            from_state=_snap_dict(change.old),
            to_state=_snap_dict(change.new),
            attribute=self.attribute,
            **({"for": str(self.duration)} if self.duration else {}),
        )
        if self.duration:
            token = self.next_token()
            self._pending[change.entity_id] = (token, new_v, variables, desc)
            out.timers.append(TimerRequest(change.time + self.duration, change.entity_id, token))
        else:
            out.firings.append(Firing(change.time, variables, desc))
        return out

    def on_timer(self, key: Any, token: int, ctx: EvalContext) -> TriggerOutput:
        pending = self._pending.get(key)
        if pending is None or pending[0] != token:
            return TriggerOutput()
        del self._pending[key]
        _, _, variables, desc = pending
        return TriggerOutput(firings=[Firing(ctx.now, variables, f"{desc} (held {self.duration})")])


# --- numeric_state ------------------------------------------------------------


class NumericStateTrigger(BaseTrigger):
    platform = "numeric_state"

    def __init__(self, config: dict[str, Any], index: int) -> None:
        super().__init__(config, index)
        self.entity_ids = as_list(config.get("entity_id"))
        if not self.entity_ids:
            raise UnsupportedFeature("numeric_state trigger without entity_id")
        if config.get("above") is None and config.get("below") is None:
            raise UnsupportedFeature("numeric_state trigger needs above and/or below")
        self.duration = parse_duration(config.get("for"))
        self._armed: dict[str, bool] = {}
        self._pending: dict[str, tuple[int, dict, str]] = {}

    def _value(self, entity_id: str, ctx: EvalContext) -> float | None:
        snap = ctx.states.get(entity_id)
        if self.config.get("value_template"):
            rendered = ctx.renderer.render(
                self.config["value_template"], ctx.states, ctx.now, {"state": snap}
            )
            return to_float(rendered)
        if snap is None:
            return None
        attr = self.config.get("attribute")
        return to_float(snap.attributes.get(attr) if attr else snap.state)

    def _match(self, entity_id: str, ctx: EvalContext) -> bool:
        return numeric_matches(self._value(entity_id, ctx), self.config, ctx)

    def on_start(self, ctx: EvalContext) -> None:
        # Already matching at start => must leave the range before it can fire.
        for entity_id in self.entity_ids:
            self._armed[entity_id] = not self._match(entity_id, ctx)

    def on_change(self, change: StateChange, ctx: EvalContext) -> TriggerOutput:
        out = TriggerOutput()
        if change.entity_id not in self.entity_ids:
            return out
        entity_id = change.entity_id
        matching = self._match(entity_id, ctx)
        if not matching:
            self._armed[entity_id] = True
            self._pending.pop(entity_id, None)
            return out
        if not self._armed.get(entity_id, True):
            return out
        self._armed[entity_id] = False
        value = self._value(entity_id, ctx)
        old = change.old.state if change.old else None
        desc = (
            f"{entity_id}: {old} → {value} "
            f"(above={self.config.get('above')}, below={self.config.get('below')})"
        )
        variables = self.variables(
            entity_id=entity_id,
            from_state=_snap_dict(change.old),
            to_state=_snap_dict(change.new),
            above=self.config.get("above"),
            below=self.config.get("below"),
        )
        if self.duration:
            token = self.next_token()
            self._pending[entity_id] = (token, variables, desc)
            out.timers.append(TimerRequest(change.time + self.duration, entity_id, token))
        else:
            out.firings.append(Firing(change.time, variables, desc))
        return out

    def on_timer(self, key: Any, token: int, ctx: EvalContext) -> TriggerOutput:
        pending = self._pending.get(key)
        if pending is None or pending[0] != token:
            return TriggerOutput()
        del self._pending[key]
        _, variables, desc = pending
        return TriggerOutput(firings=[Firing(ctx.now, variables, f"{desc} (held {self.duration})")])


# --- time / time_pattern --------------------------------------------------------


def _days(start: datetime, end: datetime, tz: tzinfo):
    day: date = start.astimezone(tz).date()
    last: date = end.astimezone(tz).date()
    while day <= last:
        yield day
        day += timedelta(days=1)


class TimeTrigger(BaseTrigger):
    platform = "time"

    def __init__(self, config: dict[str, Any], index: int) -> None:
        super().__init__(config, index)
        self.at = as_list(config.get("at"))
        if not self.at:
            raise UnsupportedFeature("Time trigger without 'at'")
        self._times: list[time] = []
        self._entity_times: list[str] = []
        for item in self.at:
            if isinstance(item, dict):
                raise UnsupportedFeature("Time trigger with entity offset is not supported yet")
            text = str(item)
            if "." in text and not text[0].isdigit():
                self._entity_times.append(text)
            else:
                self._times.append(parse_time_of_day(text))

    def on_start(self, ctx: EvalContext) -> None:
        """input_datetime values are read at the window start (changes later are ignored)."""
        for entity_id in self._entity_times:
            snap = ctx.states.get(entity_id)
            if snap is None or snap.domain != "input_datetime":
                raise UnsupportedFeature(
                    f"Time trigger on {entity_id}: only input_datetime entities are supported"
                )
            self._times.append(parse_time_of_day(snap.state.split(" ")[-1]))

    def scheduled_times(self, start: datetime, end: datetime, tz: tzinfo) -> list[datetime]:
        out = []
        for day in _days(start, end, tz):
            for t in self._times:
                when = datetime.combine(day, t, tzinfo=tz)
                if start < when <= end:
                    out.append(when)
        return out

    def on_scheduled(self, ctx: EvalContext) -> TriggerOutput:
        local = ctx.now.astimezone(ctx.tz)
        return TriggerOutput(
            firings=[Firing(ctx.now, self.variables(now=local.isoformat()), f"time {local.time()}")]
        )


def _pattern_values(spec: Any, maximum: int) -> list[int]:
    if spec is None or spec == "*":
        return list(range(maximum + 1))
    text = str(spec)
    if text.startswith("/"):
        step = int(text[1:])
        return list(range(0, maximum + 1, step))
    value = int(text)
    return [value] if 0 <= value <= maximum else []


class TimePatternTrigger(BaseTrigger):
    platform = "time_pattern"

    def __init__(self, config: dict[str, Any], index: int) -> None:
        super().__init__(config, index)
        hours, minutes, seconds = config.get("hours"), config.get("minutes"), config.get("seconds")
        if hours is None and minutes is None and seconds is None:
            raise UnsupportedFeature("time_pattern needs hours, minutes or seconds")
        if minutes is None and hours is not None:
            minutes = 0
        if seconds is None and minutes is not None:
            seconds = 0
        self.hours = _pattern_values(hours, 23)
        self.minutes = _pattern_values(minutes, 59)
        self.seconds = _pattern_values(seconds, 59)

    def scheduled_times(self, start: datetime, end: datetime, tz: tzinfo) -> list[datetime]:
        out = []
        for day in _days(start, end, tz):
            for h, m, s in product(self.hours, self.minutes, self.seconds):
                when = datetime.combine(day, time(h, m, s), tzinfo=tz)
                if start < when <= end:
                    out.append(when)
                    if len(out) > MAX_PATTERN_TICKS:
                        raise UnsupportedFeature(
                            "time_pattern fires too often for this window; shorten the period"
                        )
        return out

    def on_scheduled(self, ctx: EvalContext) -> TriggerOutput:
        local = ctx.now.astimezone(ctx.tz)
        return TriggerOutput(
            firings=[Firing(ctx.now, self.variables(now=local.isoformat()), f"pattern {local.time()}")]
        )


# --- template -----------------------------------------------------------------


class TemplateTrigger(BaseTrigger):
    platform = "template"

    def __init__(self, config: dict[str, Any], index: int) -> None:
        super().__init__(config, index)
        self.template = config.get("value_template")
        if not self.template:
            raise UnsupportedFeature("Template trigger without value_template")
        self.duration = parse_duration(config.get("for"))
        self.uses_now = template_uses_now(self.template)
        self._last = False
        self._pending_token: int | None = None

    def _eval(self, ctx: EvalContext) -> bool:
        return ctx.renderer.render_bool(self.template, ctx.states, ctx.now)

    def on_start(self, ctx: EvalContext) -> None:
        self._last = self._eval(ctx)

    def scheduled_times(self, start: datetime, end: datetime, tz: tzinfo) -> list[datetime]:
        if not self.uses_now:
            return []
        # HA re-renders now()-based templates at the start of every minute.
        first = (start + timedelta(minutes=1)).replace(second=0, microsecond=0)
        out, cur = [], first
        while cur <= end:
            out.append(cur)
            cur += timedelta(minutes=1)
        return out

    def _step(self, ctx: EvalContext) -> TriggerOutput:
        out = TriggerOutput()
        value = self._eval(ctx)
        if not value:
            self._pending_token = None
        elif not self._last:
            variables = self.variables(entity_id=None)
            if self.duration:
                token = self.next_token()
                self._pending_token = token
                out.timers.append(TimerRequest(ctx.now + self.duration, "template", token))
            else:
                out.firings.append(Firing(ctx.now, variables, "template became true"))
        self._last = value
        return out

    def on_change(self, change: StateChange, ctx: EvalContext) -> TriggerOutput:
        return self._step(ctx)

    def on_scheduled(self, ctx: EvalContext) -> TriggerOutput:
        return self._step(ctx)

    def on_timer(self, key: Any, token: int, ctx: EvalContext) -> TriggerOutput:
        if token != self._pending_token:
            return TriggerOutput()
        self._pending_token = None
        return TriggerOutput(
            firings=[Firing(ctx.now, self.variables(entity_id=None),
                            f"template true for {self.duration}")]
        )


# --- factory --------------------------------------------------------------------

_TRIGGERS = {
    "state": StateTrigger,
    "numeric_state": NumericStateTrigger,
    "time": TimeTrigger,
    "time_pattern": TimePatternTrigger,
    "template": TemplateTrigger,
}


def build_trigger(raw: dict[str, Any], index: int) -> BaseTrigger:
    platform = raw.get("trigger") or raw.get("platform")
    if platform == "device":
        raw = device_trigger_to_state(raw)
        platform = "state"
    cls = _TRIGGERS.get(platform)
    if cls is None:
        raise UnsupportedFeature(
            f"Trigger '{platform}' cannot be replayed from state history (yet)"
        )
    return cls(raw, index)
