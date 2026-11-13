"""Streamable HTTP binding (spec/bhms/02-transports.md §2.4), server and client, on ``aiohttp`` (optional extra ``http``).

**Server** — :func:`serve_http` exposes one endpoint (default ``/bhms``) of a :class:`~bhms.jsonrpc.dispatcher.Server`:

* each client message is one ``POST`` with ``Content-Type: application/json`` and the headers ``BHMS-Protocol-Version`` and
  ``BHMS-Method`` mirroring ``params._meta["bhms/protocolVersion"]`` and ``method``; a mismatch or a missing header is HTTP 400
  with an ``INVALID_ARGUMENT`` JSON-RPC error naming the header (BHMS-TRN-040);
* an ordinary request is answered with ``application/json`` (one response), ``subscriptions/listen`` with
  ``text/event-stream`` whose events each carry one JSON-RPC message and end with the listen result (BHMS-TRN-041);
* closing the response stream is the request's cancellation signal: the server treats a disconnect exactly like
  ``notifications/cancelled`` — the request is abandoned and nothing durable is cancelled (BHMS-TRN-042, BHMS-TRN-005);
* ``notifications/cancelled`` may also be ``POST``ed and is answered ``202`` without a body (BHMS-TRN-043); it is matched to the
  in-flight request of the same credential and id;
* the principal is the bearer token (BHMS-SEC-001): a missing or unknown token is HTTP 401 (``WWW-Authenticate: Bearer``)
  except for ``server/discover``, which is answered without a principal; a non-loopback bind needs TLS (BHMS-SEC-004); on
  a loopback bind the ``Host`` header must name loopback (DNS-rebinding guard). Bodies over ``max_message_bytes`` are
  refused with ``-32600`` (BHMS-TRN-004), batches likewise (BHMS-TRN-002).

Every POST gets its own :class:`~bhms.jsonrpc.session.Session` over an in-memory :class:`HttpExchange` transport, so the
dispatcher, error mapping, stream tagging and the cancellation contract are the very same code as on every other binding.
There is no stream resumption: a lost response stream loses that request; the client re-issues it, with the same
``operationKey`` for ``actions/invoke`` (BHMS-OPS-030).

**Client** — :func:`connect_http` returns a :class:`~bhms.transport.base.Transport` for :class:`~bhms.client.client.Client`
(``Client.connect("http://host:port/bhms", token=...)``): each outgoing request becomes a POST whose answer (JSON or SSE) is
delivered to ``receive()``; a ``notifications/cancelled`` aborts the matching response stream (the cancellation signal) and is
also POSTed (best effort).

Example::

    listener = await serve_http("127.0.0.1", 8766, rpc, authenticate=lambda token: token == "s3cret")
    client = await Client.connect("http://127.0.0.1:8766/bhms", token="s3cret")

Thread-safety: one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import ssl as ssl_module
from collections.abc import Callable
from typing import Any

import orjson

try:  # optional dependency: the core package must import without it
    import aiohttp
    from aiohttp import web
except ImportError as exc:  # pragma: no cover - exercised only where aiohttp is absent
    raise ImportError("Streamable HTTP needs aiohttp: pip install 'bhms[http]'") from exc

from bhms.jsonrpc.dispatcher import Server as RpcServer
from bhms.protocol.errors import BhmsError
from bhms.transport.base import (DEFAULT_MAX_MESSAGE_BYTES, FrameTooLarge, Peer, Transport, TransportClosed,
                                 check_message_limit)
from bhms.transport.stream import Listener, is_loopback

DEFAULT_PATH = "/bhms"
VERSION_HEADER = "BHMS-Protocol-Version"
METHOD_HEADER = "BHMS-Method"
KEEPALIVE_S = 15.0
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _bearer(header: str | None) -> str | None:
    if header and header[:7].lower() == "bearer ":
        return header[7:].strip() or None
    return None


def _rpc_error(request_id: Any, code: int, message: str, data: dict[str, Any] | None = None) -> bytes:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return orjson.dumps({"jsonrpc": "2.0", "id": request_id, "error": error})


def _bhms_error(request_id: Any, exc: BhmsError) -> bytes:
    return orjson.dumps({"jsonrpc": "2.0", "id": request_id, "error": exc.to_jsonrpc()})


class HttpExchange(Transport):
    """One POST as a transport: the request body is the only incoming message; outgoing messages are queued for the
    response writer. A cancellation can be injected with :meth:`feed`."""

    OUTGOING_BOUND = 16

    def __init__(self, peer: Peer, max_message_bytes: int) -> None:
        self.peer = peer
        self.max_message_bytes = max_message_bytes
        self._incoming: asyncio.Queue[bytes | None] = asyncio.Queue()
        # Bounded: when the HTTP client reads slowly the session's writer blocks here, so the session's outbox and the
        # per-subscription overflow policy (BHMS-LIF-043: drop observations, end with endReason overflow) engage.
        self.outgoing: asyncio.Queue[bytes | None] = asyncio.Queue(self.OUTGOING_BOUND)
        self._closed = False

    def feed(self, data: bytes) -> None:
        self._incoming.put_nowait(data)

    async def send(self, data: bytes) -> None:
        if self._closed:
            raise TransportClosed("exchange closed")
        await self.outgoing.put(data)
        if self._closed:
            raise TransportClosed("exchange closed")

    async def receive(self) -> bytes:
        item = await self._incoming.get()
        if item is None:
            raise TransportClosed("exchange closed")
        return item

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._incoming.put_nowait(None)
            while not self.outgoing.empty():  # unblock a writer waiting on a full queue
                self.outgoing.get_nowait()
            self.outgoing.put_nowait(None)


class HttpListener(Listener):
    """A running Streamable HTTP endpoint (``address`` is ``(host, port)``)."""

    def __init__(self, runner: web.AppRunner, address: tuple[str, int], exchanges: set[HttpExchange]) -> None:
        super().__init__(None, address)
        self._runner = runner
        self.exchanges = exchanges  # live POSTs (for diagnostics and tests)

    async def close(self) -> None:
        await self._runner.cleanup()


async def serve_http(host: str, port: int, rpc: RpcServer, *, authenticate: Callable[[str | None], bool] | None = None,
                     path: str = DEFAULT_PATH, ssl: ssl_module.SSLContext | None = None,
                     max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> HttpListener:
    """Serve ``rpc`` on ``http[s]://host:port<path>``; see the module docstring.

    ``authenticate(token)`` returns whether a bearer token (or None) maps to a principal; a request without a valid one is
    refused with 401 except ``server/discover``. A non-loopback ``host`` needs ``ssl`` and ``authenticate`` (BHMS-SEC-004).
    """
    check_message_limit(max_message_bytes)
    if not is_loopback(host) and (ssl is None or authenticate is None):
        raise ValueError(f"refusing to serve HTTP on {host!r} without TLS and bearer authentication (BHMS-SEC-004): "
                         "pass ssl= and authenticate=, or bind 127.0.0.1")
    inflight: dict[tuple[str, str], HttpExchange] = {}
    exchanges: set[HttpExchange] = set()
    closers: set[asyncio.Task[None]] = set()
    loopback_only = is_loopback(host)

    async def post(request: web.Request) -> web.StreamResponse:
        if loopback_only and _host_of(request.headers.get("Host", "")) not in _LOOPBACK_HOSTS:
            return web.Response(status=403, text="Host must be a loopback name for a loopback listener\n")
        if request.content_type != "application/json":
            return web.Response(status=415, text="Content-Type must be application/json (BHMS-TRN-040)\n")
        token = _bearer(request.headers.get("Authorization"))
        try:
            body = await request.read()
        except web.HTTPRequestEntityTooLarge:
            return _json(_rpc_error(None, -32600, f"message exceeds the {max_message_bytes} byte limit"), 413)
        message = _parse(body)
        method = message.get("method") if isinstance(message, dict) else None
        if authenticate is not None and method != "server/discover" and not authenticate(token):
            return web.Response(status=401, headers={"WWW-Authenticate": "Bearer"},
                                text="missing or invalid bearer token (BHMS-SEC-001)\n")
        if isinstance(message, dict) and isinstance(method, str):
            problem = _header_problem(request, message)
            if problem is not None:
                return _json(_bhms_error(message.get("id"), problem), 400)
        who = f"{token or 'anonymous'}@{request.remote}"
        if isinstance(message, dict) and method == "notifications/cancelled" and "id" not in message:
            target = (message.get("params") or {}).get("requestId")
            exchange = inflight.get((who, repr(target)))
            if exchange is not None:
                exchange.feed(body)
            return web.Response(status=202)
        if isinstance(message, dict) and method is not None and "id" not in message:
            return web.Response(status=202)  # no other client notification exists; nothing to deliver (BHMS-LIF-014)
        return await _exchange(request, body, message, token, who)

    async def _exchange(request: web.Request, body: bytes, message: Any, token: str | None,
                        who: str) -> web.StreamResponse:
        peer = Peer("http", address=request.remote, token=token)
        exchange = HttpExchange(peer, max_message_bytes)
        session = rpc.session_for(exchange)
        request_id = message.get("id") if isinstance(message, dict) else None
        slot = (who, repr(request_id))
        exchanges.add(exchange)
        if request_id is not None:
            inflight[slot] = exchange
        streaming = isinstance(message, dict) and message.get("method") == "subscriptions/listen"
        response: web.StreamResponse | None = None
        abandoned = False
        try:
            exchange.feed(body)
            if streaming:
                response = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-store"})
                await response.prepare(request)
            while True:
                try:
                    data = await asyncio.wait_for(exchange.outgoing.get(), KEEPALIVE_S if streaming else None)
                except asyncio.TimeoutError:
                    assert response is not None
                    await response.write(b": keep-alive\n\n")  # keeps proxies from closing an idle stream
                    continue
                if data is None:
                    break
                final = _is_final(data, request_id)
                if streaming:
                    assert response is not None
                    await response.write(b"event: message\ndata: " + data + b"\n\n")
                    if final:
                        break
                elif final:
                    return _json(data, 200)
            if response is not None:
                await response.write_eof()
                return response
            return web.Response(status=500, text="the exchange ended without a response\n")
        except (asyncio.CancelledError, ConnectionResetError):
            # The client went away: abandon the request exactly as notifications/cancelled would (BHMS-TRN-042). The
            # work it started continues (BHMS-TRN-005, BHMS-LIF-050): the session detaches its handler.
            abandoned = True
            if request_id is not None:
                exchange.feed(orjson.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled",
                                            "params": {"requestId": request_id, "reason": "http disconnect"}}))
                await asyncio.sleep(0)
            raise
        finally:
            exchanges.discard(exchange)
            if inflight.get(slot) is exchange:
                del inflight[slot]
            if abandoned:  # the handler was cancelled: do not hold it up for detached handlers to drain
                closer = asyncio.get_running_loop().create_task(_close(session, exchange))
                closers.add(closer)
                closer.add_done_callback(closers.discard)
            else:
                await _close(session, exchange)

    async def not_allowed(request: web.Request) -> web.StreamResponse:
        return web.Response(status=405, headers={"Allow": "POST"}, text="BHMS over HTTP is POST only; there is no "
                                                                         "stream resumption (BHMS-TRN-043)\n")

    app = web.Application(client_max_size=max_message_bytes)
    app.router.add_post(path, post)
    app.router.add_route("*", path, not_allowed)
    runner = web.AppRunner(app, handler_cancellation=True, shutdown_timeout=1.0, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port, ssl_context=ssl)
    await site.start()
    sockets = site._server.sockets  # type: ignore[union-attr]
    bound = sockets[0].getsockname()
    return HttpListener(runner, (bound[0], bound[1]), exchanges)


async def _close(session: Any, exchange: HttpExchange) -> None:
    await session.close()
    await exchange.close()


def _host_of(header: str) -> str:
    host = header.strip()
    if host.startswith("["):
        return host[1:].split("]", 1)[0]
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def _parse(body: bytes) -> Any:
    try:
        return orjson.loads(body)
    except orjson.JSONDecodeError:
        return None


def _json(data: bytes, status: int) -> web.Response:
    return web.Response(body=data, status=status, content_type="application/json")


def _is_final(data: bytes, request_id: Any) -> bool:
    try:
        message = orjson.loads(data)
    except orjson.JSONDecodeError:
        return False
    if not isinstance(message, dict) or ("result" not in message and "error" not in message):
        return False
    return message.get("id") == request_id or message.get("id") is None


def _header_problem(request: web.Request, message: dict[str, Any]) -> BhmsError | None:
    """BHMS-TRN-040: the headers must mirror the body."""
    params = message.get("params")
    meta = params.get("_meta") if isinstance(params, dict) else None
    version = meta.get("bhms/protocolVersion") if isinstance(meta, dict) else None
    for header, expected in ((METHOD_HEADER, message.get("method")), (VERSION_HEADER, version)):
        got = request.headers.get(header)
        if got is None or (expected is not None and got != expected) or (expected is None and header == METHOD_HEADER):
            return BhmsError("INVALID_ARGUMENT", f"header {header} is {'missing' if got is None else repr(got)}; "
                             f"the message says {expected!r} (BHMS-TRN-040)", field=header,
                             hint=f"send {header}: {expected} with every POST (it mirrors the request body)")
    return None


# --------------------------------------------------------------------------- client


class HttpClientTransport(Transport):
    """Client side of Streamable HTTP as a :class:`~bhms.transport.base.Transport` (see the module docstring)."""

    def __init__(self, url: str, token: str | None, max_message_bytes: int, session: aiohttp.ClientSession,
                 ssl: ssl_module.SSLContext | None) -> None:
        self.url = url
        self.token = token
        self.peer = Peer("http", address=url)
        self.max_message_bytes = max_message_bytes
        self._http = session
        self._ssl = ssl
        self._inbox: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._posts: dict[Any, asyncio.Task[None]] = {}
        self._closed = False

    def _headers(self, message: dict[str, Any]) -> dict[str, str]:
        meta = (message.get("params") or {}).get("_meta") or {}
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   METHOD_HEADER: str(message.get("method", ""))}
        if "bhms/protocolVersion" in meta:
            headers[VERSION_HEADER] = str(meta["bhms/protocolVersion"])
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def send(self, data: bytes) -> None:
        if self._closed:
            raise TransportClosed("transport is closed")
        message = orjson.loads(data)
        if not isinstance(message, dict) or "method" not in message:
            raise TransportClosed("only requests and notifications are sent over HTTP (BHMS-TRN-001)")
        request_id = message.get("id")
        if request_id is None:  # notification: notifications/cancelled
            target = (message.get("params") or {}).get("requestId")
            post = self._posts.pop(target, None)
            if post is not None:
                post.cancel()  # closing the response stream is the cancellation signal (BHMS-TRN-042)
            asyncio.get_running_loop().create_task(self._notify(data, message))
            return
        task = asyncio.get_running_loop().create_task(self._post(request_id, data, message))
        self._posts[request_id] = task
        task.add_done_callback(lambda t, rid=request_id: self._posts.pop(rid, None) if self._posts.get(rid) is t else None)

    async def _notify(self, data: bytes, message: dict[str, Any]) -> None:
        with contextlib.suppress(Exception):
            async with self._http.post(self.url, data=data, headers=self._headers(message), ssl=self._ssl):
                pass

    async def _post(self, request_id: Any, data: bytes, message: dict[str, Any]) -> None:
        try:
            async with self._http.post(self.url, data=data, headers=self._headers(message), ssl=self._ssl) as response:
                kind = response.content_type
                if kind == "text/event-stream":
                    await self._read_events(response)
                else:
                    body = await response.read()
                    if len(body) > self.max_message_bytes:
                        raise FrameTooLarge(self.max_message_bytes)
                    if response.status == 401:
                        error = BhmsError("UNAUTHORIZED", "the gateway refused the bearer token (HTTP 401)",
                                          hint="present a valid bearer token (BHMS-SEC-001)")
                        body = _bhms_error(request_id, error)
                    elif response.status == 202 or not body:
                        return
                    self._inbox.put_nowait(body)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a lost response stream loses the connection's request (no resumption)
            await self.close()

    async def _read_events(self, response: aiohttp.ClientResponse) -> None:
        parts: list[bytes] = []
        async for line in response.content:
            line = line.rstrip(b"\r\n")
            if line.startswith(b"data:"):
                parts.append(line[5:].lstrip())
            elif not line and parts:
                self._inbox.put_nowait(b"".join(parts))
                parts = []

    async def receive(self) -> bytes:
        item = await self._inbox.get()
        if item is None:
            raise TransportClosed("transport is closed")
        return item

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._inbox.put_nowait(None)
        for task in list(self._posts.values()):
            task.cancel()
        with contextlib.suppress(Exception):
            await self._http.close()


async def connect_http(url: str, *, token: str | None = None, ssl: ssl_module.SSLContext | None = None,
                       max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> HttpClientTransport:
    """A transport that speaks Streamable HTTP to ``http[s]://host:port/bhms`` (bearer ``token`` optional)."""
    check_message_limit(max_message_bytes)
    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=10),
                                    connector=aiohttp.TCPConnector(limit=0))
    return HttpClientTransport(url, token, max_message_bytes, session, ssl)


__all__ = ["DEFAULT_PATH", "HttpClientTransport", "HttpExchange", "HttpListener", "connect_http", "serve_http"]
