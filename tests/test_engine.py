from datetime import timezone
from zoneinfo import ZoneInfo

from conftest import ts
from engine import BLOCKED, EXECUTED, UNCERTAIN, backtest, compare, extract_entities

START, END = ts("2026-11-10 00:00"), ts("2026-11-11 00:00")


def statuses(result):
    return [(r.time.strftime("%H:%M"), r.status) for r in result.runs]


# --- state trigger --------------------------------------------------------------


def test_state_trigger_from_to(make_history):
    history = make_history([
        ("binary_sensor.door", "2026-11-09 23:00", "off"),
        ("binary_sensor.door", "2026-11-10 08:00", "on"),
        ("binary_sensor.door", "2026-11-10 08:05", "off"),
        ("binary_sensor.door", "2026-11-10 19:00", "on"),
    ])
    config = {"triggers": [{"trigger": "state", "entity_id": "binary_sensor.door", "to": "on"}]}
    result = backtest(config, history, START, END)
    assert statuses(result) == [("08:00", EXECUTED), ("19:00", EXECUTED)]


def test_state_trigger_yaml_boolean_on(make_history):
    history = make_history([
        ("light.x", "2026-11-09 23:00", "off"),
        ("light.x", "2026-11-10 08:00", "on"),
    ])
    config = {"trigger": [{"platform": "state", "entity_id": "light.x", "to": True}]}
    assert len(backtest(config, history, START, END).runs) == 1


def test_state_trigger_ignores_attribute_only_changes_when_to_given(make_history):
    history = make_history([
        ("light.x", "2026-11-09 23:00", "on", {"brightness": 10}),
        ("light.x", "2026-11-10 08:00", "on", {"brightness": 200}),
    ])
    with_to = {"triggers": [{"trigger": "state", "entity_id": "light.x", "to": None}]}
    bare = {"triggers": [{"trigger": "state", "entity_id": "light.x"}]}
    assert backtest(with_to, history, START, END).runs == []
    assert len(backtest(bare, history, START, END).runs) == 1


def test_state_trigger_for_held_and_interrupted(make_history):
    history = make_history([
        ("binary_sensor.motion", "2026-11-09 23:00", "on"),
        ("binary_sensor.motion", "2026-11-10 08:00", "off"),  # held 10 min -> fires 08:10
        ("binary_sensor.motion", "2026-11-10 09:00", "on"),
        ("binary_sensor.motion", "2026-11-10 10:00", "off"),  # interrupted at 10:04
        ("binary_sensor.motion", "2026-11-10 10:04", "on"),
    ])
    config = {"triggers": [{
        "trigger": "state", "entity_id": "binary_sensor.motion", "to": "off", "for": "00:10:00",
    }]}
    assert statuses(backtest(config, history, START, END)) == [("08:10", EXECUTED)]


# --- numeric_state ---------------------------------------------------------------


def test_numeric_state_fires_only_on_crossing(make_history):
    history = make_history([
        ("sensor.temp", "2026-11-09 23:00", "22"),   # already above at start: not armed
        ("sensor.temp", "2026-11-10 01:00", "23"),   # still above: no fire
        ("sensor.temp", "2026-11-10 02:00", "19"),   # leaves range: re-arms
        ("sensor.temp", "2026-11-10 03:00", "21.5"),  # crosses: fires
        ("sensor.temp", "2026-11-10 04:00", "unavailable"),
        ("sensor.temp", "2026-11-10 05:00", "25"),   # non-numeric re-armed it: fires
    ])
    config = {"triggers": [{"trigger": "numeric_state", "entity_id": "sensor.temp", "above": 21}]}
    assert statuses(backtest(config, history, START, END)) == [("03:00", EXECUTED), ("05:00", EXECUTED)]


# --- time / time_pattern -----------------------------------------------------------


