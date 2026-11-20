"""Translate device triggers/conditions (UI editor) into state-based ones.

Only device automations that map 1:1 onto an entity state or attribute are
translated. Event-based ones (e.g. remote button presses) are not in state
history and are reported as unsupported.
"""

from __future__ import annotations

from typing import Any

from .util import UnsupportedFeature

_GENERIC_ON_OFF = {
    "turned_on": "on",
    "turned_off": "off",
    "is_on": "on",
    "is_off": "off",
}

_DOMAIN_STATES = {
    "cover": {
        "opened": "open", "closed": "closed", "opening": "opening", "closing": "closing",
        "is_open": "open", "is_closed": "closed", "is_opening": "opening", "is_closing": "closing",
    },
    "lock": {
        "locked": "locked", "unlocked": "unlocked", "jammed": "jammed",
        "is_locked": "locked", "is_unlocked": "unlocked", "is_jammed": "jammed",
    },
    "vacuum": {
        "cleaning": "cleaning", "docked": "docked",
        "is_cleaning": "cleaning", "is_docked": "docked",
    },
    "media_player": {
        "playing": "playing", "paused": "paused", "idle": "idle",
        "is_playing": "playing", "is_paused": "paused", "is_idle": "idle",
    },
}

# Conditions that compare a value from the device config with the entity.
# (domain, type) -> (config key holding the wanted value, attribute or None for state)
_VALUE_CONDITIONS = {
    ("humidifier", "is_mode"): ("mode", "mode"),
    ("climate", "is_hvac_mode"): ("hvac_mode", None),
    ("climate", "is_preset_mode"): ("preset_mode", "preset_mode"),
}

# Triggers on a state value chosen in the device config.
_VALUE_TRIGGERS = {
    ("climate", "hvac_mode_changed"): ("hvac_mode", None),
}

# Triggers on a numeric attribute (above/below, like numeric_state).
_NUMERIC_TRIGGERS = {
    ("humidifier", "target_humidity_changed"): "humidity",
    ("humidifier", "current_humidity_changed"): "current_humidity",
    ("climate", "current_temperature_changed"): "current_temperature",
    ("climate", "current_humidity_changed"): "current_humidity",
}

_PASSTHROUGH = ("for", "id", "enabled")


def _target_state(domain: str, kind: str) -> str | None:
    if kind in _GENERIC_ON_OFF:
        return _GENERIC_ON_OFF[kind]
    if kind in _DOMAIN_STATES.get(domain, {}):
        return _DOMAIN_STATES[domain][kind]
    if domain == "binary_sensor":
        bare = kind[3:] if kind.startswith("is_") else kind
        return "off" if bare.startswith(("no_", "not_")) else "on"
    return None


def _copy(src: dict[str, Any], dst: dict[str, Any], keys=_PASSTHROUGH) -> dict[str, Any]:
    for key in keys:
        if key in src:
            dst[key] = src[key]
    return dst


def device_trigger_to_state(trigger: dict[str, Any]) -> dict[str, Any]:
    """Return an equivalent native trigger (state or numeric_state)."""
    domain = trigger.get("domain", "")
    kind = trigger.get("type", "")
    entity_id = trigger.get("entity_id")
    if not entity_id:
        raise UnsupportedFeature(
            f"Device trigger '{domain}.{kind}' has no entity (event-based, not in state history)"
        )

    if domain == "sensor":
        # Every sensor device trigger (value, temperature, battery_level, …) is a
        # threshold on the entity state.
        if trigger.get("above") is None and trigger.get("below") is None:
            return _copy(trigger, {"trigger": "state", "entity_id": entity_id, "to": None})
        out = {"trigger": "numeric_state", "entity_id": entity_id}
        return _copy(trigger, out, _PASSTHROUGH + ("above", "below"))

    attribute = _NUMERIC_TRIGGERS.get((domain, kind))
    if attribute is not None:
        if trigger.get("above") is None and trigger.get("below") is None:
            # No threshold: fires on any change of the attribute.
            return _copy(trigger, {"trigger": "state", "entity_id": entity_id, "attribute": attribute})
        out = {"trigger": "numeric_state", "entity_id": entity_id, "attribute": attribute}
        return _copy(trigger, out, _PASSTHROUGH + ("above", "below"))

    out: dict[str, Any] = {"trigger": "state", "entity_id": entity_id}
    value_spec = _VALUE_TRIGGERS.get((domain, kind))
    if value_spec is not None:
        key, attribute = value_spec
        if key not in trigger:
            raise UnsupportedFeature(f"Device trigger '{domain}.{kind}' without '{key}'")
        out["to"] = trigger[key]
        if attribute:
            out["attribute"] = attribute
    elif kind == "changed_states":
        out["to"] = None
    else:
        target = _target_state(domain, kind)
        if target is None:
            raise UnsupportedFeature(f"Device trigger '{domain}.{kind}' is not supported yet")
        out["to"] = target
    return _copy(trigger, out)


def device_condition_to_state(cond: dict[str, Any]) -> dict[str, Any]:
    domain = cond.get("domain", "")
    kind = cond.get("type", "")
    entity_id = cond.get("entity_id")
    if not entity_id:
        raise UnsupportedFeature(f"Device condition '{domain}.{kind}' has no entity")

    if domain == "sensor":
        if cond.get("above") is None and cond.get("below") is None:
            raise UnsupportedFeature(f"Device condition 'sensor.{kind}' without above/below")
        out = {"condition": "numeric_state", "entity_id": entity_id}
        return _copy(cond, out, ("above", "below"))

    value_spec = _VALUE_CONDITIONS.get((domain, kind))
    if value_spec is not None:
        key, attribute = value_spec
        if key not in cond:
            raise UnsupportedFeature(f"Device condition '{domain}.{kind}' without '{key}'")
        out = {"condition": "state", "entity_id": entity_id, "state": cond[key]}
        if attribute:
            out["attribute"] = attribute
        return _copy(cond, out, ("for",))

    target = _target_state(domain, kind)
    if target is None:
        raise UnsupportedFeature(f"Device condition '{domain}.{kind}' is not supported yet")
    return _copy(cond, {"condition": "state", "entity_id": entity_id, "state": target}, ("for",))
