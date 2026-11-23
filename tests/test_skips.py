from conftest import ts
from engine import apply_skips, backtest

START, END = ts("2026-11-10 00:00"), ts("2026-11-11 00:00")

ROWS = [
    ("binary_sensor.motion", "2026-11-09 23:00", "off"),
    ("binary_sensor.motion", "2026-11-10 08:00", "on"),
    ("binary_sensor.motion", "2026-11-10 08:01", "off"),
    ("switch.plug", "2026-11-09 23:00", "unavailable"),
    ("input_boolean.home", "2026-11-09 23:00", "on"),
    ("light.hall", "2026-11-09 23:00", "off"),
]
TRIGGER = [{"trigger": "state", "entity_id": "binary_sensor.motion", "to": "on"}]
PLUG_OK = {"condition": "state", "entity_id": "switch.plug", "state": "on"}
HOME = {"condition": "state", "entity_id": "input_boolean.home", "state": "on"}
AWAY = {"condition": "state", "entity_id": "input_boolean.home", "state": "off"}
LIGHT_ON = {"action": "light.turn_on", "entity_id": "light.hall"}


def test_skip_top_level_condition(make_history):
    config = {"triggers": TRIGGER, "conditions": [PLUG_OK, HOME]}
    assert backtest(config, make_history(ROWS), START, END).runs[0].status == "blocked"
    skipped, applied = apply_skips(config, ["condition/0"])
    assert applied == ["condition/0"]
    assert config["conditions"][0] is PLUG_OK  # original untouched
    run = backtest(skipped, make_history(ROWS), START, END).runs[0]
    assert run.status == "executed"
    assert run.conditions[0].skipped and run.conditions[0].detail == "skipped in this backtest"


def test_disabled_is_neutral_in_or_and_not(make_history):
    off = {**HOME, "enabled": False}
    cases = [
        ({"condition": "or", "conditions": [off, AWAY]}, "blocked"),  # was "executed" before 1.3.0
        ({"or": [off, HOME]}, "executed"),
        ({"condition": "not", "conditions": [off]}, "executed"),
        ({"condition": "and", "conditions": [off, AWAY]}, "blocked"),
        ({"condition": "or", "conditions": [off]}, "blocked"),
    ]
    for cond, expected in cases:
        config = {"triggers": TRIGGER, "conditions": [cond]}
        assert backtest(config, make_history(ROWS), START, END).runs[0].status == expected, cond


def test_skip_nested_and_shorthand(make_history):
    config = {"triggers": TRIGGER, "conditions": [{"or": [PLUG_OK, AWAY]}]}
    out, applied = apply_skips(config, ["condition/0", "condition/9", "action/0"])
    assert applied == ["condition/0"]
    assert out["conditions"][0]["condition"] == "or" and out["conditions"][0]["enabled"] is False
    out, applied = apply_skips(config, ["condition/0/conditions/0"])
    assert applied == ["condition/0/conditions/0"]
    # plug skipped → or(AWAY) still false
    assert backtest(out, make_history(ROWS), START, END).runs[0].status == "blocked"


def test_single_condition_without_list_and_template_string():
    out, applied = apply_skips({"condition": "{{ false }}"}, ["condition/0"])
    assert applied == ["condition/0"]
    assert out["condition"]["condition"] == "template" and out["condition"]["enabled"] is False


def test_skip_conditions_inside_actions(make_history):
    config = {
        "triggers": TRIGGER,
        "actions": [
            PLUG_OK,
            {"if": [PLUG_OK], "then": [LIGHT_ON]},
        ],
    }
    steps = backtest(config, make_history(ROWS), START, END).runs[0].actions
    assert steps[0].result == "stopped" and steps[0].skip == "action/0/0"
    out, applied = apply_skips(config, ["action/0/0"])
    assert applied == ["action/0/0"]
    steps = backtest(out, make_history(ROWS), START, END).runs[0].actions
    assert steps[0].result == "skipped" and steps[0].detail == "skipped in this backtest"
    assert steps[1].detail.startswith("→ else") and steps[1].skip == "action/1/if/0"
    out, _ = apply_skips(out, ["action/1/if/0"])
    steps = backtest(out, make_history(ROWS), START, END).runs[0].actions
    assert steps[1].detail == "→ then"
    assert steps[2].path == "action/1/then/0" and steps[2].result == "done"


def test_skip_in_choose_and_parallel_paths(make_history):
    config = {
        "triggers": TRIGGER,
        "actions": [
            {"choose": [{"conditions": [PLUG_OK], "sequence": [LIGHT_ON]}]},
            {"parallel": [{"sequence": [{"if": PLUG_OK, "then": LIGHT_ON}]}]},
        ],
    }
    out, applied = apply_skips(config, ["action/0/choose/0/conditions/0", "action/1/parallel/0/sequence/0/if/0"])
    assert len(applied) == 2
    steps = backtest(out, make_history(ROWS), START, END).runs[0].actions
    paths = [s.path for s in steps]
    assert "action/0/choose/0/sequence/0" in paths
    assert steps[[s.path for s in steps].index("action/1/parallel/0/sequence/0")].detail == "→ then"