def test_time_trigger_uses_local_timezone(make_history):
    history = make_history([("sun.sun", "2026-11-09 00:00", "below_horizon")])
    rome = ZoneInfo("Europe/Rome")
    config = {"triggers": [{"trigger": "time", "at": "07:00:00"}]}
    result = backtest(config, history, START, END, tz=rome)
    # 07:00 Rome (UTC+1 in November) == 06:00 UTC
    assert [r.time.astimezone(timezone.utc).strftime("%H:%M") for r in result.runs] == ["06:00"]


def test_time_pattern_every_6_hours(make_history):
    history = make_history([("sun.sun", "2026-11-09 00:00", "x")])
    config = {"triggers": [{"trigger": "time_pattern", "hours": "/6"}]}
    result = backtest(config, history, START, END)
    assert [r.time.strftime("%H:%M") for r in result.runs] == ["06:00", "12:00", "18:00", "00:00"]


# --- conditions -------------------------------------------------------------------


def test_conditions_block_and_explain(make_history):
    history = make_history([
        ("binary_sensor.door", "2026-11-09 23:00", "off"),
        ("person.me", "2026-11-09 23:00", "home"),
        ("binary_sensor.door", "2026-11-10 08:00", "on"),
        ("person.me", "2026-11-10 12:00", "not_home"),
        ("binary_sensor.door", "2026-11-10 12:30", "off"),
        ("binary_sensor.door", "2026-11-10 13:00", "on"),
    ])
    config = {
        "triggers": [{"trigger": "state", "entity_id": "binary_sensor.door", "to": "on"}],
        "conditions": [{"condition": "state", "entity_id": "person.me", "state": "not_home"}],
    }
    result = backtest(config, history, START, END)
    assert statuses(result) == [("08:00", BLOCKED), ("13:00", EXECUTED)]
    assert result.runs[0].blocked_by.condition == "state"
    assert "person.me=home" in result.runs[0].blocked_by.detail


def test_time_condition_across_midnight_and_weekday(make_history):
    history = make_history([
        ("binary_sensor.m", "2026-11-09 23:00", "off"),
        ("binary_sensor.m", "2026-11-10 23:30", "on"),   # Tuesday 23:30 -> in window
        ("binary_sensor.m", "2026-11-10 23:40", "off"),
        ("binary_sensor.m", "2026-11-10 12:00", "on"),   # noon -> outside window
        ("binary_sensor.m", "2026-11-10 12:10", "off"),
    ])
    config = {
        "triggers": [{"trigger": "state", "entity_id": "binary_sensor.m", "to": "on"}],
        "conditions": [{"condition": "time", "after": "22:00", "before": "06:00", "weekday": ["tue"]}],
    }
    assert statuses(backtest(config, history, START, END)) == [("12:00", BLOCKED), ("23:30", EXECUTED)]


def test_state_condition_for(make_history):
    history = make_history([
        ("binary_sensor.door", "2026-11-09 23:00", "off"),
        ("person.me", "2026-11-09 23:00", "home"),
        ("person.me", "2026-11-10 08:00", "not_home"),
        ("binary_sensor.door", "2026-11-10 08:10", "on"),  # away only 10 min
        ("binary_sensor.door", "2026-11-10 08:20", "off"),
        ("binary_sensor.door", "2026-11-10 09:00", "on"),  # away 60 min
    ])
    config = {
        "triggers": [{"trigger": "state", "entity_id": "binary_sensor.door", "to": "on"}],
        "conditions": [{"condition": "state", "entity_id": "person.me", "state": "not_home",
                        "for": {"minutes": 30}}],
    }
    assert statuses(backtest(config, history, START, END)) == [("08:10", BLOCKED), ("09:00", EXECUTED)]


