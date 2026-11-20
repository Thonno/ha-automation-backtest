"""Purpose-specific triggers and conditions (HA 2025.12+), e.g.

    trigger: vacuum.started_cleaning        condition: vacuum.is_docked
    target: {entity_id: vacuum.x}           target: {area_id: kitchen}
    options: {behavior: each, for: ...}     options: {behavior: any}

They are translated into checks on recorded states/attributes. The adapter
resolves `target` (entities, devices, areas, floors, labels) into the list of
matching entities and stores it as `_entities`; without it, plain
`target.entity_id` is used. Purpose triggers that depend on events or
astronomy (sun, calendar, timers finishing, zones...) are reported as
unsupported rather than guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .conditions import EvalContext
from .history import StateChange, StateSnapshot
from .util import UnsupportedFeature, as_list, norm_state, parse_duration, to_float

_DEAD = {"unavailable", "unknown"}

# --------------------------------------------------------------------------- values


def _state(snap: StateSnapshot | None) -> Any:
    return snap.state if snap else None


def _attr(name: str) -> Callable[[StateSnapshot | None], Any]:
    return lambda snap: snap.attributes.get(name) if snap else None


def _num_state(snap: StateSnapshot | None) -> float | None:
    return to_float(snap.state) if snap else None


def _num_attr(name: str, scale: float = 1.0) -> Callable[[StateSnapshot | None], float | None]:
    def get(snap: StateSnapshot | None) -> float | None:
        value = to_float(snap.attributes.get(name)) if snap else None
        return None if value is None else round(value * scale, 4)

    return get


def _open_closed(snap: StateSnapshot | None) -> Any:
    """Doors/windows/gates can be binary sensors (on/off) or covers (open/closed)."""
    if snap is None:
        return None
    if snap.domain == "binary_sensor":
        return {"on": "open", "off": "closed"}.get(snap.state, snap.state)
    if snap.state in ("open", "opening"):
        return "open"
    return snap.state


@dataclass(frozen=True)
class Spec:
    domains: tuple[str, ...]
    kind: str  # enter | leave | change | num_changed | num_crossed | delta_up | delta_down
    states: frozenset = frozenset()
    value: Callable[[StateSnapshot | None], Any] = _state
    device_classes: tuple[str, ...] | None = None
    to_excluded: frozenset = frozenset()


def _enter(domains, states, value=_state, dc=None):
    return Spec(tuple(as_list(domains)), "enter", frozenset(as_list(states)), value, dc)


def _leave(domains, states, value=_state, dc=None, to_excluded=()):
    return Spec(tuple(as_list(domains)), "leave", frozenset(as_list(states)), value, dc, frozenset(to_excluded))


def _change(domains, value=_state, dc=None):
    return Spec(tuple(as_list(domains)), "change", value=value, device_classes=dc)


def _num(domains, value, crossed: bool, dc=None):
    return Spec(tuple(as_list(domains)), "num_crossed" if crossed else "num_changed", value=value, device_classes=dc)


ON_OFF = ("light", "switch", "fan", "remote", "siren", "input_boolean")
ARMED = ("armed_away", "armed_home", "armed_night", "armed_vacation", "armed_custom_bypass")

TRIGGERS: dict[str, Spec] = {}

for _d in ("light", "switch", "fan", "remote", "siren", "humidifier"):
    TRIGGERS[f"{_d}.turned_on"] = _enter(_d, "on")
    TRIGGERS[f"{_d}.turned_off"] = _enter(_d, "off")
for _d in ("climate", "water_heater", "media_player"):
    TRIGGERS[f"{_d}.turned_on"] = _leave(_d, "off", to_excluded=("off",))
    TRIGGERS[f"{_d}.turned_off"] = _enter(_d, "off")

TRIGGERS.update(
    {
        # media player
        "media_player.started_playing": _enter("media_player", "playing"),
        "media_player.paused_playing": _enter("media_player", "paused"),
        "media_player.stopped_playing": _leave("media_player", "playing", to_excluded=("paused",)),
        "media_player.muted": _enter("media_player", True, _attr("is_volume_muted")),
        "media_player.unmuted": _enter("media_player", False, _attr("is_volume_muted")),
        "media_player.volume_changed": _num("media_player", _num_attr("volume_level", 100), False),
        "media_player.volume_crossed_threshold": _num("media_player", _num_attr("volume_level", 100), True),
        # vacuum / lawn mower
        "vacuum.started_cleaning": _enter("vacuum", "cleaning"),
        "vacuum.paused_cleaning": _enter("vacuum", "paused"),
        "vacuum.returned_to_dock": _enter("vacuum", "docked"),
        "vacuum.started_returning": _enter("vacuum", "returning"),
        "vacuum.errored": _enter("vacuum", "error"),
        "lawn_mower.started_mowing": _enter("lawn_mower", "mowing"),
        "lawn_mower.paused_mowing": _enter("lawn_mower", "paused"),
        "lawn_mower.returned_to_dock": _enter("lawn_mower", "docked"),
        "lawn_mower.started_returning": _enter("lawn_mower", "returning"),
        "lawn_mower.errored": _enter("lawn_mower", "error"),
        "lawn_mower.became_idle": _enter("lawn_mower", "idle"),
        # light
        "light.brightness_changed": _num("light", _num_attr("brightness", 100 / 255), False),
        "light.brightness_crossed_threshold": _num("light", _num_attr("brightness", 100 / 255), True),
        # climate / humidifier / water heater
        "climate.hvac_mode_changed": _change("climate"),
        "climate.started_heating": _enter("climate", "heating", _attr("hvac_action")),
        "climate.started_cooling": _enter("climate", "cooling", _attr("hvac_action")),
        "climate.started_drying": _enter("climate", "drying", _attr("hvac_action")),
        "climate.target_temperature_changed": _num("climate", _num_attr("temperature"), False),
        "climate.target_temperature_crossed_threshold": _num("climate", _num_attr("temperature"), True),
        "climate.target_humidity_changed": _num("climate", _num_attr("humidity"), False),
        "climate.target_humidity_crossed_threshold": _num("climate", _num_attr("humidity"), True),
        "humidifier.started_humidifying": _enter("humidifier", "humidifying", _attr("action")),
        "humidifier.started_drying": _enter("humidifier", "drying", _attr("action")),
        "humidifier.mode_changed": _change("humidifier", _attr("mode")),
        "water_heater.operation_mode_changed": _change("water_heater"),
        "water_heater.target_temperature_changed": _num("water_heater", _num_attr("temperature"), False),
        "water_heater.target_temperature_crossed_threshold": _num("water_heater", _num_attr("temperature"), True),
        # lock / alarm / valve / satellite
        "lock.locked": _enter("lock", "locked"),
        "lock.unlocked": _enter("lock", "unlocked"),
        "lock.jammed": _enter("lock", "jammed"),
        "lock.opened": _enter("lock", "open"),
        "alarm_control_panel.armed": _enter("alarm_control_panel", ARMED),
        "alarm_control_panel.disarmed": _enter("alarm_control_panel", "disarmed"),
        "alarm_control_panel.triggered": _enter("alarm_control_panel", "triggered"),
        "valve.opened": _enter("valve", "open"),
        "valve.closed": _enter("valve", "closed"),
        # helpers & simple entities
        "select.selection_changed": _change("select"),
        "text.changed": _change("text"),
        "scene.activated": _change("scene"),
        "button.pressed": _change("button"),
        "event.received": _change("event"),
        "doorbell.rang": _change("event", dc=("doorbell",)),
        "update.became_available": _enter("update", "on"),
        "schedule.block_started": _enter("schedule", "on"),
        "schedule.block_ended": _enter("schedule", "off"),
        "timer.started": _enter("timer", "active"),
        "timer.paused": _enter("timer", "paused"),
        "counter.incremented": Spec(("counter",), "delta_up", value=_num_state),
        "counter.decremented": Spec(("counter",), "delta_down", value=_num_state),
        # battery
        "battery.became_low": _enter("binary_sensor", "on", dc=("battery",)),
        "battery.no_longer_low": _enter("binary_sensor", "off", dc=("battery",)),
        "battery.started_charging": _enter("binary_sensor", "on", dc=("battery_charging",)),
        "battery.stopped_charging": _enter("binary_sensor", "off", dc=("battery_charging",)),
        "battery.level_changed": _num("sensor", _num_state, False, ("battery",)),
        "battery.level_crossed_threshold": _num("sensor", _num_state, True, ("battery",)),
    }
)
for _d in ("alarm_control_panel",):
    for _s in ARMED:
        TRIGGERS[f"{_d}.{_s}"] = _enter(_d, _s)
for _s in ("idle", "listening", "processing", "responding"):
    TRIGGERS[f"assist_satellite.{_s}"] = _enter("assist_satellite", _s)
for _kind in ("awning", "blind", "curtain", "shade", "shutter"):
    TRIGGERS[f"cover.{_kind}_opened"] = _enter("cover", "open", _open_closed, (_kind,))
    TRIGGERS[f"cover.{_kind}_closed"] = _enter("cover", "closed", _open_closed, (_kind,))
for _kind, _dcs in {
    "door": ("door",), "window": ("window",), "garage_door": ("garage_door", "garage"), "gate": ("gate", "opening"),
}.items():
    TRIGGERS[f"{_kind}.opened"] = _enter(("binary_sensor", "cover"), "open", _open_closed, _dcs)
    TRIGGERS[f"{_kind}.closed"] = _enter(("binary_sensor", "cover"), "closed", _open_closed, _dcs)
for _kind, _dc in {"motion": "motion", "occupancy": "occupancy", "moisture": "moisture", "vibration": "vibration", "illuminance": "light"}.items():
    TRIGGERS[f"{_kind}.detected"] = _enter("binary_sensor", "on", dc=(_dc,))
    TRIGGERS[f"{_kind}.cleared"] = _enter("binary_sensor", "off", dc=(_dc,))
for _kind, _dc in {
    "humidity": "humidity", "temperature": "temperature", "power": "power", "illuminance": "illuminance",
    "moisture": "moisture",
}.items():
    TRIGGERS[f"{_kind}.changed"] = _num("sensor", _num_state, False, (_dc,))
    TRIGGERS[f"{_kind}.crossed_threshold"] = _num("sensor", _num_state, True, (_dc,))
for _gas, _dc in {"co": "carbon_monoxide", "gas": "gas", "smoke": "smoke"}.items():
    TRIGGERS[f"air_quality.{_gas}_detected"] = _enter("binary_sensor", "on", dc=(_dc,))
    TRIGGERS[f"air_quality.{_gas}_cleared"] = _enter("binary_sensor", "off", dc=(_dc,))
for _q, _dc in {
    "co2": "carbon_dioxide", "co": "carbon_monoxide", "n2o": "nitrous_oxide", "no2": "nitrogen_dioxide",
    "no": "nitrogen_monoxide", "ozone": "ozone", "pm1": "pm1", "pm10": "pm10", "pm25": "pm25", "pm4": "pm4",
    "so2": "sulphur_dioxide", "voc": "volatile_organic_compounds", "voc_ratio": "volatile_organic_compounds_parts",
    "radon": "radon",
}.items():
    TRIGGERS[f"air_quality.{_q}_changed"] = _num("sensor", _num_state, False, (_dc,))
    TRIGGERS[f"air_quality.{_q}_crossed_threshold"] = _num("sensor", _num_state, True, (_dc,))

NOT_REPLAYABLE = {
    "sun": "depends on the sun position, which is not recorded",
    "moon": "depends on the moon phase calculation",
    "calendar": "depends on calendar events, which are not in state history",
    "todo": "depends on to-do list events",
    "zone": "zone triggers are not supported yet",
    "zwave_js": "Z-Wave events are not in state history",
    "fumis": "integration-specific trigger",
}

# --------------------------------------------------------------------------- conditions

STATE_SETS: dict[str, dict[str, frozenset]] = {
    "vacuum": {s: frozenset([s]) for s in ("cleaning", "docked", "paused", "returning", "idle")}
    | {"encountering_an_error": frozenset(["error"])},
    "lawn_mower": {s: frozenset([s]) for s in ("mowing", "docked", "paused", "returning", "idle")}
    | {"encountering_an_error": frozenset(["error"])},
    "lock": {s: frozenset([s]) for s in ("locked", "unlocked", "jammed", "locking", "unlocking")}
    | {"open": frozenset(["open"])},
    "alarm_control_panel": {s: frozenset([s]) for s in (*ARMED, "disarmed", "triggered", "pending", "arming")}
    | {"armed": frozenset(ARMED)},
    "assist_satellite": {s: frozenset([s]) for s in ("idle", "listening", "processing", "responding")},
    "valve": {"open": frozenset(["open"]), "closed": frozenset(["closed"])},
    "timer": {"active": frozenset(["active"]), "paused": frozenset(["paused"]), "idle": frozenset(["idle"])},
    "media_player": {"playing": frozenset(["playing"]), "paused": frozenset(["paused"]), "off": frozenset(["off"])},
}


def _condition_spec(name: str, cond: dict[str, Any]) -> Spec:
    domain, _, what = name.partition(".")
    if not what.startswith("is_"):
        raise UnsupportedFeature(f"Condition '{name}' is not supported yet")
    what = what[3:]
    if domain == "media_player":
        if what == "on":
            return _leave("media_player", "off")
        if what == "not_playing":
            return _leave("media_player", "playing")
        if what == "muted":
            return _enter("media_player", True, _attr("is_volume_muted"))
        if what == "unmuted":
            return _enter("media_player", False, _attr("is_volume_muted"))
        if what == "volume":
            return _num("media_player", _num_attr("volume_level", 100), False)
        if what == "current_source":
            source = (cond.get("options") or {}).get("source")
            if source is None:
                raise UnsupportedFeature("media_player.is_current_source without a source option")
            return _enter("media_player", as_list(source), _attr("source"))
    if domain in ON_OFF + ("humidifier",) and what in ("on", "off"):
        return _enter(domain, what)
    if domain in ("climate", "water_heater") and what in ("on", "off"):
        return _leave(domain, "off") if what == "on" else _enter(domain, "off")
    if domain == "climate" and what in ("heating", "cooling", "drying"):
        return _enter("climate", what, _attr("hvac_action"))
    if domain in ("door", "window", "garage_door", "gate") and what in ("open", "closed"):
        return Spec(("binary_sensor", "cover"), "enter", frozenset([what]), _open_closed,
                    TRIGGERS[f"{domain}.opened"].device_classes)
    if domain in ("motion", "occupancy", "moisture", "vibration") and what in ("detected", "cleared"):
        return _enter("binary_sensor", "on" if what == "detected" else "off", dc=(domain,))
    if domain in STATE_SETS and what in STATE_SETS[domain]:
        return _enter(domain, STATE_SETS[domain][what])
    raise UnsupportedFeature(f"Condition '{name}' is not supported yet")


def entity_filter(name: str, config: dict[str, Any] | None = None) -> tuple[tuple[str, ...], tuple[str, ...] | None] | None:
    """(domains, device_classes) whose entities a target should be narrowed to."""
    spec = TRIGGERS.get(name)
    if spec is None:
        try:
            spec = _condition_spec(name, config or {})
        except UnsupportedFeature:
            return None
    return spec.domains, spec.device_classes


def is_purpose(name: Any) -> bool:
    return isinstance(name, str) and "." in name and not name.startswith("homeassistant.")


# --------------------------------------------------------------------------- shared helpers


def _entities(config: dict[str, Any]) -> list[str]:
    if config.get("_entities") is not None:
        return list(config["_entities"])
    target = config.get("target") or {}
    return [e for e in as_list(target.get("entity_id")) if isinstance(e, str) and "." in e]


def _options(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("options") or {}


def _limit(spec: Any, ctx: EvalContext) -> float | None:
    if isinstance(spec, dict):
        if "number" in spec:
            return to_float(spec["number"])
        if "entity" in spec:
            snap = ctx.states.get(spec["entity"])
            return to_float(snap.state) if snap else None
    return to_float(spec)


def threshold_match(value: float | None, threshold: dict[str, Any] | None, ctx: EvalContext) -> bool:
    if value is None:
        return False
    threshold = threshold or {"type": "any"}
    kind = threshold.get("type", "any")
    if kind == "any":
        return True
    if kind in ("above", "below"):
        limit = _limit(threshold.get("value"), ctx)
        if limit is None:
            return False
        return value > limit if kind == "above" else value < limit
    low, high = _limit(threshold.get("value_min"), ctx), _limit(threshold.get("value_max"), ctx)
    if low is None or high is None:
        return False
    if kind == "between":
        return low <= value <= high
    if kind == "outside":
        return value < low or value > high
    raise UnsupportedFeature(f"Threshold type '{kind}' is not supported")


def _describe_threshold(threshold: dict[str, Any] | None) -> str:
    threshold = threshold or {"type": "any"}
    kind = threshold.get("type", "any")
    if kind == "any":
        return "any value"
    if kind in ("above", "below"):
        value = threshold.get("value")
        shown = value.get("number", value.get("entity")) if isinstance(value, dict) else value
        return f"{'>' if kind == 'above' else '<'} {shown}"
    return f"{kind} {threshold.get('value_min')}–{threshold.get('value_max')}"


def _matches(spec: Spec, snap: StateSnapshot | None, ctx: EvalContext, threshold=None) -> bool:
    if snap is None or snap.state in _DEAD:
        return False
    value = spec.value(snap)
    if spec.kind == "enter":
        return norm_state(value) in {norm_state(s) for s in spec.states}
    if spec.kind == "leave":
        return norm_state(value) not in {norm_state(s) for s in spec.states}
    if spec.kind in ("num_changed", "num_crossed"):
        return threshold_match(value, threshold, ctx)
    return True


# --------------------------------------------------------------------------- trigger


def make_purpose_trigger(base_cls, raw: dict[str, Any], index: int):
    name = raw.get("trigger") or raw.get("platform")
    domain = name.split(".", 1)[0]
    if domain in NOT_REPLAYABLE:
        raise UnsupportedFeature(f"Trigger '{name}' {NOT_REPLAYABLE[domain]}")
    spec = TRIGGERS.get(name)
    if spec is None:
        raise UnsupportedFeature(f"Trigger '{name}' cannot be replayed from state history (yet)")

    class _Purpose(base_cls):
        platform = name

        def __init__(self) -> None:
            super().__init__(raw, index)
            self.spec = spec
            self.entity_ids = _entities(raw)
            if not self.entity_ids:
                raise UnsupportedFeature(f"Trigger '{name}': the target matches no {'/'.join(spec.domains)} entity")
            options = _options(raw)
            self.behavior = options.get("behavior", "each")
            self.threshold = options.get("threshold")
            self.duration = parse_duration(options.get("for"))
            self._pending: dict[str, tuple[int, dict, str]] = {}

        def _fires(self, change: StateChange, ctx: EvalContext) -> bool:
            old, new = change.old, change.new
            if old is None or new is None or old.state in _DEAD or new.state in _DEAD:
                return False
            kind = self.spec.kind
            value = self.spec.value
            if kind == "enter":
                return not _matches(self.spec, old, ctx) and _matches(self.spec, new, ctx)
            if kind == "leave":
                if norm_state(value(new)) in {norm_state(s) for s in self.spec.to_excluded}:
                    return False
                inside = {norm_state(s) for s in self.spec.states}
                return norm_state(value(old)) in inside and norm_state(value(new)) not in inside
            if kind == "change":
                return value(old) != value(new)
            if kind == "num_changed":
                v_old, v_new = value(old), value(new)
                return v_new is not None and v_new != v_old and threshold_match(v_new, self.threshold, ctx)
            if kind == "num_crossed":
                v_old, v_new = value(old), value(new)
                return (v_old is not None and not threshold_match(v_old, self.threshold, ctx)
                        and threshold_match(v_new, self.threshold, ctx))
            if kind in ("delta_up", "delta_down"):
                v_old, v_new = value(old), value(new)
                if v_old is None or v_new is None:
                    return False
                return v_new > v_old if kind == "delta_up" else v_new < v_old
            return False

        def _holds(self, entity_id: str, ctx: EvalContext) -> bool:
            snap = ctx.states.get(entity_id)
            if self.spec.kind in ("enter", "leave", "num_changed", "num_crossed"):
                return _matches(self.spec, snap, ctx, self.threshold)
            return snap is not None and snap.state not in _DEAD

        def _behavior_ok(self, entity_id: str, ctx: EvalContext) -> bool:
            if self.behavior == "each" or len(self.entity_ids) == 1:
                return True
            others = [e for e in self.entity_ids if e != entity_id]
            if self.behavior == "first":
                return not any(self._holds(e, ctx) for e in others)
            if self.behavior == "all":
                return all(self._holds(e, ctx) for e in others)
            return True

        def on_change(self, change: StateChange, ctx: EvalContext):
            from .triggers import Firing, TimerRequest, TriggerOutput

            out = TriggerOutput()
            if change.entity_id not in self.entity_ids:
                return out
            if change.entity_id in self._pending and not self._holds(change.entity_id, ctx):
                del self._pending[change.entity_id]
            if not self._fires(change, ctx) or not self._behavior_ok(change.entity_id, ctx):
                return out
            value = self.spec.value
            desc = f"{change.entity_id}: {value(change.old)} → {value(change.new)}"
            if self.spec.kind in ("num_changed", "num_crossed"):
                desc += f" ({_describe_threshold(self.threshold)})"
            variables = self.variables(
                entity_id=change.entity_id,
                from_state=change.old.as_dict() if change.old else None,
                to_state=change.new.as_dict() if change.new else None,
            )
            if self.duration:
                token = self.next_token()
                self._pending[change.entity_id] = (token, variables, desc)
                out.timers.append(TimerRequest(change.time + self.duration, change.entity_id, token))
            else:
                out.firings.append(Firing(change.time, variables, desc))
            return out

        def on_timer(self, key, token, ctx: EvalContext):
            from .triggers import Firing, TriggerOutput

            pending = self._pending.get(key)
            if pending is None or pending[0] != token:
                return TriggerOutput()
            del self._pending[key]
            _, variables, desc = pending
            return TriggerOutput(firings=[Firing(ctx.now, variables, f"{desc} (held {self.duration})")])

    return _Purpose()


# --------------------------------------------------------------------------- condition


def evaluate_purpose_condition(cond: dict[str, Any], ctx: EvalContext) -> tuple[bool | None, str]:
    name = cond["condition"]
    domain = name.split(".", 1)[0]
    if domain in NOT_REPLAYABLE:
        raise UnsupportedFeature(f"Condition '{name}' {NOT_REPLAYABLE[domain]}")
    spec = _condition_spec(name, cond)
    entity_ids = _entities(cond)
    if not entity_ids:
        raise UnsupportedFeature(f"Condition '{name}': the target matches no {'/'.join(spec.domains)} entity")
    options = _options(cond)
    behavior = options.get("behavior", "any")
    duration = parse_duration(options.get("for"))
    threshold = options.get("threshold")
    results, details = [], []
    for entity_id in entity_ids:
        snap = ctx.states.get(entity_id)
        ok = _matches(spec, snap, ctx, threshold)
        if ok and duration is not None and snap is not None and snap.last_changed is not None:
            held = ctx.now - snap.last_changed
            if held < duration:
                ok = False
                details.append(f"{entity_id}={spec.value(snap)} only for {held}, needs {duration}")
                results.append(False)
                continue
        results.append(ok)
        details.append(f"{entity_id}={spec.value(snap) if snap else 'no state'}")
    passed = all(results) if behavior == "all" else any(results)
    extra = f", {_describe_threshold(threshold)}" if spec.kind in ("num_changed", "num_crossed") else ""
    return passed, f"{', '.join(details)} ({behavior}{extra})"
