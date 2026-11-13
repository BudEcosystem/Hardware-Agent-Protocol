"""The schema, its examples and the pydantic models agree (spec/bhms acceptance tests).

* Every valid example validates against its ``against`` definition and round-trips
  through the pydantic model to identical canonical JSON.
* Every ``invalid-*`` example fails both the schema and the model.
* The method and notification tables in spec/bhms/README.md, the schema maps,
  ``bhms.protocol.types`` and the error table all agree.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from bhms.protocol import types
from bhms.protocol.canonical import canonical, digest
from bhms.protocol.errors import CODES

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "spec" / "bhms"
SCHEMA = json.loads((SPEC / "schema" / "bhms.schema.json").read_text())
EXAMPLES = sorted((SPEC / "examples").glob("*.json"))
VALID = [p for p in EXAMPLES if not p.name.startswith("invalid-")]
INVALID = [p for p in EXAMPLES if p.name.startswith("invalid-")]


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _validator(def_ref: str) -> Draft202012Validator:
    return Draft202012Validator({**SCHEMA, "$ref": def_ref})


def _def_name(def_ref: str) -> str:
    assert def_ref.startswith("#/$defs/"), def_ref
    return def_ref.removeprefix("#/$defs/")


def _markdown_table(text: str, heading: str) -> list[list[str]]:
    """Rows (cells stripped) of the first table after a '## heading' line."""
    section = text.split(f"\n## {heading}\n", 1)[1]
    rows = []
    for line in section.splitlines():
        if line.startswith("## "):
            break
        if line.startswith("|") and not set(line) <= set("|-: "):
            rows.append([c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))])
    return rows[1:]  # drop the header row


def test_schema_is_valid_2020_12():
    Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_examples_exist_and_follow_convention():
    assert len(VALID) > 50 and len(INVALID) > 20
    for path in EXAMPLES:
        body = _load(path)
        expected = {"$comment", "against", "message"} | ({"expect"} if path in INVALID else set())
        assert set(body) == expected, path.name
        assert body["$comment"].strip(), path.name
        assert _def_name(body["against"]) in SCHEMA["$defs"], path.name


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_example_validates_and_round_trips(path: Path):
    body = _load(path)
    message = body["message"]
    errors = sorted(_validator(body["against"]).iter_errors(message), key=str)
    assert not errors, f"{path.name}: {errors[0].message} at {list(errors[0].absolute_path)}"
    name = _def_name(body["against"])
    model = types.parse(name, message)
    assert canonical(types.dump(name, model)) == canonical(message)


def _all_errors(errors):
    for error in errors:
        yield error
        yield from _all_errors(error.context or [])


def _pointer(error) -> str:
    return "".join(f"/{part}" for part in error.absolute_path)


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_invalid_example_is_rejected_for_the_labelled_reason(path: Path):
    body = _load(path)
    errors = list(_validator(body["against"]).iter_errors(body["message"]))
    assert errors, f"schema accepted {path.name}"
    expect = body["expect"]
    assert set(expect) <= {"path", "keyword", "message"}
    found = [(_pointer(e), e.validator, e.message) for e in _all_errors(errors)]
    assert any(p == expect["path"] and k == expect["keyword"] and expect.get("message", "") in m
               for p, k, m in found), f"{path.name}: expected {expect}, got {found}"
    with pytest.raises(ValidationError):
        types.parse(_def_name(body["against"]), body["message"])


def _member_names(signature: str) -> set[str]:
    """Member names in a README signature such as `{deviceId, filter?, scope: "all"}` (types and literals dropped)."""
    signature = re.sub(r'"[^"]*"', "", signature.replace("\\|", ","))
    signature = re.sub(r":\s*[A-Z][A-Za-z]*(\[\])?", "", signature)
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", signature))


def test_every_spec_method_is_in_the_schema_and_types():
    readme = (SPEC / "README.md").read_text()
    rows = _markdown_table(readme, "Methods")
    spec_methods = {row[0].strip("`"): (row[1]) for row in rows}
    for row in rows:
        method = row[0].strip("`")
        params_sig, result_sig = (part.strip() for part in row[2].split("→", 1))
        params_def = SCHEMA["$defs"][_def_name(SCHEMA["x-bhms-methods"][method]["params"])]
        assert _member_names(params_sig) == set(params_def["properties"]) - {"_meta"}, method
        result_def = SCHEMA["$defs"][_def_name(SCHEMA["x-bhms-methods"][method]["result"])]
        result_members = set(result_def["properties"]) - {"_meta", "resultType"}
        braces = re.findall(r"`(\{[^`]*\})`", result_sig)
        assert braces, method
        assert _member_names(braces[-1]) == result_members, method
    assert spec_methods, "method table not found"
    assert set(spec_methods) == set(SCHEMA["x-bhms-methods"])
    assert set(spec_methods) == set(types.METHODS)
    for method, tier in spec_methods.items():
        entry = SCHEMA["x-bhms-methods"][method]
        expected_tier, expected_cap = ("core", None) if tier == "core" else ("optional", tier.strip("`"))
        assert (entry["tier"], entry.get("capability")) == (expected_tier, expected_cap), method
        spec = types.METHODS[method]
        assert (spec.tier, spec.capability) == (expected_tier, expected_cap), method
        for key in ("params", "result", "request", "response"):
            assert _def_name(entry[key]) == getattr(spec, key).__name__, (method, key)


def test_every_spec_notification_is_in_the_schema_and_types():
    rows = _markdown_table((SPEC / "README.md").read_text(), "Notifications")
    spec_notifications = {row[0].strip("`") for row in rows}
    assert spec_notifications == set(SCHEMA["x-bhms-notifications"]) == set(types.NOTIFICATIONS)
    for name, entry in SCHEMA["x-bhms-notifications"].items():
        spec = types.NOTIFICATIONS[name]
        assert _def_name(entry["params"]) == spec.params.__name__
        assert _def_name(entry["notification"]) == spec.notification.__name__
        assert entry["direction"] == spec.direction


def test_every_method_notification_and_error_has_an_example():
    against = {_def_name(_load(p)["against"]) for p in VALID}
    for method, entry in SCHEMA["x-bhms-methods"].items():
        assert _def_name(entry["request"]) in against, f"no request example for {method}"
        assert _def_name(entry["response"]) in against, f"no response example for {method}"
    for name, entry in SCHEMA["x-bhms-notifications"].items():
        assert _def_name(entry["notification"]) in against, f"no example for {name}"
    codes: set[str] = set()

    def collect(value: object) -> None:
        if isinstance(value, dict):
            if "bhmsCode" in value:
                codes.add(value["bhmsCode"])
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    for path in VALID:
        collect(_load(path)["message"])
    assert codes == set(CODES)


def test_error_tables_agree():
    assert {k: (v["code"], v["retry"]) for k, v in SCHEMA["x-bhms-errors"].items()} == {
        k: (v.number, v.retry) for k, v in CODES.items()}
    rows = _markdown_table((SPEC / "10-errors.md").read_text(), "10.2 Code table")
    assert {r[0].strip("`"): (int(r[1]), r[2]) for r in rows} == {k: (v.number, v.retry) for k, v in CODES.items()}
    assert set(SCHEMA["$defs"]["BhmsErrorCode"]["enum"]) == set(CODES)


def test_every_schema_def_has_a_python_type():
    assert set(types.DEFS) == set(SCHEMA["$defs"])


# Definitions with "properties" that describe embedded JSON Schema documents, not message objects.
EMBEDDED_SCHEMA_DEFS = {"ObjectSchema"}
OBJECT_DEFS = sorted(n for n, d in SCHEMA["$defs"].items() if "properties" in d and n not in EMBEDDED_SCHEMA_DEFS)


@pytest.mark.parametrize("name", OBJECT_DEFS)
def test_model_members_match_schema(name: str):
    definition = SCHEMA["$defs"][name]
    model = types.DEFS[name]
    assert isinstance(model, type) and issubclass(model, BaseModel), name
    fields = {(info.alias or field): info for field, info in model.model_fields.items()}
    assert set(fields) == set(definition["properties"]), name
    required = {alias for alias, info in fields.items() if info.is_required()}
    assert required == set(definition.get("required", [])), name
    closed = definition.get("additionalProperties") is False
    assert (model.model_config.get("extra") == "forbid") == closed, name


def test_description_digests_are_correct():
    for path in VALID:
        message = _load(path)["message"]
        description = message.get("result", {}).get("description") if isinstance(message, dict) else None
        if isinstance(description, dict) and "digest" in description:
            body = {k: v for k, v in description.items() if k != "digest"}
            assert description["digest"] == digest(body), path.name
    get = _load(SPEC / "examples" / "programs.get.response.json")["message"]["result"]
    assert get["info"]["digest"] == digest(get["program"])


def test_agent_tools_match_the_spec():
    tools = SCHEMA["x-bhms-agent-tools"]
    assert len(tools) <= 8
    rows = _markdown_table((SPEC / "12-agent-surface.md").read_text(), "12.1 Tools")
    assert [r[0].strip("`") for r in rows] == list(tools)
    for tool, entry in tools.items():
        assert _def_name(entry["input"]) in types.DEFS and _def_name(entry["result"]) in types.DEFS
        assert entry["description"]
        assert (SPEC / "examples" / f"agent.{tool}.input.json").exists(), tool


def test_operation_settled_helper():
    op = types.parse("Operation", _load(SPEC / "examples" / "operations.list.response.json")
                     ["message"]["result"]["operations"][0])
    assert op.state == "unknown" and op.settled
    assert types.SETTLED_STATES == types.TERMINAL_STATES | {"unknown"}


def test_explicit_null_rejected_where_schema_forbids():
    body = _load(SPEC / "examples" / "leases.acquire.request.json")["message"]
    body["params"]["waitMs"] = None
    assert not _validator("#/$defs/LeasesAcquireRequest").is_valid(body)
    with pytest.raises(ValidationError, match="must not be null"):
        types.parse("LeasesAcquireRequest", body)
