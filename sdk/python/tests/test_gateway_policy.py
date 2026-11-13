"""Gateway step 3: scopes, bound narrowing (served and enforced), refusals that name their rule.

Spec: BHMS-AUTH-002/003/010/011/012, SEC-010/011/012, 07-leases-and-authority.md 7.4 (operations:read).
"""

from __future__ import annotations

import asyncio

import pytest

from bhms import Range
from bhms.client.client import Client
from bhms.gateway import Gateway, GatewayConfig
from bhms.protocol.errors import BhmsError
from bhms.runtime.authority import Policy, token_digest
from helpers.gateway_rig import TOKENS, UID, gateway_policy, principals, rig


async def wait_for_device(client, device_id):
    for _ in range(100):
        if device_id in [d.device_id for d in (await client.devices_list()).devices]:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"{device_id} never appeared")


def rule_of(exc: BhmsError) -> str:
    assert exc.hint.rstrip().endswith("]") and "[rule: " in exc.hint, exc.hint
    return exc.hint.rsplit("[rule: ", 1)[1].rstrip("]")


async def test_default_deny_and_read_only(tmp_path):  # BHMS-SEC-010, AUTH-002
    doc = principals(agent_scopes=["read"])
    doc["nobody"] = {"tokens": [token_digest("nobody-tok")], "scopes": []}
    async with rig(tmp_path, principals_doc=doc) as r:
        reader = await r.client()
        with pytest.raises(BhmsError) as exc:
            await reader.actions_invoke("a/axis-1", "move_to", {"target": 1}, operation_key="x")
        assert exc.value.code == "UNAUTHORIZED" and "invoke:a/axis-1/move_to" in exc.value.hint
        assert rule_of(exc.value) == "scope:invoke" and "scope:invoke" in exc.value.message
        assert r.axes["a"].commands["move_to"] == 0
        nobody = await r.client(token="nobody-tok")
        assert (await nobody.devices_list()).devices == []
        with pytest.raises(BhmsError) as exc:  # hidden devices read as unknown (BHMS-AUTH-002)
            await nobody.devices_describe("a/axis-1")
        assert exc.value.code == "UNKNOWN_DEVICE" and rule_of(exc.value) == "scope:read"
        with pytest.raises(BhmsError) as exc:
            await nobody.events_read()
        assert exc.value.code == "UNAUTHORIZED" and rule_of(exc.value) == "scope:read"


async def test_unknown_token_is_rejected_at_the_upgrade(tmp_path):  # BHMS-SEC-001, TRN-031
    async with rig(tmp_path, names=("a",)) as r:
        with pytest.raises(Exception) as exc:
            await Client.connect(f"ws://127.0.0.1:{r.ws_port}", token="not-a-token")
        assert "401" in str(exc.value)


async def test_hazardous_actions_need_a_literal_scope(tmp_path):  # BHMS-AUTH-003
    async with rig(tmp_path, names=("a",), principals_doc=principals(agent_scopes=["read", "invoke:a/oven-1/*"])) as r:
        dev = r.servers["a"].device("oven-1", name="Oven", description="A hazardous test device.",
                                    capabilities=["bhms.thermal.oven"], resources=["oven-1"])
        dev.report_alive()
        heated = []

        @dev.action(effect="hazardous", idempotency="relative", max_duration_ms=1000)
        async def heat(ctx, target: Range(20, 300, unit="Cel")) -> None:  # noqa: F821
            """Heat to a target."""
            heated.append(target)

        client = await r.client()
        await wait_for_device(client, "a/oven-1")
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("a/oven-1", "heat", {"target": 100}, operation_key="h")
        assert exc.value.code == "UNAUTHORIZED" and rule_of(exc.value) == "scope:hazardous" and not heated
        r.gateway.set_policy(Policy(principals(agent_scopes=["read", "invoke:a/oven-1/heat"])))
        op = (await client.actions_invoke("a/oven-1", "heat", {"target": 100}, operation_key="h2", wait_ms=2000)).operation
        assert op.state == "completed" and heated == [100]


