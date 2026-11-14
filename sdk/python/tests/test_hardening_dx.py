"""Task 7b group B: packaging and developer experience (Task 10 "SDK gaps", Task 11 S8/S9, Task 1 minors)."""

from __future__ import annotations

import pytest

from bhms.client.client import Client
from bhms.server.decorators import DescriptionError
from bhms.server.device import Device
from bhms.server.server import DeviceServer

# ---------------------------------------------------------------------------- B8: who receives the device is explicit


async def _read(tmp_path, declare):
    srv = DeviceServer("getters", state_dir=str(tmp_path))
    dev = srv.device("d-1", name="D")
    dev.report_alive()
    declare(dev)
    await srv.listen(f"unix:{tmp_path}/s.sock")
    client = await Client.connect(f"unix:{tmp_path}/s.sock")
    try:
        return {name: (await client.properties_read("d-1", name, fresh=True)).observation.value for name in dev.properties}
    finally:
        await client.close()
        await srv.close()


async def test_a_getter_default_argument_is_never_replaced_by_the_device(tmp_path):
    """Task 10 gap 4: ``def get(register=register)`` in a loop silently received the device instead of its default."""
    def declare(dev):
        for register in (7, 9):
            @dev.property(name=f"r{register}", unit="1", evidence="reported")
            def get(register=register) -> float:
                return float(register)

    assert await _read(tmp_path, declare) == {"r7": 7.0, "r9": 9.0}


async def test_a_getter_receives_the_device_by_name_or_annotation(tmp_path):
    def declare(dev):
        @dev.property(unit="1", evidence="reported")
        def named(device) -> float:
            return float(len(device.device_id))

        @dev.property(unit="1", evidence="reported")
        def annotated(d: Device, scale=2) -> float:
            return float(len(d.device_id) * scale)

        @dev.property(unit="1", evidence="reported")
        async def keyword_only(*, device, offset=1) -> float:
            return float(len(device.device_id) + offset)

    assert await _read(tmp_path, declare) == {"named": 3.0, "annotated": 6.0, "keyword_only": 4.0}


@pytest.mark.parametrize("source, fragment", [
    ("def bad(x) -> float: return 1.0", "name it 'device'"),                       # an unmarked required parameter
    ("def bad(device, d: Device) -> float: return 1.0", "more than one"),           # two candidates
    ("def bad(*args) -> float: return 1.0", "name it 'device'"),                    # nothing to bind by
    ("def bad(device, other) -> float: return 1.0", "name it 'device'"),            # a second required parameter
])
def test_an_ambiguous_getter_signature_is_refused_when_declared(source, fragment):
    dev = Device(None, "d-1")
    namespace = {"Device": Device}
    exec(source, namespace)  # noqa: S102 - the signatures under test
    with pytest.raises(DescriptionError) as exc:
        dev.property(unit="1", evidence="reported")(namespace["bad"])
    assert fragment in str(exc.value) and "bad" in str(exc.value)


# ---------------------------------------------------------------------------- B10: unit registry gaps (Task 10 gap 2)

from bhms.protocol import units  # noqa: E402
from bhms.protocol.errors import BhmsError  # noqa: E402


@pytest.mark.parametrize("value, src, dst, expected", [
    (3000, "{rev}/min", "{rev}/s", 50.0), (1.5, "{rev}/s", "{rev}/min", 90.0),   # rotational speed
    (2.5, "mmol/L", "umol/L", 2500.0), (250, "umol/L", "mmol/L", 0.25), (0.002, "mol/L", "mmol/L", 2.0),
    (1500, "mW", "W", 1.5), (0.75, "kW", "W", 750.0), (2, "W", "mW", 2000.0),
    (400, "[ppm]", "%", 0.04), (0.5, "%", "[ppm]", 5000.0), (1_000_000, "[ppm]", "1", 1.0),
    (2, "m3", "L", 2000.0), (500, "L", "m3", 0.5),
    (90, "L/h", "L/min", 1.5), (2, "mL/min", "L/h", 0.12),
])
def test_the_added_units_convert_exactly(value, src, dst, expected):
    assert units.convert(value, src, dst) == expected
    assert units.compatible(src, dst)


