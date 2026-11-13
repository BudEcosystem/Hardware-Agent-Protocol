"""JSON-RPC session over real Unix sockets (plus a fake transport for queue mechanics)."""

import asyncio
import logging

import orjson
import pytest

from bhms import transport as tr
from bhms.jsonrpc.session import Complete, JsonRpcError, Notification, Session
from bhms.protocol.errors import BhmsError
from bhms.transport import Peer, Transport, TransportClosed

MIB = 1024 * 1024


class Rig:
    """A client Session and a server Session joined by a real Unix socket."""

    def __init__(self):
        self.server_sessions: list[Session] = []

    async def start(self, tmp_path, handler, *, client_kw=None, server_kw=None):
        self.ready = asyncio.Event()
        self.server_done = asyncio.Event()

        async def on_transport(t):
            s = Session(t, role="server", handler=handler, **(server_kw or {}))
            self.server_sessions.append(s)
            s.start()
            self.ready.set()
            await s.wait_closed()

        self.path = str(tmp_path / "rpc.sock")
        self.listener = await tr.serve_unix(self.path, on_transport)
        self.client = Session(await tr.connect_unix(self.path), role="client", **(client_kw or {})).start()
        await asyncio.wait_for(self.ready.wait(), 5)
        self.server = self.server_sessions[0]
        return self

    async def raw(self, handler=None):
        """A raw transport connected to the same listener (to send hand-made frames)."""
        return await tr.connect_unix(self.path)

    async def aclose(self):
        await self.client.close()
        for s in self.server_sessions:
            await s.close()
        await self.listener.close()


@pytest.fixture
async def rig(tmp_path):
    made = []

    async def make(handler, **kw):
        r = await Rig().start(tmp_path, handler, **kw)
        made.append(r)
        return r

    yield make
    for r in made:
        await r.aclose()


async def echo(ctx):
    if ctx.method == "slow":
        await asyncio.sleep(ctx.params["s"])
    return {"resultType": "complete", "echo": ctx.params, "method": ctx.method}


async def raw_exchange(raw, message: bytes) -> dict:
    await raw.send(message)
    return orjson.loads(await asyncio.wait_for(raw.receive(), 5))


async def test_request_response_and_params_reach_the_handler(rig):
    r = await rig(echo)
    result = await r.client.request("devices/list", {"limit": 3})
    assert result == {"resultType": "complete", "echo": {"limit": 3}, "method": "devices/list"}
    assert r.client.peer.kind == "unix"


async def test_responses_may_arrive_out_of_order(rig):
    r = await rig(echo)
    delays = [0.15, 0.01, 0.08, 0.0]
    results = await asyncio.gather(*(r.client.request("slow", {"s": d, "i": i}) for i, d in enumerate(delays)))
    assert [x["echo"]["i"] for x in results] == [0, 1, 2, 3]


async def test_ten_thousand_concurrent_pings_without_loss(rig):
    async def ping(ctx):
        return {"resultType": "complete", "n": ctx.params["n"]}

    r = await rig(ping)
    got = await asyncio.wait_for(asyncio.gather(*(r.client.request("ping", {"n": i}) for i in range(10_000))), 60)
    assert [x["n"] for x in got] == list(range(10_000))
    assert r.client.inflight == 0 and r.server.inflight == 0


