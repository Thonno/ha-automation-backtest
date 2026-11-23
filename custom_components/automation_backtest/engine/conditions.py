"""Condition evaluation against the simulated state machine.

Every evaluation returns a tri-state result: True, False, or None
(None = could not be simulated faithfully, reported as 'uncertain').
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from typing import Any

from .devices import device_condition_to_state
from .history import SimulatedStates
from .skips import SKIP_MARK
from .templates import TemplateRenderer
from .util import (
    UnsupportedFeature,
    as_list,
    describe_bounds,
    norm_state,
    parse_duration,
    parse_time_of_day,
    to_float,
)

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@dataclass
class EvalContext:
    states: SimulatedStates
    now: datetime
    tz: tzinfo
    renderer: TemplateRenderer
    variables: dict[str, Any] = field(default_factory=dict)
    sun: Any = None  # SunProvider: (event, local date) -> datetime | None


@dataclass
class ConditionTrace:
    path: str
    condition: str
    result: bool | None
    detail: str = ""
    skipped: bool = False

    def as_dict(self) -> dict[str, Any]:
        out = {
            "path": self.path,
            "condition": self.condition,
            "result": self.result,
            "detail": self.detail,
        }
        if self.skipped:
            out["skipped"] = True
        return out


def is_disabled(raw: Any) -> bool:
    """``enabled: false`` (also written as a string, as YAML from the UI may carry it)."""
    if not isinstance(raw, dict) or "enabled" not in raw:
        return False
    value = raw["enabled"]
    if isinstance(value, str):
        return value.strip().lower() in ("false", "off", "no", "0")
    return value is False or value == 0


def normalize_condition(raw: Any) -> dict[str, Any]:
    """Expand HA shorthand forms into the canonical dict shape."""
    if isinstance(raw, str):
        return {"condition": "template", "value_template": raw}
    if not isinstance(raw, dict):
        raise UnsupportedFeature(f"Invalid condition: {raw!r}")
    if "condition" in raw:
        return raw
    for key in ("and", "or", "not"):
        if key in raw:
            out = {"condition": key, "conditions": raw[key]}
            if "enabled" in raw:
                out["enabled"] = raw["enabled"]
            return out
    raise UnsupportedFeature(f"Unrecognized condition: {raw!r}")


def evaluate_conditions(
    conditions: list[Any], ctx: EvalContext, path: str = "condition"
) -> tuple[bool | None, list[ConditionTrace]]:
    """AND of all top-level conditions, short-circuiting like Home Assistant."""
    traces: list[ConditionTrace] = []
    overall: bool | None = True
    for idx, raw in enumerate(conditions):
        result, sub = evaluate(raw, ctx, f"{path}/{idx}")
        traces.extend(sub)
        if result is False:
            return False, traces
        if result is None:
            overall = None
    return overall, traces


def evaluate(raw: Any, ctx: EvalContext, path: str) -> tuple[bool | None, list[ConditionTrace]]:
    try:
        cond = normalize_condition(raw)
    except UnsupportedFeature as err:
        return None, [ConditionTrace(path, "?", None, str(err))]

    if is_disabled(cond):
        # Neutral, like HA: passes an and/top-level list, ignored by or/not (see _logical).
        detail = "skipped in this backtest" if cond.get(SKIP_MARK) else "disabled, skipped"
        return True, [ConditionTrace(path, cond["condition"], True, detail, skipped=True)]

    kind = cond["condition"]
    try:
        if kind in ("and", "or", "not"):
            return _logical(kind, cond, ctx, path)
        handler = _HANDLERS.get(kind)
        if handler is None and isinstance(kind, str) and "." in kind:
            from .purpose import evaluate_purpose_condition  # local import: avoids a cycle

            handler = evaluate_purpose_condition
        if handler is None:
            raise UnsupportedFeature(f"Condition type '{kind}' is not supported yet")
        result, detail = handler(cond, ctx)
    except UnsupportedFeature as err:
        return None, [ConditionTrace(path, kind, None, str(err))]
    return result, [ConditionTrace(path, kind, result, detail)]


def _logical(kind: str, cond: dict, ctx: EvalContext, path: str):
    traces: list[ConditionTrace] = []
    results: list[bool | None] = []
    for idx, sub in enumerate(as_list(cond.get("conditions"))):
        res, sub_traces = evaluate(sub, ctx, f"{path}/conditions/{idx}")
        traces.extend(sub_traces)
        if sub_traces and sub_traces[0].skipped:
            continue  # disabled: HA leaves it out of and/or/not
        results.append(res)
        if kind == "and" and res is False:
            break
        if kind == "or" and res is True:
            break
    if kind == "and":
        result = False if False in results else (None if None in results else True)
    elif kind == "or":
        result = True if True in results else (None if None in results else False)
    else:  # not: true when none of the sub-conditions is true
        result = False if True in results else (None if None in results else True)
    traces.insert(0, ConditionTrace(path, kind, result))
    return result, traces


# --- individual condition types -------------------------------------------


def _resolve_value(value: Any, ctx: EvalContext) -> Any:
    """Support thresholds/states given as another entity's state."""
    if isinstance(value, str) and "." in value and " " not in value:
        snap = ctx.states.get(value)
        if snap is not None:
            return snap.state
    return value


