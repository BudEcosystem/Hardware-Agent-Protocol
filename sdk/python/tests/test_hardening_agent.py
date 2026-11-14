"""Task 7b group C: agent experience (Task 11 S1-S7, Task 6 minors)."""

from __future__ import annotations

import pytest

from bhms.bridges import AgentBridge, tool_definitions
from bhms.client.client import Client
from bhms.protocol import schema
from bhms.protocol.errors import BhmsError
from bhms.testing.conformance_device import build
from bhms.testing.memory import connect_in_process
from helpers.gateway_rig import rig as gateway_rig


@pytest.fixture
async def rig(tmp_path):
    srv, sim = build(state_dir=str(tmp_path))
    await srv.start()
    client = await Client.from_transport(await connect_in_process(srv.rpc), strict=True)
    bridge = AgentBridge(client, lease_ttl_ms=200)
    yield srv, sim, client, bridge
    await bridge.aclose()
    await client.close()
    await srv.close()


# ---------------------------------------------------------------------------- C15: bhms_find and the devices/list text filter


async def _ids(client, **flt):
    return [d.device_id for d in (await client.devices_list(filter=flt)).devices]


async def test_the_text_filter_matches_ids_and_any_token_case_insensitively(rig):
    """Task 11 S1: ``bhms_find "facility-1"`` found nothing (ids were not searched) and a descriptive phrase found
    nothing (the whole phrase had to occur). A device matches when ANY word occurs in its id, name, summary, tags or
    capabilities."""
    _, _, client, _ = rig
    assert await _ids(client, text="AXIS-1") == ["axis-1"]                      # the device id, any case
    assert await _ids(client, text="pump-1") == ["pump-1"]
    assert await _ids(client, text="a syringe to dose my assay") == ["pump-1"]  # one word of a description is enough
    assert await _ids(client, text="a") == ["axis-1", "pump-1"]                 # a lone one-letter word is still a word
    assert await _ids(client, text="linear  SYRINGE") == ["axis-1", "pump-1"]   # OR over the words
    assert await _ids(client, text="bhms.axis") == ["axis-1"]                   # capabilities are searched
    assert await _ids(client, text="conformance") == ["axis-1", "pump-1"]       # tags, as before
    assert await _ids(client, text="spectrometer zebra") == []
    assert await _ids(client, text="syringe", capability="bhms.axis.*") == []   # filters still combine with AND


async def test_capability_star_means_any_capability(rig):  # S3: "*" was refused by a pattern error
    _, _, client, bridge = rig
    assert await _ids(client, capability="*") == ["axis-1", "pump-1"]
    found = await bridge.call("bhms_find", {"capability": "*"})
    assert not found.is_error and [d["deviceId"] for d in found.data["devices"]] == ["axis-1", "pump-1"]
    bad = await bridge.call("bhms_find", {"capability": "Not A Capability"})  # the pattern is in the tool schema now
    assert bad.error["bhmsCode"] == "INVALID_ARGUMENT" and bad.error["field"] == "capability"
    assert "pattern" in schema.load_schema()["$defs"]["AgentFindInput"]["properties"]["capability"]


async def test_find_with_no_match_says_how_many_devices_exist_and_how_to_list_them(rig):
    _, _, _, bridge = rig
    found = await bridge.call("bhms_find", {"text": "facility microscope"})
    assert not found.is_error and found.data["devices"] == [] and found.data["totalDevices"] == 2
    schema.validate("AgentFindData", found.data)
    assert found.summary.startswith("0 devices match") and "2 devices exist" in found.summary
    assert "call bhms_find with no arguments to list everything" in found.summary
    everything = await bridge.call("bhms_find", {})
    assert [d["deviceId"] for d in everything.data["devices"]] == ["axis-1", "pump-1"] and "totalDevices" not in everything.data
    # any word matches, so a phrase can match many devices ("for" occurs in "conformance"): the best match comes first
    ranked = await bridge.call("bhms_find", {"text": "the syringe pump for dosing"})
    assert [d["deviceId"] for d in ranked.data["devices"]] == ["pump-1", "axis-1"] and ranked.summary.startswith("2 devices")
    by_id = await bridge.call("bhms_find", {"text": "axis-1"})
    assert [d["deviceId"] for d in by_id.data["devices"]] == ["axis-1"]


def test_the_find_tool_says_that_no_arguments_lists_everything():
    find = next(t for t in tool_definitions() if t.name == "bhms_find")
    assert "no arguments" in find.description and "list" in find.description
    text = find.input_schema["properties"]["text"]["description"]
    assert "any" in text.lower() and "id" in text


# ---------------------------------------------------------------------------- C16: the unknown-device hint names candidates


async def test_unknown_device_hint_suggests_the_namespaced_id(tmp_path):
    """Task 11 S2: ``notice-1`` behind a gateway is ``notice/notice-1``; the refusal said only "no device"."""
    async with gateway_rig(tmp_path) as r:
        client = await r.client()
        with pytest.raises(BhmsError) as exc:
            await client.devices_describe("axis-1")
        assert exc.value.bhms_code == "UNKNOWN_DEVICE"
        assert "did you mean a/axis-1 or b/axis-1" in exc.value.hint and exc.value.bound == ["a/axis-1", "b/axis-1"]
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("AXIS-1", "move_to", {"target": 1})
        assert "a/axis-1" in exc.value.hint and exc.value.may_have_acted is False
        with pytest.raises(BhmsError) as exc:
            await client.devices_describe("nothing-like-it")
        assert "did you mean" not in exc.value.hint and exc.value.bound is None and "devices/list" in exc.value.hint
        bridge = AgentBridge(client)
        try:
            refused = await bridge.call("bhms_read", {"device_id": "axis-1", "property": "position"})
            assert refused.error["bhmsCode"] == "UNKNOWN_DEVICE" and "a/axis-1" in refused.summary
        finally:
            await bridge.aclose()


async def test_unknown_device_hint_never_names_a_device_the_principal_cannot_read(tmp_path):  # BHMS-DEV-010
    from helpers.gateway_rig import principals

    async with gateway_rig(tmp_path, principals_doc=principals(agent_scopes=["lease"])) as r:
        client = await r.client()
        with pytest.raises(BhmsError) as exc:
            await client.devices_describe("axis-1")
        assert exc.value.bhms_code == "UNKNOWN_DEVICE" and "a/axis-1" not in str(exc.value.to_operation_error())


async def test_unknown_device_hint_on_a_device_server(rig):
    _, _, client, _ = rig
    with pytest.raises(BhmsError) as exc:
        await client.devices_describe("Axis-1")
    assert exc.value.bhms_code == "UNKNOWN_DEVICE" and "did you mean axis-1" in exc.value.hint
