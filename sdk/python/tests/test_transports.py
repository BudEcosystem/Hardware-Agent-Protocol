"""Transports over real sockets and a real child process."""

import asyncio
import os
import stat
import sys
from pathlib import Path

import pytest
from websockets.asyncio.client import connect as ws_connect

from bhms import transport as tr
from bhms.transport import FrameTooLarge, TransportClosed

ECHO = Path(__file__).parent / "helpers" / "echo_stdio.py"
MIB = 1024 * 1024


class Pair:
    def __init__(self, client, server, cleanup):
        self.client, self.server, self._cleanup = client, server, cleanup

    async def aclose(self):
        await self.client.close()
        await self._cleanup()


async def make_pair(kind: str, tmp_path: Path, **kw) -> Pair:
    accepted: asyncio.Queue = asyncio.Queue()
    done = asyncio.Event()

    async def on_transport(t):
        accepted.put_nowait(t)
        await done.wait()

    async def cleanup():
        done.set()
        await listener.close()

    if kind == "unix":
        listener = await tr.serve_unix(str(tmp_path / "s.sock"), on_transport, **kw)
        client = await tr.connect_unix(str(tmp_path / "s.sock"), **kw)
    elif kind == "tcp":
        listener = await tr.serve_tcp("127.0.0.1", 0, on_transport, **kw)
        client = await tr.connect_tcp(*listener.address, **kw)
    else:
        listener = await tr.serve_websocket("127.0.0.1", 0, on_transport, **kw)
        client = await tr.connect_websocket("ws://%s:%d" % listener.address, **kw)
    return Pair(client, await asyncio.wait_for(accepted.get(), 5), cleanup)


async def _send_all(transport, *messages):
    for message in messages:
        await transport.send(message)


KINDS = ["unix", "tcp", "ws"]


@pytest.mark.parametrize("kind", KINDS)
async def test_round_trip_both_directions(kind, tmp_path):
    p = await make_pair(kind, tmp_path)
    try:
        await p.client.send(b'{"a":1}')
        assert await p.server.receive() == b'{"a":1}'
        await p.server.send(b'{"b":2}')
        assert await p.client.receive() == b'{"b":2}'
        for i in range(100):
            await p.client.send(b'{"n":%d}' % i)
        assert [await p.server.receive() for _ in range(100)] == [b'{"n":%d}' % i for i in range(100)]
    finally:
        await p.aclose()


@pytest.mark.parametrize("kind", KINDS)
async def test_close_is_visible_to_the_peer_and_idempotent(kind, tmp_path):
    p = await make_pair(kind, tmp_path)
    await p.client.close()
    await p.client.close()
    with pytest.raises(TransportClosed):
        await asyncio.wait_for(p.server.receive(), 5)
    with pytest.raises(TransportClosed):
        await p.client.send(b"{}")
    await p._cleanup()


@pytest.mark.parametrize("kind", ["unix", "tcp"])
async def test_stream_newline_in_message_is_refused(kind, tmp_path):
    p = await make_pair(kind, tmp_path)
    try:
        with pytest.raises(ValueError):
            await p.client.send(b'{"a":\n1}')
    finally:
        await p.aclose()


@pytest.mark.parametrize("kind", ["unix", "tcp"])
async def test_stream_oversize_is_refused_once_and_the_stream_resyncs(kind, tmp_path):
    p = await make_pair(kind, tmp_path)
    try:
        big = b'{"x":"' + b"a" * (5 * MIB) + b'"}'
        sender = asyncio.create_task(_send_all(p.client, big, b'{"after":1}'))
        with pytest.raises(FrameTooLarge):
            await asyncio.wait_for(p.server.receive(), 5)
        assert await asyncio.wait_for(p.server.receive(), 5) == b'{"after":1}'
        await sender
        # exactly at the limit is accepted
        exact = b"x" * p.server.max_message_bytes
        sender = asyncio.create_task(_send_all(p.client, exact))
        assert await asyncio.wait_for(p.server.receive(), 5) == exact
        await sender
    finally:
        await p.aclose()


async def test_stream_messages_split_across_chunks_and_blank_lines(tmp_path):
    accepted: asyncio.Queue = asyncio.Queue()
    done = asyncio.Event()

    async def on_transport(t):
        accepted.put_nowait(t)
        await done.wait()

    listener = await tr.serve_unix(str(tmp_path / "s.sock"), on_transport)
    reader, writer = await asyncio.open_unix_connection(str(tmp_path / "s.sock"))
    server = await asyncio.wait_for(accepted.get(), 5)
    writer.write(b'{"a"')
    await writer.drain()
    await asyncio.sleep(0.02)
    writer.write(b':1}\n\n  \n{"b":2}\n{"c"')
    await writer.drain()
    assert await server.receive() == b'{"a":1}'
    assert await server.receive() == b'{"b":2}'
    writer.write(b":3}\n")
    assert await server.receive() == b'{"c":3}'
    writer.close()
    done.set()
    await listener.close()


async def test_unix_peer_credentials_and_socket_mode(tmp_path):
    p = await make_pair("unix", tmp_path)
    try:
        assert p.server.peer.kind == "unix"
        assert p.server.peer.uid == os.getuid() and p.server.peer.pid == os.getpid()
        assert stat.S_IMODE(os.stat(tmp_path / "s.sock").st_mode) == 0o600
    finally:
        await p.aclose()
    assert not (tmp_path / "s.sock").exists()


