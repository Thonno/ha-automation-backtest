"""Websocket API used by the sidebar panel.

automation_backtest/config   -> the automation's trigger/condition config as YAML
automation_backtest/run      -> full backtest (runs + traces + entities + thresholds)
automation_backtest/compare  -> A vs B, with the runs of both for the chart
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
_EDITABLE_KEYS = ("triggers", "trigger", "conditions", "condition")

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


async def _source_config(hass: HomeAssistant, msg: dict[str, Any], yaml_key: str) -> dict[str, Any]:
    if msg.get(yaml_key):
        return runner.resolve_registry_ids(hass, _yaml_to_config(msg[yaml_key]))
    return await runner.automation_config(hass, {ATTR_AUTOMATION: msg.get("automation")})


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
        config = await runner.automation_config(hass, {ATTR_AUTOMATION: msg["automation"]})
    except HomeAssistantError as err:
        _error(connection, msg["id"], err)
        return
    editable = {k: config[k] for k in _EDITABLE_KEYS if k in config}
    connection.send_result(
        msg["id"], {"alias": config.get("alias"), "yaml": dump(editable), "mode": config.get("mode")}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/run",
        vol.Exclusive("automation", "source"): str,
        vol.Exclusive("config_yaml", "source"): str,
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
        vol.Required("config_b_yaml"): str,
        **_PERIOD,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_compare(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    try:
        config_a = await _source_config(hass, msg, "config_a_yaml")
        config_b = runner.resolve_registry_ids(hass, _yaml_to_config(msg["config_b_yaml"]))
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
