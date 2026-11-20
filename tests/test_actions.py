from conftest import ts
from engine import backtest
from engine.actions import controlled_entities

START, END = ts("2026-11-10 00:00"), ts("2026-11-11 00:00")

MOTION = [
    ("binary_sensor.motion", "2026-11-09 23:00", "off"),
    ("binary_sensor.motion", "2026-11-10 08:00", "on"),
    ("binary_sensor.motion", "2026-11-10 08:01", "off"),
    ("binary_sensor.motion", "2026-11-10 20:00", "on"),
    ("binary_sensor.motion", "2026-11-10 20:01", "off"),
    ("light.hall", "2026-11-09 23:00", "off"),
]
TRIGGER = [{"trigger": "state", "entity_id": "binary_sensor.motion", "to": "on"}]


def sim(result, entity_id):
    return [(p["t"][11:16], p["s"]) for p in result.simulated[entity_id]]


def test_turn_on_then_off_after_delay(make_history):
    config = {
        "triggers": TRIGGER,
        "actions": [
            {"action": "light.turn_on", "target": {"entity_id": "light.hall"}, "data": {"brightness_pct": 40}},
            {"delay": {"minutes": 5}},
            {"action": "light.turn_off", "target": {"entity_id": "light.hall"}},
        ],
    }
    result = backtest(config, make_history(MOTION), START, END)
    assert result.controlled == ["light.hall"]
    assert sim(result, "light.hall") == [("00:00", "off"), ("08:00", "on"), ("08:05", "off"), ("20:00", "on"), ("20:05", "off")]
    assert result.simulated["light.hall"][1]["a"] == "40%"
    steps = result.runs[0].actions
    assert [s.result for s in steps] == ["done", "done", "done"]
    assert steps[2].time.strftime("%H:%M") == "08:05"


def test_mode_single_skips_overlapping_run(make_history):
    rows = MOTION + [("binary_sensor.motion", "2026-11-10 08:02", "on")]
    config = {
        "triggers": TRIGGER,
        "actions": [{"action": "light.turn_on", "entity_id": "light.hall"}, {"delay": "00:10:00"},
                    {"action": "light.turn_off", "entity_id": "light.hall"}],
    }
    result = backtest(config, make_history(rows), START, END)
    assert result.runs[1].action_note == "skipped"
    assert sim(result, "light.hall")[:3] == [("00:00", "off"), ("08:00", "on"), ("08:10", "off")]


def test_mode_restart_extends(make_history):
    rows = MOTION + [("binary_sensor.motion", "2026-11-10 08:02", "on")]
    config = {
        "mode": "restart",
        "triggers": TRIGGER,
        "actions": [{"action": "light.turn_on", "entity_id": "light.hall"}, {"delay": "00:10:00"},
                    {"action": "light.turn_off", "entity_id": "light.hall"}],
    }
    result = backtest(config, make_history(rows), START, END)
    assert sim(result, "light.hall")[:3] == [("00:00", "off"), ("08:00", "on"), ("08:12", "off")]


def test_choose_uses_history_and_toggle(make_history):
    rows = MOTION + [("sun.sun", "2026-11-09 23:00", "below_horizon"), ("sun.sun", "2026-11-10 07:30", "above_horizon"),
                     ("sun.sun", "2026-11-10 17:00", "below_horizon")]
    config = {
        "triggers": TRIGGER,
        "actions": [{"choose": [{"conditions": [{"condition": "state", "entity_id": "sun.sun", "state": "below_horizon"}],
                                 "sequence": [{"action": "light.toggle", "target": {"entity_id": "light.hall"}}]}]}],
    }
    result = backtest(config, make_history(rows), START, END)
    assert result.runs[0].actions[0].detail == "no option matched"
    assert sim(result, "light.hall") == [("00:00", "off"), ("20:00", "on")]


def test_unsupported_and_notify(make_history):
    config = {
        "triggers": TRIGGER,
        "actions": [
            {"action": "notify.mobile_app", "data": {"message": "Motion at {{ trigger.to_state.state }}"}},
            {"wait_for_trigger": [{"trigger": "state", "entity_id": "binary_sensor.motion", "to": "off"}]},
            {"action": "light.turn_on", "entity_id": "light.hall"},
        ],
    }
    result = backtest(config, make_history(MOTION), START, END)
    steps = result.runs[0].actions
    assert steps[0].detail == '"Motion at on"'
    assert steps[1].result == "not_simulated"
    assert len(steps) == 2
    assert sim(result, "light.hall") == [("00:00", "off")]


def test_input_number_and_cover(make_history):
    rows = MOTION + [("input_number.level", "2026-11-09 23:00", "1.0", {"step": 1, "max": 3}),
                     ("cover.blind", "2026-11-09 23:00", "open", {"current_position": 100})]
    config = {
        "triggers": TRIGGER,
        "actions": [{"action": "input_number.increment", "target": {"entity_id": "input_number.level"}},
                    {"action": "cover.set_cover_position", "target": {"entity_id": "cover.blind"}, "data": {"position": 0}}],
    }
    result = backtest(config, make_history(rows), START, END)
    assert [p["s"] for p in result.simulated["input_number.level"]] == ["1.0", "2.0", "3.0"]
    assert sim(result, "cover.blind") == [("00:00", "open"), ("08:00", "closed")]


def test_controlled_entities_nested():
    config = {"actions": [{"if": [], "then": [{"service": "switch.turn_on", "entity_id": ["switch.a", "switch.b"]}],
                           "else": [{"parallel": [{"action": "fan.turn_off", "target": {"entity_id": "fan.c"}}]}]}]}
    assert controlled_entities(config) == ["switch.a", "switch.b", "fan.c"]


def test_no_actions_no_simulation(make_history):
    result = backtest({"triggers": TRIGGER}, make_history(MOTION), START, END)
    assert result.controlled == [] and result.simulated == {}
    assert "actions" not in result.as_dict()["runs"][0]
