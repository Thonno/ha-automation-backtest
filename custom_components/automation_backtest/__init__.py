"""Automation Backtest: backtest automations against recorded history.

Exposes two response-only actions:
  automation_backtest.run – when would this automation have run, and why not?
  automation_backtest.compare  – how would an edited version behave differently?
No automation action is ever executed.

Plus a sidebar panel ("Backtest") backed by websocket commands.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv

from . import runner
from .const import (
    ATTR_AUTOMATION,
    ATTR_CONFIG,
    ATTR_CONFIG_B,
    ATTR_DAYS,
    ATTR_END,
    ATTR_INCLUDE_RUNS,
    ATTR_MAX_RUNS,
    ATTR_START,
    DEFAULT_DAYS,
    DEFAULT_MAX_RUNS,
    DOMAIN,
    MAX_DAYS,
    SERVICE_BACKTEST,
    SERVICE_COMPARE,
    ATTR_SKIP_CONDITIONS,
)
from .engine import apply_skips, compare
from .panel import async_register_panel, async_unregister_panel
from .websocket import async_register_websocket

_SKIP = {vol.Optional(ATTR_SKIP_CONDITIONS): vol.All(cv.ensure_list, [cv.string])}

_PERIOD = {
    vol.Optional(ATTR_START): cv.datetime,
    vol.Optional(ATTR_END): cv.datetime,
    vol.Optional(ATTR_DAYS, default=DEFAULT_DAYS): vol.All(
        vol.Coerce(float), vol.Range(min=0.01, max=MAX_DAYS)
    ),
}

BACKTEST_SCHEMA = vol.Schema(
    {
        vol.Exclusive(ATTR_AUTOMATION, "source"): cv.entity_id,
        vol.Exclusive(ATTR_CONFIG, "source"): dict,
        vol.Optional(ATTR_INCLUDE_RUNS, default=True): cv.boolean,
        vol.Optional(ATTR_MAX_RUNS, default=DEFAULT_MAX_RUNS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=5000)
        ),
        **_SKIP,
        **_PERIOD,
    }
)

COMPARE_SCHEMA = vol.Schema(
    {
        vol.Exclusive(ATTR_AUTOMATION, "a"): cv.entity_id,
        vol.Exclusive(ATTR_CONFIG, "a"): dict,
        vol.Required(ATTR_CONFIG_B): dict,
        **_SKIP,
        **_PERIOD,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    async def handle_backtest(call: ServiceCall) -> ServiceResponse:
        config = await runner.automation_config(hass, call.data)
        config, skipped = apply_skips(config, call.data.get(ATTR_SKIP_CONDITIONS))
        start, end, tz = runner.period(hass, call.data)
        result = await runner.run(hass, config, start, end, tz)
        response = result.as_dict(
            include_runs=call.data[ATTR_INCLUDE_RUNS], max_runs=call.data[ATTR_MAX_RUNS]
        )
        response["timeline"] = runner.timeline(result, call.data[ATTR_MAX_RUNS])
        response["skipped_conditions"] = skipped
        return response

    async def handle_compare(call: ServiceCall) -> ServiceResponse:
        config_a = await runner.automation_config(hass, call.data)
        config_b = runner.resolve_registry_ids(hass, call.data[ATTR_CONFIG_B])
        skip = call.data.get(ATTR_SKIP_CONDITIONS)
        config_a, skipped_a = apply_skips(config_a, skip)
        config_b, skipped_b = apply_skips(config_b, skip)
        start, end, tz = runner.period(hass, call.data)
        result_a = await runner.run(hass, config_a, start, end, tz)
        result_b = await runner.run(hass, config_b, start, end, tz)
        diff = compare(result_a, result_b)
        diff["a"] = result_a.as_dict(include_runs=False)
        diff["b"] = result_b.as_dict(include_runs=False)
        diff["skipped_conditions"] = sorted(set(skipped_a) | set(skipped_b))
        return diff

    hass.services.async_register(
        DOMAIN, SERVICE_BACKTEST, handle_backtest, schema=BACKTEST_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_COMPARE, handle_compare, schema=COMPARE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    async_register_websocket(hass)
    await async_register_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.services.async_remove(DOMAIN, SERVICE_BACKTEST)
    hass.services.async_remove(DOMAIN, SERVICE_COMPARE)
    async_unregister_panel(hass)
    return True