def test_template_condition_and_shorthand_or(make_history):
    history = make_history([
        ("sensor.lux", "2026-11-09 23:00", "500"),
        ("binary_sensor.m", "2026-11-09 23:00", "off"),
        ("binary_sensor.m", "2026-11-10 08:00", "on"),
        ("sensor.lux", "2026-11-10 17:00", "20"),
        ("binary_sensor.m", "2026-11-10 17:30", "off"),
        ("binary_sensor.m", "2026-11-10 18:00", "on"),
    ])
    config = {
        "triggers": [{"trigger": "state", "entity_id": "binary_sensor.m", "to": "on"}],
        "conditions": [{"or": [
            "{{ states('sensor.lux') | float(0) < 50 }}",
            {"condition": "state", "entity_id": "binary_sensor.m", "state": "never"},
        ]}],
    }
    assert statuses(backtest(config, history, START, END)) == [("08:00", BLOCKED), ("18:00", EXECUTED)]


def test_trigger_id_condition(make_history):
    history = make_history([
        ("binary_sensor.a", "2026-11-09 23:00", "off"),
        ("binary_sensor.b", "2026-11-09 23:00", "off"),
        ("binary_sensor.a", "2026-11-10 08:00", "on"),
        ("binary_sensor.b", "2026-11-10 09:00", "on"),
    ])
    config = {
        "triggers": [
            {"trigger": "state", "entity_id": "binary_sensor.a", "to": "on", "id": "a"},
            {"trigger": "state", "entity_id": "binary_sensor.b", "to": "on", "id": "b"},
        ],
        "conditions": [{"condition": "trigger", "id": "b"}],
    }
    assert statuses(backtest(config, history, START, END)) == [("08:00", BLOCKED), ("09:00", EXECUTED)]


def test_unsupported_condition_is_uncertain_not_wrong(make_history):
    history = make_history([
        ("binary_sensor.m", "2026-11-09 23:00", "off"),
        ("binary_sensor.m", "2026-11-10 08:00", "on"),
    ])
    config = {
        "triggers": [{"trigger": "state", "entity_id": "binary_sensor.m", "to": "on"}],
        "conditions": [{"condition": "sun", "after": "sunset"}],
    }
    result = backtest(config, history, START, END)
    assert statuses(result) == [("08:00", UNCERTAIN)]
    assert "not supported" in result.runs[0].uncertain_because.detail


# --- template / device / unsupported triggers ---------------------------------------


def test_template_trigger_rising_edge(make_history):
    history = make_history([
        ("sensor.power", "2026-11-09 23:00", "100"),
        ("sensor.power", "2026-11-10 08:00", "2500"),
        ("sensor.power", "2026-11-10 08:01", "2600"),  # still true: no new fire
        ("sensor.power", "2026-11-10 09:00", "50"),
        ("sensor.power", "2026-11-10 10:00", "3000"),
    ])
    config = {"triggers": [{"trigger": "template",
                            "value_template": "{{ states('sensor.power')|float > 2000 }}"}]}
    assert statuses(backtest(config, history, START, END)) == [("08:00", EXECUTED), ("10:00", EXECUTED)]


def test_device_trigger_translated(make_history):
    history = make_history([
        ("binary_sensor.hall_motion", "2026-11-09 23:00", "off"),
        ("binary_sensor.hall_motion", "2026-11-10 08:00", "on"),
    ])
    config = {"triggers": [{"trigger": "device", "domain": "binary_sensor", "type": "motion",
                            "device_id": "abc", "entity_id": "binary_sensor.hall_motion"}]}
    assert len(backtest(config, history, START, END).runs) == 1


def test_unsupported_trigger_reported(make_history):
    history = make_history([("sun.sun", "2026-11-09 00:00", "x")])
    config = {"triggers": [{"trigger": "event", "event_type": "foo"}]}
    result = backtest(config, history, START, END)
    assert result.runs == []
    assert result.unsupported_triggers[0]["platform"] == "event"


# --- compare / references ------------------------------------------------------------


