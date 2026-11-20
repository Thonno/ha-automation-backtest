"""Unit conversion for purpose-specific numeric conditions, mirroring HA's converters.

Each converter maps a unit to "how many of this unit make one base reference"
(HA's `_UNIT_CONVERSION` tables), so value_in_base = value / factor[unit] * factor[base].
Temperature is affine and handled separately.
"""

from __future__ import annotations

from typing import Callable

_MOLAR_VOLUME = 8.31446261815324 * 293.15 / 101325  # m³/mol at 20 °C, 1 atm


def _gas(molar_mass: float, units: tuple[str, ...]) -> dict[str | None, float]:
    all_units = {
        "ppb": 1e9,
        "ppm": 1e6,
        "mg/m³": molar_mass / _MOLAR_VOLUME * 1e3,
        "µg/m³": molar_mass / _MOLAR_VOLUME * 1e6,
    }
    return {u: all_units[u] for u in units}


TABLES: dict[str, dict[str | None, float]] = {
    "power": {"mW": 1000, "W": 1, "kW": 1e-3, "MW": 1e-6, "GW": 1e-9, "TW": 1e-12, "BTU/h": 1 / 0.29307107},
    "co": _gas(28.01, ("ppb", "ppm", "mg/m³", "µg/m³")),
    "ozone": _gas(48.00, ("ppb", "ppm", "µg/m³")),
    "no": _gas(30.0061, ("ppb", "µg/m³")),
    "no2": _gas(46.0055, ("ppb", "ppm", "µg/m³")),
    "so2": _gas(64.066, ("ppb", "µg/m³")),
    "mass_volume": {"µg/m³": 1e6, "mg/m³": 1e3, "g/m³": 1.0},
    "ratio": {None: 1, "ppb": 1e9, "ppm": 1e6, "%": 100},
    "radon": {"Bq/m³": 1, "pCi/L": 1 / 37},
}

# Same unit written differently in the wild.
_ALIASES = {"μg/m³": "µg/m³", "ug/m3": "µg/m³", "µg/m3": "µg/m³", "mg/m3": "mg/m³", "°c": "°C", "°f": "°F", "c": "°C", "f": "°F"}


def _norm(unit: str | None) -> str | None:
    if unit is None:
        return None
    return _ALIASES.get(unit, _ALIASES.get(unit.lower(), unit))


def _temperature(value: float, unit: str | None) -> float | None:
    unit = _norm(unit)
    if unit in (None, "°C"):
        return value
    if unit == "°F":
        return (value - 32) * 5 / 9
    if unit == "K":
        return value - 273.15
    return None


Converter = Callable[[float, "str | None"], "float | None"]


def converter(kind: str, base: str | None) -> Converter:
    """Function (value, unit) -> value in `base`, or None when the unit is not convertible.

    A missing unit (None) is taken to already be the base unit, except for the
    unitless ratio converter where None is a real unit.
    """
    if kind == "temperature":
        return _temperature
    table = TABLES[kind]

    def convert(value: float, unit: str | None) -> float | None:
        unit = _norm(unit)
        if unit is None and None not in table:
            return value
        if unit not in table:
            return None
        return value / table[unit] * table[base]

    return convert
