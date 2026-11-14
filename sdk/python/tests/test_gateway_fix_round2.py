"""Fix round 2 regressions: stop results keep canceledOperations, no phantom operation after a rolled-back admission,
refusal-as-proof only after the key lookup, orphan pending rows inhibit and convert, HTTP cancel per exchange, malformed
descriptions."""

from __future__ import annotations

import asyncio

import aiohttp
import orjson
import pytest

from bhms.gateway import Gateway, GatewayConfig, UpstreamConfig
from bhms.gateway.upstreams import Upstream
from bhms.protocol.errors import BhmsError
from bhms.runtime.store import StoreError
from bhms.transport.base import TransportClosed
from helpers.gateway_rig import TOKENS, UID, rig

META = {"bhms/protocolVersion": "2026-11-13"}


async def test_stop_through_the_gateway_reports_canceled_operations(tmp_path):  # BHMS-AUTH-021
    async with rig(tmp_path, conformance=True) as r:
        client = await r.client()
        stopper = await r.client(token=TOKENS["stopper"])
        running = (await client.actions_invoke("a/axis-1", "slow_move", {"duration_ms": 30000},
                                               operation_key="long")).operation
        await asyncio.sleep(0.2)
        queued = (await client.actions_invoke("a/axis-1", "slow_move", {"duration_ms": 30000},
                                              operation_key="queued")).operation
        stop = (await stopper.stop("halt", device_ids=["a/axis-1"])).stops[0]
        assert stop.canceled_operations == [queued.operation_id]  # never dispatched: canceled
        assert stop.cancel_requested_operations == [running.operation_id]


async def test_a_rolled_back_admission_leaves_no_phantom_operation(tmp_path):
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        journal = r.gateway.journal
        real, notified = journal.mirror, []
        journal.listeners.append(lambda rec, wire: notified.append(rec.id))

        def bad(rec, op, *, source):
            raise StoreError("simulated write failure while recording the answer")

        journal.mirror = bad
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("a/axis-1", "move_to", {"target": 3}, operation_key="k1")
        assert exc.value.bhms_code == "INTERNAL"
        journal.mirror = real
        assert journal.live() == [] and notified == [] and r.gateway.router.unknown == {}  # nothing was published
        assert [o async for o in client.iter_operations()] == []
        again = await client.actions_invoke("a/axis-1", "move_to", {"target": 3}, operation_key="k1")
        assert again.replayed is True  # the pending row is the one operation; the retry does not make a second
        listed = [o async for o in client.iter_operations()]
        assert [o.operation_id for o in listed] == [again.operation.operation_id]


async def _in_doubt_then_refusing(tmp_path, monkeypatch, make_refusal, mutate):
    block = {"on": True}
    original = Upstream.call

    async def lossy(self, method, params, **kw):
        if method == "actions/invoke" and block["on"]:
            raise TransportClosed("simulated: never written to the upstream")
        if method == "actions/invoke":
            raise make_refusal()
        return await original(self, method, params, **kw)

    monkeypatch.setattr(Upstream, "call", lossy)
    r_ctx = rig(tmp_path, names=("a",))
    r = await r_ctx.__aenter__()
    client = await r.client()
    op = (await client.actions_invoke("a/axis-1", "move_to", {"target": 3}, operation_key="k")).operation
    assert op.state == "unknown"
    block["on"] = False
    mutate(r)
    await asyncio.sleep(1.2)
    got = (await client.operations_get(op.operation_id)).operation
    return r_ctx, got


@pytest.mark.parametrize("code", ["UNAUTHORIZED", "INVALID_ARGUMENT", "UNSUPPORTED", "UNSUPPORTED_VERSION"])
async def test_a_refusal_before_the_upstreams_key_lookup_proves_nothing(tmp_path, monkeypatch, code):
    def refusal():
        return BhmsError(code, "refused before the key lookup", field="operationKey" if code == "INVALID_ARGUMENT" else None,
                         bound=["2026-11-13"] if code == "UNSUPPORTED_VERSION" else None, may_have_acted=False,
                         hint="x")

    r_ctx, got = await _in_doubt_then_refusing(tmp_path, monkeypatch, refusal, lambda r: None)
    try:
        assert got.state == "unknown" and got.effect == "unknown"  # not settled failed / effect none
    finally:
        await r_ctx.__aexit__(None, None, None)


async def test_a_refusal_after_the_key_lookup_is_proof(tmp_path, monkeypatch):
    r_ctx, got = await _in_doubt_then_refusing(
        tmp_path, monkeypatch, lambda: BhmsError("LEASE_EXPIRED", "lease gone", may_have_acted=False, hint="x"),
        lambda r: None)
    try:
        assert got.state == "failed" and got.effect == "none" and got.error.may_have_acted is False
    finally:
        await r_ctx.__aexit__(None, None, None)