def test_compare_threshold_change(make_history):
    rows = [("sensor.temp", "2026-11-09 23:00", "18")]
    for hour, value in [(1, "20.5"), (2, "18"), (3, "22.5"), (4, "18")]:
        rows.append(("sensor.temp", f"2026-11-10 0{hour}:00", value))
    history = make_history(rows)
    v1 = {"triggers": [{"trigger": "numeric_state", "entity_id": "sensor.temp", "above": 20}]}
    v2 = {"triggers": [{"trigger": "numeric_state", "entity_id": "sensor.temp", "above": 22}]}
    diff = compare(backtest(v1, history, START, END), backtest(v2, history, START, END))
    assert diff["summary"] == {"a_executed": 2, "b_executed": 1, "both": 1, "only_a": 1, "only_b": 0, "shifted": 0}
    assert diff["only_a"][0]["time"].startswith("2026-11-10T01:00")


def test_extract_entities():
    config = {
        "triggers": [{"trigger": "state", "entity_id": ["light.a", "light.b"]},
                     {"trigger": "numeric_state", "entity_id": "sensor.t", "above": "input_number.max"}],
        "conditions": ["{{ is_state('person.me', 'home') and states.sun.sun.state == 'above' }}"],
        "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.never_loaded"}}],
    }
    assert extract_entities(config) == {
        "light.a", "light.b", "sensor.t", "input_number.max", "person.me", "sun.sun",
    }


def test_template_dotted_states_and_trigger_variables(make_history):
    history = make_history([
        ("sensor.lux", "2026-11-09 23:00", "20"),
        ("binary_sensor.m", "2026-11-09 23:00", "off"),
        ("binary_sensor.m", "2026-11-10 08:00", "on"),
    ])
    config = {
        "triggers": [{"trigger": "state", "entity_id": "binary_sensor.m", "to": "on"}],
        "conditions": [
            "{{ states.sensor.lux.state | int < 50 }}",
            "{{ trigger.to_state.state == 'on' and trigger.entity_id == 'binary_sensor.m' }}",
        ],
    }
    assert statuses(backtest(config, history, START, END)) == [("08:00", EXECUTED)]


# --- humidifier / climate device automations ------------------------------------------


def test_humidifier_is_mode_condition_at_midnight(make_history):
    history = make_history([
        ("humidifier.camera", "2026-11-09 20:00", "on", {"mode": "auto", "humidity": 50}),
        ("humidifier.camera", "2026-11-10 12:00", "on", {"mode": "sleep", "humidity": 50}),
    ])
    config = {
        "triggers": [{"trigger": "time", "at": "00:00:00"}],
        "conditions": [{"condition": "device", "domain": "humidifier", "type": "is_mode",
                        "device_id": "abc", "entity_id": "humidifier.camera", "mode": "sleep"}],
    }
    result = backtest(config, history, ts("2026-11-09 12:00"), ts("2026-11-11 12:00"))
    # 10/11 00:00 mode=auto -> blocked; 11/11 00:00 mode=sleep -> executed
    assert statuses(result) == [("00:00", BLOCKED), ("00:00", EXECUTED)]
    assert "humidifier.camera=auto" in result.runs[0].blocked_by.detail


def test_climate_hvac_mode_condition_and_trigger(make_history):
    history = make_history([
        ("climate.salotto", "2026-11-09 23:00", "off", {"current_temperature": 18}),
        ("climate.salotto", "2026-11-10 07:00", "heat", {"current_temperature": 18}),
    ])
    trig = {"triggers": [{"trigger": "device", "domain": "climate", "type": "hvac_mode_changed",
                          "device_id": "x", "entity_id": "climate.salotto", "hvac_mode": "heat"}]}
    assert statuses(backtest(trig, history, START, END)) == [("07:00", EXECUTED)]


def test_humidity_device_trigger_numeric(make_history):
    history = make_history([
        ("humidifier.camera", "2026-11-09 23:00", "on", {"current_humidity": 45}),
        ("humidifier.camera", "2026-11-10 03:00", "on", {"current_humidity": 62}),
        ("humidifier.camera", "2026-11-10 04:00", "on", {"current_humidity": 65}),
    ])
    config = {"triggers": [{"trigger": "device", "domain": "humidifier",
                            "type": "current_humidity_changed", "device_id": "x",
                            "entity_id": "humidifier.camera", "above": 60}]}
    assert statuses(backtest(config, history, START, END)) == [("03:00", EXECUTED)]


