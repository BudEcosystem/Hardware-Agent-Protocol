"""stdio binding (spec/bhms/02-transports.md §2.1).

Client side: :func:`spawn_stdio` launches the server as a subprocess and talks over its
stdin/stdout; its stderr is inherited (logs). Server side: :func:`stdio_server_transport` serves
the current process's stdin/stdout. The parent process is the principal (BHMS-SEC-003).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shlex
import sys
from collections.abc import Mapping, Sequence
from typing import IO

from bhms.transport.base import DEFAULT_MAX_MESSAGE_BYTES, Peer, check_message_limit
from bhms.transport.stream import _CHUNK, StreamTransport


class SubprocessTransport(StreamTransport):
    """A :class:`StreamTransport` that owns the server subprocess it talks to."""

    def __init__(self, process: asyncio.subprocess.Process, max_message_bytes: int, grace_s: float) -> None:
        assert process.stdout is not None and process.stdin is not None
        peer = Peer("stdio", address="child", pid=process.pid, uid=os.getuid())
        super().__init__(process.stdout, process.stdin, peer, max_message_bytes)  # type: ignore[arg-type]
        self.process = process
        self._grace_s = grace_s

    async def close(self) -> None:
        """Close stdin (the server exits on EOF, BHMS-TRN-011), then terminate, then kill.

        Never waits on the stdin pipe itself: a child that stopped reading would block it forever.
        """
        self._closed = True
        with contextlib.suppress(Exception):
            self._writer.close()
        for action in (None, self.process.terminate, self.process.kill):
            if self.process.returncode is not None:
                break
            if action is not None:
                with contextlib.suppress(ProcessLookupError):
                    action()
            # After SIGKILL the child only lingers while stuck in the kernel (for example in an fsync on a stalled disk):
            # wait longer so it is reaped rather than leaked as a running subprocess.
            limit = self._grace_s if action != self.process.kill else max(self._grace_s, 10.0)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.process.wait(), limit)
        self.abort()

    def abort(self) -> None:
        self._closed = True
        with contextlib.suppress(ProcessLookupError):
            if self.process.returncode is None:
                self.process.kill()
        transport = self._writer.transport
        if transport is not None:
            with contextlib.suppress(Exception):  # an already-finished pipe/socket transport may have no loop left
                transport.abort()


async def spawn_stdio(command: str | Sequence[str], *, env: Mapping[str, str] | None = None,
                      cwd: str | None = None, stderr: int | IO[bytes] | None = None,
                      max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
                      grace_s: float = 2.0) -> SubprocessTransport:
    """Launch ``command`` (a shell-style string or an argv list) and connect to its stdio.

    ``stderr`` defaults to the parent's stderr (server logs). On close the child gets ``grace_s``
    to exit after EOF before it is terminated and then killed.
    """
    check_message_limit(max_message_bytes)
    if stderr == asyncio.subprocess.PIPE:
        raise ValueError("stderr=PIPE would fill and block the server; pass a file, DEVNULL or None (inherit)")
    argv = shlex.split(command) if isinstance(command, str) else list(command)
    if not argv:
        raise ValueError("empty stdio command")
    process = await asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=stderr,
        env=None if env is None else dict(env), cwd=cwd, limit=_CHUNK)
    return SubprocessTransport(process, max_message_bytes, grace_s)


async def stdio_server_transport(*, max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> StreamTransport:
    """Transport over this process's stdin/stdout.

    The original stdout descriptor is duplicated for protocol output and fd 1 is redirected to stderr,
    so a stray ``print`` can never corrupt the stream (BHMS-TRN-010).
    """
    check_message_limit(max_message_bytes)
    loop = asyncio.get_running_loop()
    out_fd = os.dup(1)
    sys.stdout.flush()
    os.dup2(2, 1)
    reader = asyncio.StreamReader(limit=_CHUNK, loop=loop)
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader, loop=loop), os.fdopen(os.dup(0), "rb", 0))
    w_transport, w_protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin,
                                                            os.fdopen(out_fd, "wb", 0))
    writer = asyncio.StreamWriter(w_transport, w_protocol, None, loop)
    peer = Peer("stdio", address="parent", pid=os.getppid(), uid=os.getuid())
    return StreamTransport(reader, writer, peer, max_message_bytes)
