"""BHMS client: connect, discover, typed methods for every protocol method, and subscriptions.

``Client.connect("unix:/run/bhms.sock")`` opens a transport, performs ``server/discover`` (there is no
handshake; BHMS-LIF-022), selects a protocol version (retrying once on ``UNSUPPORTED_VERSION``, BHMS-LIF-019) and
from then on injects ``params._meta`` (``bhms/protocolVersion`` and ``bhms/clientInfo``) into every request. Every
method of ``spec/bhms/schema/bhms.schema.json`` ``x-bhms-methods`` has a typed coroutine that returns the pydantic
result model from :mod:`bhms.protocol.types`; ``subscribe`` returns an async-iterator :class:`Subscription`.

URL forms for :meth:`Client.connect`: ``stdio:<command>``, ``unix:<path>``, ``tcp://host:port``, ``ws://host:port/...``
(``wss://`` too), ``http://host:port/bhms`` (Streamable HTTP; needs ``pip install 'bhms[http]'``).

Errors: error responses raise :class:`~bhms.protocol.errors.BhmsError` (or ``JsonRpcError`` for plain JSON-RPC errors);
a request that times out raises ``BhmsError(DEADLINE_EXCEEDED)`` with ``may_have_acted=True``: the outcome is unknown, so
use ``operations_get`` or retry with the same ``operationKey`` (BHMS-LIF-053); a dropped connection raises
``TransportClosed``.

Example::

    async with await Client.connect("unix:/tmp/bhms.sock") as client:
        listing = await client.devices_list()
        op = await client.actions_invoke(device_id="pump-1", action="dispense", arguments={"volume": 5},
                                         operation_key="k-1", wait_ms=2000)

Thread-safety: one event loop; methods may be awaited concurrently (requests are multiplexed on one connection).
"""

from __future__ import annotations

import logging
import ssl as ssl_module
from collections.abc import AsyncIterator
from dataclasses import dataclass
from types import TracebackType
from typing import Any

from pydantic import BaseModel, ValidationError
from pydantic.alias_generators import to_camel

from bhms.jsonrpc.session import ClientStream, Session
from bhms.protocol import schema
from bhms.protocol import types as t
from bhms.protocol.errors import BhmsError
from bhms.protocol.types import METHODS, NOTIFICATIONS, to_wire
from bhms.protocol.version import SUPPORTED_VERSIONS, is_v0_1
from bhms.transport.base import DEFAULT_MAX_MESSAGE_BYTES, Transport

log = logging.getLogger("bhms.client")

DEFAULT_CLIENT_INFO: dict[str, str] = {"name": "bhms-python", "version": "0.1.0"}

METHOD_ATTRS: dict[str, str] = {m: m.replace("/", "_") for m in METHODS} | {
    "server/discover": "discover", "subscriptions/listen": "subscribe", "stop": "stop"}
"""Protocol method name -> the :class:`Client` coroutine that exposes it (asserted complete by a test)."""


