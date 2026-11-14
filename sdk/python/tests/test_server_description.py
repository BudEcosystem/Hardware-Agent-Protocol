"""Description generation from decorators and argument admission (BHMS-DEV-0xx, AUTH-010/011)."""

from __future__ import annotations

import enum
from typing import Literal

import pytest

from bhms.protocol import schema
from bhms.protocol.canonical import canonical, digest
from bhms.protocol.errors import BhmsError
from bhms.server.decorators import Array, DescriptionError, Range, Schema, Text
from bhms.server.device import Device
from bhms.server.validation import ArgumentValidator, check_units, effective_bounds


def stage_device() -> Device:
    stage = Device(None, "stage-z", capabilities=["bhms.axis.linear"], resources=["stage-z"])

    @stage.property(unit="um", evidence="measured")
    def position() -> float: ...

    @stage.action(effect="reversible", idempotency="absolute", requires_lease=False,
                  completion_evidence="measured", max_duration_ms=5000)
    async def move_to(ctx, target: Range(0, 200, unit="um")) -> {"position": "um"}:  # noqa: F821 - a unit map, not a forward reference
        """Move the stage to an absolute position."""
        return {"position": target}

    return stage


def test_brief_example_description_is_schema_valid_with_stable_digest():  # BHMS-DEV-020, DEV-021
    desc = stage_device().description()
    schema.validate("DeviceDescription", desc)
    body = {k: v for k, v in desc.items() if k != "digest"}
    assert desc["digest"] == digest(body)
    assert stage_device().description() == desc  # deterministic: byte-identical canonical JSON
    assert canonical(stage_device().description()) == canonical(desc)
    action = desc["actions"]["move_to"]
    assert action["input"] == {"type": "object", "additionalProperties": False, "required": ["target"],
                               "properties": {"target": {"type": "number", "x-bhms-unit": "um", "minimum": 0,
                                                         "maximum": 200}}}
    assert action["output"]["properties"] == {"position": {"type": "number", "x-bhms-unit": "um"}}
    assert action["resources"] == ["stage-z"]  # effectful actions default to the device's resources
    assert action["description"] == "Move the stage to an absolute position."
    assert desc["properties"]["position"]["schema"] == {"type": "number", "x-bhms-unit": "um"}
    assert desc["safety"]["stop"] == "unsupported" and desc["safety"]["onDisconnect"] == "unknown"


def test_summary_is_compact_and_valid():  # BHMS-DEV-011
    dev = stage_device()
    summary = dev.summary("online")
    schema.validate("DeviceSummary", summary)
    assert len(canonical(summary)) <= 1600
    assert summary["actions"] == ["move_to"] and summary["properties"] == ["position"]


def test_digest_changes_when_a_bound_changes():  # BHMS-DEV-023
    a = stage_device().description()["digest"]
    dev = Device(None, "stage-z", capabilities=["bhms.axis.linear"], resources=["stage-z"])

    @dev.property(unit="um", evidence="measured")
    def position() -> float: ...

    @dev.action(effect="reversible", idempotency="absolute", completion_evidence="measured", max_duration_ms=5000)
    async def move_to(ctx, target: Range(0, 300, unit="um")) -> {"position": "um"}:  # noqa: F821 - a unit map, not a forward reference
        """Move the stage to an absolute position."""

    assert dev.description()["digest"] != a


def test_bare_float_argument_is_refused_with_a_fix():  # BHMS-DEV-041
    dev = Device(None, "d1", resources=["r"])
    with pytest.raises(DescriptionError) as info:
        @dev.action(effect="none", idempotency="idempotent")
        def scale(ctx, factor: float): ...
    assert "factor" in str(info.value) and "Range(" in str(info.value) and 'unit="1"' in str(info.value)


def test_effectful_action_needs_max_duration():  # BHMS-DEV-030
    dev = Device(None, "d1", resources=["r"])
    with pytest.raises(DescriptionError, match="max_duration_ms"):
        @dev.action(effect="reversible", idempotency="absolute")
        def go(ctx): ...


