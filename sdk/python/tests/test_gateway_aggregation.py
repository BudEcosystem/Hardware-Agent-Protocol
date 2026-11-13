"""Gateway step 1: configuration, upstream connections, aggregation under namespaced ids, discover/list/describe.

Spec: BHMS-DEV-002, DEV-021, DEV-022, LIF-020, LIF-024, SEC-022; capabilities.gateway (03-lifecycle 3.5).
"""

from __future__ import annotations

import asyncio

import pytest

from bhms.client.client import Client
from bhms.gateway import ConfigError, Gateway, GatewayConfig, UpstreamConfig, load_config
from bhms.protocol import schema
from bhms.protocol.canonical import digest
from bhms.protocol.errors import BhmsError
from helpers.gateway_rig import gateway_policy, rig


async def test_aggregates_two_upstreams_with_the_same_device_id(tmp_path):  # BHMS-DEV-002
    async with rig(tmp_path) as r:
        client = await r.client()
        listing = await client.devices_list()
        assert [d.device_id for d in listing.devices] == ["a/axis-1", "b/axis-1"]
        assert all(d.status == "online" for d in listing.devices)
        caps = client.server.capabilities
        assert caps.gateway.cross_device_leases is True and caps.gateway.upstreams == 2
        assert client.server.server_info.name == "gw-test"


async def test_served_description_is_namespaced_and_digest_correct(tmp_path):  # BHMS-DEV-021, SEC-022
    async with rig(tmp_path) as r:
        client = await r.client()
        listing = await client.devices_list()
        for summary in listing.devices:
            desc = (await client.devices_describe(summary.device_id)).description
            wire = desc.model_dump(by_alias=True, exclude_unset=True)
            schema.validate("DeviceDescription", wire)
            assert wire["deviceId"] == summary.device_id
            assert wire["digest"] == summary.digest == digest({k: v for k, v in wire.items() if k != "digest"})
            assert wire["resources"] == [f"{summary.device_id.split('/')[0]}/axis-1"]
        a = (await client.devices_describe("a/axis-1")).description
        b = (await client.devices_describe("b/axis-1")).description
        assert a.digest != b.digest  # the gateway serves its own bytes: ids differ, so digests differ


async def test_stale_digest_is_refused_with_the_current_one(tmp_path):  # BHMS-DEV-022
    async with rig(tmp_path) as r:
        client = await r.client()
        current = (await client.devices_describe("a/axis-1")).description.digest
        assert (await client.devices_describe("a/axis-1", digest=current)).description.digest == current
        with pytest.raises(BhmsError) as exc:
            await client.devices_describe("a/axis-1", digest="sha256:" + "0" * 64)
        assert exc.value.code == "STALE" and exc.value.bound == current


async def test_unknown_device_and_filter_and_paging(tmp_path):
    async with rig(tmp_path, names=("a", "b", "c")) as r:
        client = await r.client()
        with pytest.raises(BhmsError) as exc:
            await client.devices_describe("a/nope")
        assert exc.value.code == "UNKNOWN_DEVICE" and "routing:unknown-device" in exc.value.hint
        first = await client.devices_list(limit=2)
        rest = await client.devices_list(limit=2, cursor=first.next_cursor)
        assert [d.device_id for d in first.devices + rest.devices] == ["a/axis-1", "b/axis-1", "c/axis-1"]
        assert first.next_cursor and rest.next_cursor is None
        hit = await client.devices_list(filter={"capability": "bhms.axis.*", "tag": "test"})
        assert len(hit.devices) == 3
        assert (await client.devices_list(filter={"tag": "absent"})).devices == []


async def test_ids_are_stable_across_gateway_restart(tmp_path):  # BHMS-DEV-002
    async with rig(tmp_path) as r:
        before = [d.device_id for d in (await (await r.client()).devices_list()).devices]
        digests = [d.digest for d in (await (await r.client()).devices_list()).devices]
        await r.gateway.close()
        again = Gateway(r.gateway.config)
        await again.start()
        try:
            listener = await again.listen(r.socket)
            async with await Client.connect(r.socket) as client:
                listing = await client.devices_list()
            await listener.close()
        finally:
            await again.close()
        assert [d.device_id for d in listing.devices] == before and [d.digest for d in listing.devices] == digests


