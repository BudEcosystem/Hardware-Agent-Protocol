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
        rig.wire.hold(TO_GATEWAY)
        op = await rig.invoke("rig/bench-rig", "set_level", {"value": 10.0}, operation_key="k-unk", wait_ms=4000)
        assert op["state"] in ("unknown", "dispatching", "running")
        rig.wire.release(TO_GATEWAY, deliver=False)  # what it said while unreachable is lost for good
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
                assert exc.code == "STALE"
                await asyncio.sleep(0.05)
        assert done is not None and done["state"] == "completed"
        assert len(rig.wire.sent(cp.Invoke, TO_DEVICE)) == 2  # the first INVOKE was never sent again


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
        assert inhibited.value.code == "STALE"