# --- real-world gaps found on a live instance (2026-11-20) -------------------------------


def test_sensor_value_device_trigger_and_condition(make_history):
    history = make_history([
        ("sensor.trv_valve", "2026-11-09 23:00", "10"),
        ("timer.pausa", "2026-11-09 23:00", "idle"),
        ("sensor.trv_valve", "2026-11-10 06:00", "40"),   # above 25, held 2 min -> 06:02
        ("sensor.trv_valve", "2026-11-10 09:00", "5"),
    ])
    config = {
        "triggers": [{"trigger": "device", "domain": "sensor", "type": "value", "device_id": "x",
                      "entity_id": "sensor.trv_valve", "above": 25, "for": {"minutes": 2}}],
        "conditions": [
            {"condition": "state", "entity_id": "timer.pausa", "state": ["idle"]},
            {"condition": "device", "domain": "sensor", "type": "is_value", "device_id": "x",
             "entity_id": "sensor.trv_valve", "above": 30},
        ],
    }
    assert statuses(backtest(config, history, START, END)) == [("06:02", EXECUTED)]


def test_vacuum_is_docked_condition(make_history):
    history = make_history([
        ("binary_sensor.mission", "2026-11-09 23:00", "on"),
        ("vacuum.bogdana", "2026-11-09 23:00", "cleaning"),
        ("binary_sensor.mission", "2026-11-10 10:00", "off"),
        ("vacuum.bogdana", "2026-11-10 10:00", "returning"),
        ("vacuum.bogdana", "2026-11-10 10:00:20", "docked"),
    ])
    config = {
        "triggers": [{"trigger": "device", "domain": "binary_sensor", "type": "not_running",
                      "device_id": "x", "entity_id": "binary_sensor.mission", "for": {"seconds": 30}}],
        "conditions": [{"condition": "device", "domain": "vacuum", "type": "is_docked",
                        "device_id": "x", "entity_id": "vacuum.bogdana"}],
    }
    assert statuses(backtest(config, history, START, END)) == [("10:00", EXECUTED)]


def test_restart_glitches_do_not_fire(make_history):
    # TV goes off -> unknown -> off around a restart; real HA fires nothing.
    history = make_history([
        ("media_player.tv", "2026-11-09 23:00", "off"),
        ("media_player.tv", "2026-11-10 11:32:22", "unknown"),
        ("media_player.tv", "2026-11-10 11:32:33", "off"),
        ("media_player.tv", "2026-11-10 14:25:02", "idle"),
    ])
    on = {"triggers": [{"trigger": "state", "entity_id": "media_player.tv", "from": "off"}]}
    off = {"triggers": [{"trigger": "state", "entity_id": "media_player.tv", "to": "off"}]}
    downtime = [(ts("2026-11-10 11:32:10"), ts("2026-11-10 11:32:40"))]
    assert statuses(backtest(on, history, START, END)) == [("11:32", EXECUTED), ("14:25", EXECUTED)]
    assert statuses(backtest(on, history, START, END, downtime=downtime)) == [("14:25", EXECUTED)]
    assert backtest(off, history, START, END, downtime=downtime).runs == []


def test_restart_cancels_pending_for_timer(make_history):
    history = make_history([
        ("binary_sensor.screen", "2026-11-09 23:00", "on"),
        ("binary_sensor.screen", "2026-11-10 11:30:00", "off"),  # would fire at 11:40
        ("binary_sensor.screen", "2026-11-10 16:33:51", "on"),
        ("binary_sensor.screen", "2026-11-10 16:33:52", "off"),  # fires at 16:43:52
    ])
    config = {"triggers": [{"trigger": "state", "entity_id": "binary_sensor.screen", "to": "off",
                            "for": "00:10:00"}]}
    downtime = [(ts("2026-11-10 11:32:00"), ts("2026-11-10 11:33:00"))]
    result = backtest(config, history, START, END, downtime=downtime)
    assert [r.time.strftime("%H:%M:%S") for r in result.runs] == ["16:43:52"]
    assert result.as_dict()["restarts"][0]["stopped"].startswith("2026-11-10T11:32")