async def test_narrowed_bounds_are_served_and_enforced(tmp_path):  # BHMS-AUTH-010, SEC-020
    bounds = {"a/axis-1/move_to": {"target": {"maximum": 100}}}
    async with rig(tmp_path, names=("a",), principals_doc=principals(bounds=bounds)) as r:
        agent = await r.client()
        admin = await r.client(token=TOKENS["admin"])
        mine = (await agent.devices_describe("a/axis-1")).description.model_dump(by_alias=True, exclude_unset=True)
        theirs = (await admin.devices_describe("a/axis-1")).description.model_dump(by_alias=True, exclude_unset=True)
        assert mine["actions"]["move_to"]["input"]["properties"]["target"]["maximum"] == 100
        assert theirs["actions"]["move_to"]["input"]["properties"]["target"]["maximum"] == 200
        assert mine["digest"] != theirs["digest"]  # the narrowed bytes have their own digest (BHMS-DEV-021)
        # the list agrees with the describe for each principal
        assert (await agent.devices_list()).devices[0].digest == mine["digest"]
        assert (await admin.devices_list()).devices[0].digest == theirs["digest"]
        with pytest.raises(BhmsError) as exc:
            await agent.actions_invoke("a/axis-1", "move_to", {"target": 150}, operation_key="big")
        assert exc.value.code == "OUT_OF_RANGE" and exc.value.bound == {"maximum": 100}
        assert rule_of(exc.value) == "bounds:target" and exc.value.may_have_acted is False
        assert r.axes["a"].commands["move_to"] == 0
        ok = await agent.actions_invoke("a/axis-1", "move_to", {"target": 100}, operation_key="ok", wait_ms=2000)
        assert ok.operation.state == "completed"
        big = await admin.actions_invoke("a/axis-1", "move_to", {"target": 150}, operation_key="big", wait_ms=2000)
        assert big.operation.state == "completed"  # the bound is the agent's, not the device's
        with pytest.raises(BhmsError) as exc:  # a pin on the admin's digest is stale for the agent
            await agent.actions_invoke("a/axis-1", "move_to", {"target": 5}, operation_key="pin",
                                       description_digest=theirs["digest"])
        assert exc.value.code == "STALE" and exc.value.bound == mine["digest"]
        pinned = await agent.actions_invoke("a/axis-1", "move_to", {"target": 5}, operation_key="pin",
                                            description_digest=mine["digest"], wait_ms=2000)
        assert pinned.operation.state == "completed"


async def test_empty_envelope_makes_the_action_unavailable(tmp_path):  # BHMS-AUTH-011
    bounds = {"a/axis-1/move_to": {"target": {"minimum": 300}}}
    async with rig(tmp_path, names=("a",), principals_doc=principals(bounds=bounds)) as r:
        agent = await r.client()
        desc = (await agent.devices_describe("a/axis-1")).description
        assert "move_to" not in desc.actions and "slow" in desc.actions
        listing = (await agent.devices_list()).devices[0]
        assert "move_to" not in listing.actions
        with pytest.raises(BhmsError) as exc:
            await agent.actions_invoke("a/axis-1", "move_to", {"target": 400}, operation_key="e")
        assert exc.value.code == "UNAUTHORIZED" and rule_of(exc.value) == "bounds:empty"


async def test_a_policy_that_widens_a_device_bound_is_rejected(tmp_path):  # BHMS-SEC-011
    wide = {"a/axis-1/move_to": {"target": {"maximum": 500}}}
    async with rig(tmp_path, names=("a",)) as r:
        with pytest.raises(ValueError, match="widens"):
            r.gateway.set_policy(Policy(principals(bounds=wide)))
        client = await r.client()  # the old policy is still in force
        assert (await client.actions_invoke("a/axis-1", "move_to", {"target": 150}, operation_key="k",
                                            wait_ms=2000)).operation.state == "completed"
    # at start-up the same check applies once the upstream is described
    async with rig(tmp_path / "again", names=("a",)) as again:
        broken = GatewayConfig(id="gw2", state_dir=tmp_path / "gw2", principals=principals(bounds=wide),
                               upstreams=again.gateway.config.upstreams, connect_wait_ms=3000)
        with pytest.raises(ValueError, match="widens"):
            await Gateway(broken, memory=True).start()


