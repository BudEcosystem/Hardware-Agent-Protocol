"""Newline-delimited JSON over a reliable byte stream: Unix-domain sockets and TCP.

The framing is the stdio framing (BHMS-TRN-010, BHMS-TRN-020): one message per ``\\n``-terminated
line. Reading is bounded: a line longer than ``max_message_bytes`` is discarded as it arrives
(never buffered whole), reported once as :class:`~bhms.transport.base.FrameTooLarge`, and the
reader resynchronises at the next newline (BHMS-TRN-004).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import ssl as ssl_module
import stat
import struct
from collections import deque
from collections.abc import Awaitable, Callable
from ipaddress import ip_address
from typing import Any

from bhms.transport.base import (DEFAULT_MAX_MESSAGE_BYTES, FrameTooLarge, Peer, Transport, TransportClosed,
                                 check_message_limit)

_CHUNK = 262144
_OVERSIZE = None  # marker in the line queue


class LineReader:
    """Bounded newline splitter over an ``asyncio.StreamReader``."""

    def __init__(self, reader: asyncio.StreamReader, max_message_bytes: int) -> None:
        self._reader = reader
        self._max = max_message_bytes
        self._lines: deque[bytes | None] = deque()
        self._partial: list[bytes] = []
        self._partial_len = 0
        self._discarding = False

    def _feed(self, chunk: bytes) -> None:
        parts = chunk.split(b"\n")
        last = len(parts) - 1
        for index, part in enumerate(parts):
            if index < last:  # this part is newline-terminated
                if self._discarding:
                    self._discarding = False
                    self._partial.clear()
                    self._partial_len = 0
                    continue
                if self._partial_len + len(part) > self._max:
                    self._lines.append(_OVERSIZE)
                elif self._partial:
                    self._partial.append(part)
                    line = b"".join(self._partial)
                    if line.strip():
                        self._lines.append(line)
                elif part and not part.isspace():
                    self._lines.append(part)
                self._partial.clear()
                self._partial_len = 0
            elif not self._discarding and part:
                self._partial.append(part)
                self._partial_len += len(part)
                if self._partial_len > self._max:
                    self._lines.append(_OVERSIZE)
                    self._discarding = True
                    self._partial.clear()
                    self._partial_len = 0

    async def readline(self) -> bytes:
        """Next line without its newline; FrameTooLarge for an oversize line; TransportClosed at EOF."""
        while not self._lines:
            try:
                chunk = await self._reader.read(_CHUNK)
            except (ConnectionError, OSError) as exc:
                raise TransportClosed(str(exc)) from exc
            if not chunk:
                raise TransportClosed("end of stream")
            self._feed(chunk)
        line = self._lines.popleft()
        if line is _OVERSIZE:
            raise FrameTooLarge(self._max)
        assert line is not None
        return line


class StreamTransport(Transport):
    """A :class:`Transport` over an asyncio stream pair (sockets and subprocess pipes)."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, peer: Peer,
                 max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES, close_timeout: float = 2.0) -> None:
        self.peer = peer
        self.max_message_bytes = check_message_limit(max_message_bytes)
        self.close_timeout = close_timeout
        self._lines = LineReader(reader, self.max_message_bytes)
        self._writer = writer
        self._closed = False

    async def send(self, data: bytes) -> None:
        if b"\n" in data:
            raise ValueError("a stdio-framed message must not contain a newline (BHMS-TRN-010)")
        if self._closed:
            raise TransportClosed("transport is closed")
        try:
            self._writer.write(data + b"\n")
            await self._writer.drain()
        except (ConnectionError, OSError, RuntimeError) as exc:
            raise TransportClosed(str(exc)) from exc

    async def receive(self) -> bytes:
        if self._closed:
            raise TransportClosed("transport is closed")
        return await self._lines.readline()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._writer.close()
            await asyncio.wait_for(self._writer.wait_closed(), self.close_timeout)
        except asyncio.TimeoutError:
            self.abort()  # the peer is not reading: do not wait for its buffer to drain
        except (ConnectionError, OSError, RuntimeError):
            pass

    def abort(self) -> None:
        self._closed = True
        transport = self._writer.transport
        if transport is not None:
            with contextlib.suppress(Exception):  # an already-finished pipe/socket transport may have no loop left
                transport.abort()


# --------------------------------------------------------------------------- peers