def _state_condition(cond: dict, ctx: EvalContext):
    entity_ids = as_list(cond.get("entity_id"))
    wanted = [norm_state(_resolve_value(v, ctx)) for v in as_list(cond.get("state"))]
    attribute = cond.get("attribute")
    duration = parse_duration(cond.get("for"))
    match_any = cond.get("match") == "any"
    details = []
    hits = []
    for entity_id in entity_ids:
        snap = ctx.states.get(entity_id)
        if snap is None:
            hits.append(False)
            details.append(f"{entity_id}: no state")
            continue
        current = snap.attributes.get(attribute) if attribute else snap.state
        ok = norm_state(current) in wanted
        if ok and duration is not None and snap.last_changed is not None:
            held = ctx.now - snap.last_changed
            if held < duration:
                ok = False
                details.append(f"{entity_id}={current} only for {held}, needs {duration}")
                hits.append(False)
                continue
        hits.append(ok)
        details.append(f"{entity_id}={current}")
    result = any(hits) if match_any else all(hits)
    return result, f"{', '.join(details)} (wanted {wanted})"


def _numeric_value(cond: dict, ctx: EvalContext, entity_id: str | None):
    variables = dict(ctx.variables)
    snap = ctx.states.get(entity_id) if entity_id else None
    if cond.get("value_template"):
        if snap is not None:
            variables["state"] = snap
        rendered = ctx.renderer.render(cond["value_template"], ctx.states, ctx.now, variables)
        return to_float(rendered), rendered
    if snap is None:
        return None, "no state"
    raw = snap.attributes.get(cond["attribute"]) if cond.get("attribute") else snap.state
    return to_float(raw), raw


def numeric_matches(value: float | None, cond: dict, ctx: EvalContext) -> bool:
    if value is None:
        return False
    above = cond.get("above")
    below = cond.get("below")
    if above is not None:
        limit = to_float(_resolve_value(above, ctx))
        if limit is None or not value > limit:
            return False
    if below is not None:
        limit = to_float(_resolve_value(below, ctx))
        if limit is None or not value < limit:
            return False
    return True


def _numeric_state_condition(cond: dict, ctx: EvalContext):
    entity_ids = as_list(cond.get("entity_id")) or [None]
    details = []
    for entity_id in entity_ids:
        value, raw = _numeric_value(cond, ctx, entity_id)
        ok = numeric_matches(value, cond, ctx)
        details.append(f"{entity_id or 'template'}={raw}")
        if not ok:
            return False, f"{', '.join(details)} (needs {describe_bounds(cond)})"
    return True, ", ".join(details)


