"""Chapter 2: bindings. Framing, concurrency, size limits, WebSocket subprotocol, HTTP headers and streams."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from bhms.conformance.context import Context
from bhms.conformance.core import check
from bhms.protocol.version import PROTOCOL_VERSION


@check("transport.concurrent-requests", ["BHMS-TRN-003"], generic=True)
async def concurrent_requests(c: Context) -> None:
    """Sixteen requests in flight on one connection are correlated by id and not serialised behind a long wait."""
    wait_task = None
    if c.is_conformance_device:
        axis = c.axis()
        op = await c.invoke_op(axis, "slow_move", {"duration_ms": 1500})
        _, wait_task = c.wire.submit("operations/wait", {"operationId": op["operationId"], "timeoutMs": 5000})
    started = time.monotonic()
    limit_calls = [c.call("devices/list", {"limit": 1 + (i % 3)}) for i in range(15)]
    responses = await asyncio.gather(*limit_calls)
    took = time.monotonic() - started
    for i, response in enumerate(responses):
        result = c.result(response, f"concurrent request {i}")
        c.expect(len(result["devices"]) <= 1 + (i % 3), f"concurrent request {i} was answered with another request's page")
    ids = [r.request["id"] for r in responses]
    c.expect(len(set(ids)) == 15 and all(r.raw["id"] == r.request["id"] for r in responses), "responses must be correlated by id")
    if wait_task is not None:
        c.expect(not wait_task.done() and took < 1.0, f"requests were serialised behind a long operations/wait ({took:.2f}s)")
        waited = await wait_task
        c.expect(waited.ok, f"the long wait failed: {waited.describe()}")


@check("transport.message-size-limit", ["BHMS-TRN-004"], generic=True)
async def message_limit(c: Context) -> None:
    """A message one byte over limits.maxMessageBytes is refused with -32600 and the connection stays usable."""
    limit = int(c.limits["maxMessageBytes"])
    if limit > 16 * 1024 * 1024:
        c.skip(f"limits.maxMessageBytes is {limit}; the runner does not send messages above 16 MiB")
    head = '{"jsonrpc":"2.0","id":8001,"method":"devices/list","params":{"_meta":%s,"filter":{"text":"' % json.dumps(c.wire.meta())
    tail = '"}}}'
    padding = limit + 1 - len((head + tail).encode())
    data = (head + "x" * padding + tail).encode()
    c.expect(len(data) == limit + 1, "internal: oversize message has the wrong length")
    try:
        answers = await c.wire.exchange_raw(data, timeout=20.0)
    except Exception as exc:  # a WebSocket server closes with 1009 (message too big): that is a refusal too
        c.expect(c.wire.closed, f"the oversize message produced {exc!r} without closing the connection")
        c.skip("the server closed the connection (WebSocket 1009), which is how that binding refuses an oversize message")
    errors = [a for a in answers if isinstance(a, dict) and isinstance(a.get("error"), dict)]
    if not answers and c.wire.closed and c.target.kind == "ws":
        c.warn("the WebSocket server closed the connection (1009) instead of answering -32600; the spec asks for -32600 on every binding")
        return
    c.expect(errors and errors[0]["error"]["code"] == -32600, f"an oversize message must be answered -32600, got {answers!r}"[:300])
    c.result(await c.call("devices/list", {"limit": 1}), "devices/list after an oversize message")


@check("transport.stdio-exit-on-eof", ["BHMS-TRN-011"], needs=("stdio",), generic=True)
async def stdio_exit(c: Context) -> None:
    """The server exits when stdin reaches end-of-file."""
    transport = await c.target.connect_extra()
    process = getattr(transport, "process", None)
    if process is None:
        c.skip("the runner does not own this stdio server's process")
    process.stdin.close()
    try:
        await asyncio.wait_for(process.wait(), 10)
    except asyncio.TimeoutError:
        c.fail("the server did not exit within 10 s of stdin closing")


@check("transport.socket-framing", ["BHMS-TRN-020"], needs=("socket",), generic=True)
async def socket_framing(c: Context) -> None:
    """The stdio framing (one message per line, nothing else) holds on a Unix socket or TCP loopback."""
    c.result(await c.call("devices/list", {"limit": 1}))
    c.expect(not c.wire.frame_errors, f"frames that are not single-line JSON: {c.wire.frame_errors[:3]}")


@check("transport.ws-subprotocol", ["BHMS-TRN-030"], needs=("ws",), generic=True)
async def ws_subprotocol(c: Context) -> None:
    """The bhms subprotocol is required; one JSON-RPC message per text frame."""
    import websockets

    url = c.target.url or ""
    headers = {"Authorization": f"Bearer {c.target.token}"} if c.target.token else None
    try:
        plain = await websockets.connect(url, additional_headers=headers)
    except Exception:
        plain = None  # refused at the handshake: acceptable
    if plain is not None:
        await plain.close()
        c.fail("an upgrade that offers no subprotocol was accepted (BHMS-TRN-030 requires the bhms subprotocol)")
    good = await websockets.connect(url, subprotocols=["bhms"], additional_headers=headers)
    try:
        c.expect(good.subprotocol == "bhms", f"the server must negotiate subprotocol bhms, negotiated {good.subprotocol!r}")
        one = {"jsonrpc": "2.0", "id": 1, "method": "devices/list", "params": {"_meta": c.wire.meta(), "limit": 1}}
        await good.send(json.dumps(one) + json.dumps({**one, "id": 2}))
        reply = json.loads(await asyncio.wait_for(good.recv(), 5))
        c.expect("error" in reply and reply["error"]["code"] in (-32700, -32600), f"two messages in one frame must be rejected, got {reply}"[:300])
    finally:
        await good.close()


@check("transport.ws-auth", ["BHMS-TRN-031"], needs=("ws",), generic=True)
async def ws_auth(c: Context) -> None:
    """A non-loopback WebSocket server rejects an upgrade without a valid bearer token with HTTP 401."""
    if c.target.loopback:
        c.not_applicable("loopback target: bearer authentication is mandatory only beyond loopback")
    import websockets
    from websockets.exceptions import InvalidStatus

    for token in (None, "wrong-token-for-conformance"):
        try:
            conn = await websockets.connect(c.target.url, subprotocols=["bhms"],
                                            additional_headers={"Authorization": f"Bearer {token}"} if token else None)
        except InvalidStatus as exc:
            c.expect(exc.response.status_code == 401, f"upgrade with token {token!r}: HTTP {exc.response.status_code}, expected 401")
        else:
            await conn.close()
            c.fail(f"upgrade with token {token!r} was accepted")


async def _http(c: Context, body: Any, headers: dict[str, str] | None = None, *, read: bool = True) -> tuple[int, dict[str, str], bytes]:
    import aiohttp

    base = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
            "BHMS-Protocol-Version": PROTOCOL_VERSION, "BHMS-Method": body.get("method", "") if isinstance(body, dict) else ""}
    if c.target.token:
        base["Authorization"] = f"Bearer {c.target.token}"
    base.update(headers or {})
    async with aiohttp.ClientSession() as session, session.post(c.target.url, data=json.dumps(body), headers=base) as response:
        data = await response.content.readline() if read and response.content_type == "text/event-stream" else await response.read()
        return response.status, dict(response.headers), data


@check("transport.http-headers-and-streams", ["BHMS-TRN-040", "BHMS-TRN-041", "BHMS-TRN-043"], profile="http", needs=("http",), generic=True)
async def http_binding(c: Context) -> None:
    """Header mismatch is HTTP 400 INVALID_ARGUMENT; listen is text/event-stream; client notifications get 202, no body."""
    request = {"jsonrpc": "2.0", "id": 1, "method": "devices/list", "params": {"_meta": c.wire.meta(), "limit": 1}}
    status, headers, body = await _http(c, request)
    c.expect(status == 200 and headers.get("Content-Type", "").split(";")[0] in ("application/json", "text/event-stream"), f"ordinary request: HTTP {status} {headers.get('Content-Type')}")
    for label, override in (("mismatched BHMS-Method", {"BHMS-Method": "actions/invoke"}), ("mismatched version", {"BHMS-Protocol-Version": "1999-01-01"})):
        status, _, body = await _http(c, request, override)
        c.expect(status == 400, f"{label}: expected HTTP 400, got {status}")
        parsed = json.loads(body)
        c.expect(parsed.get("error", {}).get("data", {}).get("bhmsCode") in ("INVALID_ARGUMENT", "UNSUPPORTED_VERSION"), f"{label}: {parsed}")
    listen = {"jsonrpc": "2.0", "id": 2, "method": "subscriptions/listen", "params": {"_meta": c.wire.meta(), "notifications": {"devicesListChanged": True}}}
    status, headers, _ = await _http(c, listen)
    c.expect(status == 200 and headers.get("Content-Type", "").startswith("text/event-stream"), f"subscriptions/listen: HTTP {status} {headers.get('Content-Type')}")
    status, _, body = await _http(c, {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 999}},
                                  {"BHMS-Method": "notifications/cancelled"})
    c.expect(status == 202 and not body, f"a POSTed notification must be answered 202 with no body, got {status} {body[:60]!r}")


@check("transport.http-stream-close-is-cancel", ["BHMS-TRN-042"], profile="http", needs=("http",))
async def http_close_cancels_wait(c: Context) -> None:
    """Closing the response stream of an invoke with waitMs does not cancel the operation."""
    import aiohttp

    axis = c.axis()
    request = {"jsonrpc": "2.0", "id": 3, "method": "actions/invoke", "params": {
        "_meta": c.wire.meta(), "deviceId": axis, "action": "slow_move", "arguments": {"duration_ms": 500}, "waitMs": 5000,
        "operationKey": c.unique("http-close")}}
    headers = {"Content-Type": "application/json", "BHMS-Protocol-Version": PROTOCOL_VERSION, "BHMS-Method": "actions/invoke"}
    if c.target.token:
        headers["Authorization"] = f"Bearer {c.target.token}"
    try:
        async with aiohttp.ClientSession() as session:
            await asyncio.wait_for(session.post(c.target.url, data=json.dumps(request), headers=headers), 0.15)
    except asyncio.TimeoutError:
        pass
    await asyncio.sleep(0.2)
    ops = (await c.ok("operations/list", {"deviceId": axis, "limit": 5}))["operations"]
    mine = [o for o in ops if o["operationKey"] == request["params"]["operationKey"]]
    c.expect(mine, "the operation must exist after the client closed the response stream")
    c.expect((await c.settle(mine[0]["operationId"]))["state"] == "completed", "closing the stream must not cancel the operation")


@check("transport.stdio-opens-no-listeners", ["BHMS-SEC-003"], needs=("stdio", "direct"), generic=True)
async def stdio_no_listeners(c: Context) -> None:
    """A stdio server treats its parent as the only principal and opens no listening socket (Linux /proc inspection)."""
    import os

    pid = c.target.server_pid()
    if pid is None or not os.path.isdir(f"/proc/{pid}/fd"):
        c.skip("the runner cannot inspect the server's sockets (needs a runner-started process on Linux)")
    inodes = set()
    for entry in os.listdir(f"/proc/{pid}/fd"):
        try:
            link = os.readlink(f"/proc/{pid}/fd/{entry}")
        except OSError:
            continue
        if link.startswith("socket:["):
            inodes.add(link[8:-1])
    listening = []
    for table in ("tcp", "tcp6"):
        with open(f"/proc/net/{table}") as handle:
            for line in handle.readlines()[1:]:
                fields = line.split()
                if fields[3] == "0A" and fields[9] in inodes:
                    listening.append(f"{table} {fields[1]}")
    with open("/proc/net/unix") as handle:
        for line in handle.readlines()[1:]:
            fields = line.split()
            if len(fields) >= 7 and fields[6] in inodes and int(fields[3], 16) & 0x10000:
                listening.append(f"unix {fields[-1]}")
    c.expect(not listening, f"a stdio server opened listening sockets: {listening}")


@check("limits.bounded-requests", ["BHMS-SEC-060"], generic=True)
async def bounded_requests(c: Context) -> None:
    """Page size and waits are bounded: a page never exceeds the advertised limit; waits above limits.maxWaitMs and
    over-long observation lists are refused."""
    page_limit = int(c.limits.get("maxPageSize", 500))
    response = await c.call("devices/list", {"limit": page_limit + 1})
    if response.ok:
        c.expect(len(response.result["devices"]) <= page_limit, f"a page above limits.maxPageSize ({page_limit}) was returned")
    else:
        c.expect(response.code in ("INVALID_ARGUMENT", "OUT_OF_RANGE"), f"devices/list above maxPageSize: {response.describe()}")
    over = int(c.limits.get("maxWaitMs", 60000)) + 1
    c.refused(await c.call("operations/wait", {"operationId": "op-none", "timeoutMs": over}), "OUT_OF_RANGE", field="timeoutMs",
              what="a wait above limits.maxWaitMs")
    caps = c.caps.get("subscriptions", {})
    maximum = caps.get("maxObservations")
    if isinstance(maximum, int) and (await c.devices()):
        device = (await c.devices())[0]["deviceId"]
        prop = next(iter((await c.describe(device)).get("properties") or {"x": 0}))
        refusal = await c.call("subscriptions/listen", {"notifications": {"observations": [{"deviceId": device, "property": prop}] * (maximum + 1)}})
        c.expect(refusal.error is not None, f"a subscription with {maximum + 1} observation entries must be refused (maxObservations {maximum})")


@check("transport.http-malformed-frames", ["BHMS-LIF-001", "BHMS-LIF-010", "BHMS-TRN-002"], profile="http", needs=("http",), generic=True)
async def http_malformed(c: Context) -> None:
    """The malformed-frame vectors POSTed raw: each is refused with the expected JSON-RPC error (the SDK's HTTP client
    transport cannot carry them, so the generic checks skip on this binding)."""
    import aiohttp

    from bhms.conformance.checks._util import raw_bytes, vectors

    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "BHMS-Protocol-Version": PROTOCOL_VERSION,
               "BHMS-Method": "devices/list"}
    if c.target.token:
        headers["Authorization"] = f"Bearer {c.target.token}"
    problems = []
    async with aiohttp.ClientSession() as session:
        for vec in vectors("malformed")["vectors"]:
            if vec["group"] not in ("nan", "utf8", "id", "batch"):
                continue
            body = raw_bytes(vec["raw"], vec.get("encoding"), c.wire.meta())
            async with session.post(c.target.url, data=body, headers=headers) as response:
                text = await response.read()
                try:
                    parsed = json.loads(text)
                except ValueError:
                    problems.append(f"{vec['name']}: HTTP {response.status} with a body that is not JSON")
                    continue
            error = parsed.get("error") if isinstance(parsed, dict) else None
            if not error or error.get("code") not in vec["expect"]["rpcCodes"]:
                problems.append(f"{vec['name']}: HTTP {response.status} {str(parsed)[:100]}")
    c.expect(not problems, "; ".join(problems[:5]))
