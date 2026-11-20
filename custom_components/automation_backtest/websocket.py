"""Websocket API used by the sidebar panel.

automation_backtest/config   -> the automation's trigger/condition config as YAML
automation_backtest/run      -> full backtest (runs + traces + entities + thresholds)
automation_backtest/compare  -> A vs B, with the runs of both for the chart
automation_backtest/to_yaml  -> editor config (unsaved draft) -> editable YAML
automation_backtest/from_yaml -> YAML -> triggers/conditions objects (visual editor)
YAML is parsed server-side so the panel needs no YAML library.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import dump, parse_yaml

from . import runner
from .const import (
    ATTR_AUTOMATION,
    ATTR_DAYS,
    ATTR_END,
    ATTR_START,
    DEFAULT_DAYS,
    DOMAIN,
    MAX_DAYS,
    PANEL_MAX_RUNS,
)
from .engine import compare, extract_entities, extract_thresholds

_REGISTERED = f"{DOMAIN}_ws_registered"
_EDITABLE_KEYS = ("triggers", "trigger", "conditions", "condition", "actions", "action")

_PERIOD = {
    vol.Optional("start"): str,
    vol.Optional("end"): str,
    vol.Optional("days", default=DEFAULT_DAYS): vol.All(
        vol.Coerce(float), vol.Range(min=0.01, max=MAX_DAYS)
    ),
}


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    if hass.data.get(_REGISTERED):
        return
    websocket_api.async_register_command(hass, ws_config)
    websocket_api.async_register_command(hass, ws_run)
    websocket_api.async_register_command(hass, ws_compare)
    websocket_api.async_register_command(hass, ws_to_yaml)
    websocket_api.async_register_command(hass, ws_from_yaml)
    hass.data[_REGISTERED] = True


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        raise HomeAssistantError(f"Invalid date/time: {value}")
    return parsed


def _period_data(msg: dict[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {ATTR_DAYS: msg["days"]}
    if start := _parse_dt(msg.get("start")):
        data[ATTR_START] = start
    if end := _parse_dt(msg.get("end")):
        data[ATTR_END] = end
    return data


def _yaml_to_config(text: str) -> dict[str, Any]:
    try:
        parsed = parse_yaml(text)
    except HomeAssistantError as err:
        raise HomeAssistantError(f"YAML error: {err}") from err
    if not isinstance(parsed, dict):
        raise HomeAssistantError("The YAML must be a mapping with triggers/conditions")
    return parsed


async def _source_config(
    hass: HomeAssistant, msg: dict[str, Any], yaml_key: str, obj_key: str = "config"
) -> dict[str, Any]:
    if msg.get(obj_key):
        config = runner.resolve_registry_ids(hass, msg[obj_key])
    elif msg.get(yaml_key):
        config = runner.resolve_registry_ids(hass, _yaml_to_config(msg[yaml_key]))
    else:
        return await runner.automation_config(hass, {ATTR_AUTOMATION: msg.get("automation")})
    return _with_saved_actions(hass, config, msg.get("actions_from") or msg.get("automation"))


def _with_saved_actions(hass: HomeAssistant, config: dict[str, Any], entity_id: str | None) -> dict[str, Any]:
    """Fill what a draft does not carry from the saved automation: mode always, actions if absent."""
    if not entity_id:
        return config
    has_actions = "actions" in config or "action" in config
    if has_actions and "mode" in config:
        return config
    try:
        saved = runner.resolve_registry_ids(hass, runner.raw_automation_config(hass, entity_id))
    except HomeAssistantError:
        return config
    keys = ("mode",) if has_actions else ("actions", "action", "mode")
    extra = {k: saved[k] for k in keys if k in saved and k not in config}
    return {**config, **extra}


def _full_result(result, config: dict[str, Any]) -> dict[str, Any]:
    out = result.as_dict(include_runs=True, max_runs=PANEL_MAX_RUNS)
    out["entities"] = sorted(extract_entities(config))
    out["thresholds"] = extract_thresholds(config)
    return out


def _error(connection, msg_id: int, err: Exception) -> None:
    connection.send_error(msg_id, "backtest_failed", str(err))


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/config", vol.Required("automation"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_config(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    try:
        raw = runner.raw_automation_config(hass, msg["automation"])
    except HomeAssistantError as err:
        _error(connection, msg["id"], err)
        return
    resolved = runner.resolve_registry_ids(hass, raw)
    editable = {k: resolved[k] for k in _EDITABLE_KEYS if k in resolved}
    connection.send_result(
        msg["id"],
        {
            "alias": raw.get("alias"),
            "id": raw.get("id"),
            "mode": raw.get("mode"),
            "yaml": dump(editable),
            # Untouched copy for the visual editor (device automations keep registry ids).
            "config": runner.editable_part(raw),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/run",
        vol.Exclusive("automation", "source"): str,
        vol.Exclusive("config_yaml", "source"): str,
        vol.Exclusive("config", "source"): dict,
        vol.Optional("actions_from"): str,
        **_PERIOD,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_run(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    try:
        config = await _source_config(hass, msg, "config_yaml")
        start, end, tz = runner.period(hass, _period_data(msg))
        result = await runner.run(hass, config, start, end, tz)
    except HomeAssistantError as err:
        _error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"], _full_result(result, config))


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/compare",
        vol.Exclusive("automation", "a"): str,
        vol.Exclusive("config_a_yaml", "a"): str,
        vol.Exclusive("config_b_yaml", "b"): str,
        vol.Exclusive("config_b", "b"): dict,
        vol.Optional("actions_from"): str,
        **_PERIOD,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_compare(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    try:
        config_a = await _source_config(hass, msg, "config_a_yaml", "config_a")
        if not msg.get("config_b") and not msg.get("config_b_yaml"):
            raise HomeAssistantError("Version B is missing")
        config_b = await _source_config(hass, msg, "config_b_yaml", "config_b")
        start, end, tz = runner.period(hass, _period_data(msg))
        result_a = await runner.run(hass, config_a, start, end, tz)
        result_b = await runner.run(hass, config_b, start, end, tz)
    except HomeAssistantError as err:
        _error(connection, msg["id"], err)
        return
    merged = {**config_a, "_b": config_b}
    connection.send_result(
        msg["id"],
        {
            "diff": compare(result_a, result_b),
            "a": _full_result(result_a, config_a),
            "b": _full_result(result_b, config_b),
            "entities": sorted(extract_entities(merged)),
            "thresholds": extract_thresholds(merged),
        },
    )


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/to_yaml", vol.Required("config"): vol.Any(dict, None)}
)
@websocket_api.require_admin
@callback
def ws_to_yaml(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Turn an editor config (possibly unsaved) into the editable YAML."""
    config = runner.resolve_registry_ids(hass, msg["config"] or {})
    editable = {k: config[k] for k in _EDITABLE_KEYS if k in config}
    connection.send_result(msg["id"], {"yaml": dump(editable) if editable else ""})


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/from_yaml", vol.Required("yaml"): str}
)
@websocket_api.require_admin
@callback
def ws_from_yaml(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """YAML text -> triggers/conditions objects, for switching to the visual editor."""
    try:
        config = _yaml_to_config(msg["yaml"]) if msg["yaml"].strip() else {}
    except HomeAssistantError as err:
        _error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"], {"config": runner.editable_part(config)})