async def open_transport(target: str, *, token: str | None = None,
                         max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> Transport:
    """Open a transport from ``stdio:<command>``, ``unix:<path>``, ``tcp://host:port`` or ``ws[s]://...``."""
    from bhms.transport import connect_tcp, connect_unix, connect_websocket, spawn_stdio

    if target.startswith("stdio:"):
        return await spawn_stdio(target[len("stdio:"):].strip(), max_message_bytes=max_message_bytes)
    if target.startswith("unix:"):
        path = target[len("unix:"):]
        if path.startswith("//"):
            path = path[2:]
        return await connect_unix(path, max_message_bytes=max_message_bytes)
    if target.startswith(("tcp://", "tcps://")):
        scheme = target.split("://", 1)[0]
        host, sep, port = target[len(scheme) + 3:].rstrip("/").rpartition(":")
        if not sep or not port.isdigit() or not host:
            raise ValueError(f"bad {scheme} target {target!r}; expected {scheme}://host:port")
        context = ssl_module.create_default_context() if scheme == "tcps" else None  # a scheme is a promise (BHMS-SEC-007)
        return await connect_tcp(host.strip("[]"), int(port), ssl=context, max_message_bytes=max_message_bytes)
    if target.startswith(("ws://", "wss://")):
        return await connect_websocket(target, token=token, max_message_bytes=max_message_bytes)
    if target.startswith(("http://", "https://")):
        from bhms.transport.http import connect_http  # needs the optional aiohttp dependency

        return await connect_http(target, token=token, max_message_bytes=max_message_bytes)
    raise ValueError(f"unsupported target {target!r}; use stdio:<command>, unix:<path>, tcp://host:port, ws://host:port "
                     "or http://host:port/bhms")


@dataclass(frozen=True, slots=True)
class ReceivedNotification:
    """A notification delivered on a subscription, with ``params`` parsed into its model when the method is known."""

    method: str
    params: Any


class Subscription:
    """An open ``subscriptions/listen`` stream: ``async for`` yields :class:`ReceivedNotification`.

    ``acknowledged`` is the server's first message (honoured filter and ``refused`` parts, BHMS-LIF-040). Iteration ends
    when the server ends the subscription; then ``end_reason`` and ``result`` are set (BHMS-LIF-044). Leaving ``async with``
    or calling :meth:`cancel` cancels it. After a connection drop re-subscribe with ``events.after`` (BHMS-LIF-045).
    """

    def __init__(self, stream: ClientStream, acknowledged: t.SubscriptionsAcknowledgedNotificationParams) -> None:
        self._stream = stream
        self.acknowledged = acknowledged
        self.result: t.SubscriptionsListenResult | None = None

    @property
    def id(self) -> int:
        return self._stream.id

    @property
    def end_reason(self) -> str | None:
        return self.result.end_reason if self.result is not None else None

    def __aiter__(self) -> Subscription:
        return self

    async def __anext__(self) -> ReceivedNotification:
        try:
            raw = await self._stream.__anext__()
        except StopAsyncIteration:
            if self._stream.result is not None:
                self.result = _parse_result(t.SubscriptionsListenResult, self._stream.result, "subscriptions/listen")
            raise
        return _parse_notification(raw)

    async def cancel(self, reason: str | None = None) -> None:
        await self._stream.cancel(reason)

    async def __aenter__(self) -> Subscription:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                        tb: TracebackType | None) -> None:
        await self.cancel()


def _parse_notification(raw: dict[str, Any]) -> ReceivedNotification:
    method, params = raw["method"], raw["params"]
    spec = NOTIFICATIONS.get(method)
    if spec is None or spec.direction != "server-to-client":
        return ReceivedNotification(method, params)
    try:
        return ReceivedNotification(method, spec.params.model_validate(params))
    except ValidationError as exc:
        raise BhmsError("INTERNAL", f"malformed {method} notification from the server: {exc.errors()[0]['msg']}",
                        may_have_acted=False, hint="this is a server bug; report it with the notification") from None


def _parse_result(model: type[Any], result: dict[str, Any], method: str) -> Any:
    try:
        return model.model_validate(result)
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        raise BhmsError("INTERNAL", f"malformed {method} result from the server at "
                        f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}"[:2000], may_have_acted=True,
                        hint="the server broke the protocol (BHMS-LIF-012); the request may have taken effect, "
                             "reconcile with operations/get") from None


_NO_RESULT: Any = object()
"""``operations_resolve``: no ``result`` was given (``None`` is a possible result)."""


def _wire_params(**kwargs: Any) -> dict[str, Any]:
    """snake_case keyword arguments -> camelCase wire members, models serialised, ``None`` omitted."""
    return {to_camel(k): to_wire(v) if isinstance(v, (BaseModel, list, dict)) else v
            for k, v in kwargs.items() if v is not None}