def test_rotational_speed_is_not_a_frequency_and_concentration_is_not_dimensionless():
    for a, b in (("{rev}/min", "Hz"), ("{rev}/min", "rad"), ("mmol/L", "1"), ("W", "V"), ("[ppm]", "mmol/L")):
        assert not units.compatible(a, b)
        with pytest.raises(BhmsError) as exc:
            units.convert(1, a, b)
        assert exc.value.bhms_code == "UNIT_MISMATCH"
    for alias in ("rpm", "r/min", "ppm", "mM"):  # codes are UCUM, case-sensitive; the common spellings are named in the hint
        with pytest.raises(BhmsError) as exc:
            units.convert(1, alias, "1")
        assert exc.value.bhms_code == "INVALID_ARGUMENT"
    assert "{rev}/min" in exc.value.hint


def test_the_spec_registry_table_lists_exactly_the_implemented_units():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[3] / "spec" / "bhms" / "04-devices.md").read_text()
    table = text.split("| Dimension | Codes |", 1)[1].split("\n\n", 1)[0]
    listed = set()
    for row in table.splitlines()[2:]:
        codes = row.strip("|").split("|", 1)[1]
        listed |= {c for c in __import__("re").findall(r"`([^`]+)`", codes) if not c[0].isdigit() or c == "1"}
    assert listed == set(units.UNITS)


def test_a_conversion_that_overflows_a_double_is_out_of_range():  # B14 (Task 1 minor): it raised OverflowError
    with pytest.raises(BhmsError) as exc:
        units.convert(1e308, "kg", "ug")
    assert exc.value.bhms_code == "OUT_OF_RANGE" and exc.value.field == "value" and "ug" in exc.value.message


# ---------------------------------------------------------------------------- B11/B14: one name for the code; picklable errors

import pickle  # noqa: E402
import warnings  # noqa: E402


def test_bhms_error_and_operation_error_spell_the_code_the_same_way():
    """Task 10 gap 7: ``OperationError.bhms_code`` versus ``BhmsError.code``. ``bhms_code`` is the one name (the wire member
    ``bhmsCode``); ``BhmsError.code`` stays for one release as a deprecated alias."""
    from bhms.protocol.types import OperationError

    exc = BhmsError("STALE", "changed", hint="describe again")
    assert exc.bhms_code == "STALE"
    assert OperationError.model_validate(exc.to_operation_error()).bhms_code == exc.bhms_code
    with pytest.warns(DeprecationWarning, match="bhms_code"):
        assert exc.code == "STALE"
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert exc.to_jsonrpc()["data"]["bhmsCode"] == "STALE"  # the SDK itself never uses the deprecated alias


def test_bhms_error_survives_pickling_with_every_member():  # B14 (Task 1 minor): unpickling raised TypeError
    exc = BhmsError("LEASE_CONFLICT", "held", field="leaseId", bound=["a/x"], operation_id="op-1", may_have_acted=True,
                    retry="same-key", hint="wait")
    back = pickle.loads(pickle.dumps(exc))
    assert type(back) is BhmsError and back.to_operation_error() == exc.to_operation_error() and str(back) == "held"


def test_the_mcp_extra_matches_the_range_the_bridge_supports():
    """Task 10 gap 7: the bridge is written against the mcp 1.26+ and 2.x API; the extra must not admit a 3.x that renames it."""
    import tomllib
    from pathlib import Path

    from bhms.bridges import mcp as bridge

    extras = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())["project"]["optional-dependencies"]
    assert f"mcp{bridge.SUPPORTED_MCP}" in extras["mcp"]
    assert bridge.SUPPORTED_MCP == ">=1.26,<3"


# ---------------------------------------------------------------------------- B12/B13: device loss and results out of range

import logging  # noqa: E402

from bhms.server import DeviceLost, Range  # noqa: E402


async def _serve(tmp_path, declare):
    srv = DeviceServer("dx", state_dir=str(tmp_path))
    dev = srv.device("lh-1", name="Liquid handler", resources=["lh-1/pipette"])
    dev.report_alive()
    declare(dev)
    await srv.listen(f"unix:{tmp_path}/s.sock")
    return srv, await Client.connect(f"unix:{tmp_path}/s.sock")