async def test_descriptions_are_cached_by_digest(tmp_path, monkeypatch):
    from bhms.gateway.upstreams import Upstream

    calls: list[str] = []
    original = Upstream._send

    async def counting(self, client, method, params, seconds, trace):
        calls.append(method)
        return await original(self, client, method, params, seconds, trace)

    monkeypatch.setattr(Upstream, "_send", counting)
    async with rig(tmp_path, names=("a",)) as r:
        assert calls.count("devices/describe") == 1
        up = r.gateway.upstreams["a"]
        await up._sync(up.client)  # nothing changed upstream: no second describe
        assert calls.count("devices/describe") == 1 and calls.count("devices/list") == 2


async def test_list_changed_is_propagated(tmp_path):
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        async with await client.subscribe(devices_list_changed=True) as sub:
            dev = r.servers["a"].device("extra-1", name="Extra", description="A device added at run time.",
                                        capabilities=["bhms.axis.linear"], resources=["extra-1"])
            dev.report_alive()
            note = await asyncio.wait_for(sub.__anext__(), 5)
            assert note.method == "notifications/devices/listChanged"
            for _ in range(50):
                ids = [d.device_id for d in (await client.devices_list()).devices]
                if "a/extra-1" in ids:
                    break
                await asyncio.sleep(0.05)
            assert ids == ["a/axis-1", "a/extra-1"]


async def test_upstream_down_marks_devices_offline_and_recovers(tmp_path):
    async with rig(tmp_path, names=("a", "b")) as r:
        client = await r.client()
        await r.servers["a"].close()  # the upstream process dies: its connection to the gateway drops
        await r.listeners["a"].close()
        for _ in range(100):
            statuses = {d.device_id: d.status for d in (await client.devices_list()).devices}
            if statuses["a/axis-1"] == "offline":
                break
            await asyncio.sleep(0.05)
        assert statuses == {"a/axis-1": "offline", "b/axis-1": "online"}
        with pytest.raises(BhmsError) as exc:
            await client.properties_read("a/axis-1", "position")
        assert exc.value.code == "DEVICE_UNAVAILABLE" and exc.value.may_have_acted is False
        assert "isolation:upstream-unavailable" in exc.value.hint
        assert (await client.properties_read("b/axis-1", "position")).observation.quality == "valid"
        # it comes back: the gateway reconnects by itself
        from helpers.devices import build

        r.servers["a"], r.axes["a"] = build(tmp_path / "a", name="up-a", policy=gateway_policy())
        r.listeners["a"] = await r.servers["a"].listen(f"unix:{tmp_path}/a.sock")
        for _ in range(100):
            statuses = {d.device_id: d.status for d in (await client.devices_list()).devices}
            if statuses["a/axis-1"] == "online":
                break
            await asyncio.sleep(0.1)
        assert statuses["a/axis-1"] == "online"
        types = [(e.type, e.device_id) for e in (await client.events_read(types=["device.offline", "device.online"])).events]
        assert types == [("device.offline", "a/axis-1"), ("device.online", "a/axis-1")]


async def test_upstream_with_a_wrong_digest_is_not_served(tmp_path):  # BHMS-SEC-022
    from bhms.transport import serve_unix

    srv, _ = __import__("helpers.devices", fromlist=["build"]).build(tmp_path / "evil", name="evil")
    await srv.start()
    good = srv.devices["axis-1"].description()
    bad = {**good, "digest": "sha256:" + "1" * 64}
    original = srv.rpc._handlers["devices/describe"]

    async def lying(params, ctx):
        reply = await original(params, ctx)
        return {"description": bad} if params.device_id == "axis-1" else reply

    srv.rpc.register("devices/describe", lying)
    listener = await serve_unix(str(tmp_path / "evil.sock"), srv.rpc.handle_connection)
    config = GatewayConfig(id="gw", state_dir=tmp_path / "gw", connect_wait_ms=3000, principals={},
                           upstreams=(UpstreamConfig(name="evil", url=f"unix:{tmp_path}/evil.sock"),))
    async with Gateway(config, memory=True) as gateway:
        assert gateway.catalog.get("evil/axis-1") is None
    await listener.close()
    await srv.close()


