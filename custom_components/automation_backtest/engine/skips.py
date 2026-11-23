"""Skip conditions for one backtest without touching the automation.

A skipped condition is disabled (``enabled: false``) in a copy of the config,
so it behaves exactly like a condition disabled in Home Assistant: neutral in
``and``/``or``/``not`` and in the top-level conditions, a no-op as an action step.

Paths are the ones the engine puts in its traces, e.g. ``condition/1``,
``condition/0/conditions/2``, ``action/3/if/0``,
``action/1/choose/0/conditions/0``, ``action/2/repeat/while/0`` or ``action/4``
(a condition step).
"""

from __future__ import annotations

import copy
from typing import Any

SKIP_MARK = "_backtest_skipped"

_ROOTS = {
    "condition": ("conditions", "condition"),
    "conditions": ("conditions", "condition"),
    "action": ("actions", "action"),
    "actions": ("actions", "action"),
}
_LOGICAL = ("and", "or", "not")


def apply_skips(config: dict[str, Any], paths: list[str] | None) -> tuple[dict[str, Any], list[str]]:
    """Return a copy of ``config`` with the conditions at ``paths`` disabled, and the paths applied."""
    if not paths:
        return config, []
    out = copy.deepcopy(config)
    applied = [p for p in dict.fromkeys(paths) if isinstance(p, str) and _disable(out, p)]
    return out, applied


def _disable(config: dict[str, Any], path: str) -> bool:
    segs = [s for s in path.split("/") if s]
    if not segs or segs[0] not in _ROOTS:
        return False
    parent: Any = None
    key: Any = None
    node: Any = config
    for pos, seg in enumerate(segs):
        if seg.isdigit():
            idx = int(seg)
            if isinstance(node, list):
                if idx >= len(node):
                    return False
                parent, key, node = node, idx, node[idx]
            elif idx == 0 and node is not None:
                continue  # a single item written without a list
            else:
                return False
            continue
        if not isinstance(node, dict):
            return False
        if pos == 0:
            keys = _ROOTS[seg]
        elif seg == "conditions":
            keys = ("conditions", *_LOGICAL)
        else:
            keys = (seg,)
        found = next((k for k in keys if k in node), None)
        if found is None:
            return False
        parent, key, node = node, found, node[found]
    if parent is None:
        return False
    target = _as_condition(node)
    if target is None:
        return False
    parent[key] = {**target, "enabled": False, SKIP_MARK: True}
    return True


def _as_condition(node: Any) -> dict[str, Any] | None:
    if isinstance(node, str):
        return {"condition": "template", "value_template": node}
    if not isinstance(node, dict):
        return None
    if "condition" in node:
        return node
    for key in _LOGICAL:
        if key in node:
            rest = {k: v for k, v in node.items() if k != key}
            return {**rest, "condition": key, "conditions": node[key]}
    return None
