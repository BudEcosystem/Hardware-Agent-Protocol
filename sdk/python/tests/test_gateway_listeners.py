"""Gateway step 8: listeners - Unix socket, WebSocket (bearer), Streamable HTTP (POST + SSE), stdio.

Spec: BHMS-TRN-002/004/005/021/030/031/040..043, SEC-001/004, LIF-044.
"""

from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path

import aiohttp
import orjson
import pytest

from bhms.client.client import Client
from bhms.gateway import Gateway, GatewayConfig
from bhms.protocol.errors import BhmsError
from bhms.protocol.version import PROTOCOL_VERSION
from helpers.gateway_rig import TOKENS, principals, rig

META = {"bhms/protocolVersion": PROTOCOL_VERSION}


def post(r, session, body, *, token=TOKENS["admin"], headers=None, raw=None, **kw):
    all_headers = {"Content-Type": "application/json", "BHMS-Method": body.get("method", "x") if raw is None else "x",
                   "BHMS-Protocol-Version": PROTOCOL_VERSION}
    if token:
        all_headers["Authorization"] = f"Bearer {token}"
    all_headers.update(headers or {})
    return session.post(f"http://127.0.0.1:{r.http_port}/bhms", data=raw if raw is not None else orjson.dumps(body),
                        headers=all_headers, **kw)


@pytest.fixture
async def http():
    async with aiohttp.ClientSession() as session:
        yield session


async def test_every_binding_serves_the_same_protocol(tmp_path):
    async with rig(tmp_path) as r:
        via = {"unix": await r.client(), "ws": await r.client(token=TOKENS["agent-b"]),
               "http": await r.client(token=TOKENS["agent-b"], http=True)}
        for name, client in via.items():
            assert client.server.server_info.name == "gw-test"
            assert [d.device_id for d in (await client.devices_list()).devices] == ["a/axis-1", "b/axis-1"], name
            op = (await client.actions_invoke("a/axis-1", "move_to", {"target": 3}, operation_key=f"via-{name}",
                                              wait_ms=2000)).operation
            assert op.state == "completed" and op.result["position"] == 3, name
            assert (await client.operations_get(op.operation_id)).operation.history, name
        # the principal is the credential, not the binding: agent-b's two bindings see the same operations
        ids = {c: {o.operation_id async for o in via[c].iter_operations()} for c in ("ws", "http")}
        assert ids["ws"] == ids["http"] and len(ids["ws"]) == 2


async def test_http_listen_streams_over_sse_and_ends_with_the_result(tmp_path):  # BHMS-TRN-041, LIF-044
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client(token=TOKENS["agent-b"], http=True)
        async with await client.subscribe(operations={"all": True}) as sub:
            op = (await client.actions_invoke("a/axis-1", "move_to", {"target": 2}, operation_key="sse")).operation
            seen = []
            while not seen or seen[-1].params.operation.state != "completed":
                seen.append(await asyncio.wait_for(sub.__anext__(), 5))
            assert {n.params.operation.operation_id for n in seen} == {op.operation_id}
        sub2 = await client.subscribe(devices_list_changed=True)
        await r.gateway.close()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(sub2.__anext__(), 5)
        assert sub2.end_reason == "shutdown"


async def test_http_raw_protocol_rules(tmp_path, http):
    async with rig(tmp_path, names=("a",)) as r:
        request = {"jsonrpc": "2.0", "id": 1, "method": "devices/list", "params": {"_meta": META}}
        async with post(r, http, request) as response:  # the happy path: one JSON response
            assert response.status == 200 and response.content_type == "application/json"
            assert (await response.json())["result"]["devices"][0]["deviceId"] == "a/axis-1"
        async with post(r, http, request, headers={"BHMS-Method": "devices/describe"}) as response:  # TRN-040
            body = await response.json()
            assert response.status == 400 and body["error"]["data"]["bhmsCode"] == "INVALID_ARGUMENT"
            assert body["error"]["data"]["field"] == "BHMS-Method"
        async with post(r, http, request, headers={"BHMS-Protocol-Version": "1999-01-01"}) as response:
            assert response.status == 400 and (await response.json())["error"]["data"]["field"] == "BHMS-Protocol-Version"
        async with http.post(f"http://127.0.0.1:{r.http_port}/bhms", data=orjson.dumps(request),
                             headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKENS['admin']}"}
                             ) as response:  # headers are mandatory
            assert response.status == 400
        async with post(r, http, request, token=None) as response:  # SEC-001: no credential
            assert response.status == 401 and response.headers["WWW-Authenticate"] == "Bearer"
        async with post(r, http, request, token="wrong") as response:
            assert response.status == 401
        discover = {"jsonrpc": "2.0", "id": 2, "method": "server/discover", "params": {"_meta": META}}
        async with post(r, http, discover, token=None) as response:  # discover needs no credential
            body = await response.json()
            assert response.status == 200 and "principal" not in body["result"]
            assert body["result"]["capabilities"]["gateway"]["upstreams"] == 1
        async with post(r, http, discover) as response:
            assert (await response.json())["result"]["principal"]["id"] == "admin"
        async with post(r, http, request, headers={"Content-Type": "text/plain"}) as response:
            assert response.status == 415
        async with post(r, http, {}, raw=orjson.dumps([request, request])) as response:  # TRN-002
            assert (await response.json())["error"]["code"] == -32600
        async with post(r, http, {}, raw=b"{not json") as response:
            assert (await response.json())["error"]["code"] == -32700
        big = io.BytesIO(b'{"jsonrpc":"2.0","id":1,"method":"devices/list","params":{"_meta":' + b" " * 5_000_000 + b"{}}}")
        async with post(r, http, {}, raw=big) as response:
            assert response.status == 413 and (await response.json())["error"]["code"] == -32600  # TRN-004
        async with post(r, http, {"jsonrpc": "2.0", "method": "notifications/cancelled",
                                  "params": {"requestId": 99}}) as response:  # TRN-043
            assert response.status == 202 and await response.read() == b""
        async with http.get(f"http://127.0.0.1:{r.http_port}/bhms") as response:
            assert response.status == 405


