"""BHMS-SEC-021 / BHMS-DEV-040: one schema walker, the same bounds at the device server and at the gateway.

Depth counts the subschema steps below the root of an embedded schema (the root is depth 0, at most 32); the count includes the
root and every subschema (at most 10 000); a ``$ref`` may only point into the schema itself.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from bhms.client.client import Client
from bhms.conformance.core import Status
from bhms.conformance.runner import RunOptions, run
from bhms.gateway.upstreams import _description_problem
from bhms.protocol import schema as schema_module
from bhms.protocol.canonical import digest
from bhms.protocol.errors import BhmsError
from bhms.protocol.schema import MAX_SCHEMA_DEPTH, MAX_SUBSCHEMAS, SchemaBoundsError, iter_subschemas
from bhms.server.decorators import DescriptionError, Schema
from bhms.server.device import Device
from bhms.server.validation import check_units
from bhms.testing.memory import connect_in_process
from helpers.gateway_rig import rig


def chain(steps: int, leaf: dict[str, Any] | None = None, keyword: str = "properties") -> dict[str, Any]:
    """A schema whose deepest subschema is ``steps`` subschema steps below the root."""
    node: dict[str, Any] = leaf if leaf is not None else {"type": "string"}
    for _ in range(steps):
        node = {"type": "object", "properties": {"x": node}} if keyword == "properties" else {keyword: node}
    return node


def wide(total: int) -> dict[str, Any]:
    """A schema of ``total`` schemas: the root and ``total - 1`` members of one ``anyOf``."""
    return {"anyOf": [{"type": "string"} for _ in range(total - 1)]}


def device_refusal(schema: dict[str, Any]) -> str | None:
    """What the device server says when a device declares ``schema`` as an action output, or None when it serves it."""
    dev = Device(None, "d1", resources=["r"])

    @dev.action(effect="none", idempotency="idempotent", output=Schema(schema))
    def probe(ctx): ...

    try:
        dev.description()
    except DescriptionError as exc:
        return str(exc)
    return None


def gateway_refusal(schema: dict[str, Any]) -> str | None:
    """Why the gateway does not serve an upstream description that embeds ``schema`` (correct digest), or None when it does."""
    description = {"deviceId": "d", "actions": {"a": {"input": {"type": "object"}, "output": schema}}, "properties": {}, "resources": [],
                   "capabilities": [], "safety": {}}
    description["digest"] = digest(description)
    return _description_problem(description, "d")


CONSUMERS = pytest.mark.parametrize("refusal", [device_refusal, gateway_refusal], ids=["device-server", "gateway"])


def test_the_limits_are_the_ones_the_spec_states():
    assert (MAX_SCHEMA_DEPTH, MAX_SUBSCHEMAS) == (32, 10_000)


@CONSUMERS
def test_depth_32_is_accepted_and_depth_33_refused(refusal):
    assert refusal(chain(MAX_SCHEMA_DEPTH)) is None
    assert "BHMS-SEC-021" in (refusal(chain(MAX_SCHEMA_DEPTH + 1)) or "")


@CONSUMERS
def test_ten_thousand_schemas_are_accepted_and_one_more_refused(refusal):
    assert refusal(wide(MAX_SUBSCHEMAS)) is None
    assert "BHMS-SEC-021" in (refusal(wide(MAX_SUBSCHEMAS + 1)) or "")


@CONSUMERS
def test_a_local_ref_is_accepted_and_a_remote_one_refused(refusal):
    local = {"type": "object", "properties": {"a": {"$ref": "#/$defs/name"}}, "$defs": {"name": {"type": "string"}}}
    assert refusal(local) is None
    for ref in ("http://example.invalid/s.json", "s.json", "//example.invalid/s", "urn:x:y", "http://example.invalid/s.json#/$defs/name"):
        assert "BHMS-DEV-040" in (refusal({"type": "object", "properties": {"a": {"$ref": ref}}}) or ""), ref
    assert "BHMS-DEV-040" in (refusal({"type": "object", "properties": {"a": {"$dynamicRef": "http://example.invalid/s"}}}) or "")


@CONSUMERS
@pytest.mark.parametrize("keyword", ["items", "additionalProperties", "not", "if", "then", "else", "contains", "propertyNames",
                                     "unevaluatedItems", "unevaluatedProperties", "contentSchema"])
def test_every_single_subschema_keyword_is_walked(refusal, keyword):
    assert "BHMS-DEV-040" in (refusal({keyword: {"$ref": "http://example.invalid/s.json"}}) or ""), keyword
    assert refusal(chain(MAX_SCHEMA_DEPTH, keyword=keyword)) is None
    assert "BHMS-SEC-021" in (refusal(chain(MAX_SCHEMA_DEPTH + 1, keyword=keyword)) or "")


@CONSUMERS
@pytest.mark.parametrize("keyword", ["allOf", "anyOf", "oneOf", "prefixItems", "properties", "patternProperties", "$defs", "definitions",
                                     "dependentSchemas"])
def test_every_list_and_map_keyword_is_walked(refusal, keyword):
    child = {"$ref": "http://example.invalid/s.json"}
    container = [child] if keyword in ("allOf", "anyOf", "oneOf", "prefixItems") else {"x": child}
    assert "BHMS-DEV-040" in (refusal({keyword: container}) or ""), keyword


def test_the_walk_is_preorder_names_paths_and_tolerates_what_is_not_a_schema():
    schema = {"type": "object", "properties": {"a": {"items": True}, "b": 5}, "anyOf": [{"not": {}}], "allOf": "nonsense", "$defs": []}
    assert [path for path, _ in iter_subschemas(schema, "s")] == ["s", "s.anyOf[0]", "s.anyOf[0].not", "s.properties.a",
                                                                   "s.properties.a.items", "s.properties.b"]
    assert [path for path, _ in iter_subschemas(True, "s")] == ["s"]
    with pytest.raises(SchemaBoundsError, match=r"^s\.properties\.x\.properties\.x.*deeper than 32"):
        list(iter_subschemas(chain(MAX_SCHEMA_DEPTH + 1), "s"))
    with pytest.raises(SchemaBoundsError) as hostile_name:
        list(iter_subschemas({"properties": {"n" * 1_000_000: {"$ref": "http://example.invalid/" + "r" * 1_000_000}}}, "s"))
    assert len(str(hostile_name.value)) < 400


def test_the_walk_is_iterative_and_stops_at_the_count_without_visiting_the_rest():
    deep = chain(50_000)  # far beyond the interpreter's recursion limit
    with pytest.raises(SchemaBoundsError, match="deeper than 32"):
        list(iter_subschemas(deep, "s"))
    seen = 0
    with pytest.raises(SchemaBoundsError, match="more than 10000 subschemas"):
        for _ in iter_subschemas(wide(2_000_000), "s"):
            seen += 1
    assert seen <= MAX_SUBSCHEMAS


def test_the_device_server_and_the_gateway_share_the_walker(monkeypatch):
    """No second implementation: with the shared limit lowered, both consumers refuse what they accepted before."""
    assert device_refusal(chain(5)) is None and gateway_refusal(chain(5)) is None
    monkeypatch.setattr(schema_module, "MAX_SCHEMA_DEPTH", 4)
    assert "BHMS-SEC-021" in (device_refusal(chain(5)) or "") and "BHMS-SEC-021" in (gateway_refusal(chain(5)) or "")
    with pytest.raises(ValueError, match="BHMS-SEC-021"):
        check_units(chain(5), "x")


# --------------------------------------------------------------------------- over the wire: each hostile variant alone


async def _inject(tmp_path, params: dict[str, Any]) -> None:
    async with await Client.connect(f"unix:{tmp_path}/a.sock") as direct:
        await direct.request("x-conformance/inject", params)


@pytest.mark.parametrize("variant", ["deep", "wide", "remote_ref"])
async def test_the_gateway_does_not_serve_each_hostile_schema_variant_on_its_own(tmp_path, variant, caplog):
    from bhms.conformance.checks.gateway import _is_hostile

    url = "http://127.0.0.1:9/hostile-schema.json"
    async with rig(tmp_path, ("a",), conformance=True) as r:
        client = await r.client(token="tok-admin")
        plain = await client.request("devices/describe", {"deviceId": "a/axis-1"})
        await _inject(tmp_path, {"fault": "hostile_schema", "variant": variant, "url": url})
        for _ in range(50):  # the gateway has fetched the revised description and refused it
            if any("not serving axis-1" in record.getMessage() for record in caplog.records):
                break
            await asyncio.sleep(0.1)
        refusals = [record.getMessage() for record in caplog.records if "not serving axis-1" in record.getMessage()]
        assert refusals and ("BHMS-DEV-040" if variant == "remote_ref" else "BHMS-SEC-021") in refusals[0], refusals
        try:
            shown = await client.request("devices/describe", {"deviceId": "a/axis-1"})
        except BhmsError as exc:  # dropping the device is as good as keeping its last acceptable description
            assert exc.bhms_code == "NOT_FOUND"
        else:
            assert not _is_hostile(shown, variant, url) and shown["description"] == plain["description"]
        await _inject(tmp_path, {"fault": "none"})


async def test_the_hostile_variants_are_independent_and_an_unknown_one_is_refused(tmp_path):
    from bhms.testing.conformance_device import build

    srv, _ = build(memory=True)
    axis = srv.devices["axis-1"]
    plain = axis.description()
    await srv.start()
    try:
        async with await Client.from_transport(await connect_in_process(srv.rpc)) as client:
            found = {}
            for variant in ("deep", "wide", "remote_ref"):
                await client.request("x-conformance/inject", {"fault": "hostile_schema", "variant": variant, "url": "http://h.invalid/s"})
                found[variant] = axis.description()
                assert found[variant]["digest"] == digest({k: v for k, v in found[variant].items() if k != "digest"})
            with pytest.raises(BhmsError) as unknown:
                await client.request("x-conformance/inject", {"fault": "hostile_schema", "variant": "both"})
            assert unknown.value.bhms_code == "INVALID_ARGUMENT" and unknown.value.field == "variant"
            await client.request("x-conformance/inject", {"fault": "none"})
            assert axis.description() == plain
    finally:
        await srv.close()

    def problems(description: dict[str, Any]) -> set[str]:
        out = set()
        for action in description["actions"].values():
            try:
                list(iter_subschemas(action["input"], "input"))
            except SchemaBoundsError as exc:
                out.add("depth" if "deeper" in str(exc) else "count" if "more than" in str(exc) else "ref")
        return out

    assert problems(found["deep"]) == {"depth"} and "$ref" not in str(found["deep"]["actions"]["pulse"]["input"])
    assert problems(found["wide"]) == {"count"} and "$ref" not in str(found["wide"]["actions"]["pulse"]["input"])
    assert problems(found["remote_ref"]) == {"ref"}
    assert "http://h.invalid/s" in str(found["remote_ref"]["actions"]["pulse"]["input"])
    harmless = json.loads(json.dumps(found["remote_ref"]).replace("http://h.invalid/s", "#"))
    assert problems(harmless) == set()  # the remote reference is its only problem: shallow and small


def _only(kept: str):
    """A walker that enforces only one of the three rules (a gateway with the other two forgotten)."""
    real = schema_module.iter_subschemas

    def walker(schema: Any, where: str = "schema"):
        try:
            yield from real(schema, where)
        except SchemaBoundsError as exc:
            kind = "depth" if "deeper" in str(exc) else "count" if "more than" in str(exc) else "ref"
            if kind == kept:
                raise

    return walker


@pytest.mark.parametrize("kept", ["all", "depth", "count", "ref"])
async def test_the_wire_check_fails_a_gateway_that_enforces_only_one_bound(tmp_path, monkeypatch, kept):
    if kept != "all":
        monkeypatch.setattr(schema_module, "iter_subschemas", _only(kept))
    async with rig(tmp_path, ("a",), conformance=True) as r:
        report = await run(RunOptions(target=f"ws://127.0.0.1:{r.ws_port}", token="tok-admin", seed=3,
                                      only=("security.schema-validation-bounds",), conformance_device=("a/axis-1", "a/pump-1"),
                                      upstreams=(f"a=unix:{tmp_path}/a.sock",)))
    assert not report.fatal, report.fatal
    result = next(c for c in report.checks if c.name == "security.schema-validation-bounds")
    assert result.status is (Status.PASSED if kept == "all" else Status.FAILED), result.message
    if kept != "all":
        for variant, rule in (("deep", "depth"), ("wide", "count"), ("remote_ref", "ref")):
            assert (variant in result.message) is (rule != kept), result.message