async def test_policy_change_applies_to_new_admissions_and_is_recorded(tmp_path):  # BHMS-SEC-012
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        assert (await client.actions_invoke("a/axis-1", "move_to", {"target": 1}, operation_key="1",
                                            wait_ms=2000)).operation.state == "completed"
        before = (await client.events_read()).cursor
        r.gateway.set_policy(Policy(principals(agent_scopes=["read"])))
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("a/axis-1", "move_to", {"target": 2}, operation_key="2")
        assert exc.value.code == "UNAUTHORIZED"
        events = (await client.events_read(after=before)).events
        assert [e.type for e in events] == ["policy.changed"]


async def test_operations_read_scope_sees_but_cannot_cancel(tmp_path):  # 7.4 operations:read
    doc = principals()
    doc["auditor"] = {"tokens": [token_digest("aud")], "scopes": ["read", "operations:read"]}
    async with rig(tmp_path, names=("a",), principals_doc=doc) as r:
        owner = await r.client()
        auditor = await r.client(token="aud")
        op = (await owner.actions_invoke("a/axis-1", "slow", {"distance": 1}, operation_key="s")).operation
        assert (await auditor.operations_get(op.operation_id)).operation.operation_id == op.operation_id
        assert [x.operation_id async for x in auditor.iter_operations()] == [op.operation_id]
        with pytest.raises(BhmsError) as exc:
            await auditor.operations_cancel(op.operation_id)
        assert exc.value.code == "UNAUTHORIZED" and rule_of(exc.value) == "ownership:cancel"
        r.axes["a"].gate.set()
        assert UID >= 0


async def test_every_policy_refusal_names_its_rule(tmp_path):  # DX: the brief
    doc = principals(agent_scopes=["read", "invoke:a/axis-1/move_to"], bounds={"a/axis-1/move_to": {"target": {"maximum": 10}}})
    async with rig(tmp_path, names=("a",), principals_doc=doc) as r:
        client = await r.client()
        refusals = []
        for call in (lambda: client.actions_invoke("a/axis-1", "slow", {}, operation_key="1"),
                     lambda: client.actions_invoke("a/axis-1", "move_to", {"target": 50}, operation_key="2"),
                     lambda: client.leases_acquire(["a/axis-1"], 5000),
                     lambda: client.stop("t", device_ids=["a/axis-1"]),
                     lambda: client.operations_get("op-nope")):
            with pytest.raises(BhmsError) as exc:
                await call()
            refusals.append(rule_of(exc.value))
        assert refusals == ["scope:invoke", "bounds:target", "scope:lease", "scope:stop", "scope:operations"]


async def test_reload_policy_from_the_file_applies_at_once(tmp_path):  # BHMS-SEC-012 (SIGHUP)
    from bhms.gateway import load_config
    from helpers.devices import build

    srv, _ = build(tmp_path / "up", name="up", policy=gateway_policy())
    await srv.listen(f"unix:{tmp_path}/up.sock")
    file = tmp_path / "gw.toml"

    def write(scopes: str) -> None:
        file.write_text(f'''
[gateway]
id = "reload"
state_dir = "state"
[[upstream]]
name = "a"
url = "unix:{tmp_path}/up.sock"
[principals.agent]
uids = [{UID}]
scopes = {scopes}
''')

    write('["read", "invoke:*/*"]')
    gateway = Gateway(load_config(file))
    await gateway.start()
    listener = await gateway.listen(f"unix:{tmp_path}/gw.sock")
    try:
        async with await Client.connect(f"unix:{tmp_path}/gw.sock") as client:
            assert (await client.actions_invoke("a/axis-1", "move_to", {"target": 1}, operation_key="1",
                                                wait_ms=2000)).operation.state == "completed"
            write('["read"]')
            gateway.reload_policy()
            with pytest.raises(BhmsError) as exc:
                await client.actions_invoke("a/axis-1", "move_to", {"target": 2}, operation_key="2")
            assert exc.value.code == "UNAUTHORIZED"
            write('["read", "bogus-scope"]')
            with pytest.raises(Exception):  # an invalid file is rejected and the current policy stays
                gateway.reload_policy()
            assert (await client.devices_list()).devices
    finally:
        await listener.close()
        await gateway.close()
        await srv.close()