async def test_http_rejects_a_foreign_host_header(tmp_path, http):  # DNS-rebinding guard on loopback
    async with rig(tmp_path, names=("a",)) as r:
        request = {"jsonrpc": "2.0", "id": 1, "method": "devices/list", "params": {"_meta": META}}
        async with post(r, http, request, headers={"Host": "evil.example:80"}) as response:
            assert response.status == 403


async def test_http_disconnect_cancels_the_request_but_not_the_work(tmp_path, http):  # BHMS-TRN-042, TRN-005
    async with rig(tmp_path, names=("a",)) as r:
        client = await r.client()
        op = (await client.actions_invoke("a/axis-1", "slow", {"distance": 1}, operation_key="held")).operation
        request = {"jsonrpc": "2.0", "id": "w", "method": "operations/wait",
                   "params": {"_meta": META, "operationId": op.operation_id, "timeoutMs": 30000}}
        with pytest.raises(asyncio.TimeoutError):  # the client gives up and closes the connection
            async with post(r, http, request, timeout=aiohttp.ClientTimeout(total=0.3)) as response:
                await response.read()
        await asyncio.sleep(0.3)
        got = (await client.operations_get(op.operation_id)).operation
        assert got.state in ("running", "dispatching")  # the operation is untouched and still running
        r.axes["a"].gate.set()
        done = (await client.operations_wait(op.operation_id, 3000)).operation
        assert done.state == "completed"


async def test_non_loopback_http_needs_tls(tmp_path):  # BHMS-SEC-004
    async with rig(tmp_path, names=("a",)) as r:
        with pytest.raises(ValueError, match="TLS"):
            await r.gateway.listen("http://0.0.0.0:0/bhms")
        with pytest.raises(ValueError, match="TLS"):
            await r.gateway.listen("ws://0.0.0.0:0")


async def test_a_tls_scheme_without_a_tls_context_is_refused_not_served_in_clear(tmp_path):  # BHMS-SEC-004
    """`wss://` and `https://` promise encryption: on loopback too, without ssl= the gateway refuses instead of serving
    plain WebSocket or HTTP under a TLS scheme (found writing the gateway guide, Task 14)."""
    async with rig(tmp_path, names=("a",)) as r:
        for url in ("wss://127.0.0.1:0", "https://127.0.0.1:0/bhms"):
            with pytest.raises(ValueError, match="without a TLS context"):
                await r.gateway.listen(url)


async def test_a_device_server_refuses_wss_without_a_tls_context(tmp_path):  # BHMS-SEC-004
    from bhms import DeviceServer

    srv = DeviceServer("tls-check", state_dir=tmp_path, store=None)
    srv.device("d-1")
    try:
        with pytest.raises(ValueError, match="without a TLS context"):
            await srv.listen("wss://127.0.0.1:0")
    finally:
        await srv.close()


def test_a_listener_that_cannot_open_is_a_message_and_exit_2_not_a_traceback(tmp_path):
    """Task 14: a Unix socket path over the kernel's limit made `bhms gateway` die with an OSError traceback."""
    import subprocess

    deep = tmp_path / ("d" * 60) / ("e" * 60)
    deep.mkdir(parents=True)
    (deep / "gw.toml").write_text('[gateway]\nid = "gw-long"\nlisten = ["unix:gateway.sock"]\n')
    done = subprocess.run([sys.executable, "-m", "bhms.gateway", str(deep / "gw.toml")], capture_output=True, text=True,
                          timeout=60)
    assert done.returncode == 2, done.stderr
    assert "Traceback" not in done.stderr and "cannot serve the configured listeners" in done.stderr
    assert "shorter path" in done.stderr


async def test_gateway_serves_stdio_from_a_toml_file(tmp_path):  # BHMS-SEC-003; python -m bhms.gateway
    helper = Path(__file__).parent / "helpers" / "gateway_upstream.py"
    config = tmp_path / "gw.toml"
    config.write_text(f'''
[gateway]
id = "gw-stdio"
state_dir = "state"
listen = ["stdio"]

[[upstream]]
name = "dev"
stdio = "{sys.executable} {helper} {tmp_path / "up"}"
''')
    async with await Client.connect(f"stdio:{sys.executable} -m bhms.gateway {config}", timeout=30) as client:
        assert client.server.server_info.name == "gw-stdio"
        for _ in range(100):
            devices = (await client.devices_list()).devices
            if devices:
                break
            await asyncio.sleep(0.1)
        assert [d.device_id for d in devices] == ["dev/axis-1"]
        op = (await client.actions_invoke("dev/axis-1", "move", {"x": 5}, operation_key="s", wait_ms=5000)).operation
        assert op.state == "completed" and client.server.principal.id == "stdio"


_ = (BhmsError, Gateway, GatewayConfig, principals)


def test_the_core_and_the_gateway_import_without_aiohttp():  # the http extra is optional
    import subprocess

    code = ("import sys, bhms, bhms.gateway, bhms.client.client; "
            "assert 'aiohttp' not in sys.modules and 'bhms.transport.http' not in sys.modules")
    assert subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).returncode == 0
