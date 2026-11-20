"""Dry-run of an automation's actions: what it would have done, and to what.

Nothing is ever executed. For every run that would have executed we walk the
action sequence and record each step; for the common services (turn_on/off,
toggle, set_value, covers, climate, ...) we also compute the state the target
entity would have had. That gives a 'simulated' timeline per controlled entity,
to put next to the real one.

Templates and conditions inside the actions see the recorded history at that
instant, except for the controlled entities, which show their simulated state.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .conditions import EvalContext, evaluate_conditions
from .history import HistoryStore, StateSnapshot
from .references import _ENTITY_RE
from .templates import TemplateRenderer
from .util import UnsupportedFeature, as_list, iso, parse_duration, to_float

DONE, NOT_SIMULATED, SKIPPED, STOPPED = "done", "not_simulated", "skipped", "stopped"

MAX_STEPS = 200  # per run, guards against huge repeats
MAX_REPEAT = 50

_ON_OFF = {
    "light", "switch", "fan", "input_boolean", "automation", "siren", "humidifier",
    "remote", "group", "media_player", "water_heater",
}
_NO_STATE_DOMAINS = {"notify", "persistent_notification", "tts", "logbook", "system_log", "rest_command", "shell_command"}


def action_list(config: dict[str, Any]) -> list[Any]:
    return as_list(config.get("actions", config.get("action")))


# --- which entities do the actions control? --------------------------------------


def _targets_of(step: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for source in (step, step.get("target") or {}, step.get("data") or {}):
        if isinstance(source, dict):
            for eid in as_list(source.get("entity_id")):
                if isinstance(eid, str) and _ENTITY_RE.match(eid) and eid not in found:
                    found.append(eid)
    for eid in as_list(step.get("_entities")):
        if eid not in found:
            found.append(eid)
    return found


def _children(step: dict[str, Any]) -> list[list[Any]]:
    out: list[list[Any]] = []
    for key in ("sequence", "then", "else", "default"):
        if key in step:
            out.append(as_list(step[key]))
    for option in as_list(step.get("choose")):
        if isinstance(option, dict):
            out.append(as_list(option.get("sequence")))
    for branch in as_list(step.get("parallel")):
        out.append(as_list(branch.get("sequence")) if isinstance(branch, dict) and "sequence" in branch else [branch])
    if isinstance(step.get("repeat"), dict):
        out.append(as_list(step["repeat"].get("sequence")))
    return out


def controlled_entities(config: dict[str, Any]) -> list[str]:
    """Entities targeted by service calls / device actions, in order of appearance."""
    found: list[str] = []

    def walk(steps: list[Any]) -> None:
        for step in steps:
            if not isinstance(step, dict):
                continue
            if _service_name(step) or step.get("device_id"):
                for eid in _targets_of(step):
                    if eid not in found:
                        found.append(eid)
            for child in _children(step):
                walk(child)

    walk(action_list(config))
    return found


# --- result shapes ---------------------------------------------------------------


@dataclass
class Step:
    time: datetime
    path: str
    kind: str
    label: str
    result: str
    detail: str = ""
    entities: list[str] = field(default_factory=list)

    def as_dict(self, tz) -> dict[str, Any]:
        return {
            "time": iso(self.time.astimezone(tz)),
            "path": self.path,
            "kind": self.kind,
            "label": self.label,
            "result": self.result,
            "detail": self.detail,
            "entities": list(self.entities),
        }


class _Stop(Exception):
    """Raised to end a run (stop action, failed condition, unsupported wait)."""


class _Timeline:
    """Simulated states of the controlled entities, as an ordered list per entity."""

    def __init__(self, store: HistoryStore, entities: list[str], start: datetime) -> None:
        self.start = start
        self._times: dict[str, list[datetime]] = {}
        self._snaps: dict[str, list[StateSnapshot]] = {}
        self._owner: dict[str, list[int]] = {}
        for eid in entities:
            snap = store.state_at(eid, start)
            self._times[eid] = [start]
            self._snaps[eid] = [snap or StateSnapshot(eid, "unknown", {}, start, start)]
            self._owner[eid] = [-1]

    def __contains__(self, entity_id: str) -> bool:
        return entity_id in self._times

    def at(self, entity_id: str, when: datetime) -> StateSnapshot:
        idx = bisect.bisect_right(self._times[entity_id], when) - 1
        return self._snaps[entity_id][max(idx, 0)]

    def set(self, entity_id: str, when: datetime, state: str, attrs: dict[str, Any], run_id: int) -> None:
        old = self.at(entity_id, when)
        new = StateSnapshot(
            entity_id, state, {**old.attributes, **attrs},
            when if state != old.state else old.last_changed, when,
        )
        idx = bisect.bisect_right(self._times[entity_id], when)
        self._times[entity_id].insert(idx, when)
        self._snaps[entity_id].insert(idx, new)
        self._owner[entity_id].insert(idx, run_id)

    def cancel_after(self, run_id: int, when: datetime) -> None:
        """mode: restart — drop what the previous run had not done yet."""
        for eid in self._times:
            keep = [
                i for i, (t, o) in enumerate(zip(self._times[eid], self._owner[eid]))
                if not (o == run_id and t > when)
            ]
            self._times[eid] = [self._times[eid][i] for i in keep]
            self._snaps[eid] = [self._snaps[eid][i] for i in keep]
            self._owner[eid] = [self._owner[eid][i] for i in keep]

    def series(self, entity_id: str, end: datetime, tz) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for when, snap in zip(self._times[entity_id], self._snaps[entity_id]):
            if when > end:
                break
            info = _attr_summary(snap)
            if out and out[-1]["s"] == snap.state and out[-1].get("a", "") == info:
                continue
            item = {"t": iso(when.astimezone(tz)), "s": snap.state}
            if info:
                item["a"] = info
            out.append(item)
        return out


def _attr_summary(snap: StateSnapshot) -> str:
    a = snap.attributes
    parts = []
    if snap.domain == "light" and snap.state == "on" and to_float(a.get("brightness")) is not None:
        parts.append(f"{round(to_float(a['brightness']) / 255 * 100)}%")
    for key in ("current_position", "percentage", "temperature", "volume_level"):
        if key in a and a[key] is not None and snap.domain in ("cover", "fan", "climate", "water_heater", "media_player"):
            value = a[key]
            parts.append(f"{round(value * 100)}%" if key == "volume_level" and to_float(value) is not None else
                         f"{value}°" if key == "temperature" else f"{value}%")
    return " ".join(parts)


class _View:
    """States as seen by templates/conditions inside the actions at one instant."""

    def __init__(self, store: HistoryStore, timeline: _Timeline, when: datetime) -> None:
        self._store, self._timeline, self._when = store, timeline, when

    def get(self, entity_id: str) -> StateSnapshot | None:
        if entity_id in self._timeline:
            return self._timeline.at(entity_id, self._when)
        return self._store.state_at(entity_id, self._when)

    def all(self, domain: str | None = None) -> list[StateSnapshot]:
        ids = set(self._store.entity_ids) | set(self._timeline._times)
        snaps = [self.get(e) for e in sorted(ids) if domain is None or e.split(".", 1)[0] == domain]
        return [s for s in snaps if s is not None]


# --- the dry run -------------------------------------------------------------------


@dataclass
class _RunState:
    run_id: int
    now: datetime
    variables: dict[str, Any]
    steps: list[Step] = field(default_factory=list)


class ActionSimulator:
    def __init__(self, config: dict[str, Any], store: HistoryStore, start: datetime, end: datetime, tz, sun=None) -> None:
        self.actions = action_list(config)
        self.mode = str(config.get("mode") or "single")
        self.store, self.start, self.end, self.tz, self.sun = store, start, end, tz, sun
        self.renderer = TemplateRenderer()
        self.targets = controlled_entities(config)
        self.timeline = _Timeline(store, self.targets, start)
        self._busy_until: datetime | None = None
        self._last_run = -1

    # public ------------------------------------------------------------------

    def simulate(self, run_id: int, when: datetime, variables: dict[str, Any]) -> tuple[list[Step], str | None]:
        """Dry-run the actions for one executed run. Returns (steps, note)."""
        note = None
        busy = self._busy_until is not None and self._busy_until > when
        if busy and self.mode == "single":
            return [Step(when, "actions", "mode", "mode: single", SKIPPED, "already running: Home Assistant would skip this run")], "skipped"
        if busy and self.mode == "restart":
            self.timeline.cancel_after(self._last_run, when)
            note = "restarted"
        if busy and self.mode == "queued":
            when = self._busy_until
            note = "queued"
        rs = _RunState(run_id, when, dict(variables))
        try:
            self._sequence(self.actions, rs, "action")
        except _Stop:
            pass
        end = rs.now
        if self.mode != "parallel":
            self._busy_until = end if end > when else None
            self._last_run = run_id
        return rs.steps, note

    def series(self) -> dict[str, list[dict[str, Any]]]:
        return {eid: self.timeline.series(eid, self.end, self.tz) for eid in self.targets}

    # walking -----------------------------------------------------------------

    def _ctx(self, rs: _RunState) -> EvalContext:
        return EvalContext(
            states=_View(self.store, self.timeline, rs.now), now=rs.now, tz=self.tz,
            renderer=self.renderer, variables=rs.variables, sun=self.sun,
        )

    def _render(self, value: Any, rs: _RunState) -> Any:
        if isinstance(value, str) and ("{{" in value or "{%" in value):
            out = self.renderer.render(value, _View(self.store, self.timeline, rs.now), rs.now, rs.variables)
            num = to_float(out)
            if num is not None and out.strip() not in ("",):
                return int(num) if num.is_integer() and "." not in out else num
            return out
        if isinstance(value, dict):
            return {k: self._render(v, rs) for k, v in value.items()}
        if isinstance(value, list):
            return [self._render(v, rs) for v in value]
        return value

    def _add(self, rs: _RunState, *args, **kwargs) -> Step:
        if len(rs.steps) >= MAX_STEPS:
            raise _Stop
        step = Step(rs.now, *args, **kwargs)
        rs.steps.append(step)
        return step

    def _sequence(self, steps: list[Any], rs: _RunState, path: str) -> None:
        for idx, raw in enumerate(steps):
            if rs.now > self.end:
                return
            self._step(raw, rs, f"{path}/{idx}")

    def _conditions(self, conds: Any, rs: _RunState) -> tuple[bool | None, str]:
        passed, traces = evaluate_conditions(as_list(conds), self._ctx(rs))
        failing = next((t for t in traces if t.result is not True), None)
        return passed, (f"{failing.condition}: {failing.detail}" if failing else "")

    def _step(self, raw: Any, rs: _RunState, path: str) -> None:
        if isinstance(raw, str):  # template shorthand = condition
            raw = {"condition": "template", "value_template": raw}
        if not isinstance(raw, dict):
            self._add(rs, path, "?", str(raw), NOT_SIMULATED, "invalid action")
            return
        alias = raw.get("alias")
        if raw.get("enabled") is False:
            self._add(rs, path, "disabled", alias or _short(raw), SKIPPED, "disabled")
            return

        service = _service_name(raw)
        if service:
            self._service(raw, service, rs, path, alias)
        elif "delay" in raw:
            try:
                value = self._render(raw["delay"], rs)
                duration = parse_duration(value)
            except UnsupportedFeature as err:
                self._add(rs, path, "delay", alias or "delay", NOT_SIMULATED, str(err))
                raise _Stop from err
            if duration is None:
                self._add(rs, path, "delay", alias or "delay", NOT_SIMULATED, f"cannot read {value!r}")
                raise _Stop
            self._add(rs, path, "delay", alias or f"delay {duration}", DONE)
            rs.now = rs.now + duration
        elif "wait_template" in raw or "wait_for_trigger" in raw:
            kind = "wait_template" if "wait_template" in raw else "wait_for_trigger"
            self._add(rs, path, kind, alias or kind, NOT_SIMULATED, "waits are not simulated: the rest of this run is not shown")
            raise _Stop
        elif "condition" in raw:
            passed, why = self._conditions([raw], rs)
            if passed is True:
                self._add(rs, path, "condition", alias or f"condition {raw['condition']}", DONE, "passed")
            else:
                self._add(rs, path, "condition", alias or f"condition {raw['condition']}",
                          STOPPED if passed is False else NOT_SIMULATED, why or "not passed")
                raise _Stop
        elif "if" in raw:
            passed, why = self._conditions(raw["if"], rs)
            if passed is None:
                self._add(rs, path, "if", alias or "if", NOT_SIMULATED, why)
                raise _Stop
            branch = "then" if passed else "else"
            self._add(rs, path, "if", alias or "if", DONE, f"→ {branch}" + ("" if passed else f" ({why})"))
            self._sequence(as_list(raw.get(branch)), rs, f"{path}/{branch}")
        elif "choose" in raw:
            for opt_idx, option in enumerate(as_list(raw["choose"])):
                if not isinstance(option, dict):
                    continue
                passed, why = self._conditions(option.get("conditions"), rs)
                if passed is None:
                    self._add(rs, path, "choose", alias or "choose", NOT_SIMULATED, f"option {opt_idx + 1}: {why}")
                    raise _Stop
                if passed:
                    self._add(rs, path, "choose", alias or "choose", DONE, f"→ option {opt_idx + 1}" + (f" ({option['alias']})" if option.get("alias") else ""))
                    self._sequence(as_list(option.get("sequence")), rs, f"{path}/choose/{opt_idx}")
                    return
            if "default" in raw:
                self._add(rs, path, "choose", alias or "choose", DONE, "→ default")
                self._sequence(as_list(raw["default"]), rs, f"{path}/default")
            else:
                self._add(rs, path, "choose", alias or "choose", DONE, "no option matched")
        elif "sequence" in raw:
            self._sequence(as_list(raw["sequence"]), rs, f"{path}/sequence")
        elif "parallel" in raw:
            start, latest = rs.now, rs.now
            for b_idx, branch in enumerate(as_list(raw["parallel"])):
                rs.now = start
                steps = as_list(branch.get("sequence")) if isinstance(branch, dict) and "sequence" in branch else [branch]
                try:
                    self._sequence(steps, rs, f"{path}/parallel/{b_idx}")
                except _Stop:
                    pass
                latest = max(latest, rs.now)
            rs.now = latest
        elif "repeat" in raw:
            self._repeat(raw, rs, path, alias)
        elif "variables" in raw:
            try:
                for key, value in (raw["variables"] or {}).items():
                    rs.variables[key] = self._render(value, rs)
                self._add(rs, path, "variables", alias or "variables", DONE)
            except UnsupportedFeature as err:
                self._add(rs, path, "variables", alias or "variables", NOT_SIMULATED, str(err))
                raise _Stop from err
        elif "stop" in raw:
            self._add(rs, path, "stop", alias or "stop", STOPPED, str(raw.get("stop") or ""))
            raise _Stop
        elif "event" in raw:
            self._add(rs, path, "event", alias or f"fire event {raw['event']}", DONE, "no state change")
        elif "scene" in raw:
            self._add(rs, path, "scene", alias or f"scene {raw['scene']}", NOT_SIMULATED, "scenes are not simulated")
        elif raw.get("device_id"):
            self._device(raw, rs, path, alias)
        else:
            self._add(rs, path, "?", alias or _short(raw), NOT_SIMULATED, "action type not simulated")

    def _repeat(self, raw: dict, rs: _RunState, path: str, alias: str | None) -> None:
        rep = raw.get("repeat") or {}
        seq = as_list(rep.get("sequence"))
        if "count" in rep:
            try:
                count = int(to_float(self._render(rep["count"], rs)) or 0)
            except UnsupportedFeature as err:
                self._add(rs, path, "repeat", alias or "repeat", NOT_SIMULATED, str(err))
                raise _Stop from err
            self._add(rs, path, "repeat", alias or f"repeat ×{count}", DONE)
            for i in range(min(count, MAX_REPEAT)):
                rs.variables["repeat"] = {"index": i + 1, "first": i == 0, "last": i == count - 1}
                self._sequence(seq, rs, f"{path}/repeat")
        elif "for_each" in rep:
            items = self._render(rep["for_each"], rs)
            items = items if isinstance(items, list) else None
            if items is None:
                self._add(rs, path, "repeat", alias or "repeat for_each", NOT_SIMULATED, "list not readable")
                raise _Stop
            self._add(rs, path, "repeat", alias or f"repeat ×{len(items)}", DONE)
            for i, item in enumerate(items[:MAX_REPEAT]):
                rs.variables["repeat"] = {"index": i + 1, "first": i == 0, "last": i == len(items) - 1, "item": item}
                self._sequence(seq, rs, f"{path}/repeat")
        else:
            key = "while" if "while" in rep else "until"
            self._add(rs, path, "repeat", alias or f"repeat {key}", DONE)
            for i in range(MAX_REPEAT):
                rs.variables["repeat"] = {"index": i + 1, "first": i == 0}
                if key == "while":
                    passed, why = self._conditions(rep["while"], rs)
                    if passed is None:
                        self._add(rs, path, "repeat", "while", NOT_SIMULATED, why)
                        raise _Stop
                    if not passed:
                        return
                self._sequence(seq, rs, f"{path}/repeat")
                if key == "until":
                    passed, why = self._conditions(rep["until"], rs)
                    if passed is None:
                        self._add(rs, path, "repeat", "until", NOT_SIMULATED, why)
                        raise _Stop
                    if passed:
                        return
            self._add(rs, path, "repeat", "repeat", NOT_SIMULATED, f"stopped after {MAX_REPEAT} loops")

    def _service(self, raw: dict, service: str, rs: _RunState, path: str, alias: str | None) -> None:
        domain, _, name = service.partition(".")
        targets = _targets_of(raw)
        label = alias or service
        try:
            data = self._render({**(raw.get("data_template") or {}), **(raw.get("data") or {})}, rs)
            targets = [t for t in as_list(self._render(targets, rs)) if isinstance(t, str)]
        except UnsupportedFeature as err:
            self._add(rs, path, "service", label, NOT_SIMULATED, str(err), entities=targets)
            return
        if domain in _NO_STATE_DOMAINS or not targets:
            msg = data.get("message") if isinstance(data, dict) else None
            self._add(rs, path, "service", label, DONE, f"\"{str(msg)[:120]}\"" if msg else "no entity state to change")
            return
        changed, failed = [], []
        for eid in targets:
            if eid not in self.timeline:
                failed.append(eid)
                continue
            current = self.timeline.at(eid, rs.now)
            effect = service_effect(domain, name, data if isinstance(data, dict) else {}, current)
            if effect is None:
                failed.append(eid)
                continue
            state, attrs = effect
            self.timeline.set(eid, rs.now, state, attrs, rs.run_id)
            info = _attr_summary(self.timeline.at(eid, rs.now))
            changed.append(f"{eid} → {state}" + (f" ({info})" if info else ""))
        if failed and not changed:
            self._add(rs, path, "service", label, NOT_SIMULATED, "effect not simulated", entities=targets)
        else:
            detail = ", ".join(changed) + (f"; not simulated: {', '.join(failed)}" if failed else "")
            self._add(rs, path, "service", label, DONE, detail, entities=targets)

    def _device(self, raw: dict, rs: _RunState, path: str, alias: str | None) -> None:
        kind = str(raw.get("type") or "")
        domain = str(raw.get("domain") or "")
        service = {"turn_on": "turn_on", "turn_off": "turn_off", "toggle": "toggle",
                   "open": "open_cover", "close": "close_cover", "lock": "lock", "unlock": "unlock"}.get(kind)
        if service and _targets_of(raw):
            self._service({**raw, "action": f"{domain}.{service}"}, f"{domain}.{service}", rs, path, alias or f"{domain} {kind}")
        else:
            self._add(rs, path, "device", alias or f"device action {domain} {kind}".strip(), NOT_SIMULATED,
                      "device action not simulated", entities=_targets_of(raw))


def _service_name(step: dict[str, Any]) -> str | None:
    name = step.get("action", step.get("service"))
    return name if isinstance(name, str) and "." in name else None


def _short(raw: dict[str, Any]) -> str:
    return next(iter(raw), "?")


def _num(value: Any) -> float | None:
    return to_float(value)


def service_effect(domain: str, service: str, data: dict[str, Any], current: StateSnapshot) -> tuple[str, dict] | None:
    """(new state, changed attributes) for a service call, or None if not simulated."""
    ent = current.domain
    state = current.state
    if domain == "homeassistant":
        domain = ent
    if domain != ent:
        return None

    if service in ("turn_on", "turn_off", "toggle") and ent in _ON_OFF | {"climate", "light", "cover", "lock"}:
        if service == "toggle":
            if ent == "cover":
                return ("closed", {}) if state in ("open", "opening") else ("open", {})
            if ent == "lock":
                return ("unlocked", {}) if state == "locked" else ("locked", {})
            service = "turn_off" if state not in ("off", "unavailable", "unknown", "idle", "standby") else "turn_on"
        if service == "turn_off":
            attrs = {"brightness": None} if ent == "light" else {}
            return "off", attrs
        if ent == "climate":
            return None  # turn_on restores an unknown previous mode
        if ent == "cover":
            return "open", {}
        if ent == "lock":
            return "locked", {}
        attrs: dict[str, Any] = {}
        if ent == "light":
            if "brightness_pct" in data and _num(data["brightness_pct"]) is not None:
                attrs["brightness"] = round(_num(data["brightness_pct"]) / 100 * 255)
            elif "brightness" in data and _num(data["brightness"]) is not None:
                attrs["brightness"] = _num(data["brightness"])
            elif "brightness_step_pct" in data and _num(data["brightness_step_pct"]) is not None:
                base = _num(current.attributes.get("brightness")) or 0
                attrs["brightness"] = max(0, min(255, base + _num(data["brightness_step_pct"]) / 100 * 255))
            if attrs.get("brightness") == 0:
                return "off", {"brightness": None}
        if ent == "fan" and _num(data.get("percentage")) is not None:
            attrs["percentage"] = _num(data["percentage"])
        return "on", attrs

    if ent == "cover":
        if service == "open_cover":
            return "open", {"current_position": 100}
        if service == "close_cover":
            return "closed", {"current_position": 0}
        if service == "set_cover_position" and _num(data.get("position")) is not None:
            pos = _num(data["position"])
            return ("closed" if pos == 0 else "open"), {"current_position": int(pos)}
        if service == "stop_cover":
            return state, {}
        return None
    if ent == "lock" and service in ("lock", "unlock", "open"):
        return {"lock": "locked", "unlock": "unlocked", "open": "open"}[service], {}
    if ent in ("climate", "water_heater"):
        if service == "set_temperature":
            attrs = {k: data[k] for k in ("temperature", "target_temp_high", "target_temp_low") if k in data}
            mode = data.get("hvac_mode") or data.get("operation_mode")
            return (str(mode) if mode else state), attrs
        if service in ("set_hvac_mode", "set_operation_mode"):
            mode = data.get("hvac_mode") or data.get("operation_mode")
            return (str(mode), {}) if mode else None
        if service == "set_preset_mode" and "preset_mode" in data:
            return state, {"preset_mode": data["preset_mode"]}
        return None
    if ent == "fan" and service == "set_percentage" and _num(data.get("percentage")) is not None:
        pct = _num(data["percentage"])
        return ("off" if pct == 0 else "on"), {"percentage": pct}
    if ent in ("input_number", "number"):
        step = _num(current.attributes.get("step")) or 1
        value = _num(state)
        if service == "set_value" and _num(data.get("value")) is not None:
            new = _num(data["value"])
        elif service == "increment" and value is not None:
            new = value + step
        elif service == "decrement" and value is not None:
            new = value - step
        else:
            return None
        lo, hi = _num(current.attributes.get("min")), _num(current.attributes.get("max"))
        new = max(lo, new) if lo is not None else new
        new = min(hi, new) if hi is not None else new
        return (str(new) if not float(new).is_integer() else f"{new:.1f}"), {}
    if ent in ("input_select", "select"):
        options = list(current.attributes.get("options") or [])
        if service == "select_option" and "option" in data:
            return str(data["option"]), {}
        if service in ("select_next", "select_previous", "select_first", "select_last") and options:
            if service == "select_first":
                return str(options[0]), {}
            if service == "select_last":
                return str(options[-1]), {}
            idx = options.index(state) if state in options else -1
            idx = (idx + (1 if service == "select_next" else -1)) % len(options)
            return str(options[idx]), {}
        return None
    if ent in ("input_text", "text") and service == "set_value" and "value" in data:
        return str(data["value"]), {}
    if ent == "counter":
        value = _num(state) or 0
        step = _num(current.attributes.get("step")) or 1
        if service == "increment":
            return str(int(value + step)), {}
        if service == "decrement":
            return str(int(value - step)), {}
        if service == "reset":
            return str(int(_num(current.attributes.get("initial")) or 0)), {}
        if service == "set_value" and _num(data.get("value")) is not None:
            return str(int(_num(data["value"]))), {}
        return None
    if ent == "timer":
        return {"start": ("active", {}), "pause": ("paused", {}), "cancel": ("idle", {}), "finish": ("idle", {})}.get(service)
    if ent == "media_player":
        if service == "media_play":
            return "playing", {}
        if service == "media_pause":
            return "paused", {}
        if service == "media_stop":
            return "idle", {}
        if service == "volume_set" and _num(data.get("volume_level")) is not None:
            return state, {"volume_level": _num(data["volume_level"])}
        return None
    if ent == "vacuum":
        return {"start": ("cleaning", {}), "pause": ("paused", {}), "stop": ("idle", {}),
                "return_to_base": ("returning", {})}.get(service)
    if ent == "input_datetime" and service == "set_datetime":
        for key in ("datetime", "date", "time"):
            if key in data:
                return str(data[key]), {}
        return None
    if ent == "valve":
        return {"open_valve": ("open", {}), "close_valve": ("closed", {})}.get(service)
    return None


def dry_run(
    config: dict[str, Any], runs: list[Any], store: HistoryStore, start: datetime, end: datetime, tz, sun=None
) -> tuple[ActionSimulator, list[tuple[list[Step], str | None]]]:
    """Dry-run the actions of every executed run, in time order."""
    sim = ActionSimulator(config, store, start, end, tz, sun)
    out = []
    for idx, run in enumerate(runs):
        if run.status != "executed" or not sim.actions:
            out.append(([], None))
            continue
        out.append(sim.simulate(idx, run.time, run.variables))
    return sim, out


__all__ = ["ActionSimulator", "Step", "controlled_entities", "dry_run", "service_effect"]