async def test_a_schema_invalid_description_stops_being_served(tmp_path):  # BHMS-SEC-021, SEC-022
    from helpers.devices import build

    from bhms.jsonrpc.dispatcher import Server as RpcServer  # noqa: F401
    from bhms.transport import serve_unix

    srv, _ = build(tmp_path / "bad", name="bad")
    await srv.start()
    good = srv.devices["axis-1"].description()
    broken = {k: v for k, v in good.items() if k != "digest"}
    broken["name"] = 123  # structurally fine, but not a string: only the schema validator notices
    broken["digest"] = digest(broken)  # ... but the digest is right for what is served
    async def serve_broken(params, ctx):
        return {"description": broken}

    async def list_broken(params, ctx):
        return {"devices": [{**srv.devices["axis-1"].summary("online"), "digest": broken["digest"]}]}

    srv.rpc.register("devices/describe", serve_broken)
    srv.rpc.register("devices/list", list_broken)
    listener = await serve_unix(str(tmp_path / "bad.sock"), srv.rpc.handle_connection)
    config = GatewayConfig(id="gw", state_dir=tmp_path / "gw", connect_wait_ms=3000, principals={},
                           upstreams=(UpstreamConfig(name="bad", url=f"unix:{tmp_path}/bad.sock"),))
    async with Gateway(config, memory=True) as gateway:
        assert await gateway.wait_validated(10)
        assert gateway.catalog.get("bad/axis-1") is None  # served for a moment, then withdrawn
        events = gateway.events.read(after=None, limit=10, device_id=None, types=["device.degraded"])[0]
        assert [e["deviceId"] for e in events] == ["bad/axis-1"]
    await listener.close()
    await srv.close()


# --------------------------------------------------------------------------- configuration


def test_load_config_from_toml(tmp_path, monkeypatch):
    monkeypatch.setenv("PUMP_TOKEN", "t0k")
    path = tmp_path / "gw.toml"
    path.write_text('''
[gateway]
id = "lab"
state_dir = "st"
listen = ["unix:gw.sock", "ws://127.0.0.1:9000"]
upstream_timeout_ms = 1234

[[upstream]]
name = "bench"
stdio = "{python} servers/stage.py --dir {config_dir}"

[[upstream]]
name = "pump"
url = "ws://127.0.0.1:9100"
token_env = "PUMP_TOKEN"
timeout_ms = 99

[principals.agent]
tokens = ["sha256:%s"]
scopes = ["read", "invoke:bench/*"]
bounds = {"bench/stage-z/move_to" = {target = {maximum = 100}}}
''' % ("0" * 64))
    config = load_config(path)
    assert config.id == "lab" and config.state_dir == tmp_path / "st"
    assert config.listen == (f"unix:{tmp_path}/gw.sock", "ws://127.0.0.1:9000")
    bench, pump = config.upstreams
    assert bench.timeout_ms == 1234 and pump.timeout_ms == 99 and pump.token == "t0k"
    assert "servers/stage.py" in bench.stdio and str(tmp_path) in bench.stdio and "{python}" not in bench.stdio
    assert config.principals["agent"]["bounds"]["bench/stage-z/move_to"]["target"]["maximum"] == 100


@pytest.mark.parametrize("text, needle", [
    ('[gateway]\nid = "x"\nbogus = 1\n', "bogus"),
    ('[[upstream]]\nname = "a/b"\nstdio = "x"\n', "cannot contain '/'"),
    ('[[upstream]]\nname = "a"\n', "exactly one of"),
    ('[[upstream]]\nname = "a"\nstdio = "x"\n[[upstream]]\nname = "a"\nstdio = "y"\n', "unique"),
    ('[gateway]\ndurability = "yolo"\n', "durability"),
    ('[principals.p]\nscopes = ["read"]\ntokens = ["plaintext-secret"]\n', "GatewayPolicy"),
    ('[[upstream]]\nname = "a"\nurl = "ws://h:1"\ntoken_env = "BHMS_NOT_SET_ANYWHERE"\n', "token_env"),
    ('[nonsense]\n', "unknown top-level"),
])
def test_invalid_config_names_the_key(tmp_path, text, needle):
    path = tmp_path / "bad.toml"
    path.write_text(text)
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert needle in str(exc.value)

