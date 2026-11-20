"""Translate device triggers/conditions (UI editor) into state-based ones.

Only device automations that map 1:1 onto an entity state are translated.
Event-based ones (e.g. remote button presses) are not in state history and
are reported as unsupported.
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
    "media_player": {
        "playing": "playing", "paused": "paused", "idle": "idle",
        "is_playing": "playing", "is_paused": "paused", "is_idle": "idle",
    },
}


def _target_state(domain: str, kind: str) -> str | None:
    if kind in _GENERIC_ON_OFF:
        return _GENERIC_ON_OFF[kind]
    if kind in _DOMAIN_STATES.get(domain, {}):
        return _DOMAIN_STATES[domain][kind]
    if domain == "binary_sensor":
        bare = kind[3:] if kind.startswith("is_") else kind
        return "off" if bare.startswith(("no_", "not_")) else "on"
    return None


def device_trigger_to_state(trigger: dict[str, Any]) -> dict[str, Any]:
    domain = trigger.get("domain", "")
    kind = trigger.get("type", "")
    entity_id = trigger.get("entity_id")
    if not entity_id:
        raise UnsupportedFeature(
            f"Device trigger '{domain}.{kind}' has no entity (event-based, not in state history)"
        )
    out: dict[str, Any] = {"trigger": "state", "entity_id": entity_id}
    if kind == "changed_states":
        out["to"] = None
    else:
        target = _target_state(domain, kind)
        if target is None:
            raise UnsupportedFeature(f"Device trigger '{domain}.{kind}' is not supported yet")
        out["to"] = target
    for key in ("for", "id", "enabled"):
        if key in trigger:
            out[key] = trigger[key]
    return out


def device_condition_to_state(cond: dict[str, Any]) -> dict[str, Any]:
    domain = cond.get("domain", "")
    kind = cond.get("type", "")
    entity_id = cond.get("entity_id")
    target = _target_state(domain, kind)
    if not entity_id or target is None:
        raise UnsupportedFeature(f"Device condition '{domain}.{kind}' is not supported yet")
    out = {"condition": "state", "entity_id": entity_id, "state": target}
    if "for" in cond:
        out["for"] = cond["for"]
    return out