def _time_bound(value: Any, ctx: EvalContext):
    if value is None:
        return None
    text = str(value)
    if "." in text and not text[0].isdigit():
        snap = ctx.states.get(text)
        if snap is None:
            raise UnsupportedFeature(f"Time entity {text} has no state")
        if snap.domain == "input_datetime":
            if snap.attributes.get("has_time") is False:
                raise UnsupportedFeature(f"{text} has no time component")
            text = snap.state.split(" ")[-1]
        else:
            raise UnsupportedFeature(f"Time from {snap.domain} entities is not supported yet")
    return parse_time_of_day(text)


def _time_condition(cond: dict, ctx: EvalContext):
    local = ctx.now.astimezone(ctx.tz)
    current = local.time().replace(microsecond=0)
    after = _time_bound(cond.get("after"), ctx)
    before = _time_bound(cond.get("before"), ctx)
    weekdays = as_list(cond.get("weekday"))
    if weekdays and WEEKDAYS[local.weekday()] not in weekdays:
        return False, f"{WEEKDAYS[local.weekday()]} not in {weekdays}"
    if after is not None and before is not None and after > before:
        ok = current >= after or current < before  # crosses midnight
    else:
        ok = (after is None or current >= after) and (before is None or current < before)
    return ok, f"local time {current} (after={after}, before={before})"


def _template_condition(cond: dict, ctx: EvalContext):
    template = cond.get("value_template")
    if not template:
        raise UnsupportedFeature("Template condition without value_template")
    result = ctx.renderer.render_bool(template, ctx.states, ctx.now, ctx.variables)
    return result, f"template -> {result}"


def _trigger_condition(cond: dict, ctx: EvalContext):
    trigger = ctx.variables.get("trigger") or {}
    wanted = [str(v) for v in as_list(cond.get("id"))]
    current = str(trigger.get("id"))
    return current in wanted, f"trigger id {current!r} (wanted {wanted})"


def _sun_condition(cond: dict, ctx: EvalContext):
    """Same rules as Home Assistant's sun condition (events of the local 'today')."""
    if ctx.sun is None:
        raise UnsupportedFeature("Sun condition needs the home location")
    day = ctx.now.astimezone(ctx.tz).date()
    sunrise, sunset = ctx.sun("sunrise", day), ctx.sun("sunset", day)
    before, after = cond.get("before"), cond.get("after")
    before_offset = parse_duration(cond.get("before_offset")) or timedelta(0)
    after_offset = parse_duration(cond.get("after_offset")) or timedelta(0)
    hhmm = lambda dt: dt.astimezone(ctx.tz).strftime("%H:%M:%S")  # noqa: E731
    if before is None and after is None:
        raise UnsupportedFeature("Sun condition without before/after")

    def at(event: str) -> datetime:
        when = sunrise if event == "sunrise" else sunset
        if when is None:
            raise UnsupportedFeature(f"No {event} today at this latitude (polar day/night)")
        return when

    if before == "sunrise" and after == "sunset":  # night: before sunrise OR after sunset
        b, a = at("sunrise") + before_offset, at("sunset") + after_offset
        ok = ctx.now < b or ctx.now > a
        return ok, f"now {hhmm(ctx.now)}; night = before {hhmm(b)} or after {hhmm(a)}"
    ok, parts = True, []
    if before is not None:
        limit = at(before) + before_offset
        ok = ok and not ctx.now > limit
        parts.append(f"before {before} {hhmm(limit)}")
    if after is not None:
        limit = at(after) + after_offset
        ok = ok and not ctx.now < limit
        parts.append(f"after {after} {hhmm(limit)}")
    return ok, f"now {hhmm(ctx.now)}; " + ", ".join(parts)


def _device_condition(cond: dict, ctx: EvalContext):
    native = device_condition_to_state(cond)
    if native["condition"] == "numeric_state":
        return _numeric_state_condition(native, ctx)
    return _state_condition(native, ctx)


_HANDLERS = {
    "device": _device_condition,
    "sun": _sun_condition,
    "state": _state_condition,
    "numeric_state": _numeric_state_condition,
    "time": _time_condition,
    "template": _template_condition,
    "trigger": _trigger_condition,
}
