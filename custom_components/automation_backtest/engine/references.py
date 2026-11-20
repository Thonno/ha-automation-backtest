"""Find every entity an automation depends on, so we know which history to load."""

from __future__ import annotations

import re
from typing import Any

_ENTITY_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z0-9_]+$")
_QUOTED_RE = re.compile(r"['\"]([a-z_][a-z0-9_]*\.[a-z0-9_]+)['\"]")
_DOTTED_RE = re.compile(r"states\.([a-z_][a-z0-9_]*)\.([a-z0-9_]+)")

_ENTITY_KEYS = {"entity_id", "above", "below", "at", "after", "before", "state", "zone", "_entities", "entity"}
_SKIP_KEYS = {"actions", "action", "sequence"}  # actions are never executed


def _from_template(text: str, found: set[str]) -> None:
    if "{{" not in text and "{%" not in text:
        return
    found.update(m for m in _QUOTED_RE.findall(text))
    found.update(f"{d}.{o}" for d, o in _DOTTED_RE.findall(text))


def extract_entities(config: Any, include_actions: bool = False) -> set[str]:
    """Entities of triggers/conditions (and, if asked, of the actions too)."""
    found: set[str] = set()
    skip = set() if include_actions else _SKIP_KEYS

    def walk(node: Any, key: str | None = None) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k in skip:
                    continue
                walk(v, k)
        elif isinstance(node, list):
            for item in node:
                walk(item, key)
        elif isinstance(node, str):
            if key in _ENTITY_KEYS and _ENTITY_RE.match(node):
                found.add(node)
            _from_template(node, found)

    walk(config)
    return found


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def extract_thresholds(config: Any) -> list[dict[str, Any]]:
    """Numeric limits used by numeric_state / sensor device triggers & conditions.

    Used by the panel to draw threshold lines on the entity charts.
    """
    out: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    def visit(node: dict[str, Any]) -> None:
        kind = node.get("trigger") or node.get("platform") or node.get("condition")
        numeric = kind == "numeric_state" or (kind == "device" and node.get("domain") == "sensor")
        if not numeric or node.get("attribute") or node.get("value_template"):
            return
        entity_ids = node.get("entity_id")
        entity_ids = entity_ids if isinstance(entity_ids, list) else [entity_ids]
        for key in ("above", "below"):
            if not _is_number(node.get(key)):
                continue
            for entity_id in entity_ids:
                if not isinstance(entity_id, str):
                    continue
                item = (entity_id, key, float(node[key]))
                if item not in seen:
                    seen.add(item)
                    out.append({"entity_id": entity_id, "kind": key, "value": float(node[key])})

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            visit(node)
            for k, v in node.items():
                if k not in _SKIP_KEYS:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(config)
    return out