def test_numeric_state_rearms_after_restart(make_history):
    history = make_history([
        ("sensor.t", "2026-11-09 23:00", "10"),
        ("sensor.t", "2026-11-10 10:00:10", "30"),  # crosses during downtime: lost
        ("sensor.t", "2026-11-10 12:00", "31"),     # still above after restart: no fire
        ("sensor.t", "2026-11-10 13:00", "10"),
        ("sensor.t", "2026-11-10 14:00", "30"),     # crosses again: fires
    ])
    config = {"triggers": [{"trigger": "numeric_state", "entity_id": "sensor.t", "above": 25}]}
    downtime = [(ts("2026-11-10 10:00"), ts("2026-11-10 10:01"))]
    assert statuses(backtest(config, history, START, END, downtime=downtime)) == [("14:00", EXECUTED)]


def test_windows_from_events():
    from engine.downtime import START as S, STARTED as SD, STOP as SP, windows_from_events

    events = [
        (SP, ts("2026-11-10 11:32:10")), (S, ts("2026-11-10 11:32:20")), (SD, ts("2026-11-10 11:32:40")),
        (S, ts("2026-11-11 03:00:00")), (SD, ts("2026-11-11 03:01:00")),  # crash: no stop
    ]
    assert windows_from_events(events) == [
        (ts("2026-11-10 11:32:10"), ts("2026-11-10 11:32:40")),
        (ts("2026-11-11 03:00:00"), ts("2026-11-11 03:01:00")),
    ]


def test_extract_thresholds():
    from engine import extract_thresholds

    config = {
        "triggers": [
            {"trigger": "numeric_state", "entity_id": ["sensor.t1", "sensor.t2"], "below": 19.5},
            {"trigger": "device", "domain": "sensor", "type": "value", "entity_id": "sensor.v", "above": 25},
            {"trigger": "numeric_state", "entity_id": "sensor.h", "attribute": "x", "above": 1},
        ],
        "conditions": [{"condition": "numeric_state", "entity_id": "sensor.lux", "above": "input_number.min"}],
    }
    assert extract_thresholds(config) == [
        {"entity_id": "sensor.t1", "kind": "below", "value": 19.5},
        {"entity_id": "sensor.t2", "kind": "below", "value": 19.5},
        {"entity_id": "sensor.v", "kind": "above", "value": 25.0},
    ]


def test_time_trigger_weekday_filter(make_history):
    history = make_history([("sun.sun", "2026-11-09 00:00", "x")])
    # 2026-11-10 is a Tuesday, 2026-11-11 a Wednesday
    config = {"triggers": [{"trigger": "time", "at": "07:00:00", "weekday": ["wed", "sat"]}]}
    result = backtest(config, history, ts("2026-11-10 00:00"), ts("2026-11-12 00:00"))
    assert [r.time.strftime("%d %H:%M") for r in result.runs] == ["11 07:00"]


def test_compare_reports_shifted_runs(make_history):
    history = make_history([
        ("person.a", "2026-11-09 23:00", "home"),
        ("person.a", "2026-11-10 18:17:52", "not_home"),
    ])
    a = {"triggers": [{"trigger": "state", "entity_id": "person.a", "to": "not_home", "for": {"minutes": 10}}]}
    b = {"triggers": [{"trigger": "state", "entity_id": "person.a", "to": "not_home", "for": {"minutes": 5}}]}
    diff = compare(backtest(a, history, START, END), backtest(b, history, START, END))
    assert diff["summary"]["shifted"] == 1
    assert diff["summary"]["only_a"] == diff["summary"]["only_b"] == 0
    assert diff["shifted"][0]["delta_seconds"] == -300
