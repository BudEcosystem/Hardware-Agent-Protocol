"""A raw JSON-RPC connection for the conformance runner.

The runner is language-neutral: it never imports a server and never trusts the SDK client's parsing, because the
client would hide the very defects (a missing ``resultType``, a notification without opt-in) that a check must see.
:class:`Wire` therefore sends and receives plain JSON over any :class:`~bhms.transport.base.Transport`
(stdio, Unix socket, TCP, WebSocket, Streamable HTTP) and keeps every message in a shared :class:`Recorder` so that
whole-run observers (:mod:`bhms.conformance.observers`) can validate everything a server ever said.

A request is correlated by ``id``. Notifications that carry ``_meta["bhms/subscriptionId"]`` are routed to the
:class:`Stream` of that request id; a stream's final response ends it (BHMS-LIF-044).

Thread-safety: one event loop; a wire may be used by many tasks concurrently.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import time
from dataclasses import dataclass, field
from typing import Any

from bhms.protocol.version import PROTOCOL_VERSION
from bhms.transport.base import FrameTooLarge, Transport, TransportClosed

CLIENT_INFO = {"name": "bhms-conformance", "version": "0.1.0"}
SUBSCRIPTION_KEY = "bhms/subscriptionId"
_UNSET: Any = object()


@dataclass(slots=True)
class Seen:
    """One message observed on a wire: ``direction`` is ``out`` or ``in``; ``message`` is the parsed JSON (or the raw
    bytes when it did not parse); ``request`` is the request an inbound response answers."""

    wire: str
    direction: str
    message: Any
    at: float
    request: dict[str, Any] | None = None
    frame_error: str | None = None


@dataclass
class Recorder:
    """Every message of the run, in order; the input of the observers."""

    seen: list[Seen] = field(default_factory=list)
    limit: int = 200_000

    def add(self, item: Seen) -> None:
        if len(self.seen) < self.limit:
            self.seen.append(item)


class Response:
    """A JSON-RPC response (or the lack of one)."""

    def __init__(self, raw: Any, request: dict[str, Any]) -> None:
        self.raw = raw
        self.request = request

    @property
    def is_object(self) -> bool:
        return isinstance(self.raw, dict)

    @property
    def result(self) -> dict[str, Any] | None:
        return self.raw.get("result") if self.is_object and isinstance(self.raw.get("result"), dict) else None

    @property
    def error(self) -> dict[str, Any] | None:
        return self.raw.get("error") if self.is_object and isinstance(self.raw.get("error"), dict) else None

    @property
    def ok(self) -> bool:
        return self.result is not None

    @property
    def rpc_code(self) -> int | None:
        err = self.error
        return err.get("code") if err else None

    @property
    def data(self) -> dict[str, Any]:
        err = self.error or {}
        return err["data"] if isinstance(err.get("data"), dict) else {}

    @property
    def code(self) -> str | None:
        """``data.bhmsCode`` of an error response."""
        value = self.data.get("bhmsCode")
        return value if isinstance(value, str) else None

    def describe(self) -> str:
        if self.error:
            return f"error {self.rpc_code} {self.code or ''} {str(self.error.get('message', ''))[:160]}".strip()
        if self.result is not None:
            return "result " + json.dumps(self.result)[:160]
        return "malformed response " + json.dumps(self.raw, default=str)[:160]


class Stream:
    """The notifications of one ``subscriptions/listen`` request and its final response."""

    def __init__(self, wire: Wire, request_id: Any) -> None:
        self.wire, self.id = wire, request_id
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.final: asyncio.Future[Response] = asyncio.get_running_loop().create_future()
        self.final.add_done_callback(_consume)
        self.items: list[dict[str, Any]] = []

    async def next(self, timeout: float = 5.0) -> dict[str, Any] | None:
        """The next notification, or ``None`` when ``timeout`` passes or the stream ended."""
        try:
            item = await asyncio.wait_for(self.queue.get(), timeout)
        except asyncio.TimeoutError:
            return None
        self.items.append(item)
        return item

    async def until(self, predicate: Any, timeout: float = 5.0) -> dict[str, Any] | None:
        """Consume notifications until ``predicate(notification)`` is true; ``None`` on timeout."""
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            item = await self.next(left)
            if item is None:
                return None
            if predicate(item):
                return item
        return None

    def drain(self) -> list[dict[str, Any]]:
        out = []
        while not self.queue.empty():
            item = self.queue.get_nowait()
            self.items.append(item)
            out.append(item)
        return out

    async def cancel(self, reason: str = "conformance") -> None:
        await self.wire.notify("notifications/cancelled", {"requestId": self.id, "reason": reason})


class Wire:
    """One connection. ``name`` labels it in the recorder."""

    def __init__(self, transport: Transport, recorder: Recorder, name: str = "main") -> None:
        self.transport, self.recorder, self.name = transport, recorder, name
        self._ids = itertools.count(1)
        self._pending: dict[Any, asyncio.Future[Response]] = {}
        self._requests: dict[Any, dict[str, Any]] = {}
        self._streams: dict[Any, Stream] = {}
        self.unmatched: asyncio.Queue[Any] = asyncio.Queue()
        self.closed = False
        self.frame_errors: list[str] = []
        self._reader: asyncio.Task[None] | None = None

    def start(self) -> Wire:
        self._reader = asyncio.ensure_future(self._read())
        return self

    # -------------------------------------------------------------- receiving

    async def _read(self) -> None:
        try:
            while True:
                try:
                    data = await self.transport.receive()
                except FrameTooLarge as exc:
                    self.frame_errors.append(str(exc))
                    continue
                self._dispatch(data)
        except (TransportClosed, asyncio.CancelledError):
            pass
        except Exception as exc:  # a reader that dies silently would turn every check into a timeout
            self.frame_errors.append(f"reader failed: {exc!r}")
        finally:
            self.closed = True
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(TransportClosed("connection closed"))
            for stream in self._streams.values():
                if not stream.final.done():
                    stream.final.set_exception(TransportClosed("connection closed"))

    def _dispatch(self, data: bytes) -> None:
        now = time.monotonic()
        try:
            message = json.loads(data)
        except (ValueError, UnicodeDecodeError) as exc:
            self.recorder.add(Seen(self.name, "in", bytes(data), now, frame_error=f"not JSON: {exc}"))
            self.frame_errors.append(f"not JSON: {exc}")
            return
        if b"\n" in data.strip(b"\r\n"):
            self.frame_errors.append("embedded newline in a frame")
        request = None
        if isinstance(message, dict) and "method" not in message and "id" in message:
            request = self._requests.get(message["id"])
        self.recorder.add(Seen(self.name, "in", message, now, request))
        if not isinstance(message, dict):
            self.unmatched.put_nowait(message)
            return
        if "method" in message:
            if "id" in message:
                return  # a server-to-client request: the TRN-001 observer reports it
            sub = (message.get("params") or {}).get("_meta", {}).get(SUBSCRIPTION_KEY) if isinstance(
                message.get("params"), dict) and isinstance(message["params"].get("_meta"), dict) else None
            stream = self._streams.get(sub)
            if stream is not None:
                stream.queue.put_nowait(message)
            else:
                self.unmatched.put_nowait(message)
            return
        ident = message.get("id")
        stream = self._streams.get(ident)
        response = Response(message, self._requests.get(ident, {}))
        if stream is not None and not stream.final.done():
            stream.final.set_result(response)
            return
        future = self._pending.pop(ident, None) if isinstance(ident, (str, int)) else None
        if future is not None and not future.done():
            future.set_result(response)
        else:
            self.unmatched.put_nowait(message)

    # -------------------------------------------------------------- sending

    async def send_bytes(self, data: bytes) -> None:
        try:
            parsed: Any = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            parsed = bytes(data)
        self.recorder.add(Seen(self.name, "out", parsed, time.monotonic()))
        await self.transport.send(data)

    async def send_json(self, message: Any) -> None:
        await self.send_bytes(json.dumps(message, allow_nan=False).encode())

    def meta(self, **overrides: Any) -> dict[str, Any]:
        meta: dict[str, Any] = {"bhms/protocolVersion": PROTOCOL_VERSION, "bhms/clientInfo": CLIENT_INFO}
        meta.update(overrides)
        return meta

    def build(self, method: str, params: dict[str, Any] | None, *, meta: Any = _UNSET, ident: Any = _UNSET) -> dict[str, Any]:
        """A request. ``meta=None`` omits ``_meta``; a dict replaces it; ``params=None`` still sends an empty object."""
        body = dict(params or {})
        if meta is _UNSET:
            body["_meta"] = self.meta()
        elif meta is not None:
            body["_meta"] = meta
        return {"jsonrpc": "2.0", "id": next(self._ids) if ident is _UNSET else ident, "method": method, "params": body}

    async def request(self, method: str, params: dict[str, Any] | None = None, *, meta: Any = _UNSET,
                      timeout: float = 30.0) -> Response:
        """Send a request and await its response (raises ``TimeoutError`` / :class:`TransportClosed`)."""
        return await self.send_request(self.build(method, params, meta=meta), timeout=timeout)

    async def send_request(self, message: dict[str, Any], *, timeout: float = 30.0) -> Response:
        ident = message.get("id")
        future: asyncio.Future[Response] = asyncio.get_running_loop().create_future()
        future.add_done_callback(_consume)
        self._pending[ident] = future
        self._requests[ident] = message
        try:
            await self.send_json(message)
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(ident, None)

    def submit(self, method: str, params: dict[str, Any] | None = None, *, meta: Any = _UNSET) -> tuple[Any, asyncio.Task[Response]]:
        """Send a request without awaiting it; returns ``(id, task)`` so a check can cancel or race it."""
        message = self.build(method, params, meta=meta)
        return message["id"], asyncio.ensure_future(self.send_request(message, timeout=120.0))

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await self.send_json({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def listen(self, notifications: dict[str, Any], *, meta: Any = _UNSET, timeout: float = 10.0) -> tuple[Stream, dict[str, Any]]:
        """Open ``subscriptions/listen``; returns the stream and its acknowledgement (BHMS-LIF-040)."""
        message = self.build("subscriptions/listen", {"notifications": notifications}, meta=meta)
        stream = Stream(self, message["id"])
        self._streams[message["id"]] = stream
        self._requests[message["id"]] = message
        await self.send_json(message)
        first = await stream.next(timeout)
        if first is None:
            if stream.final.done() and not stream.final.cancelled():
                with contextlib.suppress(Exception):
                    raise ListenRefused(stream.final.result())
            raise TimeoutError("no acknowledgement of subscriptions/listen")
        return stream, first

    async def exchange_raw(self, data: bytes, *, timeout: float = 3.0, quiet: float = 0.1) -> list[Any]:
        """Send raw bytes and collect every message that comes back unprompted (an error for a malformed frame has no
        pending request to match): waits up to ``timeout`` for the first, then ``quiet`` seconds for more."""
        while not self.unmatched.empty():
            self.unmatched.get_nowait()
        await self.send_bytes(data)
        out: list[Any] = []
        try:
            out.append(await asyncio.wait_for(self.unmatched.get(), timeout))
        except asyncio.TimeoutError:
            return out
        await asyncio.sleep(quiet)
        while not self.unmatched.empty():
            out.append(self.unmatched.get_nowait())
        return out

    async def settle(self, seconds: float = 0.15) -> list[Any]:
        """Messages that arrived and matched nothing within ``seconds`` (responses to notifications, strays)."""
        await asyncio.sleep(seconds)
        out = []
        while not self.unmatched.empty():
            out.append(self.unmatched.get_nowait())
        return out

    async def close(self) -> None:
        if not self.closed:
            await self.transport.close()
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader
        self.closed = True


def _consume(future: asyncio.Future[Any]) -> None:
    """Mark a failed future's exception as retrieved (a connection that closes under a cancelled wait is not news)."""
    if not future.cancelled():
        future.exception()


class ListenRefused(Exception):
    """``subscriptions/listen`` was answered with a response instead of an acknowledgement."""

    def __init__(self, response: Response) -> None:
        super().__init__(response.describe())
        self.response = response
