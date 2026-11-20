"""Automation Backtest: backtest automations against recorded history.

Exposes two response-only actions:
  automation_backtest.run – when would this automation have run, and why not?
  automation_backtest.compare  – how would an edited version behave differently?
No automation action is ever executed.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, tzinfo
from typing import Any

import voluptuous as vol

from homeassistant.components.recorder import get_instance, history
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.util import dt as dt_util

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
)
from .engine import BacktestResult, HistoryStore, StateSnapshot, backtest, compare, extract_entities

_LOGGER = logging.getLogger(__name__)
_REGISTRY_ID = re.compile(r"^[0-9a-f]{32}$")

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
        **_PERIOD,
    }
)

COMPARE_SCHEMA = vol.Schema(
    {
        vol.Exclusive(ATTR_AUTOMATION, "a"): cv.entity_id,
        vol.Exclusive(ATTR_CONFIG, "a"): dict,
        vol.Required(ATTR_CONFIG_B): dict,
        **_PERIOD,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    async def handle_backtest(call: ServiceCall) -> ServiceResponse:
        config = await _automation_config(hass, call.data)
        start, end, tz = _period(hass, call.data)
        result = await _run(hass, config, start, end, tz)
        response = result.as_dict(
            include_runs=call.data[ATTR_INCLUDE_RUNS], max_runs=call.data[ATTR_MAX_RUNS]
        )
        response["timeline"] = _timeline(result, call.data[ATTR_MAX_RUNS])
        return response

    async def handle_compare(call: ServiceCall) -> ServiceResponse:
        config_a = await _automation_config(hass, call.data)
        config_b = _resolve_registry_ids(hass, call.data[ATTR_CONFIG_B])
        start, end, tz = _period(hass, call.data)
        result_a = await _run(hass, config_a, start, end, tz)
        result_b = await _run(hass, config_b, start, end, tz)
        diff = compare(result_a, result_b)
        diff["a"] = result_a.as_dict(include_runs=False)
        diff["b"] = result_b.as_dict(include_runs=False)
        return diff

    hass.services.async_register(
        DOMAIN, SERVICE_BACKTEST, handle_backtest, schema=BACKTEST_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_COMPARE, handle_compare, schema=COMPARE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.services.async_remove(DOMAIN, SERVICE_BACKTEST)
    hass.services.async_remove(DOMAIN, SERVICE_COMPARE)
    return True


# --- helpers -----------------------------------------------------------------


async def _automation_config(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    if ATTR_CONFIG in data:
        return _resolve_registry_ids(hass, data[ATTR_CONFIG])
    entity_id = data.get(ATTR_AUTOMATION)
    if not entity_id:
        raise ServiceValidationError("Provide either 'automation' or 'config'")
    component = hass.data.get("automation")
    entity = component.get_entity(entity_id) if component else None
    raw = getattr(entity, "raw_config", None) if entity else None
    if not raw:
        raise ServiceValidationError(f"Could not read the configuration of {entity_id}")
    return _resolve_registry_ids(hass, dict(raw))


def _resolve_registry_ids(hass: HomeAssistant, config: Any) -> Any:
    """UI device triggers store entity registry ids; turn them back into entity_ids."""
    registry = er.async_get(hass)

    def walk(node: Any, key: str | None = None) -> Any:
        if isinstance(node, dict):
            return {k: walk(v, k) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v, key) for v in node]
        if key == "entity_id" and isinstance(node, str) and _REGISTRY_ID.match(node):
            return er.async_resolve_entity_id(registry, node) or node
        return node

    return walk(config)


def _period(hass: HomeAssistant, data: dict[str, Any]) -> tuple[datetime, datetime, tzinfo]:
    tz = dt_util.get_time_zone(hass.config.time_zone) or dt_util.UTC

    def aware(value: datetime) -> datetime:
        return value.replace(tzinfo=tz) if value.tzinfo is None else value

    end = aware(data[ATTR_END]) if ATTR_END in data else dt_util.now()
    start = aware(data[ATTR_START]) if ATTR_START in data else end - timedelta(days=data[ATTR_DAYS])
    if end <= start:
        raise ServiceValidationError("'end' must be after 'start'")
    if end - start > timedelta(days=MAX_DAYS):
        raise ServiceValidationError(f"The window can be at most {MAX_DAYS} days")
    return dt_util.as_utc(start), dt_util.as_utc(end), tz


async def _run(
    hass: HomeAssistant, config: dict[str, Any], start: datetime, end: datetime, tz: tzinfo
) -> BacktestResult:
    entity_ids = sorted(extract_entities(config))
    store = HistoryStore()
    missing: list[str] = []
    if entity_ids:
        recorded = await get_instance(hass).async_add_executor_job(
            lambda: history.get_significant_states(
                hass,
                start,
                end,
                entity_ids,
                include_start_time_state=True,
                significant_changes_only=False,
            )
        )
        for entity_id in entity_ids:
            states = recorded.get(entity_id) or []
            if not states:
                missing.append(entity_id)
            for state in states:
                store.add(
                    StateSnapshot(
                        entity_id=entity_id,
                        state=state.state,
                        attributes=dict(state.attributes),
                        last_changed=state.last_changed,
                        last_updated=state.last_updated,
                    )
                )

    result = await hass.async_add_executor_job(backtest, config, store, start, end, tz)
    if missing:
        result.warnings.append(
            "No recorded history for: " + ", ".join(missing)
            + " (excluded from recorder, purged, or not existing in this window)"
        )
    _LOGGER.debug("Backtest over %s entities: %s", len(entity_ids), result.summary())
    return result


_ICONS = {"executed": "✅", "blocked": "⛔", "uncertain": "❔"}


def _timeline(result: BacktestResult, limit: int) -> list[str]:
    lines = []
    for run in result.runs[:limit]:
        when = run.time.astimezone(result.tz).strftime("%a %d/%m %H:%M:%S")
        line = f"{_ICONS.get(run.status, '')} {when}  {run.description}"
        if run.status == "blocked" and run.blocked_by:
            line += f"  — blocked by {run.blocked_by.condition}: {run.blocked_by.detail}"
        elif run.status == "uncertain" and run.uncertain_because:
            line += f"  — uncertain: {run.uncertain_because.detail}"
        lines.append(line)
    return lines