class PowerLost(DeviceLost):
    """What a twin raises when its instrument loses power mid-command (Task 11 S9)."""


@pytest.mark.parametrize("raised, expected_level, traceback", [
    (PowerLost("mains dropped during aspirate"), logging.WARNING, False),
    (ConnectionResetError("serial link reset"), logging.WARNING, False),
    (TimeoutError("no reply in 2 s"), logging.WARNING, False),
    (KeyError("a bug in the adapter"), logging.ERROR, True),
])
async def test_expected_device_loss_is_logged_without_a_traceback_and_ends_unknown(tmp_path, caplog, raised, expected_level,
                                                                                   traceback):
    def declare(dev):
        @dev.action(effect="irreversible", idempotency="relative", max_duration_ms=1000)
        async def aspirate(ctx) -> None:
            raise raised

    srv, client = await _serve(tmp_path, declare)
    try:
        with caplog.at_level(logging.DEBUG, logger="bhms"):
            op = (await client.actions_invoke("lh-1", "aspirate", {}, wait_ms=2000)).operation
        assert op.state == "unknown" and op.effect == "unknown"  # the outcome is the same either way (BHMS-OPS-004)
        assert op.error.bhms_code == "DEADLINE_EXCEEDED" and op.error.may_have_acted is True
        assert op.error.retry == "after-reconcile" and type(raised).__name__ in op.error.message
        records = [r for r in caplog.records if "aspirate" in r.getMessage() and r.name == "bhms.executor"]
        assert [r.levelno for r in records] == [expected_level], [r.getMessage() for r in records]
        assert (records[0].exc_info is not None) is traceback
        assert str(raised.args[0]) in records[0].getMessage() and op.operation_id in records[0].getMessage()
    finally:
        await client.close()
        await srv.close()


async def test_a_result_outside_its_declared_range_is_reported_as_such_with_the_value(tmp_path):
    """Task 11 S8: 200.138 uL against Range(0, 200) ended as INTERNAL "returned a result that cannot be recorded"."""
    def declare(dev):
        @dev.action(effect="irreversible", idempotency="relative", max_duration_ms=1000)
        async def aspirate(ctx) -> {"volume": Range(0, 200, unit="uL"), "tip": Range(0, 96, unit="1", integer=True)}:  # noqa: F821
            return {"volume": 200.138, "tip": 3}

        @dev.action(effect="irreversible", idempotency="relative", max_duration_ms=1000)
        async def garbled(ctx) -> {"volume": Range(0, 200, unit="uL")}:  # noqa: F821
            return {"volume": "a lot"}

    srv, client = await _serve(tmp_path, declare)
    try:
        op = (await client.actions_invoke("lh-1", "aspirate", {}, wait_ms=2000)).operation
        assert op.state == "failed" and op.result is None  # BHMS-OPS-008: a result is recorded only when it is valid
        assert op.effect == "unverified" and op.evidence.kind == "reported"  # the device acted and reported completion
        error = op.error
        assert (error.bhms_code, error.field, error.bound, error.may_have_acted) == ("OUT_OF_RANGE", "result.volume",
                                                                                 {"maximum": 200}, True)
        assert "200.138" in error.message and "aspirate" in error.message and "cannot be recorded" not in error.message
        assert "acted" in error.hint and error.retry == "after-reconcile"
        history = (await client.operations_get(op.operation_id)).operation.history
        returned = [h for h in history if h.kind == "evidence"]
        assert returned and '"volume":200.138' in returned[0].detail.replace(" ", "") and '"tip":3' in returned[0].detail.replace(" ", "")
        # anything else that is wrong with a result is still a server-side INTERNAL (a bug, not a measurement)
        bad = (await client.actions_invoke("lh-1", "garbled", {}, wait_ms=2000)).operation
        assert bad.state == "failed" and bad.error.bhms_code == "INTERNAL" and bad.error.may_have_acted is True
    finally:
        await client.close()
        await srv.close()
