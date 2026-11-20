# 🔁 Automation Backtest for Home Assistant

**Backtest your automations against your own history, before you trust them.**

You write or tweak an automation and then… wait a week to find out whether it works.
Automation Backtest replays it over the states your recorder already has and tells you:

- **when** it would have run in the last N days,
- **which condition blocked it** every time it triggered but did not run,
- **what changes** if you edit it ("v2 would have run 3 times less, here's when").

Nothing is executed. No lights flip, no notifications go out: actions are never run.

```
✅ Tue 10/11 07:42:10  binary_sensor.hallway_motion: off → on
⛔ Tue 10/11 13:05:44  binary_sensor.hallway_motion: off → on  — blocked by numeric_state: sensor.hallway_lux=412 (above=None, below=30)
✅ Tue 10/11 18:31:02  binary_sensor.hallway_motion: off → on
❔ Wed 11/11 06:58:00  binary_sensor.hallway_motion: off → on  — uncertain: Condition type 'sun' is not supported yet
```

## Install

**HACS (custom repository)**
1. HACS → ⋮ → *Custom repositories* → add `https://github.com/Thonno/ha-automation-backtest`, category *Integration*.
2. Install **Automation Backtest**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → Automation Backtest*.

**Manual**: copy `custom_components/automation_backtest` into your `config/custom_components/` and restart.

## Use

Open *Developer tools → Actions*.

### Backtest an existing automation

```yaml
action: automation_backtest.run
data:
  automation: automation.hallway_lights
  days: 7
```

### Backtest a draft (not saved yet)

```yaml
action: automation_backtest.run
data:
  days: 3
  config:
    triggers:
      - trigger: state
        entity_id: binary_sensor.hallway_motion
        to: "on"
    conditions:
      - condition: numeric_state
        entity_id: sensor.hallway_lux
        below: 30
```

### Compare two versions

```yaml
action: automation_backtest.compare
data:
  automation: automation.heating_morning      # version A: what runs today
  days: 14
  config_b:                                   # version B: your edit
    triggers:
      - trigger: numeric_state
        entity_id: sensor.living_temperature
        below: 19.5
    conditions:
      - condition: time
        after: "06:00"
        before: "09:00"
```

The response lists executions that happen **only in A** and **only in B**.

### Response

| key | content |
|---|---|
| `summary` | `triggered`, `executed`, `blocked`, `uncertain` counts |
| `timeline` | human-readable lines (as above) |
| `runs` | per-run details: trigger, full condition trace, `blocked_by` |
| `warnings` | e.g. entities with no recorded history |
| `unsupported_triggers` | triggers that cannot be replayed, with the reason |

## What can be simulated (v0.1)

| | Supported | Not yet |
|---|---|---|
| **Triggers** | `state` (from/to/not_from/not_to/attribute/for), `numeric_state` (above/below/attribute/value_template/for, crossing semantics), `time` (fixed times, `input_datetime`), `time_pattern`, `template` (incl. `for`, `now()` re-rendered every minute), `device` triggers that map to a state or attribute (turned on/off, motion, open/close, lock, climate HVAC mode, humidity/temperature thresholds…) | `event`, `mqtt`, `webhook`, `sun`, `zone`, `homeassistant`, `calendar`, `tag`, button/remote device triggers, `conversation` |
| **Conditions** | `state` (incl. `for`, `match: any`, attribute), `numeric_state`, `time` (after/before/weekday, across midnight), `template`, `trigger` (id), `and`/`or`/`not` (incl. shorthand), `device` conditions that map to a state or attribute (on/off, open/closed, humidifier mode, climate HVAC/preset mode…) | `sun`, `zone` |
| **Templates** | `states()`, `states.domain.object`, `is_state`, `state_attr`, `is_state_attr`, `has_value`, `now()`, `today_at`, `as_timestamp`, `as_datetime`, `float/int/bool` with defaults, `iif`, `trigger.*` | everything else in HA's template API |

**Design rule: never silently wrong.** Anything that cannot be replayed faithfully makes
the run `uncertain` (with the reason) or lists the trigger under `unsupported_triggers`.
It never guesses.

## Limits worth knowing

- **History depth = your recorder.** Default `purge_keep_days` is 10. Excluded entities have no history.
- **Actions are not simulated**, so `mode: single` / `restart` interactions and
  automations that react to their own actions are not modelled.
- `input_datetime` used in `time` triggers is read at the start of the window.
- A `state` trigger with `for:` uses recorded timestamps; very short `for` values may be
  affected by how often a device reports.

## How it works

`custom_components/automation_backtest/engine/` is a standalone, pure-Python event-driven
simulator (only depends on `jinja2`) with its own test suite. The integration loads the
history of every entity referenced by the automation from the recorder, merges state
changes, scheduled times and `for:` timers into one time-ordered queue, and evaluates
triggers and conditions exactly at the moment they would have been evaluated live.

## Development

```bash
pip install -r requirements_test.txt
pytest
```

## Roadmap

- Sidebar panel: pick an automation, see the timeline on a chart of the involved entities
- `sun` trigger/condition, `zone`, event triggers from the recorder's event table
- "What-if" overrides: replay with a sensor offset (e.g. lux −20%)
- Threshold sweep: "for `below` from 15 to 40, how many runs would each value give?"

## License

MIT