class Client:
    """Typed BHMS client over one :class:`~bhms.jsonrpc.session.Session`; see the module docstring."""

    def __init__(self, session: Session, *, client_info: dict[str, Any] | None = None, strict: bool = False,
                 versions: tuple[str, ...] = SUPPORTED_VERSIONS, credential: str | None = None) -> None:
        self.session = session
        self._credential = credential
        """Bearer token sent in ``_meta["bhms/authorization"]`` on transports without a credential header (TCP, BHMS-SEC-005);
        never logged or shown."""
        self.client_info = client_info or DEFAULT_CLIENT_INFO
        self.strict = strict
        self._versions = versions
        self.version: str = versions[0]
        self.server: t.DiscoverResult | None = None

    # ------------------------------------------------------------------ connect

    @classmethod
    async def connect(cls, target: str, *, token: str | None = None, client_info: dict[str, Any] | None = None,
                      timeout: float | None = 30.0, strict: bool = False,
                      max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> Client:
        """Open ``target``, run ``server/discover`` and return a ready client (closes the transport on failure)."""
        transport = await open_transport(target, token=token, max_message_bytes=max_message_bytes)
        carried = token if target.startswith(("tcp://", "tcps://")) else None  # TCP has no header: the carrier
        return await cls.from_transport(transport, client_info=client_info, timeout=timeout, strict=strict, credential=carried)

    @classmethod
    async def from_transport(cls, transport: Transport, *, client_info: dict[str, Any] | None = None,
                             timeout: float | None = 30.0, strict: bool = False,
                             versions: tuple[str, ...] = SUPPORTED_VERSIONS, credential: str | None = None) -> Client:
        """Build a client on an already-open transport and perform discovery. ``credential``: a bearer token every request
        carries in ``_meta["bhms/authorization"]`` (transports without a credential header, BHMS-SEC-005)."""
        session = Session(transport, role="client", default_timeout=timeout).start()
        client = cls(session, client_info=client_info, strict=strict, versions=versions, credential=credential)
        try:
            await client.discover()
        except BaseException:
            await session.close()
            raise
        return client

    async def discover(self, *, timeout: float | None = None) -> t.DiscoverResult:
        """``server/discover``; selects the protocol version and the outgoing message limit."""
        try:
            result = await self._call("server/discover", timeout=timeout)
        except BhmsError as exc:
            if exc.bhms_code != "UNSUPPORTED_VERSION" or not isinstance(exc.bound, list):
                raise
            common = [v for v in self._versions if v in exc.bound]
            if not common:
                raise BhmsError("UNSUPPORTED_VERSION", f"no common protocol version: client speaks "
                                f"{list(self._versions)}, server serves {exc.bound}", field=exc.field, bound=exc.bound,
                                hint="upgrade the client or the server so that they share a version") from None
            self.version = common[0]
            result = await self._call("server/discover", timeout=timeout)
        self.server = result
        self.session.max_message_bytes = min(self.session.max_message_bytes, result.limits.max_message_bytes)
        return result

    async def close(self) -> None:
        """Close the connection (BHMS-TRN-005: nothing durable is cancelled)."""
        await self.session.close()

    async def __aenter__(self) -> Client:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                        tb: TracebackType | None) -> None:
        await self.close()

    # ------------------------------------------------------------------ plumbing

    def _meta(self) -> dict[str, Any]:
        meta = {"bhms/protocolVersion": self.version, "bhms/clientInfo": self.client_info}
        if self._credential and not is_v0_1(self.version):  # a v0.1 server knows no bhms/authorization (BHMS-LIF-016)
            meta["bhms/authorization"] = f"Bearer {self._credential}"
        return meta

    def _params(self, method: str, wire: dict[str, Any]) -> dict[str, Any]:
        params = {"_meta": self._meta(), **wire}
        spec = METHODS.get(method)
        if spec is not None:
            if self.strict:
                schema.validate(spec.params.__name__, params)
            try:
                spec.params.model_validate(params)
            except ValidationError as exc:
                raise schema.from_pydantic_error(exc) from None
        return params

    def _timeout(self, timeout: float | None, wait_ms: int | None) -> float | None:
        """A server-side wait extends the default request timeout; an explicit ``timeout`` always wins."""
        if timeout is not None or not wait_ms or self.session.default_timeout is None:
            return timeout
        return self.session.default_timeout + wait_ms / 1000

    async def request(self, method: str, params: dict[str, Any] | None = None, *,
                      timeout: float | None = None) -> dict[str, Any]:
        """Raw request for extension methods: ``_meta`` is injected; the result object is returned unparsed."""
        return await self.session.request(method, self._params(method, params or {}), timeout=timeout)

    async def _call(self, method: str, *, timeout: float | None = None, **kwargs: Any) -> Any:
        spec = METHODS[method]
        waited = kwargs.get("wait_ms") or kwargs.get("timeout_ms")
        result = await self.session.request(method, self._params(method, _wire_params(**kwargs)),
                                            timeout=self._timeout(timeout, waited))
        if self.strict:
            schema.validate(spec.result.__name__, result)
        return _parse_result(spec.result, result, method)

    async def _pages(self, method: str, member: str, **kwargs: Any) -> AsyncIterator[Any]:
        cursor: str | None = None
        while True:
            page = await self._call(method, cursor=cursor, **kwargs)
            for item in getattr(page, member):
                yield item
            cursor = page.next_cursor
            if cursor is None:
                return

    # ------------------------------------------------------------------ devices, observations

    async def devices_list(self, *, filter: t.DevicesListFilter | dict[str, Any] | None = None,
                           cursor: str | None = None, limit: int | None = None,
                           timeout: float | None = None) -> t.DevicesListResult:
        """``devices/list``: one page of device summaries."""
        return await self._call("devices/list", timeout=timeout, filter=filter, cursor=cursor, limit=limit)

    def iter_devices(self, *, filter: t.DevicesListFilter | dict[str, Any] | None = None,
                     limit: int | None = None) -> AsyncIterator[t.DeviceSummary]:
        """Every device across pages (follows ``nextCursor``, BHMS-LIF-060)."""
        return self._pages("devices/list", "devices", filter=filter, limit=limit)

    async def devices_describe(self, device_id: str, *, digest: str | None = None,
                               timeout: float | None = None) -> t.DevicesDescribeResult:
        """``devices/describe``; pass the cached ``digest`` to learn cheaply whether it is still current."""
        return await self._call("devices/describe", timeout=timeout, device_id=device_id, digest=digest)

    async def properties_read(self, device_id: str, property: str, *, max_age_ms: int | None = None,
                              fresh: bool | None = None, timeout: float | None = None) -> t.PropertiesReadResult:
        """``properties/read``: an observation with evidence, age and quality."""
        return await self._call("properties/read", timeout=timeout, device_id=device_id, property=property,
                                max_age_ms=max_age_ms, fresh=fresh)

    # ------------------------------------------------------------------ operations

    async def actions_invoke(self, device_id: str, action: str, arguments: dict[str, Any], *,
                             operation_key: str | None = None, lease_id: str | None = None,
                             deadline_ms: int | None = None, wait_ms: int | None = None,
                             require: t.Requirement | dict[str, Any] | None = None,
                             description_digest: str | None = None,
                             timeout: float | None = None) -> t.ActionsInvokeResult:
        """``actions/invoke``. On timeout the outcome is unknown: ``operations_get`` or retry with the same key."""
        return await self._call("actions/invoke", timeout=timeout, device_id=device_id, action=action,
                                arguments=arguments, operation_key=operation_key, lease_id=lease_id,
                                deadline_ms=deadline_ms, wait_ms=wait_ms, require=require, description_digest=description_digest)

    async def operations_get(self, operation_id: str, *, timeout: float | None = None) -> t.OperationsGetResult:
        """``operations/get``: the durable record of an operation."""
        return await self._call("operations/get", timeout=timeout, operation_id=operation_id)

    async def operations_wait(self, operation_id: str, timeout_ms: int, *,
                              timeout: float | None = None) -> t.OperationsWaitResult:
        """``operations/wait``: waits up to ``timeout_ms`` server-side; cancelling only stops waiting (BHMS-LIF-050)."""
        return await self._call("operations/wait", timeout=timeout, operation_id=operation_id,
                                timeout_ms=timeout_ms)

    async def operations_list(self, *, device_id: str | None = None, state: str | None = None,
                              parent_operation_id: str | None = None, cursor: str | None = None,
                              limit: int | None = None, timeout: float | None = None) -> t.OperationsListResult:
        """``operations/list``: one page, newest first."""
        return await self._call("operations/list", timeout=timeout, device_id=device_id, state=state,
                                parent_operation_id=parent_operation_id, cursor=cursor, limit=limit)

    def iter_operations(self, *, device_id: str | None = None, state: str | None = None,
                        parent_operation_id: str | None = None,
                        limit: int | None = None) -> AsyncIterator[t.Operation]:
        """Every matching operation across pages."""
        return self._pages("operations/list", "operations", device_id=device_id, state=state,
                           parent_operation_id=parent_operation_id, limit=limit)

    async def operations_cancel(self, operation_id: str, *, reason: str | None = None,
                                timeout: float | None = None) -> t.OperationsCancelResult:
        """``operations/cancel``: asks to cancel the physical work (distinct from cancelling a request)."""
        return await self._call("operations/cancel", timeout=timeout, operation_id=operation_id, reason=reason)

    async def operations_resolve(self, operation_id: str, *, resolution: t.OperatorResolution | dict[str, Any] | None = None,
                                 state: str | None = None, basis: str | None = None, effect: str | None = None,
                                 may_have_acted: bool | None = None, result: Any = _NO_RESULT,
                                 timeout: float | None = None) -> t.OperationsResolveResult:
        """``operations/resolve`` (operators; needs ``admin`` or ``operations:resolve``): resolve an ``unknown`` operation.

        With no resolution the server only asks the device again (its reconcile hook) and returns the operation, which
        may still be ``unknown``. Give the resolution as keywords, or whole as ``resolution`` (an ``OperatorResolution``
        or its wire dict), not both: ``state`` (``"completed"`` or ``"failed"``) and ``basis`` (free text: what was
        inspected, by whom, what was found) make the server record that resolution if the device still cannot say;
        device evidence always wins. ``result`` belongs to ``completed`` and must match the action's output. An
        operator's statement is a report: the recorded effect is at most ``"unverified"`` (evidence ``reported``);
        ``verified`` comes only from the device. ``may_have_acted=False`` (``failed`` only) claims proof that nothing
        happened and goes with ``effect="none"``. Check the returned operation's state and history.
        """
        given = {"state": state, "basis": basis, "effect": effect, "mayHaveActed": may_have_acted}
        stated = any(value is not None for value in given.values()) or result is not _NO_RESULT
        if stated and resolution is not None:
            raise ValueError("give the resolution either whole (resolution=) or as keywords, not both")
        if stated:
            resolution = {key: to_wire(value) if isinstance(value, (BaseModel, dict)) else value
                          for key, value in given.items() if value is not None}
            if result is not _NO_RESULT:
                resolution["result"] = result
        return await self._call("operations/resolve", timeout=timeout, operation_id=operation_id, resolution=resolution)

    async def stop(self, reason: str, *, device_ids: list[str] | None = None, scope: str | None = None,
                   wait_ms: int | None = None, timeout: float | None = None) -> t.StopResult:
        """``stop`` for ``device_ids`` or ``scope="all"``; never waits behind leases (BHMS-AUTH stop rules)."""
        return await self._call("stop", timeout=timeout, reason=reason, device_ids=device_ids,
                                scope=scope, wait_ms=wait_ms)

    # ------------------------------------------------------------------ leases (capability ``leases``)

    async def leases_acquire(self, resources: list[str], ttl_ms: int, *, wait_ms: int | None = None,
                             timeout: float | None = None) -> t.LeasesAcquireResult:
        """``leases/acquire``."""
        return await self._call("leases/acquire", timeout=timeout, resources=resources, ttl_ms=ttl_ms,
                                wait_ms=wait_ms)

    async def leases_renew(self, lease_id: str, ttl_ms: int, *, timeout: float | None = None) -> t.LeasesRenewResult:
        """``leases/renew``."""
        return await self._call("leases/renew", timeout=timeout, lease_id=lease_id, ttl_ms=ttl_ms)

    async def leases_release(self, lease_id: str, *, timeout: float | None = None) -> t.LeasesReleaseResult:
        """``leases/release``."""
        return await self._call("leases/release", timeout=timeout, lease_id=lease_id)

    # ------------------------------------------------------------------ events, programs

    async def events_read(self, *, after: str | None = None, limit: int | None = None, device_id: str | None = None,
                          types: list[str] | None = None, timeout: float | None = None) -> t.EventsReadResult:
        """``events/read`` (capability ``events``): events after a cursor, with the ``gap`` flag."""
        return await self._call("events/read", timeout=timeout, after=after, limit=limit, device_id=device_id,
                                types=types)

    async def programs_run(self, *, arguments: dict[str, Any], program: t.Program | dict[str, Any] | None = None,
                           digest: str | None = None, operation_key: str | None = None, lease_id: str | None = None,
                           deadline_ms: int | None = None, wait_ms: int | None = None,
                           timeout: float | None = None) -> t.ProgramsRunResult:
        """``programs/run`` (capability ``programs``) with an inline ``program`` or a registered ``digest``."""
        return await self._call("programs/run", timeout=timeout, program=program, digest=digest,
                                arguments=arguments, operation_key=operation_key, lease_id=lease_id,
                                deadline_ms=deadline_ms, wait_ms=wait_ms)

    async def programs_register(self, program: t.Program | dict[str, Any], *,
                                timeout: float | None = None) -> t.ProgramsRegisterResult:
        """``programs/register`` (capability ``programs.registry``)."""
        return await self._call("programs/register", timeout=timeout, program=program)

    async def programs_get(self, digest: str, *, timeout: float | None = None) -> t.ProgramsGetResult:
        """``programs/get`` (capability ``programs.registry``)."""
        return await self._call("programs/get", timeout=timeout, digest=digest)

    async def programs_list(self, *, cursor: str | None = None, limit: int | None = None,
                            timeout: float | None = None) -> t.ProgramsListResult:
        """``programs/list`` (capability ``programs.registry``): one page by digest."""
        return await self._call("programs/list", timeout=timeout, cursor=cursor, limit=limit)

    def iter_programs(self, *, limit: int | None = None) -> AsyncIterator[t.ProgramInfo]:
        """Every registered program across pages."""
        return self._pages("programs/list", "programs", limit=limit)

    # ------------------------------------------------------------------ subscriptions

    async def subscribe(self, *, devices_list_changed: bool | None = None,
                        operations: t.OperationsFilter | dict[str, Any] | None = None,
                        observations: list[Any] | None = None, events: t.EventsFilter | dict[str, Any] | None = None,
                        timeout: float | None = None) -> Subscription:
        """``subscriptions/listen``: open a stream of the requested notifications.

        Returns after the server's acknowledgement (so a refused or failing request raises here). Use
        ``async with`` / ``async for``; see :class:`Subscription`.
        """
        notifications = _wire_params(devices_list_changed=devices_list_changed, operations=operations,
                                     observations=observations, events=events)
        params = self._params("subscriptions/listen", {"notifications": notifications})
        stream = await self.session.stream("subscriptions/listen", params)
        try:
            first = await _first_message(stream, timeout if timeout is not None else self.session.default_timeout)
        except BaseException:
            await stream.cancel()
            raise
        if first["method"] != "notifications/subscriptions/acknowledged":
            await stream.cancel()
            raise BhmsError("INTERNAL", "the first message of a subscription must be notifications/subscriptions/"
                            "acknowledged (BHMS-LIF-040)", hint="server bug; report it")
        ack = _parse_notification(first).params
        return Subscription(stream, ack)


async def _first_message(stream: ClientStream, timeout: float | None) -> dict[str, Any]:
    import asyncio

    try:
        return await asyncio.wait_for(stream.__anext__(), timeout)
    except StopAsyncIteration:
        raise BhmsError("INTERNAL", "the server ended the subscription before acknowledging it",
                        hint="server bug; report it") from None
    except asyncio.TimeoutError:
        raise BhmsError("DEADLINE_EXCEEDED", "the server did not acknowledge the subscription in time",
                        may_have_acted=False, hint="retry subscriptions/listen; nothing durable was created") from None
