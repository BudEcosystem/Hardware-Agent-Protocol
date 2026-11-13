import math

import pytest

from bhms.protocol.errors import BhmsError
from bhms.protocol.units import UNITS, compatible, convert


def test_exact_conversions():
    assert convert(25, "Cel", "K") == 298.15
    assert convert(1, "mm", "um") == 1000
    assert convert(60, "s", "min") == 1
    assert convert(298.15, "K", "Cel") == 25
    assert convert(32, "[degF]", "Cel") == 0
    assert convert(212, "[degF]", "Cel") == 100
    assert convert(0, "Cel", "[degF]") == 32
    assert convert(1, "bar", "kPa") == 100
    assert convert(1, "L", "mL") == 1000
    assert convert(1, "kg", "mg") == 1_000_000
    assert convert(1, "L/min", "mL/min") == 1000
    assert convert(1, "kHz", "Hz") == 1000
    assert convert(1, "A", "mA") == 1000
    assert convert(500, "mV", "V") == 0.5
    assert convert(1, "h", "min") == 60
    assert convert(1, "cm", "mm") == 10
    assert convert(1, "nm", "um") == 0.001
    assert convert(1, "uL/min", "mL/min") == 0.001
    assert convert(50, "%", "1") == 0.5


def test_angle_and_psi():
    assert convert(180, "deg", "rad") == pytest.approx(math.pi, rel=1e-15)
    assert convert(1000, "mrad", "rad") == 1
    assert convert(1, "[psi]", "Pa") == pytest.approx(6894.757293168361, rel=1e-12)


def test_identity_and_roundtrip():
    for u in UNITS:
        assert convert(3.5, u, u) == 3.5
    assert convert(convert(12.3, "mbar", "[psi]"), "[psi]", "mbar") == pytest.approx(12.3, rel=1e-12)


def test_compatible():
    assert compatible("mm", "nm") and compatible("Cel", "[degF]") and compatible("%", "1")
    assert not compatible("mm", "s")
    assert not compatible("L", "L/min")
    assert not compatible("rad", "1")
    with pytest.raises(BhmsError) as ei:
        compatible("mm", "furlong")
    assert ei.value.code == "INVALID_ARGUMENT"


def test_incompatible_raises_unit_mismatch():
    with pytest.raises(BhmsError) as ei:
        convert(1, "mm", "s")
    assert ei.value.code == "UNIT_MISMATCH"
    assert "length" in ei.value.hint and "time" in ei.value.hint


def test_unknown_unit_is_invalid_argument():
    with pytest.raises(BhmsError) as ei:
        convert(1, "furlong", "m")
    assert ei.value.code == "INVALID_ARGUMENT"
    assert ei.value.field == "unit" and "furlong" in ei.value.message and ei.value.hint


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "3"])
def test_bad_value_rejected(bad):
    with pytest.raises(BhmsError) as ei:
        convert(bad, "m", "mm")
    assert ei.value.code == "INVALID_ARGUMENT"
