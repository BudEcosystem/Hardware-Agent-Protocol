"""Linux pipe transport for the local MCP projection; bounded input and output.

The event loop owns pipe I/O. Workers enqueue replies without touching stdout.
EOF/transport failure abandons delivery, never sends an HMS cancellation.
"""
from collections import deque
import os
import selectors
import socket
import sys
import threading
import time

from .contracts import MAX_BYTES
from .mcp import Projection, TransportClosed, dumps

MAX_OUTPUT_BYTES = 524288
MAX_QUEUED_BYTES = 2097152
MAX_QUEUED_MESSAGES = 32
FRAME_TIMEOUT = 2.0
WRITE_TIMEOUT = 2.0


class _Outbox:
    def __init__(self, wake):
        self.wake = wake
        self.lock = threading.Lock()
        self.messages = deque()
        self.bytes = 0
        self.failed = False

    def emit(self, value):
        data = (dumps(value) + '\n').encode('utf-8')
        with self.lock:
            if (len(data) > MAX_OUTPUT_BYTES or self.bytes + len(data) > MAX_QUEUED_BYTES or
                    len(self.messages) >= MAX_QUEUED_MESSAGES):
                self.failed = True
            elif not self.failed:
                self.messages.append([data, 0, time.monotonic()])
                self.bytes += len(data)
        try:
            self.wake.send(b'x')
        except (BlockingIOError, OSError):
            pass  # A pending wake byte or a closed transport suffices.

    def pending(self):
        with self.lock:
            return bool(self.messages)

    def write(self, fd):
        with self.lock:
            if not self.messages:
                return
            message = self.messages[0]
            try:
                count = os.write(fd, memoryview(message[0])[message[1]:])
            except BlockingIOError:
                return
            if count == 0:
                raise TransportClosed('stdout stopped accepting bytes')
            message[1] += count
            if message[1] == len(message[0]):
                self.bytes -= len(message[0])
                self.messages.popleft()

    def check(self):
        with self.lock:
            if self.failed or self.messages and time.monotonic() - self.messages[0][2] > WRITE_TIMEOUT:
                raise TransportClosed('bounded output exhausted or timed out')


def serve(client, *, input_fd=None, output_fd=None):
    """Serve caller-provided pipes; returns 0 on EOF and 2 on framing/transport loss.

    Linux pipes and stream sockets are supported. Regular files are not an MCP
    process transport. Worker threads are bounded and daemonized: exit need not
    wait for a blocked local filesystem, and cannot assert anything about effects.
    """
    input_fd = sys.stdin.fileno() if input_fd is None else input_fd
    output_fd = sys.stdout.fileno() if output_fd is None else output_fd
    original = {fd: os.get_blocking(fd) for fd in (input_fd, output_fd)}
    wake_read, wake_write = socket.socketpair()
    wake_read.setblocking(False)
    wake_write.setblocking(False)
    selector = selectors.DefaultSelector()
    outbox = _Outbox(wake_write)
    projection = Projection(client, outbox.emit)
    data = bytearray()
    started = None
    output_registered = False
    try:
        for fd in original:
            os.set_blocking(fd, False)
        selector.register(input_fd, selectors.EVENT_READ, 'input')
        selector.register(wake_read, selectors.EVENT_READ, 'wake')
        while True:
            outbox.check()
            if started is not None and time.monotonic() - started > FRAME_TIMEOUT:
                raise TransportClosed('incomplete input frame timed out')
            pending = outbox.pending()
            if pending and not output_registered:
                selector.register(output_fd, selectors.EVENT_WRITE, 'output')
                output_registered = True
            elif not pending and output_registered:
                selector.unregister(output_fd)
                output_registered = False
            for key, _ in selector.select(0.05):
                if key.data == 'output':
                    outbox.write(output_fd)
                elif key.data == 'wake':
                    try:
                        wake_read.recv(4096)
                    except BlockingIOError:
                        pass
                else:
                    try:
                        chunk = os.read(input_fd, min(4096, MAX_BYTES + 1 - len(data)))
                    except BlockingIOError:
                        continue
                    if not chunk:
                        return 2 if data else 0
                    if not data:
                        started = time.monotonic()
                    data.extend(chunk)
                    while b'\n' in data:
                        frame, _, trailing = data.partition(b'\n')
                        projection.receive(bytes(frame))
                        data = trailing
                        started = time.monotonic() if data else None
                    if len(data) > MAX_BYTES:
                        raise TransportClosed('input frame too large')
    except (TransportClosed, OSError, ValueError):
        return 2
    finally:
        projection.close()
        selector.close()
        wake_read.close()
        wake_write.close()
        for fd, blocking in original.items():
            try:
                os.set_blocking(fd, blocking)
            except OSError:
                pass
