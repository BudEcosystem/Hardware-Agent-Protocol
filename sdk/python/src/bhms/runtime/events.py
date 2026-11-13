"""The append-only event log with opaque cursors and explicit gaps (spec/bhms/09-events-and-streams.md).

Events are rows of the :class:`~bhms.runtime.store.Store`; a cursor is ``"e.<tag>.<seq>"`` where ``tag`` is derived from
the store epoch. Cursors are therefore totally ordered per server and stable (BHMS-EVT-001). A cursor whose tag is not
the current one belongs to a log that was reset (a new epoch) and reads with ``gap: true`` (BHMS-EVT-011); anything
that is not a cursor at all is ``INVALID_ARGUMENT`` naming ``after``/``cursor`` (BHMS-LIF-060). Events older than the
retention window are pruned and a read from before them reports ``gap: true``.

Live delivery: :meth:`EventLog.listen` registers a synchronous callback that sees every event appended after
registration. Because appends and reads run on one event loop without awaiting in between, registering a listener and
then reading the retained events up to the current head leaves no seam: no duplicate and no omission
(BHMS-EVT-020).

Example::

    log = EventLog(store, retention_s=604800)
    event = log.append("device.fault", severity="error", device_id="pump-1", message="stall", data={"code": "E12"})
    events, cursor, gap = log.read(after=None, limit=100)

Thread-safety: one event loop.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from typing import Any

from bhms.protocol.errors import BhmsError
from bhms.runtime.operations import iso, now_ns
from bhms.runtime.store import Store

log = logging.getLogger("bhms.events")

EventListener = Callable[[dict[str, Any], int], None]


class EventLog:
    """Durable event log over a store; see the module docstring."""

    def __init__(self, store: Store, *, retention_s: int = 7 * 86400, prune_every: int = 1000) -> None:
        self.store = store
        self.retention_s = retention_s
        self._tag = hashlib.sha256(f"events:{store.epoch}".encode()).hexdigest()[:8]
        self._listeners: list[EventListener] = []
        self._prune_every = prune_every
        self._since_prune = 0

    # ------------------------------------------------------------------ cursors

    def cursor(self, seq: int) -> str:
        return f"e.{self._tag}.{seq:x}"

    def parse(self, cursor: str, field: str = "after") -> int | None:
        """The sequence number of ``cursor``; None when it belongs to a reset log; INVALID_ARGUMENT when malformed."""
        parts = cursor.split(".")
        if len(parts) != 3 or parts[0] != "e" or len(parts[1]) != 8:
            raise BhmsError("INVALID_ARGUMENT", f"{field} is not an event cursor of this server", field=field,
                            hint="pass a cursor exactly as returned by events/read or an event; omit it to start at "
                                 "the oldest retained event (BHMS-LIF-060)")
        try:
            seq = int(parts[2], 16)
        except ValueError:
            raise BhmsError("INVALID_ARGUMENT", f"{field} is not an event cursor of this server", field=field,
                            hint="pass a cursor exactly as returned (BHMS-LIF-060)") from None
        if parts[1] != self._tag:
            return None
        return seq

    def head(self) -> int:
        return self.store.event_bounds()[1]

    # ------------------------------------------------------------------ writing

    def append(self, type: str, *, severity: str = "info", device_id: str | None = None,
               operation_id: str | None = None, message: str | None = None,
               data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Record an event and deliver it to live listeners; returns the ``Event``. Raises
        :class:`~bhms.runtime.store.StoreError` when the journal cannot be written."""
        stamp = now_ns()
        body: dict[str, Any] = {"time": iso(stamp), "type": type, "severity": severity}
        if device_id is not None:
            body["deviceId"] = device_id
        if operation_id is not None:
            body["operationId"] = operation_id
        if message is not None:
            body["message"] = message[:1000]
        if data is not None:
            body["data"] = data
        seq = self.store.append_event(time_ns=stamp, type=type, device_id=device_id, event=body)
        event = {"cursor": self.cursor(seq), **body}
        for listener in list(self._listeners):
            try:
                listener(event, seq)
            except Exception:  # noqa: BLE001 - one broken subscriber must not lose the event for others
                log.exception("event listener failed")
        self._since_prune += 1
        if self._since_prune >= self._prune_every:
            self.prune()
        return event

    def prune(self) -> int:
        """Drop events older than the retention window (BHMS-EVT-012 keeps at least ``retention_s``)."""
        self._since_prune = 0
        return self.store.prune_events(now_ns() - self.retention_s * 1_000_000_000)

    # ------------------------------------------------------------------ reading

    def listen(self, listener: EventListener) -> Callable[[], None]:
        """Register a live listener; returns the function that removes it."""
        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    def start_position(self, after: str | None, field: str = "after") -> tuple[int, bool]:
        """(sequence to read after, gap) for a client cursor (BHMS-EVT-011)."""
        if after is None:
            return 0, False
        seq = self.parse(after, field)
        if seq is None:
            return 0, True  # cursor from a reset log
        if seq < self.store.events_pruned_through():
            return seq, True
        if seq > self.head():
            raise BhmsError("INVALID_ARGUMENT", f"{field} is ahead of this server's log", field=field,
                            hint="pass a cursor exactly as returned by this server (BHMS-LIF-060)")
        return seq, False

    def read(self, *, after: str | None, limit: int, device_id: str | None = None, types: list[str] | None = None,
             visible: Callable[[str | None], bool] | None = None) -> tuple[list[dict[str, Any]], str, bool]:
        """``events/read``: events strictly after ``after`` in cursor order, the next cursor and ``gap``.

        Events of devices ``visible`` rejects are skipped without a gap (BHMS-EVT-013).
        """
        start, gap = self.start_position(after)
        head = self.head()
        rows = self.store.read_events(after=start, limit=limit, device_ids=[device_id] if device_id else None,
                                      types=types, upto=head)
        events = [{"cursor": self.cursor(seq), **body} for seq, body in rows
                  if visible is None or visible(body.get("deviceId"))]
        if len(rows) >= limit:
            next_seq = rows[-1][0]
        else:
            next_seq = max(head, start)
        return events, self.cursor(next_seq), gap

    def retained_after(self, seq: int, *, upto: int, device_ids: list[str] | None, types: list[str] | None,
                       batch: int = 1000) -> list[tuple[int, dict[str, Any]]]:
        """All retained events with ``seq < s <= upto`` (subscription replay)."""
        out: list[tuple[int, dict[str, Any]]] = []
        position = seq
        while True:
            rows = self.store.read_events(after=position, limit=batch, device_ids=device_ids, types=types, upto=upto)
            out += [(s, {"cursor": self.cursor(s), **body}) for s, body in rows]
            if len(rows) < batch:
                return out
            position = rows[-1][0]


__all__ = ["EventLog"]
