"""Method routing for a BHMS server: :class:`Server` turns a :class:`~bhms.jsonrpc.session.Session` into a protocol endpoint.

``Server`` is deliberately small. It owns what every BHMS server must do identically
(spec/bhms/03-lifecycle.md) and nothing about devices:

* routes ``method`` to a registered handler; unknown methods get ``-32601`` (BHMS-LIF-013);
* requires ``params`` to be an object whose ``_meta`` carries ``bhms/protocolVersion`` (BHMS-LIF-011) and answers
  ``UNSUPPORTED_VERSION`` with the supported list as ``bound`` (BHMS-LIF-019);
* answers a method whose capability is not advertised with ``UNSUPPORTED`` naming it (BHMS-LIF-013);
* validates ``params`` against the pydantic model of the method (closed objects, BHMS-LIF-015) and maps failures to
  ``INVALID_ARGUMENT`` naming the member; ``strict=True`` additionally runs full JSON Schema validation of every
  request and result (the conformance mode; off by default for speed);
* serialises results (models or dicts) and adds ``resultType: "complete"``;
* implements ``server/discover`` from its configuration unless a handler is registered for it.

Handlers are ``async def handler(params, ctx) -> result``. For a BHMS method ``params`` is the validated pydantic params
model and the result may be the result model or a dict; for an extension method (``<prefix>/<name>/<method>`` or
``x-<name>/<method>``, BHMS-LIF-070) ``params`` is the raw dict. A handler for ``subscriptions/listen`` may return an
async iterator yielding :class:`~bhms.jsonrpc.session.Notification` and finally :class:`~bhms.jsonrpc.session.Complete`
(params/results may be models). Task 4's ``DeviceServer`` builds on this class.

Cancellation: see :meth:`Server.register`; ``close`` awaits detached handlers up to ``drain_timeout`` and logs survivors.

Thread-safety: single event loop; register handlers before serving.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from bhms.jsonrpc.session import (METHOD_NOT_FOUND, Complete, JsonRpcError, Notification, RequestContext, Session,
                                    drain_detached)
from bhms.protocol import schema
from bhms.protocol.errors import BhmsError
from bhms.protocol.types import METHODS, to_wire
from bhms.protocol.version import PROTOCOL_VERSION
from bhms.transport.base import Peer, Transport

log = logging.getLogger("bhms.jsonrpc")

META_VERSION_FIELD = "_meta.bhms/protocolVersion"
_EXTENSION_NAME = re.compile(r"^(?!bhms/)(?:[a-z0-9][a-z0-9.-]*/[^/\s]+/[^/\s]+|x-[a-z0-9-]+/[^/\s]+)$")

MethodHandler = Callable[[Any, RequestContext], Awaitable[Any]]
PrincipalResolver = Callable[[Peer], dict[str, Any] | None]


def _version_error(supported: tuple[str, ...]) -> BhmsError:
    return BhmsError("UNSUPPORTED_VERSION", "the requested protocol version is not served", field=META_VERSION_FIELD,
                     bound=list(supported),
                     hint=f"retry with one of {', '.join(supported)} in _meta[\"bhms/protocolVersion\"]")


def _meta_error(field: str, text: str) -> BhmsError:
    return BhmsError("INVALID_ARGUMENT", text, field=field,
                     hint='send params._meta = {"bhms/protocolVersion": "' + PROTOCOL_VERSION + '"} on every request '
                          "(BHMS-LIF-011)")


class Server:
    """Routes BHMS requests to handlers; see the module docstring.

    Args:
        server_info: ``Implementation`` (``{"name", "version", "title"?}``) reported by ``server/discover``.
        capabilities: ``ServerCapabilities`` object; ``operations``, ``stop`` and ``subscriptions`` are added with
            defaults when missing (BHMS-LIF-023).
        epoch: identity of the durable state (BHMS-OPS-034).
        supported_versions: versions this server serves.
        instructions: optional guidance for models (untrusted text).
        principal: ``peer -> {"id", "scopes"} | None`` resolved per ``server/discover`` request.
        max_page_size / max_wait_ms: reported in ``limits``; ``limits.maxMessageBytes`` is the connection's real limit.
        strict: full JSON Schema validation of requests and results.
    """

    def __init__(self, *, server_info: dict[str, Any], capabilities: dict[str, Any] | None = None,
                 epoch: str = "ephemeral", supported_versions: tuple[str, ...] = (PROTOCOL_VERSION,),
                 instructions: str | None = None, principal: PrincipalResolver | None = None,
                 max_page_size: int = 100, max_wait_ms: int = 30_000, strict: bool = False,
                 drain_timeout: float = 10.0) -> None:
        self.drain_timeout = drain_timeout
        self._detached: dict[asyncio.Task[None], RequestContext] = {}  # this server's detached handler tasks
        self._cancellable: set[str] = {"subscriptions/listen", "operations/wait"}
        self.server_info = server_info
        self.capabilities: dict[str, Any] = {
            "operations": {"durable": False, "cancel": True, "keyRetentionS": 0}, "stop": {},
            "subscriptions": {"maxObservations": 256, "maxOperationIds": 256}, **(capabilities or {})}
        self.epoch = epoch
        self.supported_versions = supported_versions
        self.instructions = instructions
        self.principal = principal
        self.max_page_size = max_page_size
        self.max_wait_ms = max_wait_ms
        self.strict = strict
        self._handlers: dict[str, MethodHandler] = {"server/discover": self._discover}
        self.sessions: set[Session] = set()
        self.active = 0  # requests whose handler is running now, over every connection (a stream counts until it starts)

    # ------------------------------------------------------------------ registration

    def register(self, method: str, handler: MethodHandler, *, cancellable: bool | None = None) -> None:
        """Register ``handler`` for a BHMS method or an extension method.

        Cancellation contract (BHMS-LIF-050, BHMS-TRN-005): when the client cancels the request or disconnects, the
        handler is *detached* (response dropped, ``ctx.cancelled`` set, task keeps running; ``close`` drains and logs
        it) unless ``cancellable`` is true, in which case its task is cancelled. Pure waits (``operations/wait``) and
        ``subscriptions/listen`` are cancellable by default; anything that may start physical work must not be.
        """
        if method not in METHODS and not _EXTENSION_NAME.match(method):
            raise ValueError(f"{method!r} is neither a BHMS method nor a valid extension method name "
                             "(<prefix>/<name>/<method> or x-<name>/<method>, BHMS-LIF-070)")
        self._handlers[method] = handler
        if cancellable is not None:
            (self._cancellable.add if cancellable else self._cancellable.discard)(method)

    def is_cancellable(self, method: str) -> bool:
        """Whether a cancelled request for ``method`` has its task cancelled (else it is detached)."""
        return method in self._cancellable

    def method(self, name: str, *, cancellable: bool | None = None) -> Callable[[MethodHandler], MethodHandler]:
        """Decorator form of :meth:`register`."""
        def decorate(handler: MethodHandler) -> MethodHandler:
            self.register(name, handler, cancellable=cancellable)
            return handler

        return decorate

    def advertises(self, capability: str) -> bool:
        """Whether ``capability`` (``"leases"``, ``"programs.registry"``) is advertised (BHMS-LIF-020)."""
        head, _, member = capability.partition(".")
        value = self.capabilities.get(head)
        if value is None:
            return False
        if not member:
            return True
        return bool(value.get(member)) if isinstance(value, dict) else False

    @property
    def quiet(self) -> bool:
        """At most one request is being handled (the caller's own): a durable write may sync on the event loop thread
        instead of sharing a sync (see :meth:`bhms.runtime.store.Store.wait_synced`)."""
        return self.active <= 1

    # ------------------------------------------------------------------ dispatch

    async def dispatch(self, ctx: RequestContext) -> Any:
        """The :data:`~bhms.jsonrpc.session.Handler` a session uses for this server."""
        handler = self._handlers.get(ctx.method)
        spec = METHODS.get(ctx.method)
        if handler is None:
            raise JsonRpcError(METHOD_NOT_FOUND, f"Method not found: {ctx.method}")
        params = ctx.params
        if not isinstance(params, dict):
            raise _meta_error(META_VERSION_FIELD, "params must be an object carrying _meta.bhms/protocolVersion")
        meta = params.get("_meta")
        if not isinstance(meta, dict) or "bhms/protocolVersion" not in meta:
            raise _meta_error(META_VERSION_FIELD, "missing _meta.bhms/protocolVersion")
        version = meta["bhms/protocolVersion"]
        if version not in self.supported_versions:  # also catches non-string versions
            raise _version_error(self.supported_versions)
        argument: Any = params
        if spec is not None:
            if spec.capability is not None and not self.advertises(spec.capability):
                raise BhmsError("UNSUPPORTED", f"{ctx.method} needs the {spec.capability!r} capability, which this "
                                "server does not advertise", field=None,
                                hint=f"check server/discover capabilities.{spec.capability} before calling {ctx.method}")
            if self.strict:
                schema.validate(spec.params.__name__, params)
            try:
                argument = spec.params.model_validate(params)
            except ValidationError as exc:
                raise schema.from_pydantic_error(exc) from None
        self.active += 1
        try:
            outcome = await handler(argument, ctx)
        finally:
            self.active -= 1
        if hasattr(outcome, "__aiter__"):
            return _wire_stream(outcome)
        return self._finish_result(spec, outcome)

    def _finish_result(self, spec: Any, outcome: Any) -> dict[str, Any]:
        result = to_wire(outcome) if isinstance(outcome, BaseModel) else outcome
        if not isinstance(result, dict):
            raise TypeError(f"handler returned {type(result).__name__}; a result object is required")
        if "resultType" not in result:
            result = {"resultType": "complete", **result}
        if self.strict and spec is not None:
            schema.validate(spec.result.__name__, result)
        return result

    async def _discover(self, params: Any, ctx: RequestContext) -> dict[str, Any]:
        result: dict[str, Any] = {
            "resultType": "complete", "supportedVersions": list(self.supported_versions),
            "serverInfo": self.server_info, "capabilities": self.capabilities, "epoch": self.epoch,
            "limits": {"maxMessageBytes": ctx.session.max_message_bytes, "maxPageSize": self.max_page_size,
                       "maxWaitMs": self.max_wait_ms}}
        if self.instructions:
            result["instructions"] = self.instructions
        principal = self.principal(ctx.peer) if self.principal is not None else None
        if principal is not None:
            result["principal"] = principal
        return result

    # ------------------------------------------------------------------ serving

    def session_for(self, transport: Transport, **session_kw: Any) -> Session:
        """A started server session for ``transport`` (not tracked in :attr:`sessions`)."""
        session_kw.setdefault("cancellable", self.is_cancellable)
        session_kw.setdefault("drain_timeout", self.drain_timeout)
        session_kw.setdefault("registry", self._detached)
        return Session(transport, role="server", handler=self.dispatch, **session_kw).start()

    async def handle_connection(self, transport: Transport, **session_kw: Any) -> None:
        """Serve one connection until it ends; pass as ``on_transport`` to ``serve_unix``/``serve_tcp``/..."""
        session = self.session_for(transport, **session_kw)
        self.sessions.add(session)
        try:
            await session.wait_closed()
        finally:
            self.sessions.discard(session)
            await session.close()

    async def serve_stdio(self, **session_kw: Any) -> None:
        """Serve this process's stdin/stdout until the parent closes it (BHMS-TRN-011)."""
        from bhms.transport.stdio import stdio_server_transport

        await self.handle_connection(await stdio_server_transport(), **session_kw)

    async def close(self) -> None:
        """Close every live connection (in-flight requests are abandoned, BHMS-TRN-005)."""
        await asyncio.gather(*(s.close() for s in list(self.sessions)))
        await drain_detached(self._detached, self.drain_timeout)  # handlers detached by connections that already dropped


async def _wire_stream(stream: AsyncIterator[Any]) -> AsyncIterator[Notification | Complete]:
    """Serialise models yielded by a streaming handler; closes the inner iterator on cancellation."""
    try:
        async for item in stream:
            if isinstance(item, Notification) and isinstance(item.params, BaseModel):
                item = Notification(item.method, to_wire(item.params))
            elif isinstance(item, Complete) and isinstance(item.result, BaseModel):
                item = Complete(to_wire(item.result))
            yield item
    finally:
        aclose = getattr(stream, "aclose", None)
        if aclose is not None:
            await aclose()
