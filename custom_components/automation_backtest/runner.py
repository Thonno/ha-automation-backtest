"""Shared plumbing: read an automation, load history, run the engine."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, tzinfo
from typing import Any

from homeassistant.components.recorder import get_instance, history
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import ATTR_AUTOMATION, ATTR_CONFIG, ATTR_DAYS, ATTR_END, ATTR_START, MAX_DAYS
from .engine import BacktestResult, HistoryStore, StateSnapshot, backtest, extract_entities
from .restarts import async_get_downtime

_LOGGER = logging.getLogger(__name__)
_REGISTRY_ID = re.compile(r"^[0-9a-f]{32}$")


async def automation_config(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    if ATTR_CONFIG in data:
        return resolve_registry_ids(hass, data[ATTR_CONFIG])
    entity_id = data.get(ATTR_AUTOMATION)
    if not entity_id:
        raise ServiceValidationError("Provide either 'automation' or 'config'")
    return resolve_registry_ids(hass, raw_automation_config(hass, entity_id))


def raw_automation_config(hass: HomeAssistant, entity_id: str) -> dict[str, Any]:
    """The automation config exactly as stored (registry ids kept, for the HA editor)."""
    component = hass.data.get("automation")
    entity = component.get_entity(entity_id) if component else None
    raw = getattr(entity, "raw_config", None) if entity else None
    if not raw:
        raise ServiceValidationError(f"Could not read the configuration of {entity_id}")
    return dict(raw)


def editable_part(config: dict[str, Any]) -> dict[str, list]:
    """Just triggers and conditions, normalised to the plural keys."""
    def as_list(value: Any) -> list:
        if value is None:
            return []
        return list(value) if isinstance(value, list) else [value]

    return {
        "triggers": as_list(config.get("triggers", config.get("trigger"))),
        "conditions": as_list(config.get("conditions", config.get("condition"))),
    }


def resolve_registry_ids(hass: HomeAssistant, config: Any) -> Any:
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


def period(hass: HomeAssistant, data: dict[str, Any]) -> tuple[datetime, datetime, tzinfo]:
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


async def run(
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

    downtime = await async_get_downtime(hass, start, end)
    result = await hass.async_add_executor_job(
        backtest, config, store, start, end, tz, downtime or []
    )
    if downtime is None:
        result.warnings.append(
            "Could not read Home Assistant restarts from the recorder: "
            "runs around restarts may be over-counted"
        )
    if missing:
        result.warnings.append(
            "No recorded history for: " + ", ".join(missing)
            + " (excluded from recorder, purged, or not existing in this window)"
        )
    _LOGGER.debug("Backtest over %s entities: %s", len(entity_ids), result.summary())
    return result


_ICONS = {"executed": "✅", "blocked": "⛔", "uncertain": "❔"}


def timeline(result: BacktestResult, limit: int) -> list[str]:
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
