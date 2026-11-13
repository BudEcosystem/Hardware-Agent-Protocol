"""UCUM subset used by BHMS, with exact rational conversion.

Conversion only happens when a caller explicitly calls :func:`convert`; nothing in
the protocol converts silently. Arithmetic uses ``Fraction`` so results are the
correctly rounded float (25 Cel -> 298.15 K exactly).
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import NamedTuple

from bhms.protocol.errors import BhmsError


class Unit(NamedTuple):
    dimension: str
    factor: Fraction  # base = value * factor + offset
    offset: Fraction = Fraction(0)


def _f(s: str) -> Fraction:
    return Fraction(s)


_PSI = _f("0.45359237") * _f("9.80665") / (_f("0.0254") ** 2)
_DEG = Fraction(math.pi) / 180

UNITS: dict[str, Unit] = {
    "m": Unit("length", _f(1)), "cm": Unit("length", _f("0.01")), "mm": Unit("length", _f("0.001")),
    "um": Unit("length", _f("0.000001")), "nm": Unit("length", _f("0.000000001")),
    "rad": Unit("angle", _f(1)), "deg": Unit("angle", _DEG), "mrad": Unit("angle", _f("0.001")),
    "s": Unit("time", _f(1)), "ms": Unit("time", _f("0.001")), "us": Unit("time", _f("0.000001")),
    "min": Unit("time", _f(60)), "h": Unit("time", _f(3600)),
    "K": Unit("temperature", _f(1)), "Cel": Unit("temperature", _f(1), _f("273.15")),
    "[degF]": Unit("temperature", _f(5) / 9, _f("459.67") * 5 / 9),
    "L": Unit("volume", _f(1)), "mL": Unit("volume", _f("0.001")),
    "uL": Unit("volume", _f("0.000001")), "nL": Unit("volume", _f("0.000000001")),
    "kg": Unit("mass", _f(1)), "g": Unit("mass", _f("0.001")), "mg": Unit("mass", _f("0.000001")),
    "ug": Unit("mass", _f("0.000000001")),
    "Pa": Unit("pressure", _f(1)), "kPa": Unit("pressure", _f(1000)),
    "bar": Unit("pressure", _f(100000)), "mbar": Unit("pressure", _f(100)),
    "[psi]": Unit("pressure", _PSI),
    "L/min": Unit("flow", _f(1)), "mL/min": Unit("flow", _f("0.001")),
    "uL/min": Unit("flow", _f("0.000001")),
    "A": Unit("current", _f(1)), "mA": Unit("current", _f("0.001")),
    "V": Unit("voltage", _f(1)), "mV": Unit("voltage", _f("0.001")),
    "Hz": Unit("frequency", _f(1)), "kHz": Unit("frequency", _f(1000)),
    "%": Unit("dimensionless", _f("0.01")), "1": Unit("dimensionless", _f(1)),
}


def _lookup(unit: str) -> Unit:
    found = UNITS.get(unit) if isinstance(unit, str) else None
    if found is None:
        raise BhmsError("INVALID_ARGUMENT", f"unknown unit {unit!r}", field="unit",
                        hint=f"use one of the supported UCUM codes: {', '.join(UNITS)}")
    return found


def compatible(a: str, b: str) -> bool:
    """True only when both units share a dimension. Unknown units raise INVALID_ARGUMENT."""
    return _lookup(a).dimension == _lookup(b).dimension


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert ``value`` between units of the same dimension.

    Raises INVALID_ARGUMENT for unknown units or non-finite/non-numeric values and
    UNIT_MISMATCH for incompatible dimensions. Pure; thread-safe.
    """
    src, dst = _lookup(from_unit), _lookup(to_unit)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise BhmsError("INVALID_ARGUMENT", f"value {value!r} must be a finite number", field="value",
                        hint="pass an int or finite float")
    if src.dimension != dst.dimension:
        raise BhmsError("UNIT_MISMATCH", f"cannot convert {from_unit} to {to_unit}", field="unit",
                        bound=to_unit,
                        hint=f"{from_unit} is {src.dimension}, {to_unit} is {dst.dimension}; supply a {dst.dimension} unit")
    if from_unit == to_unit:
        return value
    # Decimal shortest repr, so 298.15 means 298.15 rather than its binary neighbour.
    base = Fraction(repr(value)) * src.factor + src.offset
    return float((base - dst.offset) / dst.factor)
