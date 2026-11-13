"""Asyncio JSON-RPC 2.0 session over a :class:`~bhms.transport.base.Transport`.

One class serves both roles of spec/bhms/02-transports.md:

* ``role="client"``: :meth:`Session.request` (concurrent, per-request timeout, cancellation),
  :meth:`Session.stream` (a request whose handler yields notifications until cancelled, e.g.
  ``subscriptions/listen``) and :meth:`Session.notify` (``notifications/cancelled``). Servers MUST NOT
  send requests and clients MUST NOT send responses (BHMS-TRN-001); the roles enforce it.
* ``role="server"``: every incoming request runs in its own task through the ``handler``. A handler
  returns a result ``dict``, or an *async iterator* yielding :class:`Notification` items and finally a
  :class:`Complete`; the iterator form is how ``subscriptions/listen`` is served. ``notifications/cancelled``
  cancels the handler's task and no response is sent (BHMS-LIF-051); a handler that must not abandon
  physical work on cancellation shields that work (BHMS-LIF-050).

Mechanics: messages are parsed with orjson only (schema/pydantic validation belongs to the dispatcher and
client above); a malformed frame is answered ``-32700`` and an oversize or batch frame ``-32600`` with
``id: null`` and the session keeps going (BHMS-TRN-002/004); the outbound queue is bounded, so a slow peer
blocks the producer instead of growing memory; ``close()`` cancels in-flight handlers (BHMS-TRN-005), flushes
the queue and fails pending requests with :class:`~bhms.transport.base.TransportClosed`.

The only BHMS-specific behaviour here is stream tagging: notifications and the final result of a stream
carry ``_meta["bhms/subscriptionId"]`` equal to the request id (BHMS-LIF-041, BHMS-LIF-044).

Error mapping: ``BhmsError`` <-> JSON-RPC error objects via :mod:`bhms.protocol.errors`; any other handler
exception is logged locally and sent as ``INTERNAL`` with ``mayHaveActed: true`` (it is unknown whether the
work started) and no detail.

Thread-safety: a session belongs to one event loop; all public coroutines are safe to call concurrently
from tasks of that loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Any

import orjson

from bhms.protocol.errors import BhmsError, from_jsonrpc
from bhms.transport.base import FrameTooLarge, Peer, Transport, TransportClosed

log = logging.getLogger("bhms.jsonrpc")

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
SUBSCRIPTION_KEY = "bhms/subscriptionId"
CANCELLED = "notifications/cancelled"


class JsonRpcError(Exception):
    """A JSON-RPC error that is not a BHMS error (``-32700``, ``-32600``, ``-32601``, ...).

    Raised by a handler to produce that error on the wire, and raised by the client session when the peer
    answers with one.
    """

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"{message} (JSON-RPC {code})")
        self.code = code
        self.message = message
        self.data = data

    def to_error(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message[:2000]}
        if self.data is not None:
            error["data"] = self.data
        return error


@dataclass(slots=True)
class Notification:
    """A server-to-client notification yielded by a streaming handler (tagged by the session)."""

    method: str
    params: dict[str, Any]


@dataclass(slots=True)
class Complete:
    """The final item of a streaming handler: the result that ends the stream."""

    result: dict[str, Any]


@dataclass(slots=True)
class RequestContext:
    """What a request handler receives: the raw request, who sent it, and the session."""

    id: str | int
    method: str
    params: Any
    peer: Peer
    session: Session


Handler = Callable[[RequestContext], Awaitable[Any]]
"""``async def handler(ctx) -> dict | AsyncIterator[Notification | Complete]``."""


def _valid_id(value: Any) -> bool:
    return isinstance(value, (str, int)) and not isinstance(value, bool)


def _internal_error() -> BhmsError:
    return BhmsError("INTERNAL", "internal server error", may_have_acted=True,
                     hint="This is a server bug and not a problem with your request; whether work started is "
                          "unknown, so reconcile with operations/get before retrying. Details are in the server log.")


def _error_object(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, JsonRpcError):
        return exc.to_error()
    if isinstance(exc, BhmsError):
        try:
            error = exc.to_jsonrpc()
        except ValueError:
            log.error("handler raised operation-only error %s as a JSON-RPC error", exc.code)
            error = _internal_error().to_jsonrpc()
    else:
        log.error("request handler failed", exc_info=exc)
        error = _internal_error().to_jsonrpc()
    error["message"] = error["message"][:2000]
    return error


class ClientStream:
    """Client end of a streaming request: an async iterator of notifications, then a final result.

    Iteration ends when the server completes the stream (``result`` is then set) and raises the error if the
    request fails or the connection drops (:class:`TransportClosed`). Leaving ``async with`` or calling
    :meth:`cancel` sends ``notifications/cancelled`` (BHMS-LIF-044).
    """

    def __init__(self, session: Session, request_id: int, queue_size: int) -> None:
        self.id = request_id
        self._session = session
        self._queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(queue_size)
        self._done = False
        self.result: dict[str, Any] | None = None

    def __aiter__(self) -> ClientStream:
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._done:
            raise StopAsyncIteration
        kind, payload = await self._queue.get()
        if kind == "n":
            return payload
        self._done = True
        self._session._streams.pop(self.id, None)
        if kind == "result":
            self.result = payload
            raise StopAsyncIteration
        raise payload

    async def cancel(self, reason: str | None = None) -> None:
        """Abandon the stream: tell the server and drop anything buffered (idempotent)."""
        if self._done:
            return
        self._done = True
        self._session._streams.pop(self.id, None)
        while not self._queue.empty():  # releases a receive loop blocked on a full queue
            self._queue.get_nowait()
        self._session._send_cancel(self.id, reason)

    async def __aenter__(self) -> ClientStream:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                        tb: TracebackType | None) -> None:
        await self.cancel()


class Session:
    """JSON-RPC session; see the module docstring.

    Args:
        transport: the connection; the session owns it and closes it in :meth:`close`.
        role: ``"client"`` or ``"server"``.
        handler: required for a server to answer anything (else every method is ``-32601``).
        max_message_bytes: limit for outgoing messages (default: the transport's limit). Incoming limits are
            enforced by the transport.
        outbound_queue_size: bound of the outbound queue; producers wait when it is full (backpressure).
        default_timeout: seconds a client request waits when ``timeout`` is not given (None: wait forever).
        max_inflight_requests: server limit of concurrently handled requests; beyond it ``BUSY``.
        stream_queue_size: client-side buffer per stream; a consumer that stops reading eventually stalls the
            connection's read loop, which stalls the server's sends (end-to-end backpressure).
        flush_timeout: seconds :meth:`close` waits for the outbound queue to drain.
    """

    def __init__(self, transport: Transport, *, role: str, handler: Handler | None = None,
                 max_message_bytes: int | None = None, outbound_queue_size: int = 256,
                 default_timeout: float | None = 30.0, max_inflight_requests: int = 16384,
                 stream_queue_size: int = 1024, flush_timeout: float = 5.0) -> None:
        if role not in ("client", "server"):
            raise ValueError("role must be 'client' or 'server'")
        self._transport = transport
        self.role = role
        self._handler = handler
        self.max_message_bytes = max_message_bytes or transport.max_message_bytes
        self.default_timeout = default_timeout
        self._max_inflight = max_inflight_requests
        self._stream_queue_size = stream_queue_size
        self._flush_timeout = flush_timeout
        self._outbox: asyncio.Queue[bytes] = asyncio.Queue(outbound_queue_size)
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._streams: dict[int, ClientStream] = {}
        self._handlers: dict[str | int, asyncio.Task[None]] = {}
        self._next_id = 0
        self._reader: asyncio.Task[None] | None = None
        self._writer: asyncio.Task[None] | None = None
        self._background: set[asyncio.Task[Any]] = set()
        self._closing = False
        self._closed = asyncio.Event()

    # ------------------------------------------------------------------ lifecycle

    @property
    def peer(self) -> Peer:
        return self._transport.peer

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    @property
    def inflight(self) -> int:
        """Requests awaiting a response (client) or being handled (server)."""
        if self.role == "server":
            return len(self._handlers)
        return len(self._pending) + len(self._streams)

    def start(self) -> Session:
        """Start the reader and writer tasks; returns self."""
        if self._reader is not None:
            raise RuntimeError("session already started")
        self._reader = asyncio.create_task(self._read_loop(), name="bhms-session-reader")
        self._writer = asyncio.create_task(self._write_loop(), name="bhms-session-writer")
        return self

    async def wait_closed(self) -> None:
        """Wait until the session has fully shut down (peer closed, I/O failure or :meth:`close`)."""
        await self._closed.wait()

    async def close(self) -> None:
        """Graceful shutdown: abandon in-flight requests, flush queued output, close the transport. Idempotent."""
        if self._closing:
            await self._closed.wait()
            return
        self._closing = True
        await self._cancel_handlers()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._outbox.join(), self._flush_timeout)
        await self._teardown(TransportClosed("session closed"))

    async def __aenter__(self) -> Session:
        return self if self._reader is not None else self.start()

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                        tb: TracebackType | None) -> None:
        await self.close()

    async def _cancel_handlers(self) -> None:
        tasks = [t for t in self._handlers.values() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _teardown(self, reason: TransportClosed) -> None:
        if self._closed.is_set():
            return
        self._closing = True
        self._closed.set()  # first, so concurrent callers and late enqueues see it
        current = asyncio.current_task()
        for task in (self._reader, self._writer):
            if task is not None and task is not current:
                task.cancel()
        await self._cancel_handlers()
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(reason)
        self._pending.clear()
        for stream in list(self._streams.values()):
            self._finish_stream(stream, "error", reason)
        self._streams.clear()
        while not self._outbox.empty():  # wakes blocked producers and lets join() return
            self._outbox.get_nowait()
            self._outbox.task_done()
        await self._transport.close()
        for task in list(self._background):
            task.cancel()

    # ------------------------------------------------------------------ outbound

    def _encode(self, message: dict[str, Any]) -> bytes:
        data = orjson.dumps(message)
        if len(data) > self.max_message_bytes:
            raise _TooLarge(len(data), self.max_message_bytes)
        return data

    async def _enqueue(self, data: bytes) -> None:
        if self._closed.is_set():
            raise TransportClosed("session is closed")
        await self._outbox.put(data)
        if self._closed.is_set():
            raise TransportClosed("session is closed")

    def _enqueue_nowait(self, data: bytes) -> None:
        """Best-effort send that never blocks the caller (cancellation notices)."""
        if self._closed.is_set():
            return
        try:
            self._outbox.put_nowait(data)
        except asyncio.QueueFull:
            self._spawn(self._enqueue(data))

    def _spawn(self, coro: Awaitable[Any]) -> None:
        async def run() -> None:
            with contextlib.suppress(TransportClosed):
                await coro

        task = asyncio.create_task(run())
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _write_loop(self) -> None:
        while True:
            data = await self._outbox.get()
            try:
                await self._transport.send(data)
            except (TransportClosed, OSError) as exc:
                log.debug("send failed: %s", exc)
                self._outbox.task_done()
                await self._teardown(TransportClosed(str(exc)))
                return
            self._outbox.task_done()

    def _send_cancel(self, request_id: int, reason: str | None) -> None:
        params: dict[str, Any] = {"requestId": request_id}
        if reason:
            params["reason"] = reason[:500]
        self._enqueue_nowait(orjson.dumps({"jsonrpc": "2.0", "method": CANCELLED, "params": params}))

    # ------------------------------------------------------------------ client API

    def _require_client(self, what: str) -> None:
        if self.role != "client":
            raise RuntimeError(f"a server session cannot {what} (BHMS-TRN-001)")

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _encode_request(self, request_id: int, method: str, params: Any) -> bytes:
        try:
            return self._encode({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        except _TooLarge as exc:
            raise BhmsError("INVALID_ARGUMENT", f"request of {exc.size} bytes exceeds the {exc.limit} byte message limit",
                            field="", bound=exc.limit,
                            hint="send less data per request; the server's limits.maxMessageBytes is the bound") from None

    async def request(self, method: str, params: Any, *, timeout: float | None = None) -> dict[str, Any]:
        """Send a request and return its result object.

        Raises ``BhmsError`` / :class:`JsonRpcError` for an error response, ``BhmsError(DEADLINE_EXCEEDED,
        may_have_acted=True)`` after ``timeout`` seconds (default ``default_timeout``; the request is cancelled
        with ``notifications/cancelled`` and the outcome is unknown, BHMS-LIF-053), :class:`TransportClosed` if
        the connection drops, and re-raises ``CancelledError`` after cancelling the request on the wire.
        """
        self._require_client("send requests")
        request_id = self._new_id()
        data = self._encode_request(request_id, method, params)
        limit = self.default_timeout if timeout is None else timeout
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            async with asyncio.timeout(limit):
                await self._enqueue(data)
                return await future
        except TimeoutError:
            self._send_cancel(request_id, "timeout")
            raise BhmsError("DEADLINE_EXCEEDED", f"no response to {method} within {limit} s",
                            may_have_acted=True,
                            hint="The outcome is unknown. Check with operations/get, or retry with the same "
                                 "operationKey; never re-issue with a new key (BHMS-LIF-053).") from None
        except asyncio.CancelledError:
            self._send_cancel(request_id, "client cancelled")
            raise
        finally:
            self._pending.pop(request_id, None)

    async def stream(self, method: str, params: Any) -> ClientStream:
        """Send a streaming request (``subscriptions/listen``); returns once it is on the wire."""
        self._require_client("send requests")
        request_id = self._new_id()
        data = self._encode_request(request_id, method, params)
        stream = ClientStream(self, request_id, self._stream_queue_size)
        self._streams[request_id] = stream
        try:
            await self._enqueue(data)
        except BaseException:
            self._streams.pop(request_id, None)
            raise
        return stream

    async def notify(self, method: str, params: Any) -> None:
        """Send a notification (a client sends only ``notifications/cancelled``)."""
        self._require_client("send notifications")
        await self._enqueue(self._encode({"jsonrpc": "2.0", "method": method, "params": params}))

    # ------------------------------------------------------------------ inbound

    async def _read_loop(self) -> None:
        reason = TransportClosed("connection closed")
        try:
            while True:
                try:
                    data = await self._transport.receive()
                except FrameTooLarge as exc:
                    await self._protocol_error(None, INVALID_REQUEST,
                                               f"message exceeds the {exc.limit} byte limit (BHMS-TRN-004)")
                    continue
                await self._on_message(data)
        except TransportClosed as exc:
            reason = exc
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a bug here must still end the session cleanly
            log.exception("session reader failed")
        await self._teardown(reason)

    async def _protocol_error(self, request_id: Any, code: int, message: str) -> None:
        if self.role != "server":
            log.warning("dropping malformed incoming message: %s", message)
            return
        await self._enqueue(orjson.dumps({"jsonrpc": "2.0", "id": request_id,
                                          "error": {"code": code, "message": message}}))

    async def _on_message(self, data: bytes) -> None:
        try:
            msg = orjson.loads(data)
        except orjson.JSONDecodeError as exc:
            await self._protocol_error(None, PARSE_ERROR, f"Parse error: {str(exc)[:200]}")
            return
        if not isinstance(msg, dict):
            kind = "batch arrays are not allowed (BHMS-TRN-002)" if isinstance(msg, list) else "message must be an object"
            await self._protocol_error(None, INVALID_REQUEST, f"Invalid Request: {kind}")
            return
        method = msg.get("method")
        if method is None and ("result" in msg or "error" in msg):
            if self.role == "client":
                self._on_response(msg)
            else:
                log.debug("ignoring a response sent to a server (BHMS-TRN-001)")
            return
        request_id = msg.get("id") if "id" in msg else _NO_ID
        if request_id is not _NO_ID:
            await self._on_request(msg, request_id, method)
        elif isinstance(method, str) and msg.get("jsonrpc") == "2.0":
            await self._on_notification(method, msg.get("params"))
        else:
            await self._protocol_error(None, INVALID_REQUEST, "Invalid Request: not a JSON-RPC 2.0 message")

    async def _on_notification(self, method: str, params: Any) -> None:
        if self.role == "server":
            if method == CANCELLED and isinstance(params, dict):
                target = params.get("requestId")
                task = self._handlers.get(target) if _valid_id(target) else None
                if task is not None:
                    task.cancel()
            return
        meta = params.get("_meta") if isinstance(params, dict) else None
        sub = meta.get(SUBSCRIPTION_KEY) if isinstance(meta, dict) else None
        stream = self._streams.get(sub) if isinstance(sub, int) else None
        if stream is None:
            log.debug("dropping notification %s outside any stream", method)
            return
        await stream._queue.put(("n", {"method": method, "params": params}))  # waits when full: backpressure

    async def _on_request(self, msg: dict[str, Any], request_id: Any, method: Any) -> None:
        if self.role != "server":
            log.warning("ignoring a request sent to a client (BHMS-TRN-001)")
            return
        if not _valid_id(request_id):
            await self._protocol_error(None, INVALID_REQUEST, "Invalid Request: id must be a string or an integer")
            return
        if msg.get("jsonrpc") != "2.0" or not isinstance(method, str):
            await self._protocol_error(request_id, INVALID_REQUEST,
                                       "Invalid Request: jsonrpc must be '2.0' and method a string")
            return
        if request_id in self._handlers:
            await self._protocol_error(None, INVALID_REQUEST,
                                       f"Invalid Request: id {request_id!r} is already in flight (BHMS-LIF-010)")
            return
        if len(self._handlers) >= self._max_inflight:
            busy = BhmsError("BUSY", "too many requests in flight on this connection",
                             bound=self._max_inflight, hint="retry with backoff, or wait for responses first")
            await self._enqueue(orjson.dumps({"jsonrpc": "2.0", "id": request_id, "error": busy.to_jsonrpc()}))
            return
        ctx = RequestContext(request_id, method, msg.get("params"), self.peer, self)
        task = asyncio.create_task(self._run_request(ctx))
        self._handlers[request_id] = task

    def _on_response(self, msg: dict[str, Any]) -> None:
        request_id = msg.get("id")
        if not isinstance(request_id, int) or isinstance(request_id, bool):
            log.debug("dropping response with unusable id %r", request_id)
            return
        outcome: Any
        kind = "result"
        if "error" in msg:
            kind, outcome = "error", _decode_error(msg["error"])
        elif isinstance(msg.get("result"), dict):
            outcome = msg["result"]
        else:
            kind, outcome = "error", JsonRpcError(INVALID_REQUEST, "response result is not an object")
        future = self._pending.get(request_id)
        if future is not None:
            if not future.done():
                if kind == "result":
                    future.set_result(outcome)
                else:
                    future.set_exception(outcome)
            return
        stream = self._streams.get(request_id)
        if stream is not None:
            self._finish_stream(stream, kind, outcome)
            return
        log.debug("ignoring a response to unknown or cancelled request %r (BHMS-LIF-051)", request_id)

    def _finish_stream(self, stream: ClientStream, kind: str, payload: Any) -> None:
        try:
            stream._queue.put_nowait((kind, payload))
        except asyncio.QueueFull:
            self._spawn(stream._queue.put((kind, payload)))

    # ------------------------------------------------------------------ server request execution

    async def _run_request(self, ctx: RequestContext) -> None:
        try:
            if self._handler is None:
                raise JsonRpcError(METHOD_NOT_FOUND, f"Method not found: {ctx.method}")
            outcome = await self._handler(ctx)
            if hasattr(outcome, "__aiter__"):
                await self._pump_stream(ctx, outcome)
            else:
                await self._respond(ctx.id, outcome)
        except asyncio.CancelledError:
            # Abandoned by notifications/cancelled or by close(): nothing is sent (BHMS-LIF-051).
            pass
        except TransportClosed:
            pass
        except Exception as exc:  # noqa: BLE001 - every handler failure becomes a JSON-RPC error
            with contextlib.suppress(TransportClosed):
                await self._send_error(ctx.id, exc)
        finally:
            self._handlers.pop(ctx.id, None)

    async def _respond(self, request_id: str | int, result: Any) -> None:
        if not isinstance(result, dict):
            raise TypeError(f"handler for request {request_id!r} returned {type(result).__name__}, not a result object")
        try:
            data = self._encode({"jsonrpc": "2.0", "id": request_id, "result": result})
        except _TooLarge as exc:
            log.error("result of %d bytes exceeds the %d byte limit", exc.size, exc.limit)
            raise _internal_error() from None
        await self._enqueue(data)

    async def _send_error(self, request_id: str | int, exc: BaseException) -> None:
        await self._enqueue(orjson.dumps({"jsonrpc": "2.0", "id": request_id, "error": _error_object(exc)}))

    async def _pump_stream(self, ctx: RequestContext, stream: AsyncIterator[Any]) -> None:
        """Send a streaming handler's notifications, then its result; tag both with the subscription id."""
        final: dict[str, Any] = {"resultType": "complete"}
        try:
            async for item in stream:
                if isinstance(item, Complete):
                    final = item.result
                    break
                if not isinstance(item, Notification):
                    raise TypeError(f"stream handler yielded {type(item).__name__}; expected Notification or Complete")
                params = dict(item.params)
                params["_meta"] = {**params.get("_meta", {}), SUBSCRIPTION_KEY: ctx.id}
                try:
                    data = self._encode({"jsonrpc": "2.0", "method": item.method, "params": params})
                except _TooLarge as exc:
                    log.error("notification of %d bytes exceeds the %d byte limit", exc.size, exc.limit)
                    raise _internal_error() from None
                await self._enqueue(data)
        finally:
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                await aclose()
        final = {"resultType": "complete", **final, "_meta": {**final.get("_meta", {}), SUBSCRIPTION_KEY: ctx.id}}
        await self._respond(ctx.id, final)


_NO_ID = object()


class _TooLarge(Exception):
    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"{size} > {limit}")
        self.size = size
        self.limit = limit


def _decode_error(error: Any) -> Exception:
    """Turn a JSON-RPC error object into BhmsError (BHMS errors) or JsonRpcError (everything else)."""
    if not isinstance(error, dict):
        return JsonRpcError(INVALID_REQUEST, "malformed error object in response")
    try:
        return from_jsonrpc(error)
    except ValueError:
        code = error.get("code")
        return JsonRpcError(code if isinstance(code, int) else INVALID_REQUEST, str(error.get("message", "")),
                            error.get("data"))
