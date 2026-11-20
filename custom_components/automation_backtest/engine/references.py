"""Find every entity an automation depends on, so we know which history to load."""

from __future__ import annotations

import re
from typing import Any

_ENTITY_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z0-9_]+$")
_QUOTED_RE = re.compile(r"['\"]([a-z_][a-z0-9_]*\.[a-z0-9_]+)['\"]")
_DOTTED_RE = re.compile(r"states\.([a-z_][a-z0-9_]*)\.([a-z0-9_]+)")

_ENTITY_KEYS = {"entity_id", "above", "below", "at", "after", "before", "state", "zone"}
_SKIP_KEYS = {"actions", "action", "sequence"}  # actions are never executed


def _from_template(text: str, found: set[str]) -> None:
    if "{{" not in text and "{%" not in text:
        return
    found.update(m for m in _QUOTED_RE.findall(text))
    found.update(f"{d}.{o}" for d, o in _DOTTED_RE.findall(text))


def extract_entities(config: Any) -> set[str]:
    found: set[str] = set()

    def walk(node: Any, key: str | None = None) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k in _SKIP_KEYS:
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
