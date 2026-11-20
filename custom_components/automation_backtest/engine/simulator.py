"""Replay an automation config over recorded history without executing actions."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from datetime import datetime, timezone, tzinfo
from typing import Any

from .conditions import ConditionTrace, EvalContext, evaluate_conditions
from .history import HistoryStore, SimulatedStates
from .templates import TemplateRenderer
from .triggers import BaseTrigger, Firing, TriggerOutput, build_trigger
from .util import UnsupportedFeature, as_list, iso

EXECUTED = "executed"
BLOCKED = "blocked"
UNCERTAIN = "uncertain"

# Ordering for events that share a timestamp: timers and schedules first
# (they represent time passing up to this instant), then state changes.
_PRIO_DOWNTIME, _PRIO_TIMER, _PRIO_SCHEDULED, _PRIO_CHANGE = -1, 0, 1, 2


@dataclass
class Run:
    time: datetime
    trigger_index: int
    trigger_id: str
    trigger_platform: str
    description: str
    status: str
    conditions: list[ConditionTrace] = field(default_factory=list)

    @property
    def blocked_by(self) -> ConditionTrace | None:
        for trace in self.conditions:
            if trace.result is False and trace.condition not in ("and", "or", "not"):
                return trace
        for trace in self.conditions:
            if trace.result is False:
                return trace
        return None

    @property
    def uncertain_because(self) -> ConditionTrace | None:
        return next((t for t in self.conditions if t.result is None), None)

    def as_dict(self, tz: tzinfo) -> dict[str, Any]:
        out: dict[str, Any] = {
            "time": iso(self.time.astimezone(tz)),
            "status": self.status,
            "trigger": {
                "index": self.trigger_index,
                "id": self.trigger_id,
                "platform": self.trigger_platform,
                "description": self.description,
            },
            "conditions": [t.as_dict() for t in self.conditions],
        }
        if self.status == BLOCKED and self.blocked_by:
            out["blocked_by"] = self.blocked_by.as_dict()
        if self.status == UNCERTAIN and self.uncertain_because:
            out["uncertain_because"] = self.uncertain_because.as_dict()
        return out


@dataclass
class BacktestResult:
    start: datetime
    end: datetime
    tz: tzinfo
    runs: list[Run] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unsupported_triggers: list[dict[str, Any]] = field(default_factory=list)
    downtime: list[tuple[datetime, datetime]] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for r in self.runs if r.status == status)

    def summary(self) -> dict[str, int]:
        return {
            "triggered": len(self.runs),
            "executed": self.count(EXECUTED),
            "blocked": self.count(BLOCKED),
            "uncertain": self.count(UNCERTAIN),
        }

    def as_dict(self, include_runs: bool = True, max_runs: int | None = None) -> dict[str, Any]:
        runs = self.runs if max_runs is None else self.runs[:max_runs]
        out: dict[str, Any] = {
            "period": {"start": iso(self.start.astimezone(self.tz)), "end": iso(self.end.astimezone(self.tz))},
            "summary": self.summary(),
            "warnings": list(self.warnings),
            "unsupported_triggers": list(self.unsupported_triggers),
            "restarts": [
                {"stopped": iso(a.astimezone(self.tz)), "started": iso(b.astimezone(self.tz))}
                for a, b in self.downtime
            ],
        }
        if include_runs:
            out["runs"] = [r.as_dict(self.tz) for r in runs]
            if max_runs is not None and len(self.runs) > max_runs:
                out["truncated"] = len(self.runs) - max_runs
        return out


def normalize_automation(config: dict[str, Any]) -> tuple[list[dict], list[Any]]:
    triggers = as_list(config.get("triggers", config.get("trigger")))
    conditions = as_list(config.get("conditions", config.get("condition")))
    return triggers, conditions


def backtest(
    config: dict[str, Any],
    history: HistoryStore,
    start: datetime,
    end: datetime,
    tz: tzinfo = timezone.utc,
    downtime: list[tuple[datetime, datetime]] | None = None,
    sun: Any = None,
    events: list[Any] | None = None,
) -> BacktestResult:
    """Replay `config` over [start, end] and report every would-be run.

    `downtime` lists (stopped, started) intervals in which Home Assistant was
    not running automations (restarts). Like the real thing, triggers do not
    fire then, pending `for:` timers are lost, and triggers re-attach to the
    current states once HA has started again.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    if end <= start:
        raise ValueError("end must be after start")

    windows = sorted(
        (a, b) for a, b in (downtime or []) if b > start and a <= end and b > a
    )
    result = BacktestResult(start=start, end=end, tz=tz, downtime=windows)
    raw_triggers, conditions = normalize_automation(config)
    if not raw_triggers:
        result.warnings.append("Automation has no triggers")
        return result

    renderer = TemplateRenderer()
    states = SimulatedStates(history, start)
    ctx = EvalContext(states=states, now=start, tz=tz, renderer=renderer, sun=sun)

    triggers: list[BaseTrigger] = []
    for idx, raw in enumerate(raw_triggers):
        if not isinstance(raw, dict):
            result.unsupported_triggers.append({"index": idx, "reason": "invalid trigger"})
            continue
        if raw.get("enabled") is False:
            continue
        try:
            trig = build_trigger(raw, idx)
            trig.on_start(ctx)
        except UnsupportedFeature as err:
            result.unsupported_triggers.append(
                {"index": idx, "platform": raw.get("trigger") or raw.get("platform"), "reason": str(err)}
            )
            continue
        triggers.append(trig)

    if not triggers:
        result.warnings.append("None of the triggers can be simulated")
        return result

    queue: list[tuple] = []
    seq = 0
    stops_or_starts: list[Any] = []

    def push(when: datetime, prio: int, payload: tuple) -> None:
        nonlocal seq
        seq += 1
        heapq.heappush(queue, (when, prio, seq, payload))

    for change in history.changes_between(start, end):
        push(change.time, _PRIO_CHANGE, ("change", change))
    for event in events or []:
        if start < event.time <= end:
            # stop is handled with the 'down' marker, started with the 'up' marker
            if event.event_type in ("homeassistant_stop", "homeassistant_started"):
                stops_or_starts.append(event)
            else:
                push(event.time, _PRIO_CHANGE, ("event", event))
    disabled: set[int] = set()
    for trig in triggers:
        try:
            for when in trig.scheduled_times(start, end, tz):
                push(when, _PRIO_SCHEDULED, ("scheduled", trig))
        except UnsupportedFeature as err:
            result.unsupported_triggers.append(
                {"index": trig.index, "platform": trig.platform, "reason": str(err)}
            )
            disabled.add(trig.index)

    def handle(trig: BaseTrigger, output: TriggerOutput) -> None:
        for timer in output.timers:
            if timer.time <= end:
                push(timer.time, _PRIO_TIMER, ("timer", trig, timer.key, timer.token))
        for firing in output.firings:
            result.runs.append(_evaluate_run(trig, firing, conditions, ctx))

    def safe(trig: BaseTrigger, fn, *args) -> None:
        if trig.index in disabled:
            return
        try:
            handle(trig, fn(*args))
        except UnsupportedFeature as err:
            disabled.add(trig.index)
            result.warnings.append(
                f"Trigger {trig.index} ({trig.platform}) stopped at {iso(ctx.now.astimezone(tz))}: {err}"
            )

    offline = False
    for down, up in windows:
        if down <= start < up:
            offline = True
        else:
            push(down, _PRIO_DOWNTIME, ("down",))
        if up <= end:
            push(up, _PRIO_DOWNTIME, ("up",))

    def rearm(trig: BaseTrigger) -> None:
        if trig.index in disabled:
            return
        try:
            trig.rearm(ctx)
        except UnsupportedFeature as err:
            disabled.add(trig.index)
            result.warnings.append(f"Trigger {trig.index} ({trig.platform}) could not re-arm: {err}")

    while queue:
        when, _prio, _seq, payload = heapq.heappop(queue)
        ctx.now = when
        kind = payload[0]
        if kind == "down":
            for event in stops_or_starts:  # clean stop: shutdown triggers still run
                if event.event_type == "homeassistant_stop" and abs((event.time - when).total_seconds()) < 1:
                    for trig in triggers:
                        safe(trig, trig.on_event, event, ctx)
            offline = True
            for trig in triggers:
                trig.cancel_pending()
        elif kind == "up":
            offline = False
            for trig in triggers:
                rearm(trig)
            for event in stops_or_starts:
                if event.event_type == "homeassistant_started" and abs((event.time - when).total_seconds()) < 1:
                    for trig in triggers:
                        safe(trig, trig.on_event, event, ctx)
        elif kind == "event":
            if not offline:
                for trig in triggers:
                    safe(trig, trig.on_event, payload[1], ctx)
        elif kind == "change":
            change = payload[1]
            states.apply(change)
            if not offline:
                for trig in triggers:
                    safe(trig, trig.on_change, change, ctx)
        elif offline:
            continue  # time triggers and 'for:' timers do not run while HA is down
        elif kind == "scheduled":
            trig = payload[1]
            safe(trig, trig.on_scheduled, ctx)
        else:  # timer
            _, trig, key, token = payload
            safe(trig, trig.on_timer, key, token, ctx)

    result.runs.sort(key=lambda r: (r.time, r.trigger_index))
    return result


def wanted_event_types(config: dict[str, Any]) -> set[str]:
    """Recorded event types the triggers of `config` listen to."""
    wanted: set[str] = set()
    for idx, raw in enumerate(as_list(config.get("triggers", config.get("trigger")))):
        if not isinstance(raw, dict) or raw.get("enabled") is False:
            continue
        try:
            wanted |= set(build_trigger(raw, idx).event_types)
        except UnsupportedFeature:
            continue
    if wanted & {"homeassistant_stop", "homeassistant_started"}:
        wanted |= {"homeassistant_stop", "homeassistant_started"}
    return wanted


def _evaluate_run(trig: BaseTrigger, firing: Firing, conditions: list, ctx: EvalContext) -> Run:
    ctx.variables = firing.variables
    try:
        passed, traces = evaluate_conditions(conditions, ctx)
    finally:
        ctx.variables = {}
    status = EXECUTED if passed is True else BLOCKED if passed is False else UNCERTAIN
    return Run(
        time=firing.time,
        trigger_index=trig.index,
        trigger_id=trig.trigger_id,
        trigger_platform=trig.platform,
        description=firing.description,
        status=status,
        conditions=traces,
    )