def test_requires_lease_needs_a_resource_and_resources_are_a_subset():  # BHMS-DEV-032
    dev = Device(None, "d1")
    with pytest.raises(DescriptionError, match="at least one resource"):
        @dev.action(effect="reversible", idempotency="absolute", requires_lease=True, max_duration_ms=10)
        def go(ctx): ...
    dev2 = Device(None, "d2", resources=["a"])
    with pytest.raises(DescriptionError, match="subset"):
        @dev2.action(effect="reversible", idempotency="absolute", max_duration_ms=10, resources=["b"])
        def go2(ctx): ...


def test_requires_fresh_must_name_a_property_once():  # BHMS-DEV-034
    dev = Device(None, "d1", resources=["r"])

    @dev.action(effect="reversible", idempotency="absolute", max_duration_ms=10, requires_fresh={"pressure": 100})
    def go(ctx): ...

    with pytest.raises(DescriptionError, match="requires_fresh"):
        dev.description()


def test_annotations_cover_enums_text_arrays_defaults_and_nullables():
    class Mode(enum.Enum):
        FAST = "fast"
        PRECISE = "precise"

    dev = Device(None, "d1", resources=["r"])

    @dev.action(effect="none", idempotency="idempotent")
    def configure(ctx, mode: Mode, label: Text(max_length=8), speed: Literal["lo", "hi"] = "lo",
                  points: Array(Range(0, 10, unit="mm"), max_items=3) = None,
                  gain: Range(0, 1, unit="1", nullable=True) = None, enabled: bool = True,
                  raw: Schema({"type": "string", "pattern": "^[a-z]+$"}) = "abc"): ...

    schema_in = dev.description()["actions"]["configure"]["input"]
    props = schema_in["properties"]
    assert schema_in["required"] == ["mode", "label"]
    assert props["mode"] == {"enum": ["fast", "precise"], "type": "string"}
    assert props["speed"] == {"enum": ["lo", "hi"], "type": "string", "default": "lo"}
    assert props["points"]["items"] == {"type": "number", "x-bhms-unit": "mm", "minimum": 0, "maximum": 10}
    assert props["gain"]["type"] == ["number", "null"]
    assert props["enabled"] == {"type": "boolean", "default": True}
    schema.validate("DeviceDescription", dev.description())


@pytest.mark.parametrize("bad, path", [
    ({"type": "object", "properties": {"a": {"type": "object", "properties": {"b": {"type": "number"}}}}},
     "properties.a.properties.b"),
    ({"type": "array", "items": {"type": "integer"}}, "items"),
    ({"type": ["number", "null"]}, "x"),
    ({"anyOf": [{"type": "string"}, {"type": "number"}]}, "anyOf[1]"),
])
def test_check_units_deep_scans(bad, path):  # BHMS-DEV-041 (deferred Task 2 finding 3)
    with pytest.raises(ValueError) as info:
        check_units(bad, "x")
    assert path in str(info.value)


def test_output_without_unit_is_refused_at_description_time():  # BHMS-DEV-041 outputs
    dev = Device(None, "d1", resources=["r"])

    @dev.action(effect="none", idempotency="idempotent", output=Schema({"type": "object", "properties": {
        "n": {"type": "number"}}}))
    def count(ctx): ...

    with pytest.raises(DescriptionError, match="output"):
        dev.description()


def test_external_ref_is_refused():  # BHMS-DEV-040
    with pytest.raises(ValueError, match="DEV-040"):
        check_units({"$ref": "https://example.com/s.json"}, "x")


# --------------------------------------------------------------------------- argument admission

MOVE = {"type": "object", "additionalProperties": False, "required": ["target"],
        "properties": {"target": {"type": "number", "x-bhms-unit": "mm", "minimum": 0, "maximum": 200,
                                  "multipleOf": 0.1},
                       "speed": {"type": "number", "x-bhms-unit": "mm", "minimum": 1, "maximum": 50, "default": 10},
                       "mode": {"enum": ["fast", "precise"]},
                       "nested": {"type": "object", "additionalProperties": False,
                                  "properties": {"depth": {"type": "integer", "x-bhms-unit": "1", "maximum": 3}}}}}


