"""Bounded local stream transport for the explicitly synthetic compact binding.

The trusted launcher supplies a connected Unix stream socket to the original C
fixture. This module neither opens devices nor launches/restarts an endpoint.
It makes one handoff attempt; recovery belongs to the durable binding.
"""
import os
import select
import socket
import struct
import time

from protocol.serial.frame import Decoder, encode
from .journal import JournalError


class LocalEndpointStream:
    def __init__(self, fd, *, timeout=0.5):
        if type(fd) is not int or fd < 0 or not 0 < timeout <= 2:
            raise JournalError("INVALID_ENDPOINT_STREAM")
        owned = os.dup(fd)
        try:
            self.socket = socket.socket(fileno=owned)
        except BaseException:
            os.close(owned)
            raise
        try:
            if self.socket.family != socket.AF_UNIX or self.socket.type != socket.SOCK_STREAM:
                raise JournalError("INVALID_ENDPOINT_STREAM")
            self.socket.getpeername()
            _pid, uid, _gid = struct.unpack('3i', self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid():
                raise JournalError("ENDPOINT_OWNER_MISMATCH")
            self.socket.setblocking(False)
        except BaseException:
            self.socket.close()
            raise
        self.timeout = timeout
        self.decoder = Decoder()

    def close(self):
        self.socket.close()

    def exchange(self, request, receive):
        """Call receive(frame) before consuming correlation; never retry a write.

        receive must durably validate/store inbound sequence continuity. Stale
        replies can arrive after a prior timeout, but cannot satisfy this call.
        An absolute deadline and byte/frame bounds also limit malformed peers.
        """
        deadline = time.monotonic() + self.timeout
        wire = encode(request.frame)
        offset = 0
        try:
            while offset < len(wire):
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([], [self.socket], [], remaining)[1]:
                    raise JournalError("ENDPOINT_IO_TIMEOUT")
                try:
                    count = self.socket.send(wire[offset:])
                except BlockingIOError:
                    continue
                if count == 0:
                    raise JournalError("ENDPOINT_DISCONNECTED")
                offset += count
            frames = 0
            for _ in range(4096):
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([self.socket], [], [], remaining)[0]:
                    raise JournalError("ENDPOINT_IO_TIMEOUT")
                try:
                    octet = self.socket.recv(1)
                except BlockingIOError:
                    continue
                if not octet:
                    raise JournalError("ENDPOINT_DISCONNECTED")
                event = self.decoder.feed(octet[0])
                if event is None:
                    continue
                if event[0] != 'frame':
                    raise JournalError("ENDPOINT_FRAME_INVALID")
                frame = event[1]
                receive(frame)
                frames += 1
                if (len(frame.payload) >= 6 and frame.payload[1] == (request.opcode | 0x80)
                        and int.from_bytes(frame.payload[2:6], 'big') == request.frame.sequence):
                    return frame
                if frames >= 16:
                    break
            raise JournalError("ENDPOINT_REPLY_LIMIT")
        except OSError as error:
            self.decoder.reset()
            raise JournalError("ENDPOINT_IO_FAILURE") from error
        except BaseException:
            self.decoder.reset()
            raise