def unix_peer(writer: asyncio.StreamWriter, path: str | None = None) -> Peer:
    """Peer for a Unix-domain connection, from SO_PEERCRED (BHMS-TRN-022)."""
    sock: socket.socket | None = writer.get_extra_info("socket")
    pid = uid = gid = None
    if sock is not None and hasattr(socket, "SO_PEERCRED"):
        try:
            raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("iII"))
            pid, uid, gid = struct.unpack("iII", raw)
        except OSError:
            pass
    return Peer("unix", address=path, uid=uid, gid=gid, pid=pid)


def tcp_peer(writer: asyncio.StreamWriter) -> Peer:
    name = writer.get_extra_info("peername")
    address = f"{name[0]}:{name[1]}" if isinstance(name, tuple) and len(name) >= 2 else None
    return Peer("tcp", address=address)


def is_loopback(host: str) -> bool:
    """True for ``localhost`` and loopback IP literals."""
    if host == "localhost":
        return True
    try:
        return ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


# --------------------------------------------------------------------------- listeners


class Listener:
    """A running listener; ``close()`` stops accepting and closes live connections' accept loop."""

    def __init__(self, server: Any, address: Any, path: str | None = None) -> None:
        self._server = server
        self.address = address
        self._path = path

    async def close(self) -> None:
        self._server.close()
        await self._server.wait_closed()
        if self._path is not None:
            try:
                if stat.S_ISSOCK(os.stat(self._path).st_mode):
                    os.unlink(self._path)
            except OSError:
                pass


OnTransport = Callable[[Transport], Awaitable[None]]


def _accept(make: Callable[[asyncio.StreamReader, asyncio.StreamWriter], Transport],
            on_transport: OnTransport) -> Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        transport = make(reader, writer)
        try:
            await on_transport(transport)
        finally:
            await transport.close()

    return handle


async def serve_unix(path: str, on_transport: OnTransport, *, mode: int = 0o600,
                     max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> Listener:
    """Listen on a Unix-domain socket created with permissions ``mode`` (no wider; BHMS-TRN-022).

    ``on_transport`` runs once per connection in its own task; the transport is closed when it returns.
    A stale socket file at ``path`` is replaced; any other kind of file is an error.
    """
    check_message_limit(max_message_bytes)
    try:
        if stat.S_ISSOCK(os.stat(path).st_mode):
            os.unlink(path)
    except FileNotFoundError:
        pass
    old_umask = os.umask(0o777 & ~mode)  # the socket file is created with `mode` atomically
    try:
        server = await asyncio.start_unix_server(
            _accept(lambda r, w: StreamTransport(r, w, unix_peer(w, path), max_message_bytes), on_transport),
            path=path, limit=_CHUNK)
    finally:
        os.umask(old_umask)
    return Listener(server, path, path)


async def serve_tcp(host: str, port: int, on_transport: OnTransport, *, ssl: ssl_module.SSLContext | None = None,
                    max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> Listener:
    """Listen on TCP. Binding a non-loopback address without TLS is refused (BHMS-TRN-021).

    Every request on a non-loopback listener must also carry a bearer token (BHMS-SEC-004); that is
    enforced above the transport.
    """
    check_message_limit(max_message_bytes)
    if not is_loopback(host) and ssl is None:
        raise ValueError(f"refusing to bind {host!r}: a TCP listener must bind a loopback address unless "
                         "protected by TLS (BHMS-TRN-021); pass ssl=<SSLContext> or bind 127.0.0.1")
    server = await asyncio.start_server(
        _accept(lambda r, w: StreamTransport(r, w, tcp_peer(w), max_message_bytes), on_transport),
        host=host, port=port, ssl=ssl, limit=_CHUNK)
    sockname = server.sockets[0].getsockname()
    return Listener(server, (sockname[0], sockname[1]))


# --------------------------------------------------------------------------- clients


async def connect_unix(path: str, *, max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> StreamTransport:
    """Open a client connection to a Unix-domain socket."""
    reader, writer = await asyncio.open_unix_connection(path, limit=_CHUNK)
    return StreamTransport(reader, writer, unix_peer(writer, path), max_message_bytes)


async def connect_tcp(host: str, port: int, *, ssl: ssl_module.SSLContext | None = None,
                      max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> StreamTransport:
    """Open a client connection over TCP."""
    reader, writer = await asyncio.open_connection(host, port, ssl=ssl, limit=_CHUNK)
    return StreamTransport(reader, writer, tcp_peer(writer), max_message_bytes)
