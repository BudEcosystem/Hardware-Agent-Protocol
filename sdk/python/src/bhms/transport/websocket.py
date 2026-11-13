"""WebSocket binding (spec/bhms/02-transports.md §2.3): one message per text frame, subprotocol ``bhms``.

A message larger than ``max_message_bytes`` makes the ``websockets`` library close the
connection with code 1009 (message too big); unlike the byte-stream bindings the session cannot
survive it, because the protocol offers no way to resynchronise inside a frame.
"""

from __future__ import annotations

import ssl as ssl_module
from collections.abc import Callable
from http import HTTPStatus
from typing import Any

from websockets.asyncio.client import connect as _ws_connect
from websockets.asyncio.server import serve as _ws_serve
from websockets.exceptions import ConnectionClosed, WebSocketException

from bhms.transport.base import (DEFAULT_MAX_MESSAGE_BYTES, FrameTooLarge, Peer, Transport, TransportClosed,
                                 check_message_limit)
from bhms.transport.stream import Listener, OnTransport, is_loopback

SUBPROTOCOL = "bhms"


class WebSocketTransport(Transport):
    """A :class:`Transport` over a ``websockets`` connection (client or server side)."""

    def __init__(self, connection: Any, peer: Peer, max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> None:
        self.peer = peer
        self.max_message_bytes = check_message_limit(max_message_bytes)
        self._ws = connection
        self._closed = False

    async def send(self, data: bytes) -> None:
        if self._closed:
            raise TransportClosed("transport is closed")
        try:
            await self._ws.send(data.decode("utf-8"))
        except ConnectionClosed as exc:
            raise TransportClosed(str(exc)) from exc

    async def receive(self) -> bytes:
        if self._closed:
            raise TransportClosed("transport is closed")
        try:
            frame = await self._ws.recv()
        except ConnectionClosed as exc:
            raise TransportClosed(str(exc)) from exc
        if isinstance(frame, str):
            data = frame.encode("utf-8")
            if len(data) > self.max_message_bytes:
                raise FrameTooLarge(self.max_message_bytes)
            return data
        await self._ws.close(1003, "BHMS uses text frames only (BHMS-TRN-030)")
        raise TransportClosed("binary frame received")

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._ws.close()
        except (WebSocketException, OSError):
            pass


def _bearer(header: str | None) -> str | None:
    if header and header[:7].lower() == "bearer ":
        return header[7:].strip() or None
    return None


async def serve_websocket(host: str, port: int, on_transport: OnTransport, *,
                          authenticate: Callable[[str | None], bool] | None = None,
                          ssl: ssl_module.SSLContext | None = None,
                          max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> Listener:
    """Listen for WebSocket clients speaking subprotocol ``bhms``.

    ``authenticate(token)`` receives the ``Authorization: Bearer`` token (or None) and returns
    whether to accept; a refusal answers HTTP 401 (BHMS-TRN-031). A listener reachable from beyond
    loopback must supply it. The token is surfaced on ``transport.peer.token``; authorization
    decisions remain the caller's.
    """
    check_message_limit(max_message_bytes)
    if not is_loopback(host) and authenticate is None:
        raise ValueError(f"refusing to listen on {host!r} without authenticate=: a WebSocket server reachable "
                         "beyond loopback must require a bearer token (BHMS-TRN-031)")

    def process_request(connection: Any, request: Any) -> Any:
        offered = [p.strip() for v in request.headers.get_all("Sec-WebSocket-Protocol") for p in v.split(",")]
        if SUBPROTOCOL not in offered:
            return connection.respond(HTTPStatus.BAD_REQUEST, f"subprotocol {SUBPROTOCOL!r} is required\n")
        token = _bearer(request.headers.get("Authorization"))
        if authenticate is not None and not authenticate(token):
            response = connection.respond(HTTPStatus.UNAUTHORIZED, "missing or invalid bearer token\n")
            response.headers["WWW-Authenticate"] = "Bearer"
            return response
        connection.bhms_token = token
        return None

    async def handler(connection: Any) -> None:
        remote = connection.remote_address
        address = f"{remote[0]}:{remote[1]}" if isinstance(remote, tuple) and len(remote) >= 2 else None
        transport = WebSocketTransport(
            connection, Peer("ws", address=address, token=getattr(connection, "bhms_token", None)),
            max_message_bytes)
        try:
            await on_transport(transport)
        finally:
            await transport.close()

    server = await _ws_serve(handler, host, port, subprotocols=[SUBPROTOCOL], process_request=process_request,
                             max_size=max_message_bytes, compression=None, ssl=ssl)
    sockname = server.sockets[0].getsockname()
    return Listener(server, (sockname[0], sockname[1]))


async def connect_websocket(url: str, *, token: str | None = None, ssl: ssl_module.SSLContext | None = None,
                            max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> WebSocketTransport:
    """Connect to ``ws://`` / ``wss://`` offering subprotocol ``bhms`` and an optional bearer token."""
    check_message_limit(max_message_bytes)
    headers = {"Authorization": f"Bearer {token}"} if token else None
    connection = await _ws_connect(url, subprotocols=[SUBPROTOCOL], additional_headers=headers,
                                   max_size=max_message_bytes, compression=None, ssl=ssl)
    if connection.subprotocol != SUBPROTOCOL:
        await connection.close()
        raise TransportClosed(f"server did not negotiate subprotocol {SUBPROTOCOL!r} (BHMS-TRN-030)")
    remote = connection.remote_address
    address = f"{remote[0]}:{remote[1]}" if isinstance(remote, tuple) and len(remote) >= 2 else url
    return WebSocketTransport(connection, Peer("ws", address=address), max_message_bytes)