async def test_unix_socket_mode_is_configurable_and_stale_socket_replaced(tmp_path):
    sock = tmp_path / "s.sock"
    first = await tr.serve_unix(str(sock), lambda t: asyncio.sleep(0), mode=0o660)
    assert stat.S_IMODE(os.stat(sock).st_mode) == 0o660
    first._server.close()  # leaves the stale socket file behind
    second = await tr.serve_unix(str(sock), lambda t: asyncio.sleep(0))
    await second.close()


async def test_tcp_peer_address_and_non_loopback_requires_tls():
    async def noop(t):
        await asyncio.sleep(0)

    with pytest.raises(ValueError, match="loopback"):
        await tr.serve_tcp("0.0.0.0", 0, noop)
    with pytest.raises(ValueError, match="loopback"):
        await tr.serve_websocket("0.0.0.0", 0, noop)


async def test_tcp_peer_address(tmp_path):
    p = await make_pair("tcp", tmp_path)
    try:
        assert p.server.peer.kind == "tcp" and p.server.peer.address.startswith("127.0.0.1:")
    finally:
        await p.aclose()


async def test_max_message_bytes_floor():
    with pytest.raises(ValueError, match="1048576"):
        await tr.serve_tcp("127.0.0.1", 0, lambda t: asyncio.sleep(0), max_message_bytes=1000)


async def test_ws_bearer_token_surfaces_in_peer_and_401_when_refused():
    accepted: asyncio.Queue = asyncio.Queue()
    done = asyncio.Event()

    async def on_transport(t):
        accepted.put_nowait(t)
        await done.wait()

    listener = await tr.serve_websocket("127.0.0.1", 0, on_transport, authenticate=lambda tok: tok == "s3cret")
    url = "ws://%s:%d" % listener.address
    client = await tr.connect_websocket(url, token="s3cret")
    server = await asyncio.wait_for(accepted.get(), 5)
    assert server.peer.kind == "ws" and server.peer.token == "s3cret"
    assert "s3cret" not in repr(server.peer) and "s3cret" not in server.peer.description
    await client.send(b"{}")
    assert await server.receive() == b"{}"
    for token in (None, "wrong"):
        with pytest.raises(Exception) as exc:
            await tr.connect_websocket(url, token=token)
        assert getattr(getattr(exc.value, "response", None), "status_code", None) == 401
    await client.close()
    done.set()
    await listener.close()


async def test_ws_requires_the_bhms_subprotocol_and_negotiates_it():
    async def hold(t):
        await asyncio.sleep(0.2)

    listener = await tr.serve_websocket("127.0.0.1", 0, hold)
    url = "ws://%s:%d" % listener.address
    with pytest.raises(Exception) as exc:
        await ws_connect(url)  # no subprotocol offered
    assert exc.value.response.status_code == 400
    client = await tr.connect_websocket(url)
    assert client._ws.subprotocol == "bhms"
    await client.close()
    await listener.close()


async def test_ws_oversize_closes_the_connection_with_1009():
    p = await make_pair("ws", tmp_path=None)
    try:
        sender = asyncio.create_task(_send_all(p.client, b'{"x":"' + b"a" * (5 * MIB) + b'"}'))
        with pytest.raises(TransportClosed):
            await asyncio.wait_for(p.server.receive(), 5)
        await asyncio.gather(sender, return_exceptions=True)
    finally:
        await p.aclose()


async def test_ws_binary_frame_is_refused():
    p = await make_pair("ws", tmp_path=None)
    try:
        await p.client._ws.send(b"\x00\x01")
        with pytest.raises(TransportClosed):
            await asyncio.wait_for(p.server.receive(), 5)
    finally:
        await p.aclose()


async def test_stdio_spawn_echo_with_real_child_process():
    t = await tr.spawn_stdio([sys.executable, str(ECHO)])
    try:
        assert t.peer.kind == "stdio" and t.peer.pid == t.process.pid
        await t.send(b'{"hello":1}')
        assert await asyncio.wait_for(t.receive(), 10) == b'echo:{"hello":1}'
        # stray print in the child went to stderr, not into the protocol stream; oversize resyncs
        sender = asyncio.create_task(_send_all(t, b"z" * (5 * MIB), b'{"next":1}'))
        assert await asyncio.wait_for(t.receive(), 10) == b"TOO-LARGE"
        assert await asyncio.wait_for(t.receive(), 10) == b'echo:{"next":1}'
        await sender
    finally:
        await t.close()
    assert t.process.returncode == 0  # the child exited on stdin EOF (BHMS-TRN-011)


async def test_stdio_spawn_accepts_a_command_string_and_rejects_empty():
    t = await tr.spawn_stdio(f"{sys.executable} {ECHO}")
    await t.send(b"{}")
    assert await asyncio.wait_for(t.receive(), 10) == b"echo:{}"
    await t.close()
    with pytest.raises(ValueError):
        await tr.spawn_stdio("")


async def test_stdio_child_that_dies_closes_the_transport():
    t = await tr.spawn_stdio([sys.executable, "-c", "import sys; sys.exit(3)"])
    with pytest.raises(TransportClosed):
        await asyncio.wait_for(t.receive(), 10)
    await t.close()
    assert t.process.returncode == 3


async def test_stdio_close_kills_a_child_that_ignores_eof():
    code = "import time\nwhile True: time.sleep(1)"
    t = await tr.spawn_stdio([sys.executable, "-c", code], grace_s=0.3)
    await t.close()
    assert t.process.returncode is not None
