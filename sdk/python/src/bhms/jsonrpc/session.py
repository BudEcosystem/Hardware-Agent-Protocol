"""Asyncio JSON-RPC 2.0 session over a :class:`~bhms.transport.base.Transport`.

One class serves both roles of spec/bhms/02-transports.md:

* ``role="client"``: :meth:`Session.request` (concurrent, per-request timeout, cancellation),
  :meth:`Session.stream` (a request whose handler yields notifications until cancelled, e.g.
  ``subscriptions/listen``) and :meth:`Session.notify` (``notifications/cancelled``). Servers MUST NOT
  send requests and clients MUST NOT send responses (BHMS-TRN-001); the roles enforce it.
* ``role="server"``: every incoming request runs in its own task through the ``handler``. Cancellation contract
  (BHMS-LIF-050, BHMS-TRN-005): ``notifications/cancelled``, a disconnect and ``close()`` never cancel physical work. By
  default the handler is *detached*: its response is dropped, ``ctx.cancelled`` is set, and the task keeps running,
  tracked by the session; ``close()`` waits for detached tasks up to ``drain_timeout`` and logs survivors. Only streaming
  handlers and methods for which the ``cancellable`` predicate is true (e.g. ``operations/wait``) are really cancelled. A handler
  returns a result ``dict``, or an *async iterator* yielding :class:`Notification` items and finally a
  :class:`Complete`; the iterator form is how ``subscriptions/listen`` is served. No response is sent after a cancellation
  (BHMS-LIF-051).

Mechanics: messages are parsed with orjson only (schema/pydantic validation belongs to the dispatcher and
client above); a malformed frame is answered ``-32700`` and an oversize or batch frame ``-32600`` with
``id: null`` and the session keeps going (BHMS-TRN-002/004); the outbound queue is bounded (a slow peer blocks the
producer instead of growing memory) and a client stream never blocks the read loop; ``close()`` abandons in-flight handlers (detaching them, see
above; BHMS-TRN-005), flushes the queue, waits for detached handlers and fails pending requests with :class:`~bhms.transport.base.TransportClosed`.

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
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
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
OBSERVATION = "notifications/observation"


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
    """What a request handler receives: the raw request, who sent it, and the session.

    ``cancelled`` is set when the client sent ``notifications/cancelled`` for this request or the connection closed;
    a detached handler (the default, see :class:`Session`) keeps running and may poll it to stop *waiting*;
    ``cancellable`` tells whether the session will cancel the task itself.
    """

    id: str | int
    method: str
    params: Any
    peer: Peer
    session: Session
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)
    cancellable: bool = False


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
            log.error("handler raised operation-only error %s as a JSON-RPC error", exc.bhms_code)
            error = _internal_error().to_jsonrpc()
    else:
        log.error("request handler failed", exc_info=exc)
        error = _internal_error().to_jsonrpc()
    error["message"] = error["message"][:2000]
    return error


class StreamOverflow(Exception):
    """Local: the consumer of a :class:`ClientStream` fell more than its buffer behind.

    The stream is cancelled on the wire. Per BHMS-LIF-044 the client reads current state (``operations/get``,
    ``events/read``) and calls ``subscriptions/listen`` again.
    """


class ClientStream:
    """Client end of a streaming request: an async iterator of notifications, then a final result.

    Iteration ends when the server completes the stream (``result`` is then set) and raises the error if the
    request fails, the connection drops (:class:`TransportClosed`) or the consumer falls ``stream_queue_size``
    messages behind (:class:`StreamOverflow`; buffered messages are still delivered first). The session read loop
    never blocks on a stream, so a slow consumer cannot delay other responses (slow-consumer policy is the
    server's, BHMS-LIF-043). The terminal outcome lives in its own slot, never in the buffer, so it cannot be lost.
    Leaving ``async with`` or calling :meth:`cancel` sends ``notifications/cancelled`` (BHMS-LIF-044).
    """

    def __init__(self, session: Session, request_id: int, queue_size: int) -> None:
        self.id = request_id
        self._session = session
        self._size = queue_size
        self._buffer: deque[dict[str, Any]] = deque()
        self._wake = asyncio.Event()
        self._terminal: tuple[str, Any] | None = None
        self._done = False
        self.result: dict[str, Any] | None = None

    def _push(self, item: dict[str, Any]) -> None:
        if self._terminal is not None or self._done:
            return
        if len(self._buffer) >= self._size:
            self._session._streams.pop(self.id, None)
            self._finish("error", StreamOverflow(
                f"subscription {self.id} fell more than {self._size} messages behind; read current state and "
                "call subscriptions/listen again (BHMS-LIF-044)"))
            self._session._send_cancel(self.id, "client buffer overflow")
            return
        self._buffer.append(item)
        self._wake.set()

    def _finish(self, kind: str, payload: Any) -> None:
        if self._terminal is None and not self._done:
            self._terminal = (kind, payload)
            self._wake.set()

    def __aiter__(self) -> ClientStream:
        return self

    async def __anext__(self) -> dict[str, Any]:
        while True:
            if self._buffer:
                return self._buffer.popleft()
            if self._done:
                raise StopAsyncIteration
            if self._terminal is not None:
                kind, payload = self._terminal
                self._done = True
                self._session._streams.pop(self.id, None)
                if kind == "result":
                    self.result = payload
                    raise StopAsyncIteration
                raise payload
            self._wake.clear()
            await self._wake.wait()

    async def cancel(self, reason: str | None = None) -> None:
        """Abandon the stream: tell the server and drop anything buffered (idempotent)."""
        if self._done:
            return
        self._done = True
        self._terminal = None
        self._buffer.clear()
        self._wake.set()
        if self._session._streams.pop(self.id, None) is not None:
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
        stream_queue_size: client-side buffer per stream. The read loop never blocks on it: a consumer that falls
            more than this many messages behind gets :class:`StreamOverflow` (slow-consumer policy is the server's,
            BHMS-LIF-043).
        flush_timeout: seconds :meth:`close` waits for the outbound queue to drain (and for the transport to close
            before it is aborted).
        cancellable: ``method -> bool``; handlers of methods for which it is true (and every streaming handler) are
            really cancelled on ``notifications/cancelled`` / disconnect; all others are detached (see above).
        drain_timeout: seconds :meth:`close` waits for detached handlers to finish; survivors are logged, never
            cancelled.
        subscription_queue_size: server-side bound of the per-subscription queue (BHMS-LIF-043).
        registry: dict shared by the sessions of one server to track detached handler tasks (default: private).
    """

    def __init__(self, transport: Transport, *, role: str, handler: Handler | None = None,
                 max_message_bytes: int | None = None, outbound_queue_size: int = 256,
                 default_timeout: float | None = 30.0, max_inflight_requests: int = 16384,
                 stream_queue_size: int = 1024, flush_timeout: float = 5.0,
                 cancellable: Callable[[str], bool] | None = None, drain_timeout: float = 10.0,
                 subscription_queue_size: int = 1024,
                 registry: dict[asyncio.Task[None], RequestContext] | None = None) -> None:
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
        self._cancellable = cancellable
        self.drain_timeout = drain_timeout
        self._subscription_queue_size = subscription_queue_size
        self._ctx: dict[str | int, RequestContext] = {}
        self._detached: set[asyncio.Task[None]] = set()
        self._outbox: asyncio.Queue[bytes] = asyncio.Queue(outbound_queue_size)
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._streams: dict[int, ClientStream] = {}
        self._handlers: dict[str | int, asyncio.Task[None]] = {}
        self._next_id = 0
        self._reader: asyncio.Task[None] | None = None
        self._writer: asyncio.Task[None] | None = None
        self._background: set[asyncio.Task[Any]] = set()
        self._closing = False
        self._close_task: asyncio.Future[None] | None = None
        self._registry = registry if registry is not None else {}
        self._closed = asyncio.Event()
        self._torn_down = asyncio.Event()  # set when _teardown has finished: transport closed, I/O tasks ended

    # ------------------------------------------------------------------ lifecycle

    @property
    def peer(self) -> Peer:
        return self._transport.peer

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    @property
    def detached(self) -> int:
        """Handlers abandoned by the client or a disconnect that are still running (server role)."""
        return len(self._detached)

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
        """Graceful shutdown: abandon in-flight requests, flush queued output, close the transport, then wait up to
        ``drain_timeout`` for detached handlers. Idempotent; concurrent and repeated calls (also after the peer already
        disconnected) all wait for the same drain. Worst-case duration: flush_timeout + transport close + drain_timeout."""
        if self._close_task is None:
            self._close_task = asyncio.ensure_future(self._do_close())
        await asyncio.shield(self._close_task)

    async def _do_close(self) -> None:
        """One shared shutdown for every ``close()`` caller; also drains after a peer-initiated teardown."""
        self._closing = True
        await self._abandon_handlers()
        if not self._closed.is_set():
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._outbox.join(), self._flush_timeout)
            await self._teardown(TransportClosed("session closed"))
        else:  # the peer or an I/O failure started the teardown: it may still be closing the transport
            await self._torn_down.wait()
        await self.drain(self.drain_timeout)

    async def drain(self, timeout: float) -> None:
        """Wait up to ``timeout`` s for detached handlers; log (never cancel) those still running (BHMS-TRN-005)."""
        tasks = {t for t in self._detached if t is not asyncio.current_task()}
        if not tasks:
            return
        _, running = await asyncio.wait(tasks, timeout=timeout)
        for task in running:
            ctx = self._registry.get(task)
            log.warning("handler for %s (request %r) still running %.1f s after its request was abandoned; left "
                        "detached because it may be physical work", ctx.method if ctx else "?",
                        ctx.id if ctx else "?", timeout)

    async def __aenter__(self) -> Session:
        return self if self._reader is not None else self.start()

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                        tb: TracebackType | None) -> None:
        await self.close()

    def _abandon(self, request_id: str | int) -> asyncio.Task[None] | None:
        """Abandon one request: drop its response; cancel the task only if it is cancellable, else detach it.

        BHMS-LIF-050 / BHMS-TRN-005: cancelling a request or closing the connection must not cancel physical work.
        Returns the task when it was cancelled (so callers may await it).
        """
        task = self._handlers.get(request_id)
        ctx = self._ctx.get(request_id)
        if task is None or ctx is None:
            return None
        ctx.cancelled.set()
        if ctx.cancellable:
            task.cancel()
            return task
        del self._handlers[request_id], self._ctx[request_id]
        self._detached.add(task)
        self._registry[task] = ctx
        task.add_done_callback(self._forget)
        return None

    def _forget(self, task: asyncio.Task[None]) -> None:
        self._detached.discard(task)
        self._registry.pop(task, None)

    async def _abandon_handlers(self) -> None:
        cancelled = [t for t in (self._abandon(i) for i in list(self._handlers)) if t is not None]
        cancelled = [t for t in cancelled if t is not asyncio.current_task()]
        if cancelled:
            await asyncio.gather(*cancelled, return_exceptions=True)

    async def _teardown(self, reason: TransportClosed) -> None:
        if self._closed.is_set():
            return
        self._closing = True
        self._closed.set()  # first, so concurrent callers and late enqueues see it
        try:
            current = asyncio.current_task()
            io_tasks = [task for task in (self._reader, self._writer) if task is not None and task is not current]
            for task in io_tasks:
                task.cancel()
            await self._abandon_handlers()
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(reason)
            self._pending.clear()
            for stream in list(self._streams.values()):
                stream._finish("error", reason)
            self._streams.clear()
            while not self._outbox.empty():  # wakes blocked producers and lets join() return
                self._outbox.get_nowait()
                self._outbox.task_done()
            try:
                await asyncio.wait_for(self._transport.close(), self._flush_timeout)
            except asyncio.TimeoutError:
                log.warning("transport did not close within %.1f s (peer not reading?); aborting", self._flush_timeout)
                self._transport.abort()
            for task in list(self._background):
                task.cancel()
            # The reader and writer end here, not at some later turn of the loop: a caller that returns from close() and
            # stops its loop must not leave them pending ("Task was destroyed but it is pending").
            if io_tasks:
                await asyncio.gather(*io_tasks, return_exceptions=True)
        finally:
            self._torn_down.set()  # close() callers that found the teardown under way wait for this

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

    async def flushed(self) -> None:
        """Return when every message queued so far has been handed to the transport."""
        await self._outbox.join()

    async def request(self, method: str, params: Any, *, timeout: float | None = None,
                      queued: asyncio.Event | None = None) -> dict[str, Any]:
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
                if queued is not None:
                    queued.set()  # the request is in the outbox: :meth:`flushed` now covers it
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
                if _valid_id(target):
                    self._abandon(target)
            return
        meta = params.get("_meta") if isinstance(params, dict) else None
        sub = meta.get(SUBSCRIPTION_KEY) if isinstance(meta, dict) else None
        stream = self._streams.get(sub) if isinstance(sub, int) else None
        if stream is None:
            log.debug("dropping notification %s outside any stream", method)
            return
        stream._push({"method": method, "params": params})  # never blocks the read loop

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
        if len(self._handlers) + len(self._detached) >= self._max_inflight:
            busy = BhmsError("BUSY", "too many requests in flight on this connection",
                             bound=self._max_inflight, hint="retry with backoff, or wait for responses first")
            await self._enqueue(orjson.dumps({"jsonrpc": "2.0", "id": request_id, "error": busy.to_jsonrpc()}))
            return
        ctx = RequestContext(request_id, method, msg.get("params"), self.peer, self,
                             cancellable=bool(self._cancellable and self._cancellable(method)))
        task = asyncio.create_task(self._run_request(ctx))
        self._handlers[request_id] = task
        self._ctx[request_id] = ctx

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
        self._streams.pop(stream.id, None)
        stream._finish(kind, payload)

    # ------------------------------------------------------------------ server request execution

    async def _run_request(self, ctx: RequestContext) -> None:
        me = asyncio.current_task()
        try:
            if self._handler is None:
                raise JsonRpcError(METHOD_NOT_FOUND, f"Method not found: {ctx.method}")
            outcome = await self._handler(ctx)
            is_stream = hasattr(outcome, "__aiter__")
            if ctx.cancelled.is_set():  # abandoned while it ran: the response is dropped (BHMS-LIF-051)
                if is_stream:
                    await outcome.aclose()
                return
            if is_stream:
                ctx.cancellable = True  # streams are cancelled for real; no physical work hangs off a listen
                await self._pump_stream(ctx, outcome)
            else:
                await self._respond(ctx.id, outcome)
        except asyncio.CancelledError:
            pass  # only cancellable handlers and streams get here; nothing is sent (BHMS-LIF-051)
        except TransportClosed:
            pass
        except Exception as exc:  # noqa: BLE001 - every handler failure becomes a JSON-RPC error
            if ctx.cancelled.is_set():
                log.error("handler for %s failed after its request was abandoned", ctx.method, exc_info=exc)
            else:
                with contextlib.suppress(TransportClosed):
                    await self._send_error(ctx.id, exc)
        finally:
            if self._handlers.get(ctx.id) is me:
                del self._handlers[ctx.id]
                self._ctx.pop(ctx.id, None)

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

    def _encode_notification(self, ctx: RequestContext, item: Any) -> tuple[bool, bytes]:
        if not isinstance(item, Notification):
            raise TypeError(f"stream handler yielded {type(item).__name__}; expected Notification or Complete")
        params = dict(item.params)
        meta = params.get("_meta")
        params["_meta"] = {**(meta if isinstance(meta, dict) else {}), SUBSCRIPTION_KEY: ctx.id}
        try:
            data = self._encode({"jsonrpc": "2.0", "method": item.method, "params": params})
        except _TooLarge as exc:
            log.error("notification of %d bytes exceeds the %d byte limit", exc.size, exc.limit)
            raise _internal_error() from None
        return item.method == OBSERVATION, data

    async def _pump_stream(self, ctx: RequestContext, stream: AsyncIterator[Any]) -> None:
        """Send a streaming handler's notifications, then its result; tag both with the subscription id.

        BHMS-LIF-043: the handler is drained by a producer task into a bounded per-subscription queue, so a slow peer
        never blocks it (nor, through the shared outbox, other requests' responses for long). When the queue is full the
        oldest ``notifications/observation`` is dropped; if it holds nothing droppable the subscription ends with
        ``endReason: "overflow"`` after the queued messages (terminal operation notifications are never dropped).
        """
        queue: deque[tuple[bool, bytes]] = deque()
        wake = asyncio.Event()
        state: dict[str, Any] = {"done": False, "final": {"resultType": "complete"}, "error": None}

        async def produce() -> None:
            try:
                async for item in stream:
                    if isinstance(item, Complete):
                        state["final"] = item.result
                        return
                    queue.append(self._encode_notification(ctx, item))
                    if len(queue) > self._subscription_queue_size:
                        for index, (is_observation, _) in enumerate(queue):
                            if is_observation:
                                del queue[index]
                                break
                        else:
                            state["final"] = {"resultType": "complete", "endReason": "overflow"}
                            return
                    wake.set()
                    await asyncio.sleep(0)  # a generator that never awaits must not starve the loop
            except Exception as exc:  # noqa: BLE001 - reported to the client after the queue drains
                state["error"] = exc
            finally:
                state["done"] = True
                wake.set()
                aclose = getattr(stream, "aclose", None)
                if aclose is not None:
                    await aclose()

        producer = asyncio.create_task(produce())
        try:
            while True:
                while queue:
                    await self._enqueue(queue.popleft()[1])
                if state["done"]:
                    break
                wake.clear()
                await wake.wait()
        finally:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)
        if state["error"] is not None:
            raise state["error"]
        final = state["final"]
        meta = final.get("_meta")
        final = {"resultType": "complete", **final,
                 "_meta": {**(meta if isinstance(meta, dict) else {}), SUBSCRIPTION_KEY: ctx.id}}
        await self._respond(ctx.id, final)


async def drain_detached(registry: dict[asyncio.Task[None], RequestContext], timeout: float) -> None:
    """Wait up to ``timeout`` s for the detached handlers in ``registry`` (one server's); log survivors, never cancel."""
    tasks = {task for task in registry if not task.done()}
    if not tasks:
        return
    _, running = await asyncio.wait(tasks, timeout=timeout)
    for task in running:
        ctx = registry.get(task)
        log.warning("handler for %s (request %r) is still running after the %.1f s drain; left detached",
                    ctx.method if ctx else "?", ctx.id if ctx else "?", timeout)


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