def refuse(arguments, **kw) -> BhmsError:
    with pytest.raises(BhmsError) as info:
        ArgumentValidator(MOVE).admit(arguments, **kw)
    error = info.value
    error.to_jsonrpc()  # every refusal is a well-formed JSON-RPC error with mayHaveActed false
    assert error.may_have_acted is False and error.hint
    return error


def test_out_of_range_is_refused_with_field_bound_and_hint_never_clamped():  # BHMS-DEV-044, ERR-011
    error = refuse({"target": 250})
    assert error.bhms_code == "OUT_OF_RANGE" and error.field == "arguments.target"
    assert error.bound == {"maximum": 200}
    assert "250 mm" in error.message and "200 mm" in error.message
    assert "between 0 and 200 mm" in error.hint


def test_admission_applies_defaults_and_keeps_values_exact():  # BHMS-DEV-044
    admitted = ArgumentValidator(MOVE).admit({"target": 50.1})
    assert admitted == {"target": 50.1, "speed": 10}


def test_multiple_of_uses_tolerance():  # BHMS-DEV-071
    assert ArgumentValidator(MOVE).admit({"target": 0.3})["target"] == 0.3
    error = refuse({"target": 50.15})
    assert error.bhms_code == "INVALID_ARGUMENT" and error.bound == {"multipleOf": 0.1}
    assert "50.1" in error.hint and "50.2" in error.hint


def test_quantity_objects_in_the_declared_unit_are_normalised():  # BHMS-DEV-043
    assert ArgumentValidator(MOVE).admit({"target": {"value": 20, "unit": "mm"}}) == {"target": 20, "speed": 10}


def test_quantity_in_another_unit_is_unit_mismatch_with_conversion_hint():  # BHMS-DEV-043, ERR-011
    error = refuse({"target": {"value": 2, "unit": "cm"}})
    assert error.bhms_code == "UNIT_MISMATCH" and error.field == "arguments.target" and error.bound == "mm"
    assert "20 mm" in error.hint
    error = refuse({"target": {"value": 2, "unit": "s"}})
    assert error.bhms_code == "UNIT_MISMATCH" and "cannot be converted" in error.hint


@pytest.mark.parametrize("arguments, code, field", [
    ({"target": "10"}, "INVALID_ARGUMENT", "arguments.target"),
    ({"target": True}, "INVALID_ARGUMENT", "arguments.target"),
    ({}, "INVALID_ARGUMENT", "arguments.target"),
    ({"target": 1, "force": True}, "INVALID_ARGUMENT", "arguments.force"),  # BHMS-SEC-030 authority claim
    ({"target": 1, "mode": "turbo"}, "OUT_OF_RANGE", "arguments.mode"),
    ({"target": 1, "nested": {"depth": 4}}, "OUT_OF_RANGE", "arguments.nested.depth"),
    ({"target": 1, "nested": {"depth": 1.5}}, "INVALID_ARGUMENT", "arguments.nested.depth"),
])
def test_refusal_codes_and_fields(arguments, code, field):  # BHMS-DEV-044
    error = refuse(arguments)
    assert (error.bhms_code, error.field) == (code, field)


def test_unknown_member_hint_lists_accepted_members():
    error = refuse({"target": 1, "override": 1})
    assert "mode, nested, speed, target" in error.hint


def test_policy_bounds_narrow_the_envelope():  # BHMS-AUTH-010
    error = refuse({"target": 150}, bounds={"target": {"maximum": 100}})
    assert error.bhms_code == "OUT_OF_RANGE" and error.bound == {"maximum": 100}
    assert ArgumentValidator(MOVE).admit({"target": 90}, bounds={"target": {"maximum": 100}})["target"] == 90


def test_policy_cannot_widen_and_empty_intersection_is_flagged():  # BHMS-AUTH-011
    node = MOVE["properties"]["target"]
    assert effective_bounds(node, {"maximum": 500}) == {"minimum": 0, "maximum": 200}
    assert effective_bounds(node, {"minimum": 300}).get("empty") is True
