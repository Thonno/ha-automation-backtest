# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.2.1] - 2026-11-20

### Added
- **All purpose-specific conditions of Home Assistant 2026.11**, including `select.is_option_selected` ([#1](https://github.com/Thonno/ha-automation-backtest/issues/1)) and `battery.is_charging` ([#2](https://github.com/Thonno/ha-automation-backtest/issues/2))reported by @Aaroneisele55. Also new: `battery.*`, `text.is_equal_to`, `climate.is_hvac_mode` / `is_target_temperature` / `is_target_humidity`, `humidifier.*`, `water_heater.*`, `counter.is_value`, `light.is_brightness`, `temperature.is_value`, `humidity.is_value`, `power.is_value`, `illuminance.*`, `moisture.*`, `air_quality.*`, `cover.<type>_is_open/closed`, `schedule.*`, `update.*`. Only `button.is_being_held` stays unsupported (the hold timing is not in the history).
- Numeric conditions convert units like Home Assistant does (°F/K → °C, kW → W, ppm ↔ µg/m³…) and ignore sensors that report a different unit than the one HA expects.
- GitHub issue templates: unsupported trigger/condition/action, bug report, feature request.
- CI workflow (`.github/workflows/validate.yml`): HACS validation, hassfest, pytest and `node --check` on the frontend.

### Fixed
- `motion`, `occupancy`, `moisture`, `vibration`, `illuminance`: the "not detected" conditions use HA's name `is_not_detected`.
- Purpose-specific conditions leave unavailable/unknown entities out of the *any/all* check, as HA does (before they counted as "not matching").
- `battery.*` conditions on a device or area also include its diagnostic entities, as HA does.
- Covers count as open while opening or closing (HA's `is_closed` attribute is used when present).

## [1.2.0] - 2026-11-20

### Added
- **Actions in the draft editor**: a *Then do* block next to *When* and *And if*, with Home Assistant's own visual editor (or YAML). Draft actions are dry-run in the backtest.
- **Save from the panel**: *Save as new automation* (name required; saving again updates the same automation) or *Save* over the existing one (second click to confirm). Uses Home Assistant's own automation config API.
- **Open in the HA editor with your draft**: *Create in the HA editor* / *Open in the HA editor with these changes* opens the automation editor pre-filled with the draft, unsaved.

### Changed
- `automation_backtest/config`, `to_yaml` and `from_yaml` now include `actions`. A draft that has its own actions only takes `mode` from the saved automation.

### Fixed
- *Create in the HA editor* opened an empty editor and the draft was lost.

## [1.1.0] - 2026-11-20

### Added
- **Dry-run of the actions** for every run that would have executed: service calls, `delay`, `choose`, `if`, `repeat`, `variables`, `stop`, `condition`, `parallel`, `event`. Nothing is ever executed.
- **Controlled entities in the chart**, with a *Real / Simulated / Both* switch. *Simulated* is the state the entity would have had if only this automation had driven it.
- *Actions (dry run)* section in the run details, with the time offset of each step.
- Simulated effects: on/off/toggle (light brightness included), covers, locks, climate, `input_*`, `number`, `select`, `text`, counters, timers, media players, vacuums, valves.
- `mode: single / restart / queued / parallel` taken into account for overlapping runs.
- Action targets given as device, area, floor or label are resolved to entities.
- Websocket `run` / `compare` accept `actions_from`: a draft without actions borrows them from the saved automation.

### Changed
- `wait_*`, scenes, scripts, device actions other than on/off and custom services are listed as *not simulated* instead of being guessed.

## [1.0.2] - 2026-11-20

### Fixed
- The ⋮ *Backtest* entries and the editor button were missing when the app or browser served a cached page: the panel now loads the menu script itself if it is missing.

## [1.0.1] - 2026-11-20

### Added
- *Backtest* button in the automation editor toolbar.
- Touch gestures on the chart: pinch to zoom, drag to move, double-tap to reset, plus − + ◀ ▶ buttons.

### Fixed
- ⋮ menu entries now work with every current frontend menu (`ha-dropdown`, `ha-md-menu`, `ha-list-item`).

## [1.0.0] - 2026-11-20

### Added
- First stable release: replay an automation over the recorder history without executing anything.
- Sidebar panel (admins only) with a timeline of every would-be run (executed, blocked, uncertain), the entities involved, thresholds and Home Assistant restarts.
- Full condition trace for each run, with the blocking condition highlighted.
- Drafts with Home Assistant's own editor (visual or YAML), new automations that don't exist yet, A/B comparison with shifted runs.
- ⋮ → *Backtest* in *Settings → Automations* and in the automation editor (unsaved changes included).
- Restarts modelled: no runs while Home Assistant was down, pending `for:` timers dropped.
- Actions `automation_backtest.run` and `automation_backtest.compare`.

[Unreleased]: https://github.com/Thonno/ha-automation-backtest/compare/v1.2.1...HEAD
[1.2.1]: https://github.com/Thonno/ha-automation-backtest/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/Thonno/ha-automation-backtest/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Thonno/ha-automation-backtest/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/Thonno/ha-automation-backtest/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/Thonno/ha-automation-backtest/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/Thonno/ha-automation-backtest/releases/tag/v1.0.0
