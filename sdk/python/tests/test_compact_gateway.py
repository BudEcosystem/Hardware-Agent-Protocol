"""A real gateway serving a compact endpoint: configuration, the invoke path, durable semantics, stop (Task 9b)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from helpers.compact_rig import BENCH, LED, compact_gateway

from bhms.gateway import ConfigError, load_config
from bhms.protocol.errors import BhmsError
from bhms.gateway.compact_bridge import CompactUpstream
from bhms.protocol.types import to_wire
from bhms.testing.compact_endpoint import TO_DEVICE, TO_GATEWAY
from bhms.transport import compact as cp

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "bhms"


# ------------------------------------------------------------------------------------------------ configuration


def test_the_example_config_loads_both_sidecars_and_hashes_its_tokens():
    config = load_config(EXAMPLES / "compact-gateway.toml")
    assert [u.name for u in config.upstreams] == ["led", "arm"]
    assert all(isinstance(u.connector, CompactUpstream) for u in config.upstreams)
    led, arm = (u.connector.bridge for u in config.upstreams)
    assert (led.port, arm.port, arm.baud) == ("/dev/ttyACM0", "/dev/ttyACM1", 115200)
    assert led.digest8.hex() == "238ae39cebf1188c" and arm.device_id == "bhms-arm" and len(arm.layouts.actions) == 11
    assert arm.timing.retries == 3 and arm.timing.reply == 1.0
    assert all(t.startswith("sha256:") for p in config.principals.values() for t in p.get("tokens", []))
    assert led.state_dir == config.state_dir / "compact"


@pytest.mark.parametrize("body,message", [
    ('type = "compact"\nsidecar = "s.json"', "needs port"),
    ('type = "compact"\nport = "/dev/ttyACM0"', "needs sidecar"),
    ('type = "serial"\nport = "x"\nsidecar = "s.json"', "type must be"),
    ('type = "compact"\nport = "x"\nsidecar = "s.json"\nstdio = "cmd"', "stdio does not apply"),
    ('type = "compact"\nport = "x"\nsidecar = "missing.json"', "sidecar"),
    ('type = "compact"\nport = "x"\nsidecar = "s.json"\nbadrate = 1', "unknown key"),
])
def test_bad_compact_upstreams_name_the_key_at_fault(tmp_path, body, message):
    (tmp_path / "s.json").write_text(json.dumps(LED))
    (tmp_path / "g.toml").write_text(f'[gateway]\nid = "g"\n\n[[upstream]]\nname = "u"\n{body}\n')
    with pytest.raises(ConfigError, match=message):
        load_config(tmp_path / "g.toml")


def test_a_sidecar_that_breaks_the_layout_rules_fails_at_load_not_at_the_first_request(tmp_path):
    broken = json.loads(json.dumps(LED))
    broken["actions"]["led_set"]["compact"]["args"] = []
    (tmp_path / "s.json").write_text(json.dumps(broken))
    (tmp_path / "g.toml").write_text('[gateway]\nid = "g"\n\n[[upstream]]\nname = "u"\ntype = "compact"\nport = "x"\n'
                                     'sidecar = "s.json"\n')
    with pytest.raises(ConfigError, match="BHMS-DEV-070"):
        load_config(tmp_path / "g.toml")


# ------------------------------------------------------------------------------------------------ the invoke path


@pytest.mark.usefixtures("native")
async def test_a_gateway_serves_the_compact_device_and_runs_actions_through_it(tmp_path, native):
    async with compact_gateway(tmp_path, native) as rig:
        devices = [d async for d in rig.client.iter_devices()]
        assert [d.device_id for d in devices] == ["rig/bench-rig"] and devices[0].status == "online"
        description = (await rig.client.devices_describe("rig/bench-rig")).description
        assert description.actions["move"].compact.index == 1  # the layouts survive the gateway (DEV-070)
        op = await rig.invoke("rig/bench-rig", "set_level", {"value": 42.5}, operation_key="k-1")
        assert op["state"] == "completed" and op["result"] == {"writes": 1}
        assert rig.endpoint.count("SET") == 1
        replay = await rig.invoke("rig/bench-rig", "set_level", {"value": 42.5}, operation_key="k-1")
        assert replay["operationId"] == op["operationId"] and rig.endpoint.count("SET") == 1  # same key: never twice
        read = to_wire(await rig.client.properties_read("rig/bench-rig", "level"))["observation"]
        assert read["value"] == 425 and read["epoch"] == "compact:1"


@pytest.mark.usefixtures("native")
async def test_a_lost_reply_is_retransmitted_to_a_persistent_endpoint_and_the_action_runs_once(tmp_path, native):
    async with compact_gateway(tmp_path, native) as rig:
        rig.wire.drop(TO_GATEWAY, match=lambda m: isinstance(m, cp.Result))
        op = await rig.invoke("rig/bench-rig", "set_level", {"value": 10.0}, operation_key="k-lost")
        assert op["state"] == "completed" and rig.endpoint.count("SET") == 1
        assert len(rig.wire.sent(cp.Invoke, TO_DEVICE)) == 2


@pytest.mark.usefixtures("native")
async def test_unknown_at_the_gateway_is_reconciled_from_the_endpoint_without_a_second_command(tmp_path, native):
    async with compact_gateway(tmp_path, native, epoch=False) as rig:  # a non-persistent endpoint: QUERY, never a retransmit
        # Every RESULT is lost but the link lives (probes are answered): no HELLO may follow, so the incarnation is unchanged and
        # QUERY is evidence; a HELLO of an endpoint without a persistent epoch would end the right to ask (BHMS-CMP-020).
        rig.wire.drop(TO_GATEWAY, count=1000, match=lambda m: isinstance(m, cp.Result))
        op = await rig.invoke("rig/bench-rig", "set_level", {"value": 10.0}, operation_key="k-unk", wait_ms=4000)
        assert op["state"] in ("unknown", "dispatching", "running")
        rig.wire.clear_rules()
        for _ in range(200):
            op = await rig.operation(op["operationId"])
            if op["state"] == "completed":
                break
            await asyncio.sleep(0.05)
        assert op["state"] == "completed" and op["result"] == {"writes": 1}
        assert rig.endpoint.count("SET") == 1 and len(rig.wire.sent(cp.Invoke, TO_DEVICE)) == 1


@pytest.mark.usefixtures("native")
async def test_a_stale_pending_forward_after_a_gateway_restart_never_resends_the_command(tmp_path, native):
    async with compact_gateway(tmp_path, native) as rig:
        lease = to_wire(await rig.client.leases_acquire(["rig/bench-rig/axis"], 30_000))["lease"]
        op = await rig.invoke("rig/bench-rig", "move", {"duration_ms": 500, "target": 5.0}, lease_id=lease["leaseId"],
                              operation_key="k-restart", wait_ms=0)
        for _ in range(100):
            if rig.endpoint.count("MOVE-start"):
                break
            await asyncio.sleep(0.02)
        await rig.gateway.close()  # the gateway and its bridge stop mid-operation
        from bhms.gateway import Gateway, load_config

        gateway = Gateway(load_config(rig.config_path))
        await gateway.start()
        try:
            await gateway.listen(f"unix:{rig.tmp}/gw2.sock")
            from bhms.client.client import Client

            async with await Client.connect(f"unix:{rig.tmp}/gw2.sock") as client:
                for _ in range(200):
                    got = to_wire(await client.operations_get(op["operationId"]))["operation"]
                    if got["state"] in ("completed", "failed", "canceled"):
                        break
                    await asyncio.sleep(0.05)
                assert got["state"] == "completed" and got["result"] == {"reached": 5.0}
        finally:
            await gateway.close()
        assert rig.endpoint.count("MOVE-start") == 1 and len(rig.wire.sent(cp.Invoke, TO_DEVICE)) == 1


@pytest.mark.usefixtures("native")
async def test_stop_through_the_gateway_reaches_the_board_and_is_confirmed(tmp_path, native):
    async with compact_gateway(tmp_path, native) as rig:
        op = await rig.invoke("rig/bench-rig", "lock", {"duration_ms": 4000}, wait_ms=0)
        for _ in range(100):
            if rig.endpoint.count("LOCK-start"):
                break
            await asyncio.sleep(0.02)
        stops = to_wire(await rig.client.stop("test", scope="all", wait_ms=3000))["stops"]
        assert [(s["deviceId"], s["outcome"], s["evidence"]) for s in stops] == [("rig/bench-rig", "confirmed", "measured")]
        for _ in range(100):
            got = await rig.operation(op["operationId"])
            if got["state"] == "canceled":
                break
            await asyncio.sleep(0.05)
        assert got["state"] == "canceled" and rig.endpoint.count("STOP") == 1


@pytest.mark.usefixtures("native")
async def test_a_digest_mismatch_is_not_served_by_the_gateway(tmp_path, native):
    other = json.loads(json.dumps(BENCH))
    other["description"] += " (rev B)"
    async with compact_gateway(tmp_path, native, sidecar=other, served=False) as rig:
        await asyncio.sleep(0.8)
        assert [d.device_id async for d in rig.client.iter_devices()] == []
        assert rig.bridge.mismatch and rig.endpoint.count("SET") == 0


@pytest.mark.usefixtures("native")
async def test_closing_the_gateway_closes_the_bridge_and_its_link(tmp_path, native):
    async with compact_gateway(tmp_path, native) as rig:
        bridge = rig.bridge
        assert bridge.ready
        await rig.gateway.close()
        assert not bridge.ready and bridge._link is None and not bridge._started


@pytest.mark.usefixtures("native")
async def test_a_proven_epoch_advance_lifts_the_gateways_inhibition_of_the_unknown_operation(tmp_path, native):  # CMP-022, OPS-042
    async with compact_gateway(tmp_path, native) as rig:
        op = await rig.invoke("rig/bench-rig", "lock", {"duration_ms": 4000}, wait_ms=0)
        for _ in range(100):
            if rig.endpoint.count("LOCK-start"):
                break
            await asyncio.sleep(0.02)
        await rig.wire.reboot()  # a persistent epoch: the new boot epoch proves the old work purged
        for _ in range(200):
            got = await rig.operation(op["operationId"])
            if got["state"] == "unknown":
                break
            await asyncio.sleep(0.05)
        assert got["state"] == "unknown"  # the outcome is never guessed ...
        done = None
        for _ in range(100):  # ... but the resource is free again once the gateway has seen the proof
            try:
                done = await rig.invoke("rig/bench-rig", "lock", {"duration_ms": 20})
                break
            except BhmsError as exc:
                assert exc.bhms_code == "STALE"
                await asyncio.sleep(0.05)
        assert done is not None and done["state"] == "completed"
        # The bridge may legitimately retransmit before it learns of the reboot (refused with SESSION_MISMATCH, nothing ran): what
        # matters is what the endpoint did. One lock started before the reboot and one after; none was run a second time.
        assert rig.endpoint.count("LOCK-start") == 2


@pytest.mark.usefixtures("native")
async def test_without_a_persistent_epoch_the_gateways_inhibition_stays_until_a_confirmed_stop(tmp_path, native):  # OPS-042
    async with compact_gateway(tmp_path, native, epoch=False) as rig:
        op = await rig.invoke("rig/bench-rig", "lock", {"duration_ms": 4000}, wait_ms=0)
        for _ in range(100):
            if rig.endpoint.count("LOCK-start"):
                break
            await asyncio.sleep(0.02)
        await rig.wire.reboot()
        for _ in range(200):
            if (await rig.operation(op["operationId"]))["state"] == "unknown":
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.5)
        with pytest.raises(BhmsError) as inhibited:
            await rig.invoke("rig/bench-rig", "lock", {"duration_ms": 20})
        assert inhibited.value.bhms_code == "STALE"


@pytest.mark.parametrize("port", ["tcp://10.0.0.5:7000", "TCP://host:1", "ws://host:1/x", "tls://host:1", "https://host/x"])
def test_a_networked_compact_link_is_refused_at_configuration_load(tmp_path, port):  # BHMS-SEC-050
    (tmp_path / "s.json").write_text(json.dumps(LED))
    (tmp_path / "g.toml").write_text(f'[gateway]\nid = "g"\n\n[[upstream]]\nname = "u"\ntype = "compact"\nport = "{port}"\n'
                                     'sidecar = "s.json"\n')
    with pytest.raises(ConfigError, match="BHMS-SEC-050"):
        load_config(tmp_path / "g.toml")


async def test_the_link_opener_refuses_a_networked_port_even_when_used_directly():  # BHMS-SEC-050
    from bhms.transport.compact import open_stream

    with pytest.raises(ValueError, match="BHMS-SEC-050"):
        await open_stream("tcp://127.0.0.1:9")


@pytest.mark.usefixtures("native")
async def test_a_purge_proof_lifts_only_the_operations_it_names_and_survives_a_gateway_restart(tmp_path, native):  # OPS-042, spec 9.2
    """Under-lift is allowed, lifting without proof is not: the inhibition goes for the named operation only, durably."""
    from bhms.gateway import Gateway, load_config

    async def lock(client_invoke):
        return await client_invoke("rig/bench-rig", "lock", {"duration_ms": 20})

    async with compact_gateway(tmp_path, native) as rig:
        rig.wire.drop(TO_GATEWAY, count=1000, match=lambda m: isinstance(m, cp.Result))
        before = await rig.invoke("rig/bench-rig", "lock", {"duration_ms": 20}, wait_ms=4000)
        rig.wire.clear_rules()
        assert before["state"] == "unknown"
        with pytest.raises(BhmsError) as refused:
            await lock(rig.invoke)
        assert refused.value.bhms_code == "STALE"
        await rig.wire.reboot()  # the persistent epoch advances: the endpoint proves it purged `before`
        for _ in range(200):
            try:
                assert (await lock(rig.invoke))["state"] == "completed"
                break
            except BhmsError as exc:
                assert exc.bhms_code == "STALE"
                await asyncio.sleep(0.05)
        else:
            pytest.fail("the purge proof never lifted the inhibition")
        assert (await rig.operation(before["operationId"]))["state"] == "unknown"  # lifted, not settled: still unknown
        # work dispatched after the proof is not covered by it
        rig.wire.drop(TO_GATEWAY, count=1000, match=lambda m: isinstance(m, cp.Result))
        after = await rig.invoke("rig/bench-rig", "lock", {"duration_ms": 20}, wait_ms=4000)
        rig.wire.clear_rules()
        assert after["state"] == "unknown"
        rig.gateway.router.endpoint_purged("rig", [])  # a proof that names nothing (lost in a restart) lifts nothing
        with pytest.raises(BhmsError) as still:
            await lock(rig.invoke)
        assert still.value.bhms_code == "STALE" and after["operationId"] in still.value.message
        # `before` stays lifted across a gateway restart (the lift is journaled with the operation)
        record = rig.gateway.journal.get(before["operationId"])
        assert record is not None and record.private.get("inhibitionLifted") is True
        await rig.gateway.close()
        gateway = Gateway(load_config(rig.config_path))
        await gateway.start()
        try:
            restarted = gateway.journal.get(before["operationId"])
            assert restarted is not None and restarted.state == "unknown" and restarted.private.get("inhibitionLifted") is True
        finally:
            await gateway.close()


@pytest.mark.usefixtures("native")
async def test_a_gateway_that_restarts_between_the_proof_and_the_lift_lifts_only_what_the_proof_names(tmp_path, native):  # OPS-042
    """The bridge journals the purge proof, the gateway never hears it (it goes down first). After the restart the gateway replays
    the event from its cursor: the operation the proof names is lifted, work dispatched after the proof is not."""
    from bhms.client.client import Client
    from bhms.gateway import Gateway, load_config

    async def settle_listed(client):
        for _ in range(200):
            if [d async for d in client.iter_devices()]:
                return
            await asyncio.sleep(0.05)
        pytest.fail("the restarted gateway never served the device")

    async with compact_gateway(tmp_path, native) as rig:
        rig.wire.drop(TO_GATEWAY, count=10_000, match=lambda m: isinstance(m, cp.Result))  # nothing is ever answered with a RESULT
        before = await rig.invoke("rig/bench-rig", "lock", {"duration_ms": 20}, wait_ms=4000)
        assert before["state"] == "unknown"
        real = rig.gateway.upstream_notification
        rig.gateway.upstream_notification = lambda up, method, params: None if method == "notifications/event" else real(up, method, params)
        epoch = rig.bridge.epoch
        await rig.wire.reboot()  # the bridge proves the purge and journals device.epoch; this gateway hears nothing of it
        for _ in range(200):
            if rig.bridge.epoch != epoch and rig.bridge.ready:
                break
            await asyncio.sleep(0.05)
        with pytest.raises(BhmsError) as unlifted:
            await rig.invoke("rig/bench-rig", "lock", {"duration_ms": 20})
        assert unlifted.value.bhms_code == "STALE"  # the proof never reached the gateway: nothing is lifted (under-lift)
        after = await rig.invoke("rig/bench-rig", "set_level", {"value": 1.0}, wait_ms=4000)  # dispatched after the proof
        assert after["state"] == "unknown"
        await rig.gateway.close()
        gateway = Gateway(load_config(rig.config_path))
        await gateway.start()
        try:
            await gateway.listen(f"unix:{rig.tmp}/gw4.sock")
            async with await Client.connect(f"unix:{rig.tmp}/gw4.sock") as client:
                await settle_listed(client)
                lifted = None
                for _ in range(100):  # the replay of the journaled proof lifts `before`
                    try:
                        lifted = to_wire(await client.actions_invoke("rig/bench-rig", "lock", {"duration_ms": 20}, wait_ms=3000))["operation"]
                        break
                    except BhmsError as exc:
                        assert exc.bhms_code == "STALE"
                        await asyncio.sleep(0.05)
                assert lifted is not None  # dispatched (its own RESULT is dropped too, so it ends unknown: not the point)
                with pytest.raises(BhmsError) as still:  # but never `after`: it was dispatched after the proof
                    await client.actions_invoke("rig/bench-rig", "set_level", {"value": 2.0}, wait_ms=3000)
                assert still.value.bhms_code == "STALE" and after["operationId"] in still.value.message
        finally:
            await gateway.close()
