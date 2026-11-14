"""Fix round 1 regressions: durable pending forwards, no re-send after cancel/stop/deadline, stop frames first,
HTTP backpressure, and the cheap minors. Each test failed against the pre-fix source."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from bhms.client.client import Client
from bhms.gateway import Gateway, GatewayConfig, UpstreamConfig
from bhms.gateway.upstreams import Upstream
from bhms.protocol.errors import BhmsError
from bhms.runtime.authority import Policy
from bhms.runtime.store import StoreError
from bhms.testing.gateway_fleet import build_light_fleet
from bhms.transport.base import TransportClosed
from helpers.gateway_rig import TOKENS, UID, principals, rig

HELPERS = Path(__file__).parent / "helpers"


# ---------------------------------------------------------------- 1. a durable record between send and answer


async def test_a_failed_record_after_the_upstream_accepted_leaves_an_unknown_operation(tmp_path):  # BHMS-OPS-003, 033
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        journal = r.gateway.journal
        real = journal.admit_forwarded

        def lost(**kw):
            raise StoreError("simulated: the record could not be written after the upstream accepted")

        journal.admit_forwarded = lost
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("a/axis-1", "move_to", {"target": 3}, operation_key="k1", wait_ms=500)
        assert exc.value.bhms_code == "INTERNAL" and exc.value.may_have_acted is True
        journal.admit_forwarded = real
        await asyncio.sleep(0.3)
        assert r.axes["a"].commands["move_to"] == 1
        r.gateway.set_policy(Policy(principals(agent_scopes=["read"])))  # the scope is revoked before the retry
        again = await client.actions_invoke("a/axis-1", "move_to", {"target": 3}, operation_key="k1")
        assert again.replayed is True  # the retry finds the pending forward before policy (OPS-033)
        for _ in range(100):
            got = (await client.operations_get(again.operation.operation_id)).operation
            if got.state == "completed":
                break
            await asyncio.sleep(0.05)
        assert got.state == "completed" and r.axes["a"].commands["move_to"] == 1
        assert [o.operation_id async for o in client.iter_operations()] == [got.operation_id]


async def test_a_keyless_forward_without_a_recorded_answer_is_not_lost(tmp_path):
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        journal = r.gateway.journal
        journal.admit_forwarded = lambda **kw: (_ for _ in ()).throw(StoreError("simulated"))
        with pytest.raises(BhmsError):
            await client.actions_invoke("a/axis-1", "move_to", {"target": 4})  # no operationKey
        del journal.admit_forwarded
        assert len(journal.pending_all()) == 1
        r.gateway.journal.convert_all_pending()  # what a restart does
        ops = [o async for o in client.iter_operations()]
        assert len(ops) == 1 and ops[0].key_origin == "server" and ops[0].state == "unknown"


async def test_a_refusal_leaves_no_pending_row_and_no_operation(tmp_path):  # BHMS-OPS-040
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        r.servers["a"].devices["axis-1"].remove_action("move_to")  # the upstream now refuses what the catalog offers
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("a/axis-1", "move_to", {"target": 1}, operation_key="gone")
        assert exc.value.may_have_acted is False
        assert r.gateway.journal.pending_all() == {} and [o async for o in client.iter_operations()] == []


def write_config(path: Path, state: Path, upstream_state: Path, scopes: str) -> None:
    path.write_text(f'''
[gateway]
id = "crash-gw"
state_dir = "{state}"
listen = ["unix:{path.parent}/gw.sock"]
trust_same_uid = false
[[upstream]]
name = "dev"
stdio = "{sys.executable} {HELPERS / "gateway_upstream.py"} {upstream_state}"
[principals.agent]
uids = [{UID}]
scopes = {scopes}
''')


async def connect_when_ready(sock: str) -> Client:
    for _ in range(300):
        try:
            return await Client.connect(f"unix:{sock}", timeout=20)
        except (OSError, BhmsError, TransportClosed):
            await asyncio.sleep(0.1)
    raise AssertionError("gateway did not come up")


async def test_gateway_killed_after_the_upstream_accepted_recovers_the_operation(tmp_path):  # the review's crash test
    config, state, upstream = tmp_path / "gw.toml", tmp_path / "state", tmp_path / "up"
    write_config(config, state, upstream, '["read", "invoke:*/*"]')
    env = {**os.environ, "CRASH": "after-forward"}
    first = subprocess.Popen([sys.executable, str(HELPERS / "gateway_crash.py"), str(config)], env=env)
    try:
        client = await connect_when_ready(f"{tmp_path}/gw.sock")
        for _ in range(100):  # wait until the upstream is connected
            if (await client.devices_list()).devices:
                break
            await asyncio.sleep(0.1)
        with pytest.raises((TransportClosed, BhmsError)):
            await client.actions_invoke("dev/axis-1", "move", {"x": 7}, operation_key="crash-1", wait_ms=5000)
        await client.close()
        assert first.wait(timeout=20) == -signal.SIGKILL  # the gateway died between send and record
    finally:
        if first.poll() is None:
            first.kill()
    log = (upstream / "device.log").read_text().splitlines()
    assert sum(line.startswith("start") for line in log) == 1  # the device acted exactly once
    write_config(config, state, upstream, '["read"]')  # the scope is revoked while the gateway is down
    second = subprocess.Popen([sys.executable, str(HELPERS / "gateway_crash.py"), str(config)])
    try:
        client = await connect_when_ready(f"{tmp_path}/gw.sock")
        again = await client.actions_invoke("dev/axis-1", "move", {"x": 7}, operation_key="crash-1")
        assert again.replayed is True  # OPS-033: the original operation, although the scope is gone
        op_id = again.operation.operation_id
        for _ in range(200):
            got = (await client.operations_get(op_id)).operation
            if got.state == "completed":
                break
            await asyncio.sleep(0.1)
        assert got.state == "completed" and got.result == {"x": 7}
        kinds = [(h.state, h.kind) for h in got.history if h.state in ("unknown", "completed")]
        assert ("unknown", "state") in kinds and ("completed", "reconciliation") in kinds
        await client.close()
    finally:
        second.terminate()
        second.wait(timeout=20)
    log = (upstream / "device.log").read_text().splitlines()
    assert sum(line.startswith("start") for line in log) == 1  # still exactly once


# ---------------------------------------------------------------- 2. no re-send after cancel / stop / deadline


@pytest.mark.parametrize("how", ["cancel", "stop", "deadline"])
async def test_an_in_doubt_forward_is_not_resent_after_cancel_stop_or_deadline(tmp_path, monkeypatch, how):
    block = {"on": True}
    original = Upstream.call

    async def lossy(self, method, params, **kw):
        if method == "actions/invoke" and block["on"]:
            raise TransportClosed("simulated: never written to the upstream")
        return await original(self, method, params, **kw)

    monkeypatch.setattr(Upstream, "call", lossy)
    async with rig(tmp_path, names=("a",)) as r:
        client, admin = await r.client(), await r.client(token=TOKENS["admin"])
        op = (await client.actions_invoke("a/axis-1", "move_to", {"target": 3}, operation_key="k",
                                          deadline_ms=300 if how == "deadline" else None)).operation
        assert op.state == "unknown"
        if how == "cancel":
            await client.operations_cancel(op.operation_id)
        elif how == "stop":
            await admin.stop("halt", device_ids=["a/axis-1"])
        await asyncio.sleep(0.6 if how == "deadline" else 0.2)
        block["on"] = False
        await asyncio.sleep(1.6)  # several reconcile passes
        got = (await client.operations_get(op.operation_id)).operation
        assert got.state == "unknown" and r.axes["a"].commands["move_to"] == 0  # never executed
        assert any(h.kind == "correction" and "not re-sent" in (h.detail or "") for h in got.history)


async def test_a_refused_resend_settles_the_operation_with_proof(tmp_path, monkeypatch):
    block = {"on": True}
    original = Upstream.call

    async def lossy(self, method, params, **kw):
        if method == "actions/invoke" and block["on"]:
            raise TransportClosed("simulated: never written to the upstream")
        return await original(self, method, params, **kw)

    monkeypatch.setattr(Upstream, "call", lossy)
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        op = (await client.actions_invoke("a/axis-1", "move_to", {"target": 3}, operation_key="k")).operation
        assert op.state == "unknown"
        r.servers["a"].devices["axis-1"].remove_action("move_to")
        block["on"] = False
        for _ in range(100):
            got = (await client.operations_get(op.operation_id)).operation
            if got.state != "unknown":
                break
            await asyncio.sleep(0.05)
        assert got.state == "failed" and got.effect == "none" and got.error.may_have_acted is False
        assert [h.kind for h in got.history if h.state == "failed"] == ["reconciliation"]


# ---------------------------------------------------------------- 3. stop frames before bookkeeping


async def test_every_stop_request_is_on_the_wire_before_the_bookkeeping(tmp_path):  # BHMS-AUTH-021
    fleet = await build_light_fleet(40, devices_per=3)
    gateway = Gateway(GatewayConfig(id="stop-order", state_dir=tmp_path / "gw", upstreams=fleet.upstream_configs(),
                                    principals={}, connect_wait_ms=60_000), memory=True)
    await gateway.start()
    await gateway.listen(f"unix:{tmp_path}/gw.sock")
    client = await Client.connect(f"unix:{tmp_path}/gw.sock", timeout=60)
    seen = {}
    original = gateway.router._stop_bookkeeping

    def watch(entries, reason, results, *rest):
        seen["unsent"] = sum(up.client.session._outbox._unfinished_tasks for up in gateway.upstreams.values())
        return original(entries, reason, results, *rest)

    gateway.router._stop_bookkeeping = watch
    try:
        result = await client.stop("order", scope="all")
        assert len(result.stops) == 120 and seen["unsent"] == 0
    finally:
        await client.close()
        await gateway.close()
        await fleet.close()


# ---------------------------------------------------------------- 4. HTTP backpressure


async def test_a_slow_sse_reader_cannot_grow_the_server_without_bound(tmp_path):  # BHMS-LIF-043
    async with rig(tmp_path, names=("a",)) as r:
        listener = r.listeners["gw-http"]
        reader, writer = await asyncio.open_connection("127.0.0.1", r.http_port, limit=1024)
        body = (b'{"jsonrpc":"2.0","id":1,"method":"subscriptions/listen","params":{"_meta":'
                b'{"bhms/protocolVersion":"2026-11-13"},"notifications":{"events":{}}}}')
        writer.write(b"POST /bhms HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
                     b"BHMS-Method: subscriptions/listen\r\nBHMS-Protocol-Version: 2026-11-13\r\n"
                     + f"Authorization: Bearer {TOKENS['admin']}\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
        await writer.drain()
        await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)  # the headers; the client never reads again
        (exchange,) = listener.exchanges
        big, deepest = "x" * 4000, 0
        for _ in range(60):  # ~ 120 MB of events for a client that reads nothing
            for _ in range(500):
                r.gateway.record("device.degraded", device_id="a/axis-1", message=big)
            await asyncio.sleep(0.02)
            deepest = max(deepest, exchange.outgoing.qsize())
            for session in r.gateway.rpc.sessions:
                assert session._outbox.qsize() <= 256
        assert deepest <= exchange.OUTGOING_BOUND  # the writer waits instead of queueing without bound
        received = b""
        try:  # now read: the stream ends with endReason overflow (the session's slow-consumer policy engaged)
            while b"endReason" not in received:
                received += await asyncio.wait_for(reader.read(1 << 20), 10)
        finally:
            writer.close()
        assert b'"endReason":"overflow"' in received
        for _ in range(100):
            if not listener.exchanges:
                break
            await asyncio.sleep(0.05)
        assert not listener.exchanges


# ---------------------------------------------------------------- minors


async def test_a_gateway_key_refused_by_a_plain_unix_upstream_is_a_clear_config_error(tmp_path):
    from helpers.devices import build

    srv, axis = build(tmp_path / "up", name="plain")  # default policy: this uid is admin but not a gateway
    await srv.listen(f"unix:{tmp_path}/plain.sock")
    config = GatewayConfig(id="gw", state_dir=tmp_path / "gw", principals={"agent": {"uids": [UID], "scopes": ["read", "invoke:*/*"]}},
                           upstreams=(UpstreamConfig(name="plain", url=f"unix:{tmp_path}/plain.sock"),), connect_wait_ms=3000)
    async with Gateway(config, memory=True) as gateway:
        listener = await gateway.listen(f"unix:{tmp_path}/gw.sock")
        async with await Client.connect(f"unix:{tmp_path}/gw.sock") as client:
            with pytest.raises(BhmsError) as exc:
                await client.actions_invoke("plain/axis-1", "move_to", {"target": 1}, operation_key="k")
        await listener.close()
    await srv.close()
    assert "'plain'" in exc.value.message and "gateway = true" in exc.value.hint and exc.value.may_have_acted is False
    assert axis.commands["move_to"] == 0


async def test_a_malformed_but_digest_correct_description_is_dropped_without_a_reconnect_loop(tmp_path):
    from helpers.devices import build

    from bhms.protocol.canonical import digest
    from bhms.transport import serve_unix

    srv, _ = build(tmp_path / "bad", name="bad")
    await srv.start()
    good = srv.devices["axis-1"].description()
    broken = {k: v for k, v in good.items() if k != "digest"}
    broken["actions"] = ["not", "a", "map"]
    broken["digest"] = digest(broken)

    async def describe(params, ctx):
        return {"description": broken}

    async def listing(params, ctx):
        return {"devices": [{**srv.devices["axis-1"].summary("online"), "digest": broken["digest"]}]}

    srv.rpc.register("devices/describe", describe)
    srv.rpc.register("devices/list", listing)
    listener = await serve_unix(str(tmp_path / "bad.sock"), srv.rpc.handle_connection)
    config = GatewayConfig(id="gw", state_dir=tmp_path / "gw", principals={}, connect_wait_ms=3000,
                           upstreams=(UpstreamConfig(name="bad", url=f"unix:{tmp_path}/bad.sock"),))
    async with Gateway(config, memory=True) as gateway:
        await asyncio.sleep(1.0)
        up = gateway.upstreams["bad"]
        assert up.status == "up" and up.connections == 1  # no crash into a reconnect loop
        assert gateway.catalog.get("bad/axis-1") is None
    await listener.close()
    await srv.close()


async def test_settled_operations_leave_the_upstream_index(tmp_path):
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        op = (await client.actions_invoke("a/axis-1", "move_to", {"target": 1}, operation_key="p", wait_ms=2000)).operation
        assert op.state == "completed"
        await asyncio.sleep(0.1)
        assert r.gateway.router.by_upstream == {}

