"""The transport contract: one connection that moves whole BHMS messages as bytes.

A transport frames and delivers JSON-RPC messages and carries the peer identity. It
never interprets a message (spec/bhms/02-transports.md). Every binding presents the
same :class:`Transport` interface:

* ``send(data)``: deliver one message (a single JSON text, no framing from the caller).
* ``receive()``: the next whole message; raises :class:`FrameTooLarge` for a message over
  ``max_message_bytes`` (the transport has already skipped it and stays usable, except on
  WebSocket where the protocol closes the connection with 1009) and :class:`TransportClosed`
  at end of stream.
* ``close()``: release the connection; idempotent.
* ``peer``: who is on the other end (:class:`Peer`).

Thread-safety: a transport belongs to one event loop; ``send`` and ``receive`` may each be
awaited by one task at a time (a :class:`~bhms.jsonrpc.session.Session` does exactly that).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from types import TracebackType

DEFAULT_MAX_MESSAGE_BYTES = 4 * 1024 * 1024
"""Default message size limit (BHMS-TRN-004 requires at least 1 MiB)."""

MIN_MAX_MESSAGE_BYTES = 1_048_576


class TransportError(Exception):
    """Base class of transport failures."""


class TransportClosed(TransportError):
    """The connection ended (peer closed, local close, or I/O failure)."""


class FrameTooLarge(TransportError):
    """An incoming message exceeded ``max_message_bytes`` and was discarded."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"message exceeds the {limit} byte limit")
        self.limit = limit


@dataclass(frozen=True, slots=True)
class Peer:
    """Identity of the other end of a connection, surfaced to the session unmodified.

    ``kind`` is ``stdio``, ``unix``, ``tcp`` or ``ws``. Unix peers carry the kernel-verified
    ``uid``/``gid``/``pid`` (SO_PEERCRED); TCP and WebSocket peers carry ``address`` and, for
    WebSocket, the ``token`` presented in the handshake ``Authorization: Bearer`` header. A
    ``Peer`` is evidence, not authorization: policy decides what it may do.
    """

    kind: str
    address: str | None = None
    uid: int | None = None
    gid: int | None = None
    pid: int | None = None
    token: str | None = field(default=None, repr=False)

    @property
    def description(self) -> str:
        """Short human-readable form for logs; never includes the token."""
        parts = [self.kind]
        if self.address:
            parts.append(self.address)
        if self.pid is not None:
            parts.append(f"pid={self.pid}")
        if self.uid is not None:
            parts.append(f"uid={self.uid}")
        return " ".join(parts)


class Transport(abc.ABC):
    """Abstract connection; see the module docstring for the contract."""

    peer: Peer
    max_message_bytes: int

    @abc.abstractmethod
    async def send(self, data: bytes) -> None:
        """Deliver one message. Raises :class:`TransportClosed` if the connection is gone."""

    @abc.abstractmethod
    async def receive(self) -> bytes:
        """Return the next whole message."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Close the connection (idempotent, never raises)."""

    async def __aenter__(self) -> Transport:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                        tb: TracebackType | None) -> None:
        await self.close()


def check_message_limit(max_message_bytes: int) -> int:
    """Validate a configured limit (BHMS-TRN-004: at least 1 048 576)."""
    if max_message_bytes < MIN_MAX_MESSAGE_BYTES:
        raise ValueError(f"max_message_bytes must be at least {MIN_MAX_MESSAGE_BYTES} (BHMS-TRN-004), "
                         f"got {max_message_bytes}")
    return max_message_bytes