async def test_a_pending_row_a_failed_record_leaves_inhibits_and_converts_when_writable(tmp_path):
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        journal = r.gateway.journal
        real = journal.admit_forwarded

        def lost(**kw):
            raise StoreError("simulated")

        journal.admit_forwarded = lost
        with pytest.raises(BhmsError):
            await client.actions_invoke("a/axis-1", "move_to", {"target": 4})  # keyless: it cannot be retried
        journal.admit_forwarded = real
        r.gateway.store.set_writable(False)
        try:
            with pytest.raises(BhmsError) as exc:  # the resources are inhibited meanwhile
                await client.actions_invoke("a/axis-1", "move_to", {"target": 5}, operation_key="other")
            assert exc.value.bhms_code in ("STALE", "BUSY")
            await asyncio.sleep(0.8)
            assert journal.pending_all()  # not convertible while the journal cannot be written
        finally:
            r.gateway.store.set_writable(True)
        for _ in range(100):
            ops = [o async for o in client.iter_operations()]
            if ops:
                break
            await asyncio.sleep(0.1)
        assert len(ops) == 1 and ops[0].key_origin == "server" and journal.pending_all() == {}
        assert r.gateway.router._orphans == {}


async def test_http_cancel_needs_the_exchange_id_of_the_stream_it_targets(tmp_path):  # BHMS-TRN-043
    async with rig(tmp_path, names=("a",)) as r:
        url = f"http://127.0.0.1:{r.http_port}/bhms"
        headers = {"Content-Type": "application/json", "BHMS-Method": "subscriptions/listen",
                   "BHMS-Protocol-Version": META["bhms/protocolVersion"],
                   "Authorization": f"Bearer {TOKENS['admin']}"}
        body = orjson.dumps({"jsonrpc": "2.0", "id": 1, "method": "subscriptions/listen",
                             "params": {"_meta": META, "notifications": {"devicesListChanged": True}}})
        cancel = orjson.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}})
        async with aiohttp.ClientSession() as http:
            a = await http.post(url, data=body, headers=headers)  # two clients, one token, one address, the same id
            b = await http.post(url, data=body, headers=headers)
            assert a.status == b.status == 200
            id_a, id_b = a.headers["BHMS-Exchange"], b.headers["BHMS-Exchange"]
            assert id_a != id_b and len(id_a) >= 20
            cancel_headers = {**headers, "BHMS-Method": "notifications/cancelled"}
            async with http.post(url, data=cancel, headers=cancel_headers) as bare:  # no exchange id: ignored
                assert bare.status == 202
            async with http.post(url, data=cancel, headers={**cancel_headers, "BHMS-Exchange": id_a}) as ok:
                assert ok.status == 202
            await asyncio.wait_for(a.read(), 5)  # A's stream ended (nothing more is sent after a cancel)
            assert len(r.listeners["gw-http"].exchanges) == 1  # B is untouched
            b.close()
        for _ in range(100):
            if not r.listeners["gw-http"].exchanges:
                break
            await asyncio.sleep(0.05)
        assert not r.listeners["gw-http"].exchanges


async def test_a_description_that_is_not_an_object_is_dropped_without_a_reconnect_loop(tmp_path):
    from helpers.devices import build

    from bhms.transport import serve_unix

    srv, _ = build(tmp_path / "bad", name="bad")
    await srv.start()

    async def describe(params, ctx):
        return {"description": "not an object"}

    srv.rpc.register("devices/describe", describe)
    listener = await serve_unix(str(tmp_path / "bad.sock"), srv.rpc.handle_connection)
    config = GatewayConfig(id="gw", state_dir=tmp_path / "gw", principals={}, connect_wait_ms=3000,
                           upstreams=(UpstreamConfig(name="bad", url=f"unix:{tmp_path}/bad.sock"),))
    async with Gateway(config, memory=True) as gateway:
        await asyncio.sleep(1.0)
        up = gateway.upstreams["bad"]
        assert up.status == "up" and up.connections == 1 and gateway.catalog.get("bad/axis-1") is None
    await listener.close()
    await srv.close()


async def test_convert_pending_failure_on_a_retry_is_a_busy_error(tmp_path):  # fix round 2, item 7
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        journal = r.gateway.journal
        journal.admit_forwarded = lambda **kw: (_ for _ in ()).throw(StoreError("simulated"))
        with pytest.raises(BhmsError):
            await client.actions_invoke("a/axis-1", "move_to", {"target": 3}, operation_key="k")
        del journal.admit_forwarded
        real = journal.convert_pending
        journal.convert_pending = lambda *a: (_ for _ in ()).throw(StoreError("simulated"))
        with pytest.raises(BhmsError) as exc:
            await client.actions_invoke("a/axis-1", "move_to", {"target": 3}, operation_key="k")
        assert exc.value.bhms_code == "BUSY" and exc.value.may_have_acted is False
        journal.convert_pending = real
        assert (await client.actions_invoke("a/axis-1", "move_to", {"target": 3}, operation_key="k")).replayed is True
        assert UID >= 0
