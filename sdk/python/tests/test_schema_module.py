"""bhms.protocol.schema: packaged bytes, per-def validators, DEV-071 tolerant multipleOf."""

import json
from pathlib import Path

import pytest

from bhms.protocol import schema
from bhms.protocol.errors import BhmsError

SPEC_SCHEMA = Path(__file__).resolve().parents[3] / "spec" / "bhms" / "schema" / "bhms.schema.json"


def test_packaged_bytes_equal_the_spec_source():
    assert schema.schema_bytes() == SPEC_SCHEMA.read_bytes()


def test_package_data_declares_the_schema():
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    assert "protocol/bhms.schema.json" in text


def test_validator_is_cached_and_unknown_def_is_keyerror():
    assert schema.validator("Limits") is schema.validator("Limits")
    with pytest.raises(KeyError):
        schema.validator("NoSuchDef")


def test_validate_accepts_and_refuses_with_json_pointer():
    schema.validate("Limits", {"maxMessageBytes": 1048576, "maxPageSize": 10, "maxWaitMs": 0})
    with pytest.raises(BhmsError) as exc:
        schema.validate("Limits", {"maxMessageBytes": 5, "maxPageSize": 10, "maxWaitMs": 0})
    assert exc.value.code == "INVALID_ARGUMENT"
    assert exc.value.field == "/maxMessageBytes"
    assert exc.value.hint


def test_multiple_of_tolerance_dev_071():
    doc = {"$schema": schema.load_schema()["$schema"], "type": "number", "multipleOf": 0.1}
    v = schema._Validator(doc)
    assert v.is_valid(50.1) and v.is_valid(0.3) and v.is_valid(50) and v.is_valid(0)
    assert not v.is_valid(50.15)
    assert not schema._Validator({"multipleOf": 3}).is_valid(10)
    assert schema._Validator({"multipleOf": 3}).is_valid(9)
