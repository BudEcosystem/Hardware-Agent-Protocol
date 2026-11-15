"""Server dispatcher + typed Client over real transports, driven by the spec example corpus."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

from bhms import transport as tr
from bhms.client.client import METHOD_ATTRS, Client
from bhms.jsonrpc.dispatcher import Server
from bhms.jsonrpc.session import Complete, JsonRpcError, Notification, Session
from bhms.protocol import schema, types
from bhms.protocol.errors import BhmsError
from bhms.protocol.version import PROTOCOL_VERSION, SUPPORTED_VERSIONS
from bhms.transport import TransportClosed

EXAMPLES = Path(__file__).resolve().parents[3] / "spec" / "bhms" / "examples"
STDIO_SERVER = Path(__file__).parent / "helpers" / "stdio_server.py"
CAPS = {k: v for k, v in json.loads((EXAMPLES / "server.discover.response.json").read_text())["message"]
        ["result"]["capabilities"].items() if k in ("leases", "events", "programs", "operations")}


def example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text())["message"]


def example_methods() -> list[str]:
    return [m for m in types.METHODS if (EXAMPLES / f"{m.replace('/', '.')}.request.json").exists()
            and (EXAMPLES / f"{m.replace('/', '.')}.response.json").exists()
            and m not in ("server/discover", "subscriptions/listen")]


class Env:
    def __init__(self, server, listener, path):
        self.server, self.listener, self.path = server, listener, path
        self.clients: list[Client] = []

    async def client(self, **kw) -> Client:
        c = await Client.connect(f"unix:{self.path}", **kw)
        self.clients.append(c)
        return c


@pytest.fixture
async def make_env(tmp_path):
    envs = []

    async def make(**server_kw) -> Env:
        server_kw.setdefault("capabilities", CAPS)
        server = Server(server_info={"name": "test-server", "version": "1.2.3"}, epoch="epoch-1", **server_kw)
        path = str(tmp_path / f"s{len(envs)}.sock")
        listener = await tr.serve_unix(path, server.handle_connection)
        env = Env(server, listener, path)
        envs.append(env)
        return env

    yield make
    for env in envs:
        for c in env.clients:
            await c.close()
        await env.server.close()
        await env.listener.close()


def register_examples(server: Server, seen: dict):
    for method in example_methods():
        result = example(f"{method.replace('/', '.')}.response.json")["result"]

        async def handler(params, ctx, method=method, result=result):
            seen[method] = params
            return result

        server.register(method, handler)


def snake(key: str) -> str:
    out = ""
    for ch in key:
        out += "_" + ch.lower() if ch.isupper() else ch
    return out


@pytest.mark.parametrize("strict", [False, True], ids=["pydantic", "strict-json-schema"])
async def test_every_method_round_trips_the_spec_examples(make_env, strict):
    env = await make_env(strict=strict)
    seen: dict = {}
    register_examples(env.server, seen)
    client = await env.client(strict=strict)
    methods = example_methods()
    assert len(methods) >= 17
    for method in methods:
        request = example(f"{method.replace('/', '.')}.request.json")["params"]
        kwargs = {snake(k): v for k, v in request.items() if k != "_meta"}
        result = await getattr(client, METHOD_ATTRS[method])(**kwargs)
        expected = example(f"{method.replace('/', '.')}.response.json")["result"]
        assert isinstance(result, types.METHODS[method].result)
        assert types.dump(types.METHODS[method].result.__name__, result) == expected, method
        got = types.to_wire(seen[method])
        assert got == request | {"_meta": got["_meta"]}, method
        assert got["_meta"]["bhms/protocolVersion"] == PROTOCOL_VERSION
        assert got["_meta"]["bhms/clientInfo"]["name"] == "bhms-python"


def test_client_has_a_typed_method_for_every_schema_method():
    methods = set(schema.load_schema()["x-bhms-methods"])
    assert set(METHOD_ATTRS) == methods
    for method, attr in METHOD_ATTRS.items():
        assert callable(getattr(Client, attr)), (method, attr)
    assert len(set(METHOD_ATTRS.values())) == len(methods)


async def test_connect_discovers_and_exposes_server_description(make_env):
    env = await make_env(principal=lambda ctx: {"id": f"uid:{ctx.peer.uid}", "scopes": ["read"]}, instructions="be kind")
    client = await env.client()
    d = client.server
    assert d.server_info.name == "test-server" and d.epoch == "epoch-1" and d.supported_versions == list(SUPPORTED_VERSIONS)
    assert d.instructions == "be kind" and d.principal.id.startswith("uid:")
    assert d.limits.max_message_bytes == 4 * 1024 * 1024 == client.session.max_message_bytes
    for cap in ("operations", "stop", "subscriptions", "leases"):
        assert env.server.advertises(cap)
    assert not env.server.advertises("programs.x") and env.server.advertises("programs.registry")
    schema.validate("DiscoverResult", types.to_wire(d))


async def test_version_negotiation_retries_with_a_mutual_version(make_env):
    env = await make_env()
    c = await Client.connect(f"unix:{env.path}")
    env.clients.append(c)
    t = await tr.connect_unix(env.path)
    older = await Client.from_transport(t, versions=("2025-01-01", "2026-11-13"))
    env.clients.append(older)
    assert older.version == "2026-11-13"
    with pytest.raises(BhmsError) as exc:
        await Client.from_transport(await tr.connect_unix(env.path), versions=("2025-01-01",))
    assert exc.value.bhms_code == "UNSUPPORTED_VERSION" and exc.value.bound == list(SUPPORTED_VERSIONS)


async def raw_request(env, message: dict):
    t = await tr.connect_unix(env.path)
    await t.send(json.dumps(message).encode())
    reply = json.loads(await asyncio.wait_for(t.receive(), 5))
    await t.close()
    return reply


async def test_missing_meta_and_version_errors_follow_lif_011_and_019(make_env):
    env = await make_env()
    register_examples(env.server, {})
    for params in (None, [], {}, {"_meta": {}}, {"_meta": "x"}):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "devices/list"}
        if params is not None:
            msg["params"] = params
        err = (await raw_request(env, msg))["error"]
        assert err["code"] == -32602 and err["data"]["bhmsCode"] == "INVALID_ARGUMENT"
        assert err["data"]["field"] == "_meta.bhms/protocolVersion", params
    err = (await raw_request(env, {"jsonrpc": "2.0", "id": 1, "method": "devices/list",
                                   "params": {"_meta": {"bhms/protocolVersion": "1999-01-01"}}}))["error"]
    assert err["code"] == -32015 and err["data"]["bound"] == list(SUPPORTED_VERSIONS)
    assert err["data"]["field"] == "_meta.bhms/protocolVersion"


async def test_unknown_method_gets_32601_even_for_bhms_looking_names(make_env):
    env = await make_env()
    for method in ("nope/nothing", "bhms/secret", "devices/list"):  # devices/list has no handler registered here
        err = (await raw_request(env, {"jsonrpc": "2.0", "id": 1, "method": method,
                                       "params": {"_meta": {"bhms/protocolVersion": "2026-11-13"}}}))["error"]
        assert err["code"] == -32601, method


async def test_closed_params_and_bad_values_are_invalid_argument_with_field(make_env):
    env = await make_env()
    register_examples(env.server, {})
    client = await env.client()
    for params, field in (({"deviceId": "pump-1", "extra": 1}, "extra"), ({"limit": 0}, "limit"),
                          ({"cursor": 5}, "cursor")):
        method = "devices/describe" if "deviceId" in params else "devices/list"
        t = await tr.connect_unix(env.path)
        await t.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": {
            "_meta": {"bhms/protocolVersion": "2026-11-13"}, **params}}).encode())
        err = json.loads(await t.receive())["error"]
        await t.close()
        assert err["data"]["bhmsCode"] == "INVALID_ARGUMENT" and err["data"]["field"] == field, params
        assert err["data"]["hint"] and err["data"]["mayHaveActed"] is False
    del client


async def test_client_validates_before_sending(make_env):
    env = await make_env()
    seen: dict = {}
    register_examples(env.server, seen)
    client = await env.client()
    with pytest.raises(BhmsError) as exc:
        await client.devices_list(limit=0)
    assert exc.value.bhms_code == "INVALID_ARGUMENT" and exc.value.field == "limit"
    with pytest.raises(BhmsError):
        await client.leases_acquire(["a"], ttl_ms="soon")  # type: ignore[arg-type]
    assert "devices/list" not in seen


async def test_unadvertised_capability_gets_unsupported_naming_it(make_env):
    env = await make_env(capabilities={})
    register_examples(env.server, {})
    client = await env.client()
    for call, cap in ((client.leases_acquire(["r"], 1000), "leases"), (client.events_read(), "events"),
                      (client.programs_get("sha256:" + "0" * 64), "programs.registry")):
        with pytest.raises(BhmsError) as exc:
            await call
        assert exc.value.bhms_code == "UNSUPPORTED" and cap in exc.value.hint and cap in exc.value.message


async def test_handler_error_mapping_through_the_dispatcher(make_env):
    env = await make_env()

    async def boom(params, ctx):
        raise BhmsError("UNKNOWN_DEVICE", "no such device", field="deviceId", hint="call devices/list")

    async def crash(params, ctx):
        raise RuntimeError("TOP-SECRET")

    env.server.register("devices/describe", boom)
    env.server.register("operations/get", crash)
    client = await env.client()
    with pytest.raises(BhmsError) as exc:
        await client.devices_describe("nope")
    assert (exc.value.bhms_code, exc.value.field) == ("UNKNOWN_DEVICE", "deviceId")
    with pytest.raises(BhmsError) as exc:
        await client.operations_get("op-1")
    assert exc.value.bhms_code == "INTERNAL" and "SECRET" not in str(exc.value) + exc.value.hint
    with pytest.raises(JsonRpcError) as rpc:
        await client.devices_list()  # no handler registered
    assert rpc.value.code == -32601


async def test_extension_methods_and_name_validation(make_env):
    env = await make_env()

    async def hello(params, ctx):
        return {"hello": params["name"], "peer": ctx.peer.kind}

    env.server.register("com.example/demo/hello", hello)
    env.server.register("x-demo/hello", hello)
    for bad in ("bhms/x/y", "plain", "devices/liszt", "x-/a"):
        with pytest.raises(ValueError):
            env.server.register(bad, hello)
    client = await env.client()
    result = await client.request("com.example/demo/hello", {"name": "w"})
    assert result == {"resultType": "complete", "hello": "w", "peer": "unix"}  # resultType added
    assert (await client.request("x-demo/hello", {"name": "v"}))["hello"] == "v"


async def test_result_without_result_type_from_a_buggy_server_is_refused(make_env):
    env = await make_env()

    async def bad_handler(ctx):  # a server that bypasses the dispatcher and omits resultType
        return {"devices": []}

    async def on_t(tp):
        s = Session(tp, role="server", handler=bad_handler).start()
        await s.wait_closed()

    listener = await tr.serve_unix(env.path + "2", on_t)
    session = Session(await tr.connect_unix(env.path + "2"), role="client").start()
    client = Client(session)
    with pytest.raises(BhmsError) as exc:
        await client.devices_list()
    assert exc.value.bhms_code == "INTERNAL" and exc.value.may_have_acted and "resultType" in str(exc.value)
    await client.close()
    await listener.close()


async def test_pagination_iterators_follow_next_cursor(make_env):
    env = await make_env()
    summary = example("devices.list.response.json")["result"]["devices"][0]
    pages = {None: ("c1", ["a", "b"]), "c1": ("c2", ["c", "d"]), "c2": (None, ["e"])}
    cursors = []

    async def devices_list(params, ctx):
        cursors.append(params.cursor)
        nxt, ids = pages[params.cursor]
        result = {"resultType": "complete", "devices": [{**summary, "deviceId": i} for i in ids]}
        if nxt:
            result["nextCursor"] = nxt
        return result

    env.server.register("devices/list", devices_list)
    client = await env.client()
    assert [d.device_id async for d in client.iter_devices()] == list("abcde")
    assert cursors == [None, "c1", "c2"]


async def test_server_side_waits_extend_the_client_timeout(make_env):
    env = await make_env()
    op = example("operations.wait.response.json")["result"]

    async def wait(params, ctx):
        await asyncio.sleep(0.4)
        return op

    env.server.register("operations/wait", wait)
    client = await env.client(timeout=0.2)
    await client.operations_wait("op-1", 1000)  # 0.2 s + 1 s: not cut short
    with pytest.raises(BhmsError) as exc:
        await client.operations_wait("op-1", 1000, timeout=0.1)
    assert exc.value.bhms_code == "DEADLINE_EXCEEDED" and exc.value.may_have_acted


def listen_handler(events: int, end_reason: str = "shutdown", closed: asyncio.Event | None = None):
    ack = example("notifications.subscriptions.acknowledged.json")["params"]
    obs = example("notifications.observation.json")["params"]

    async def handler(params, ctx):
        async def gen():
            try:
                yield Notification("notifications/subscriptions/acknowledged",
                                   {k: v for k, v in ack.items() if k != "_meta"})
                for _ in range(events):
                    yield Notification("notifications/observation", {k: v for k, v in obs.items() if k != "_meta"})
                if end_reason:
                    yield Complete({"resultType": "complete", "endReason": end_reason})
                else:
                    await asyncio.sleep(30)
            finally:
                if closed is not None:
                    closed.set()

        return gen()

    return handler


async def test_subscribe_yields_typed_notifications_then_end_reason(make_env):
    env = await make_env()
    env.server.register("subscriptions/listen", listen_handler(3))
    client = await env.client()
    sub = await client.subscribe(devices_list_changed=True, observations=[{"deviceId": "pump-1", "property": "pressure"}])
    assert isinstance(sub.acknowledged, types.SubscriptionsAcknowledgedNotificationParams)
    assert sub.acknowledged.refused and sub.acknowledged.refused[0].bhms_code == "INVALID_ARGUMENT"
    got = [n async for n in sub]
    assert [n.method for n in got] == ["notifications/observation"] * 3
    assert isinstance(got[0].params, types.ObservationNotificationParams)
    assert got[0].params.meta.subscription_id == sub.id
    assert sub.end_reason == "shutdown" and isinstance(sub.result, types.SubscriptionsListenResult)


async def test_subscribe_cancel_on_exit_stops_the_server_generator(make_env):
    env = await make_env()
    closed = asyncio.Event()
    env.server.register("subscriptions/listen", listen_handler(1, end_reason="", closed=closed))
    client = await env.client()
    async with await client.subscribe(devices_list_changed=True) as sub:
        first = await anext(sub)
        assert first.method == "notifications/observation"
    await asyncio.wait_for(closed.wait(), 5)
    await asyncio.sleep(0.05)
    assert all(s.inflight == 0 for s in env.server.sessions)


async def test_subscribe_failure_raises_at_subscribe(make_env):
    env = await make_env()

    async def refuse(params, ctx):
        raise BhmsError("UNAUTHORIZED", "no read scope", hint="request the read scope")

    env.server.register("subscriptions/listen", refuse)
    client = await env.client()
    with pytest.raises(BhmsError) as exc:
        await client.subscribe(devices_list_changed=True)
    assert exc.value.bhms_code == "UNAUTHORIZED"
    with pytest.raises(BhmsError):  # invalid filter is caught client-side
        await client.subscribe(observations=[{"deviceId": "x"}])


async def test_connection_drop_ends_subscription_with_transport_closed(make_env):
    env = await make_env()
    env.server.register("subscriptions/listen", listen_handler(0, end_reason=""))
    client = await env.client()
    sub = await client.subscribe(devices_list_changed=True)
    await env.server.close()
    with pytest.raises(TransportClosed):
        await asyncio.wait_for(anext(sub), 5)


@pytest.mark.parametrize("scheme", ["unix", "tcp", "ws", "stdio"])
async def test_connect_url_forms(scheme, tmp_path):
    server = Server(server_info={"name": "s", "version": "1"})

    async def ping(params, ctx):
        return {"n": params["n"]}

    server.register("x-test/ping", ping)
    listener = None
    if scheme == "unix":
        listener = await tr.serve_unix(str(tmp_path / "u.sock"), server.handle_connection)
        target = f"unix:{tmp_path}/u.sock"
    elif scheme == "tcp":
        listener = await tr.serve_tcp("127.0.0.1", 0, server.handle_connection)
        target = "tcp://%s:%d" % listener.address
    elif scheme == "ws":
        listener = await tr.serve_websocket("127.0.0.1", 0, server.handle_connection)
        target = "ws://%s:%d/bhms" % listener.address
    else:
        target = f"stdio:{sys.executable} {STDIO_SERVER}"
    async with await Client.connect(target) as client:
        assert client.server.server_info.name in ("s", "stdio-test-server")
        assert (await client.request("x-test/ping", {"n": 7}))["n"] == 7
    if listener:
        await listener.close()


async def test_connect_rejects_unknown_url_forms_and_closes_on_failure(tmp_path):
    for bad in ("gopher://x", "tcp://nohost", "tcp://:80", "carrier-pigeon:x"):
        with pytest.raises(ValueError):
            await Client.connect(bad)
    with pytest.raises(OSError):
        await Client.connect(f"unix:{tmp_path}/missing.sock")


async def test_connect_to_a_non_bhms_peer_fails_cleanly(tmp_path):
    async def silent(t):
        await t.receive()
        await t.send(b'{"jsonrpc":"2.0","id":1,"result":{"resultType":"complete"}}')  # not a DiscoverResult

    listener = await tr.serve_unix(str(tmp_path / "x.sock"), silent)
    with pytest.raises(BhmsError) as exc:
        await Client.connect(f"unix:{tmp_path}/x.sock", timeout=2)
    assert exc.value.bhms_code == "INTERNAL"
    await listener.close()


async def test_ws_bearer_token_is_passed_by_connect(tmp_path):
    server = Server(server_info={"name": "s", "version": "1"},
                    principal=lambda ctx: {"id": f"token:{ctx.peer.token}", "scopes": ["read"]})
    listener = await tr.serve_websocket("127.0.0.1", 0, server.handle_connection,
                                        authenticate=lambda tok: tok == "good")
    url = "ws://%s:%d" % listener.address
    async with await Client.connect(url, token="good") as c:
        assert c.server.principal.id == "token:good"
    with pytest.raises(Exception):
        await Client.connect(url, token="bad")
    await listener.close()


async def test_stdio_child_dies_mid_session(tmp_path):
    client = await Client.connect(f"stdio:{sys.executable} {STDIO_SERVER}")
    client.session._transport.process.kill()
    with pytest.raises(TransportClosed):
        await asyncio.wait_for(client.request("x-test/ping", {"n": 1}), 10)
    await client.close()


def test_advertises_tolerates_non_dict_capability_values():
    server = Server(server_info={"name": "s", "version": "1"}, capabilities={"programs": True, "leases": {}})
    assert server.advertises("programs") and not server.advertises("programs.registry")
    assert server.advertises("leases") and not server.advertises("events")


async def test_dispatcher_cancellable_flags(make_env):
    env = await make_env()
    assert env.server.is_cancellable("subscriptions/listen") and env.server.is_cancellable("operations/wait")
    assert not env.server.is_cancellable("actions/invoke")
    env.server.register("actions/invoke", lambda p, c: None, cancellable=True)  # type: ignore[arg-type]
    assert env.server.is_cancellable("actions/invoke")