async def test_malformed_frame_gets_parse_error_and_session_survives(rig):
    r = await rig(echo)
    raw = await r.raw()
    resp = await raw_exchange(raw, b'{"jsonrpc":"2.0","id":1,"method":')
    assert resp == {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": resp["error"]["message"]}}
    resp = await raw_exchange(raw, b"\xff\xfe not utf8")
    assert resp["error"]["code"] == -32700
    resp = await raw_exchange(raw, b'{"jsonrpc":"2.0","id":2,"method":"x","params":{}}')
    assert resp["id"] == 2 and resp["result"]["method"] == "x"
    await raw.close()


async def test_oversize_frame_is_refused_and_session_survives(rig):
    r = await rig(echo)
    raw = await r.raw()
    big = b'{"jsonrpc":"2.0","id":1,"method":"x","params":{"p":"' + b"a" * (5 * MIB) + b'"}}'
    sender = asyncio.create_task(raw.send(big))
    resp = await asyncio.wait_for(raw.receive(), 10)
    resp = orjson.loads(resp)
    assert resp["id"] is None and resp["error"]["code"] == -32600 and "limit" in resp["error"]["message"]
    await sender
    resp = await raw_exchange(raw, b'{"jsonrpc":"2.0","id":3,"method":"x","params":{}}')
    assert resp["id"] == 3
    await raw.close()


async def test_batch_arrays_and_non_objects_get_invalid_request(rig):
    r = await rig(echo)
    raw = await r.raw()
    for frame in (b'[{"jsonrpc":"2.0","id":1,"method":"x"}]', b"[]", b"42", b'"s"'):
        resp = await raw_exchange(raw, frame)
        assert resp["id"] is None and resp["error"]["code"] == -32600, frame
    await raw.close()


@pytest.mark.parametrize("frame,expected_id", [
    (b'{"jsonrpc":"2.0","id":null,"method":"x"}', None),
    (b'{"jsonrpc":"2.0","id":true,"method":"x"}', None),
    (b'{"jsonrpc":"2.0","id":1.5,"method":"x"}', None),
    (b'{"jsonrpc":"2.0","id":7,"method":5}', 7),
    (b'{"id":8,"method":"x"}', 8),
    (b'{"jsonrpc":"1.0","id":9,"method":"x"}', 9),
    (b'{"jsonrpc":"2.0","id":10}', 10),
])
async def test_invalid_requests_get_invalid_request(rig, frame, expected_id):
    r = await rig(echo)
    raw = await r.raw()
    resp = await raw_exchange(raw, frame)
    assert resp["id"] == expected_id and resp["error"]["code"] == -32600
    await raw.close()


async def test_notifications_get_no_response_and_unknown_ones_are_ignored(rig):
    r = await rig(echo)
    raw = await r.raw()
    await raw.send(b'{"jsonrpc":"2.0","method":"notifications/unknown","params":{}}')
    await raw.send(b'{"jsonrpc":"2.0","method":"x"}')
    await raw.send(b'{"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":999}}')
    resp = await raw_exchange(raw, b'{"jsonrpc":"2.0","id":1,"method":"x","params":{}}')
    assert resp["id"] == 1  # the first thing back is the answer to the request: nothing answered the notifications
    await raw.close()


async def test_server_ignores_responses_and_duplicate_in_flight_id_is_invalid(rig):
    r = await rig(echo)
    raw = await r.raw()
    await raw.send(b'{"jsonrpc":"2.0","id":1,"result":{}}')  # clients must not send responses (BHMS-TRN-001)
    await raw.send(b'{"jsonrpc":"2.0","id":5,"method":"slow","params":{"s":0.3}}')
    resp = await raw_exchange(raw, b'{"jsonrpc":"2.0","id":5,"method":"x","params":{}}')
    assert resp["id"] is None and resp["error"]["code"] == -32600
    first = orjson.loads(await asyncio.wait_for(raw.receive(), 5))
    assert first["id"] == 5 and first["result"]["method"] == "slow"
    await raw.close()


async def test_client_cancel_reaches_the_server_and_no_response_is_sent(rig):
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def handler(ctx):
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    r = await rig(handler)
    task = asyncio.create_task(r.client.request("slow", {}))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(cancelled.wait(), 5)
    assert r.client.inflight == 0
    await asyncio.sleep(0.05)
    assert r.server.inflight == 0


async def test_request_timeout_cancels_and_reports_outcome_unknown(rig):
    cancelled = asyncio.Event()

    async def handler(ctx):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    r = await rig(handler)
    with pytest.raises(BhmsError) as exc:
        await r.client.request("actions/invoke", {}, timeout=0.1)
    assert exc.value.code == "DEADLINE_EXCEEDED" and exc.value.may_have_acted
    assert "operations/get" in exc.value.hint and exc.value.retry == "after-reconcile"
    await asyncio.wait_for(cancelled.wait(), 5)  # notifications/cancelled was sent (BHMS-LIF-053)


async def test_late_response_after_cancel_is_ignored(rig):
    async def handler(ctx):
        await asyncio.sleep(0.1)
        return {"resultType": "complete"}

    r = await rig(handler)
    with pytest.raises(BhmsError):
        await r.client.request("x", {}, timeout=0.02)
    assert (await r.client.request("y", {}))["resultType"] == "complete"


async def test_default_timeout_applies(rig):
    async def handler(ctx):
        await asyncio.sleep(30)

    r = await rig(handler, client_kw={"default_timeout": 0.1})
    with pytest.raises(BhmsError) as exc:
        await r.client.request("x", {})
    assert exc.value.code == "DEADLINE_EXCEEDED"


async def test_error_mapping_and_no_traceback_leak(rig, caplog):
    async def handler(ctx):
        if ctx.method == "bhms":
            raise BhmsError("OUT_OF_RANGE", "too high", field="arguments.v", bound={"max": 5},
                            may_have_acted=False, hint="use <= 5")
        if ctx.method == "rpc":
            raise JsonRpcError(-32601, "Method not found")
        if ctx.method == "opcode":
            raise BhmsError("DEVICE_FAULT", "x")
        raise RuntimeError("SECRET-internal-detail /srv/path")

    r = await rig(handler)
    with pytest.raises(BhmsError) as exc:
        await r.client.request("bhms", {})
    e = exc.value
    assert (e.code, e.field, e.bound, e.hint, e.may_have_acted) == ("OUT_OF_RANGE", "arguments.v", {"max": 5},
                                                                    "use <= 5", False)
    with pytest.raises(JsonRpcError) as rpc:
        await r.client.request("rpc", {})
    assert rpc.value.code == -32601
    with caplog.at_level(logging.ERROR, logger="bhms.jsonrpc"):
        for method in ("boom", "opcode"):
            with pytest.raises(BhmsError) as exc:
                await r.client.request(method, {})
            assert exc.value.code == "INTERNAL"
            assert "SECRET" not in str(exc.value) and "SECRET" not in exc.value.hint
            assert "Traceback" not in exc.value.hint and exc.value.may_have_acted  # unknown whether it acted
    assert "SECRET-internal-detail" in caplog.text  # logged locally, not sent


async def test_streaming_handler_yields_tagged_notifications_then_result(rig):
    async def handler(ctx):
        async def gen():
            yield Notification("notifications/subscriptions/acknowledged", {"notifications": {}})
            for i in range(3):
                yield Notification("notifications/event", {"n": i, "_meta": {"x.com/k": 1}})
            yield Complete({"resultType": "complete", "endReason": "shutdown"})

        return gen()

    r = await rig(handler)
    stream = await r.client.stream("subscriptions/listen", {"notifications": {}})
    seen = [n async for n in stream]
    assert [n["method"] for n in seen] == ["notifications/subscriptions/acknowledged"] + ["notifications/event"] * 3
    assert all(n["params"]["_meta"]["bhms/subscriptionId"] == stream.id for n in seen)
    assert seen[1]["params"]["_meta"]["x.com/k"] == 1  # extension _meta preserved
    assert stream.result["endReason"] == "shutdown"
    assert stream.result["_meta"]["bhms/subscriptionId"] == stream.id
    assert r.client.inflight == 0


async def test_stream_end_without_complete_still_sends_a_result(rig):
    async def handler(ctx):
        async def gen():
            yield Notification("notifications/event", {"n": 1})

        return gen()

    r = await rig(handler)
    stream = await r.client.stream("subscriptions/listen", {})
    assert len([n async for n in stream]) == 1
    assert stream.result["resultType"] == "complete"


async def test_stream_error_surfaces_on_the_iterator(rig):
    async def handler(ctx):
        async def gen():
            yield Notification("notifications/event", {"n": 1})
            raise BhmsError("UNAUTHORIZED", "revoked", hint="get a token")

        return gen()

    r = await rig(handler)
    stream = await r.client.stream("subscriptions/listen", {})
    with pytest.raises(BhmsError) as exc:
        async for _ in stream:
            pass
    assert exc.value.code == "UNAUTHORIZED"


async def test_stream_cancel_stops_the_generator_and_nothing_more_is_sent(rig):
    closed = asyncio.Event()
    produced = []

    async def handler(ctx):
        async def gen():
            try:
                i = 0
                while True:
                    produced.append(i)
                    yield Notification("notifications/event", {"n": i})
                    i += 1
                    await asyncio.sleep(0.005)
            finally:
                closed.set()

        return gen()

    r = await rig(handler)
    async with await r.client.stream("subscriptions/listen", {}) as stream:
        first = await anext(stream)
        assert first["params"]["n"] == 0
    await asyncio.wait_for(closed.wait(), 5)
    count = len(produced)
    await asyncio.sleep(0.05)
    assert len(produced) == count and r.server.inflight == 0 and r.client.inflight == 0


async def test_stream_backpressure_blocks_the_producer_instead_of_buffering(rig):
    produced = []
    closed = asyncio.Event()

    async def handler(ctx):
        async def gen():
            try:
                i = 0
                while True:
                    produced.append(i)
                    yield Notification("notifications/event", {"n": i, "pad": "x" * 4096})
                    i += 1
            finally:
                closed.set()

        return gen()

    r = await rig(handler, client_kw={"stream_queue_size": 4}, server_kw={"outbound_queue_size": 4})
    stream = await r.client.stream("subscriptions/listen", {})  # nobody consumes it
    await asyncio.sleep(0.3)
    a = len(produced)
    await asyncio.sleep(0.3)
    b = len(produced)
    assert a == b, "the producer must stall once the slow consumer's buffers are full"
    assert a < 20_000  # bounded by queue + socket buffers, not by time
    await stream.cancel()
    await asyncio.wait_for(closed.wait(), 5)


class StalledTransport(Transport):
    """A transport whose send blocks until released; records what was sent."""

    def __init__(self):
        self.peer = Peer("test")
        self.max_message_bytes = 4 * MIB
        self.release = asyncio.Event()
        self.sent: list[bytes] = []
        self._inbox: asyncio.Queue = asyncio.Queue()

    async def send(self, data):
        await self.release.wait()
        self.sent.append(data)

    async def receive(self):
        item = await self._inbox.get()
        if item is None:
            raise TransportClosed("eof")
        return item

    async def close(self):
        self._inbox.put_nowait(None)


async def test_bounded_outbound_queue_applies_backpressure_to_callers():
    t = StalledTransport()
    s = Session(t, role="client", outbound_queue_size=2).start()
    notifies = [asyncio.create_task(s.notify("notifications/cancelled", {"requestId": i})) for i in range(10)]
    await asyncio.sleep(0.05)
    done = [n for n in notifies if n.done()]
    assert 0 < len(done) <= 4, len(done)  # queue(2) + one held by the writer (+ slack), the rest are blocked
    t.release.set()
    await asyncio.wait_for(asyncio.gather(*notifies), 5)
    await s.close()
    assert len(t.sent) == 10  # close flushed everything queued


async def test_close_flushes_queued_messages_and_is_idempotent(rig):
    got = []

    async def handler(ctx):
        got.append(ctx.params)
        return {"resultType": "complete"}

    r = await rig(handler)
    await r.client.request("x", {"i": 1})
    await r.client.close()
    await r.client.close()
    assert r.client.closed
    with pytest.raises(TransportClosed):
        await r.client.request("x", {})


async def test_peer_close_fails_pending_requests_and_cancels_handlers(rig):
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def handler(ctx):
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()  # TRN-005: the connection closing abandons in-flight requests
            raise

    r = await rig(handler)
    pending = asyncio.create_task(r.client.request("x", {}))
    stream = await r.client.stream("y", {})
    await asyncio.wait_for(started.wait(), 5)
    await r.server.close()
    with pytest.raises(TransportClosed):
        await asyncio.wait_for(pending, 5)
    with pytest.raises(TransportClosed):
        await anext(stream)
    await asyncio.wait_for(cancelled.wait(), 5)
    await asyncio.wait_for(r.client.wait_closed(), 5)


async def test_max_inflight_requests_gives_busy(rig):
    async def handler(ctx):
        await asyncio.sleep(0.2)
        return {"resultType": "complete"}

    r = await rig(handler, server_kw={"max_inflight_requests": 2})
    results = await asyncio.gather(*(r.client.request("x", {}) for i in range(4)), return_exceptions=True)
    busy = [x for x in results if isinstance(x, BhmsError)]
    assert len(busy) == 2 and busy[0].code == "BUSY" and busy[0].retry == "backoff"


async def test_roles_are_enforced(rig):
    r = await rig(echo)
    with pytest.raises(RuntimeError):
        await r.server.request("x", {})  # servers MUST NOT send requests (BHMS-TRN-001)
    with pytest.raises(RuntimeError):
        await r.server.notify("notifications/cancelled", {"requestId": 1})
    # a server that sends a request anyway is ignored by the client, which keeps working
    raw_server_side = r.server._transport
    await raw_server_side.send(b'{"jsonrpc":"2.0","id":1,"method":"x","params":{}}')
    assert (await r.client.request("y", {}))["method"] == "y"


async def test_outbound_message_over_the_limit_is_refused_before_sending(rig):
    r = await rig(echo, client_kw={"max_message_bytes": 1_048_576})
    with pytest.raises(BhmsError) as exc:
        await r.client.request("x", {"p": "a" * (2 * MIB)})
    assert exc.value.code == "INVALID_ARGUMENT" and "1048576" in exc.value.message
    assert (await r.client.request("x", {}))["method"] == "x"


async def test_oversize_response_becomes_internal_error_not_a_dead_connection(rig):
    async def handler(ctx):
        return {"resultType": "complete", "blob": "a" * (2 * MIB)}

    r = await rig(handler, server_kw={"max_message_bytes": 1_048_576})
    with pytest.raises(BhmsError) as exc:
        await r.client.request("x", {})
    assert exc.value.code == "INTERNAL" and exc.value.may_have_acted


async def test_session_over_tcp_and_websocket(tmp_path):
    async def handler(ctx):
        return {"resultType": "complete", "peer": ctx.peer.kind}

    sessions = []

    async def on_transport(t):
        s = Session(t, role="server", handler=handler).start()
        sessions.append(s)
        await s.wait_closed()

    for serve, connect, kind in (
        (lambda cb: tr.serve_tcp("127.0.0.1", 0, cb), lambda a: tr.connect_tcp(*a), "tcp"),
        (lambda cb: tr.serve_websocket("127.0.0.1", 0, cb), lambda a: tr.connect_websocket("ws://%s:%d" % a), "ws"),
    ):
        listener = await serve(on_transport)
        client = Session(await connect(listener.address), role="client").start()
        results = await asyncio.gather(*(client.request("ping", {}) for _ in range(50)))
        assert all(x["peer"] == kind for x in results)
        await client.close()
        await listener.close()
