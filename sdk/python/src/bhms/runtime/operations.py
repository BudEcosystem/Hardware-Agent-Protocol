"""Operation state machine, durable journal and idempotency (spec/bhms/06-operations.md, 08-programs.md §8.4).

:class:`Journal` is the only code that changes an operation. Every change is checked against the transition table of
§6.3 (:data:`TRANSITIONS`), appended to the operation's history and committed to the :class:`~bhms.runtime.store.Store`
before listeners (subscriptions, events) hear about it:

* ``state`` only moves along the table (BHMS-OPS-001); terminal states never change (BHMS-OPS-002) — later evidence is
  a ``correction`` entry; leaving ``unknown`` needs a ``reconciliation`` entry that names its evidence (BHMS-OPS-005);
* entering ``unknown`` needs ``DEADLINE_EXCEEDED`` with ``mayHaveActed: true`` and ``retry: after-reconcile``
  (BHMS-OPS-004, :meth:`Journal.unknown_error`); ``rejected``/``canceled``-before-dispatch force ``effect: none``
  (BHMS-OPS-006); ``result`` exists exactly in ``completed`` (BHMS-OPS-008); a dispatched failure says
  ``mayHaveActed: true`` unless device evidence proves otherwise (BHMS-OPS-009);
* ``dispatching`` is written in a *barrier* commit (fsync) so the intent is durable before any handler runs
  (BHMS-OPS-003); entering it marks the effect ``unknown`` for effectful actions until evidence arrives.

Idempotency (§6.4): :func:`intent_digest` computes ``requestDigest`` from the request alone (arguments exactly as sent);
:meth:`Journal.lookup_key` maps ``(principal, operationKey)`` to at most one operation (a UNIQUE index backs it);
:meth:`Journal.admission` serialises concurrent admissions of one key so that 50 identical requests create one
operation (BHMS-OPS-032); :func:`key_conflict_error` builds ``KEY_CONFLICT`` (BHMS-OPS-031/040).

Recovery (:meth:`Journal.recover`, BHMS-OPS-080, BHMS-PRG-017): after a restart action operations found
``dispatching``/``running`` become ``unknown``; ``accepted`` ones (provably never dispatched, because ``dispatching`` is
durable before dispatch) are ``rejected`` (``INTERNAL``, ``mayHaveActed: false``) — the time-dependent recheck of
BHMS-OPS-041 fails because the server cannot vouch for leases or device state across its own restart; unsettled
programs are settled from their step history and never resumed.

Example::

    journal = Journal(Store(path))
    async with journal.admission(principal, key):
        rec = journal.lookup_key(principal, key) or journal.create(...)
    journal.transition(rec, "dispatching", barrier=True)

Thread-safety: one event loop; methods are synchronous except :meth:`wait` and :meth:`admission`.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import secrets
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable, Iterable
from typing import Any

from bhms.protocol.canonical import canonical, digest
from bhms.protocol.errors import BhmsError
from bhms.protocol.types import SETTLED_STATES, TERMINAL_STATES
from bhms.runtime.store import Store, StoredOperation

TRANSITIONS: dict[str, frozenset[str]] = {
    "accepted": frozenset({"dispatching", "rejected", "canceled"}),
    "dispatching": frozenset({"running", "completed", "failed", "canceled", "unknown"}),
    "running": frozenset({"completed", "failed", "canceled", "unknown"}),
    "unknown": frozenset({"running", "completed", "failed", "canceled"}),
    "completed": frozenset(), "failed": frozenset(), "canceled": frozenset(), "rejected": frozenset(),
}
_EFFECTS = frozenset({"none", "verified", "unverified", "unknown"})
_DISPATCHED = frozenset({"dispatching", "running", "unknown", "completed", "failed"})
_EFFECT_RANK = {"none": 0, "reversible": 1, "irreversible": 2, "hazardous": 3}
_INTENT_INVOKE = ("deviceId", "action", "arguments", "deadlineMs", "require", "descriptionDigest")
_UNSET = object()


def _measured(evidence: dict[str, Any] | None) -> bool:
    """True for operation evidence that proves an effect: kind ``measured`` and a measured, valid observation."""
    if not evidence or evidence.get("kind") != "measured":
        return False
    observations = evidence.get("observations")
    return bool(observations) and all(o.get("evidence") == "measured" and o.get("quality") == "valid"
                                      for o in observations.values())


class InvalidTransition(RuntimeError):
    """A change the state machine of §6.3 forbids; nothing was written."""


def now_ns() -> int:
    return time.time_ns()


def iso(ns: int) -> str:
    """RFC 3339 UTC with microseconds (``Time`` of the schema)."""
    seconds, rest = divmod(ns, 1_000_000_000)
    t = time.gmtime(seconds)
    return (f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}T{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"
            f".{rest // 1000:06d}Z")


def new_id(prefix: str) -> str:
    """A server-minted identifier (BHMS-LIF-031): time-ordered, unguessable."""
    return f"{prefix}-{time.time_ns():x}{secrets.token_hex(5)}"


def intent_digest(method: str, params: dict[str, Any]) -> str:
    """``requestDigest`` of a request (§6.4): the intent object with arguments exactly as sent, absent members omitted.

    ``actions/invoke``: ``{method, deviceId, action, arguments, deadlineMs?, require?, descriptionDigest?}``;
    ``programs/run``: ``{method, digest, arguments, deadlineMs?}`` where ``digest`` is the program digest
    (``params["digest"]``, or the digest of ``params["program"]``).
    """
    if method == "actions/invoke":
        intent = {k: params[k] for k in _INTENT_INVOKE if k in params and params[k] is not None}
    elif method == "programs/run":
        program_digest = params.get("digest") or digest(params["program"])
        intent = {"digest": program_digest, "arguments": params.get("arguments", {})}
        if params.get("deadlineMs") is not None:
            intent["deadlineMs"] = params["deadlineMs"]
    else:
        raise ValueError(f"{method} has no intent")
    intent["method"] = method
    return digest(intent)


def derived_key(parent_id: str, execution_path: str) -> str:
    """Program-step key (BHMS-PRG-010): ``"d-"`` + first 40 hex digits of sha256(parent + "/" + path)."""
    return "d-" + hashlib.sha256(f"{parent_id}/{execution_path}".encode()).hexdigest()[:40]


def server_key() -> str:
    """A key for a request that carried none (BHMS-OPS-035); never retry-safe."""
    return "s-" + secrets.token_hex(12)


def key_conflict_error(rec: OperationRecord, key: str) -> BhmsError:
    """``KEY_CONFLICT`` for a key that names ``rec`` with a different intent (BHMS-OPS-031, BHMS-OPS-040)."""
    error = rec.op.get("error")
    acted = error["mayHaveActed"] if error else rec.dispatched
    return BhmsError(
        "KEY_CONFLICT", f"operationKey {key} already names operation {rec.id} with a different request",
        field="operationKey", operation_id=rec.id, may_have_acted=acted,
        hint=f"inspect {rec.id} with operations/get first: it may be the same intent sent in a different form "
             "(for example a quantity object instead of a number, or another deadlineMs); use a new operationKey "
             "only for a genuinely new intent")


def unknown_error(cause: str) -> dict[str, Any]:
    """The uniform error of every transition into ``unknown`` (BHMS-OPS-004); ``cause`` becomes the message."""
    return BhmsError("DEADLINE_EXCEEDED", cause[:2000], may_have_acted=True, retry="after-reconcile",
                     hint="the device may or may not have acted: read its state (operations/get, properties/read) "
                          "or wait for reconciliation before deciding; a blind retry with a new key may act "
                          "twice").to_operation_error()


def program_effect(children: Iterable[OperationRecord]) -> str:
    """Aggregate effect of a program from its children (BHMS-PRG-016)."""
    effectful = [c for c in children if c.private.get("effectClass", "none") != "none" and c.dispatched]
    if not effectful:
        return "none"
    if any(c.state == "unknown" or c.op["effect"] == "unknown" for c in effectful):
        return "unknown"
    if all(c.op["effect"] == "verified" for c in effectful):
        return "verified"
    return "unverified"


def most_severe(effects: Iterable[str]) -> str:
    return max(effects, key=lambda e: _EFFECT_RANK[e], default="none")


class OperationRecord:
    """In-memory mirror of one operation: the wire object (without history), history, owner and private data.

    ``private`` holds server-side facts that are not on the wire: ``resources``, ``effectClass``, ``deadlineNs``.
    """

    __slots__ = ("op", "_history", "principal", "private", "_settled", "created_ns", "_journal")

    def __init__(self, op: dict[str, Any], history: list[dict[str, Any]] | None, principal: str,
                 private: dict[str, Any], created_ns: int, journal: Journal | None = None) -> None:
        self._journal = journal
        self.op = op
        self._history = history
        self.principal = principal
        self.private = private
        self._settled: asyncio.Event | None = None
        self.created_ns = created_ns

    @property
    def id(self) -> str:
        return self.op["operationId"]

    @property
    def state(self) -> str:
        return self.op["state"]

    @property
    def settled(self) -> bool:
        return self.op["state"] in SETTLED_STATES

    @property
    def terminal(self) -> bool:
        return self.op["state"] in TERMINAL_STATES

    @property
    def dispatched(self) -> bool:
        """Whether the operation ever reached ``dispatching`` (so a device may have acted)."""
        if self.op["state"] in ("dispatching", "running", "unknown"):
            return True
        return bool(self.private.get("dispatched"))

    @property
    def resources(self) -> tuple[str, ...]:
        return tuple(self.private.get("resources", ()))

    def wire(self, *, history: bool = False) -> dict[str, Any]:
        """The ``Operation`` wire object; with ``history`` the full history (loaded from the store if needed)."""
        if not history:
            return dict(self.op)
        if self._history is None and self._journal is not None:
            self._history = self._journal.store.history(self.id)
        return {**self.op, "history": list(self._history or [])}


class Journal:
    """The durable operation journal; see the module docstring.

    ``listeners`` are called as ``listener(record, wire_without_history)`` after every committed change of state,
    cancel state or effect (BHMS-OPS-090). ``on_unknown`` is called with each record that enters ``unknown``
    (events, BHMS-EVT-002). ``on_settled`` is called when an operation settles (resource release, programs).
    """

    def __init__(self, store: Store, *, cache_size: int = 4096) -> None:
        self.store = store
        self.listeners: list[Callable[[OperationRecord, dict[str, Any]], None]] = []
        self.on_unknown: list[Callable[[OperationRecord], None]] = []
        self.on_settled: list[Callable[[OperationRecord], None]] = []
        self._live: dict[str, OperationRecord] = {}
        self._recent: OrderedDict[str, OperationRecord] = OrderedDict()
        self._cache_size = cache_size
        self._admissions: dict[tuple[str, str], tuple[asyncio.Lock, int]] = {}
        self._cursor_tag = hashlib.sha256(f"ops:{store.epoch}".encode()).hexdigest()[:8]

    unknown_error = staticmethod(unknown_error)

    # ------------------------------------------------------------------ lookup

    def _remember(self, rec: OperationRecord) -> OperationRecord:
        if rec.settled:
            self._live.pop(rec.id, None)
            self._recent[rec.id] = rec
            self._recent.move_to_end(rec.id)
            while len(self._recent) > self._cache_size:
                self._recent.popitem(last=False)
        else:
            self._live[rec.id] = rec
        return rec

    def _load(self, row: StoredOperation | None) -> OperationRecord | None:
        if row is None:
            return None
        found = self._live.get(row.id) or self._recent.get(row.id)
        if found is not None:
            return found
        return self._remember(OperationRecord(row.record, None, row.principal, row.private, row.created_ns, self))

    def get(self, op_id: str) -> OperationRecord | None:
        """The operation with ``op_id`` (live object when in memory) or None."""
        found = self._live.get(op_id) or self._recent.get(op_id)
        if found is not None:
            return found
        return self._load(self.store.get_operation(op_id))

    def lookup_key(self, principal: str, key: str) -> OperationRecord | None:
        """The operation ``(principal, key)`` names, if any (BHMS-OPS-030, BHMS-OPS-033)."""
        return self._load(self.store.find_key(principal, key))

    def history(self, rec: OperationRecord) -> list[dict[str, Any]]:
        if rec._history is None:
            rec._history = self.store.history(rec.id)
        return rec._history

    def live(self) -> list[OperationRecord]:
        """Operations not yet settled (in creation order)."""
        return sorted(self._live.values(), key=lambda r: (r.created_ns, r.id))

    def children(self, parent_id: str) -> list[OperationRecord]:
        return [r for r in (self._load(row) for row in self.store.children(parent_id)) if r is not None]

    @contextlib.asynccontextmanager
    async def admission(self, principal: str, key: str) -> AsyncIterator[None]:
        """Serialise admissions of one ``(principal, key)`` so concurrent identical requests create one operation."""
        slot = (principal, key)
        lock, users = self._admissions.get(slot, (None, 0))
        if lock is None:
            lock = asyncio.Lock()
        self._admissions[slot] = (lock, users + 1)
        try:
            async with lock:
                yield
        finally:
            lock_now, count = self._admissions[slot]
            if count <= 1:
                del self._admissions[slot]
            else:
                self._admissions[slot] = (lock_now, count - 1)

    # ------------------------------------------------------------------ creation

    def create(self, *, principal: str, key: str, key_origin: str, kind: str, request_digest: str,
               arguments: dict[str, Any], private: dict[str, Any], device_id: str | None = None,
               action: str | None = None, program_digest: str | None = None, parent_id: str | None = None,
               admitted: dict[str, Any] | None = None, require: dict[str, Any] | None = None,
               lease_id: str | None = None, fence: int | None = None, deadline_ns: int | None = None,
               progress: dict[str, int] | None = None, dispatch: bool = False,
               barrier: bool | None = None) -> OperationRecord:
        """Durably record a new ``accepted`` operation (and, with ``dispatch``, ``dispatching`` in the same barrier
        commit; ``barrier`` defaults to ``dispatch``: a device server must have the intent on stable storage before it
        acts, a gateway relies on its deterministic upstream key instead and passes ``False``). Raises
        :class:`~bhms.runtime.store.StoreError` when it cannot be written (no operation exists)."""
        created = now_ns()
        at = iso(created)
        op: dict[str, Any] = {"operationId": new_id("op"), "operationKey": key, "keyOrigin": key_origin,
                              "kind": kind}
        if device_id is not None:
            op["deviceId"] = device_id
        if action is not None:
            op["action"] = action
        if program_digest is not None:
            op["programDigest"] = program_digest
        if parent_id is not None:
            op["parentOperationId"] = parent_id
        op["arguments"] = arguments
        if admitted is not None and admitted != arguments:
            op["admittedArguments"] = admitted
        op.update(requestDigest=request_digest, state="accepted", cancel={"state": "none"}, effect="none")
        if require is not None:
            op["require"] = require
        if lease_id is not None:
            op["leaseId"] = lease_id
        if fence is not None:
            op["fence"] = fence
        if deadline_ns is not None:
            op["deadlineAt"] = iso(deadline_ns)
            private = {**private, "deadlineNs": deadline_ns}
        if progress is not None:
            op["progress"] = progress
        op["createdAt"] = op["updatedAt"] = at
        history = [{"seq": 1, "at": at, "kind": "state", "state": "accepted"}]
        accepted = dict(op)
        if dispatch:
            op["state"] = "dispatching"
            private = {**private, "dispatched": True}
            entry: dict[str, Any] = {"seq": 2, "at": at, "kind": "state", "state": "dispatching"}
            if private.get("effectClass", "none") != "none":
                op["effect"] = entry["effect"] = "unknown"
            history.append(entry)
        with self.store.transaction(barrier=dispatch if barrier is None else barrier):
            self.store.insert_operation(op_id=op["operationId"], principal=principal, key=key,
                                        request_digest=request_digest, kind=kind, device_id=device_id,
                                        parent_id=parent_id, state=op["state"], created_ns=created, record=op,
                                        private=private, history=history)
        rec = self._remember(OperationRecord(op, history, principal, private, created, self))
        self._notify(rec, accepted)
        if dispatch:
            self._notify(rec)
        return rec

    # ------------------------------------------------------------------ changes

    def transition(self, rec: OperationRecord, state: str, *, error: dict[str, Any] | None = None,
                   result: Any = _UNSET, effect: str | None = None, evidence: dict[str, Any] | None = None,
                   detail: str | None = None, kind: str = "state", barrier: bool | None = None,
                   proof: str | None = None, cancel: str | None = None) -> None:
        """Move ``rec`` to ``state``; see the module docstring for the rules. Writes one history entry.

        ``barrier`` defaults to True for ``dispatching``. ``proof`` names device evidence that no effect occurred
        (required for a dispatched failure with ``mayHaveActed: false``). ``cancel`` sets ``cancel.state`` in the
        same entry (``confirmed`` on a termination observed after a cancel request).
        """
        current = rec.op["state"]
        if state not in TRANSITIONS[current]:
            raise InvalidTransition(f"{rec.id}: {current} -> {state} is not allowed (BHMS-OPS-001/002)")
        if current == "unknown" and (kind != "reconciliation" or not detail):
            raise InvalidTransition(f"{rec.id}: leaving unknown needs a reconciliation entry naming its evidence "
                                    "(BHMS-OPS-005)")
        op = dict(rec.op)
        new_effect = effect
        effect_class = rec.private.get("effectClass", "none")
        if state == "unknown":
            if not error or error.get("bhmsCode") != "DEADLINE_EXCEEDED" or error.get("mayHaveActed") is not True \
                    or error.get("retry") != "after-reconcile":
                raise InvalidTransition(f"{rec.id}: entering unknown needs DEADLINE_EXCEEDED with mayHaveActed true "
                                        "and retry after-reconcile (BHMS-OPS-004)")
            new_effect = "unknown"
        elif state in ("failed", "rejected"):
            if not error:
                raise InvalidTransition(f"{rec.id}: {state} needs an error (BHMS-OPS-009)")
            if state == "rejected":
                if error.get("mayHaveActed"):
                    raise InvalidTransition(f"{rec.id}: rejected means no dispatch; mayHaveActed must be false")
                new_effect = "none"
            elif rec.dispatched and not error.get("mayHaveActed") and not proof:
                raise InvalidTransition(f"{rec.id}: a dispatched operation fails with mayHaveActed true unless device "
                                        "evidence proves no effect (BHMS-OPS-009); pass proof=")
        elif state == "canceled":
            if current == "accepted":
                new_effect = "none"
            cancel = "confirmed"
        elif state == "completed":
            if result is _UNSET:
                raise InvalidTransition(f"{rec.id}: completed needs a result (BHMS-OPS-008)")
            if new_effect is None:
                new_effect = "none" if effect_class == "none" else "unverified"
        elif state == "dispatching" and effect_class != "none" and new_effect is None:
            new_effect = "unknown"
        if new_effect is not None and new_effect not in _EFFECTS:
            raise InvalidTransition(f"{rec.id}: effect {new_effect!r} is not one of {', '.join(sorted(_EFFECTS))} "
                                    "(EffectCertainty)")
        if state == "completed":
            try:
                canonical(result)  # the journal and the wire carry JSON: refuse what cannot be recorded (BHMS-OPS-008)
            except BhmsError as exc:
                raise InvalidTransition(f"{rec.id}: the result is not JSON-serialisable: {exc}") from None
            if rec.op.get("require", {}).get("effect") == "verified" and new_effect != "verified":
                raise InvalidTransition(f"{rec.id}: the intent requires a verified effect; completed needs "
                                        "effect verified with measured evidence (BHMS-OPS-006)")
            op["result"] = result
        if new_effect == "verified" and not _measured(evidence if evidence is not None else rec.op.get("evidence")):
            raise InvalidTransition(f"{rec.id}: effect verified needs evidence of kind measured with at least one "
                                    "observation (BHMS-OPS-006)")
        if state in ("failed", "rejected", "unknown"):
            op["error"] = error
        else:
            op.pop("error", None)
        entry: dict[str, Any] = {"kind": kind, "state": state}
        if new_effect is not None and new_effect != op["effect"]:
            op["effect"] = entry["effect"] = new_effect
        if cancel is not None and cancel != op["cancel"]["state"]:
            op["cancel"] = {**op["cancel"], "state": cancel}
            entry["cancel"] = cancel
        if evidence is not None:
            op["evidence"] = evidence
        if detail or proof:
            entry["detail"] = (detail or proof or "")[:1000]
        op["state"] = state
        private = None
        if state == "dispatching" and not rec.private.get("dispatched"):
            private = {**rec.private, "dispatched": True}
        self._commit(rec, op, entry, barrier=state == "dispatching" if barrier is None else barrier, private=private)
        if state == "unknown":
            for hook in self.on_unknown:
                hook(rec)
        if current == "unknown" and rec.op.get("parentOperationId"):
            self._settle_parent_after_reconcile(rec.op["parentOperationId"])

    def set_cancel(self, rec: OperationRecord, cancel_state: str, *, reason: str | None = None,
                   detail: str | None = None) -> None:
        """Change ``cancel.state`` (``requested``/``acknowledged``/``refused``); a late change never touches a
        terminal ``state`` (BHMS-OPS-052)."""
        if rec.op["cancel"]["state"] == cancel_state:
            return
        op = dict(rec.op)
        cancel = {"state": cancel_state}
        if cancel_state == "requested":
            if reason:
                cancel["reason"] = reason[:500]
            cancel["requestedAt"] = iso(now_ns())
        else:
            cancel.update({k: v for k, v in rec.op["cancel"].items() if k != "state"})
        op["cancel"] = cancel
        entry: dict[str, Any] = {"kind": "cancel", "cancel": cancel_state}
        if detail:
            entry["detail"] = detail[:1000]
        self._commit(rec, op, entry)

    def set_effect(self, rec: OperationRecord, effect: str, *, detail: str | None = None,
                   evidence: dict[str, Any] | None = None) -> None:
        """Change ``effect`` of a non-terminal operation (an ``evidence`` entry)."""
        if rec.terminal:
            raise InvalidTransition(f"{rec.id}: the effect of a terminal operation never changes; append a "
                                    "correction (BHMS-OPS-002)")
        op = dict(rec.op)
        entry: dict[str, Any] = {"kind": "evidence" if evidence is not None else "effect"}
        if effect != op["effect"]:
            op["effect"] = entry["effect"] = effect
        if evidence is not None:
            op["evidence"] = evidence
        if detail:
            entry["detail"] = detail[:1000]
        self._commit(rec, op, entry)

    def annotate(self, rec: OperationRecord, kind: str, detail: str | None = None, *, step_index: int | None = None,
                 child_operation_id: str | None = None, progress: dict[str, int] | None = None) -> None:
        """Append a non-state entry (``step``, ``stop``, ``lease``, ``correction``, ``evidence``) without changing
        state, result or effect."""
        if kind in ("state", "cancel", "effect", "reconciliation"):
            raise ValueError(f"{kind} entries are written by transition/set_cancel/set_effect")
        op = dict(rec.op)
        entry: dict[str, Any] = {"kind": kind}
        if detail:
            entry["detail"] = detail[:1000]
        if step_index is not None:
            entry["stepIndex"] = step_index
        if child_operation_id is not None:
            entry["childOperationId"] = child_operation_id
        if progress is not None:
            op["progress"] = progress
        self._commit(rec, op, entry, notify=False)

    def mark_private(self, rec: OperationRecord, **values: Any) -> None:
        """Persist server-private facts of an operation (for example ``inhibitionLifted``) without a history entry."""
        private = {**rec.private, **values}
        with self.store.transaction():
            self.store.update_operation(rec.id, state=rec.state, updated_ns=now_ns(), record=rec.op, private=private)
        rec.private = private

    def set_progress(self, rec: OperationRecord, progress: dict[str, int]) -> None:
        """Update ``progress`` in memory; it is persisted with the next history entry (not durable by itself)."""
        if not rec.settled:
            rec.op = {**rec.op, "progress": progress}

    def _commit(self, rec: OperationRecord, op: dict[str, Any], entry: dict[str, Any], *, barrier: bool = False,
                private: dict[str, Any] | None = None, notify: bool = True) -> None:
        history = self.history(rec)
        stamp = now_ns()
        entry = {"seq": len(history) + 1, "at": iso(stamp), **entry}
        op["updatedAt"] = entry["at"]
        with self.store.transaction(barrier=barrier):
            self.store.update_operation(rec.id, state=op["state"], updated_ns=stamp, record=op, history=[entry],
                                        private=private)
        rec.op = op
        if private is not None:
            rec.private = private
        history.append(entry)
        self._remember(rec)
        if notify:
            self._notify(rec)
        if rec.settled:
            if rec._settled is not None:
                rec._settled.set()
            for hook in self.on_settled:
                hook(rec)

    def _notify(self, rec: OperationRecord, wire: dict[str, Any] | None = None) -> None:
        if self.listeners:
            wire = wire if wire is not None else rec.wire()
            for listener in list(self.listeners):
                listener(rec, wire)

    # ------------------------------------------------------------------ waiting and listing

    async def wait(self, rec: OperationRecord, timeout: float) -> OperationRecord:
        """Return when ``rec`` is settled or after ``timeout`` seconds, whichever is first (BHMS-OPS-060)."""
        live = self._live.get(rec.id, rec)
        if live.settled or timeout <= 0:
            return live
        if live._settled is None:
            live._settled = asyncio.Event()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(live._settled.wait(), timeout)
        return live

    def _cursor(self, row: StoredOperation) -> str:
        raw = f"{row.created_ns}:{row.id}".encode()
        return f"o.{self._cursor_tag}.{base64.urlsafe_b64encode(raw).decode().rstrip('=')}"

    def _parse_cursor(self, cursor: str) -> tuple[int, str]:
        try:
            prefix, tag, body = cursor.split(".", 2)
            if prefix != "o" or tag != self._cursor_tag:
                raise ValueError
            created, op_id = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode().split(":", 1)
            return int(created), op_id
        except ValueError:
            raise BhmsError("INVALID_ARGUMENT", "cursor is not an operations/list cursor of this server",
                            field="cursor", hint="pass nextCursor exactly as returned, or omit cursor to start "
                                                 "from the newest operation (BHMS-LIF-060)") from None

    def list(self, *, principal: str | None, limit: int, after: str | None = None, device_id: str | None = None,
             state: str | None = None, parent_id: str | None = None) -> tuple[list[dict[str, Any]], str | None]:
        """One page of operations visible to ``principal`` (None = admin) and the next cursor (BHMS-LIF-061/062)."""
        position = self._parse_cursor(after) if after is not None else None
        rows = self.store.list_operations(principal=principal, device_id=device_id, state=state, parent_id=parent_id,
                                          after=position, limit=limit + 1)
        more = len(rows) > limit
        rows = rows[:limit]
        page = []
        for row in rows:
            live = self._live.get(row.id)
            page.append(live.wire() if live is not None else row.record)
        return page, (self._cursor(rows[-1]) if more and rows else None)

    # ------------------------------------------------------------------ recovery

    def recover(self) -> list[OperationRecord]:
        """Settle what a crash left in flight (BHMS-OPS-080, BHMS-PRG-017); returns the changed records."""
        changed: list[OperationRecord] = []
        rows = self.store.operations_in_states(["accepted", "dispatching", "running"])
        records = [r for r in (self._load(row) for row in rows) if r is not None]
        for rec in records:
            if rec.op["kind"] != "action":
                continue
            if rec.state == "accepted":
                self.transition(rec, "rejected", error=BhmsError(
                    "INTERNAL", "the server restarted before dispatch; nothing was sent to the device",
                    may_have_acted=False, hint="no effect occurred; send the request again (a new operationKey is "
                                               "safe)").to_operation_error())
            else:
                self.transition(rec, "unknown", error=unknown_error(
                    f"the server restarted while the operation was {rec.state}; the device may have acted"))
            changed.append(rec)
        for rec in records:
            if rec.op["kind"] == "program":
                self._settle_program_after_restart(rec)
                changed.append(rec)
        # A crash between the last child's reconciliation commit and the program's own settle leaves a program
        # ``unknown`` although every child is resolved (BHMS-PRG-017).
        for row in self.store.operations_in_states(["unknown"]):
            if row.record.get("kind") == "program":
                parent = self.get(row.id)
                if parent is not None and parent.state == "unknown":
                    self._settle_parent_after_reconcile(parent.id)
                    if parent not in changed:
                        changed.append(parent)
        return changed

    def _step_summary(self, rec: OperationRecord) -> tuple[int | None, list[OperationRecord]]:
        steps = [h for h in self.history(rec) if h["kind"] == "step"]
        children = self.children(rec.id)
        by_id = {c.id: c for c in children}
        last_completed = None
        for index, entry in enumerate(steps):
            child = by_id.get(entry.get("childOperationId", ""))
            finished = index + 1 < len(steps) or (child is not None and child.state == "completed")
            if finished:
                last_completed = entry.get("stepIndex")
        return last_completed, children

    def _settle_program_after_restart(self, rec: OperationRecord) -> None:
        children = self.children(rec.id)
        if rec.state == "accepted":
            if not children:
                self.transition(rec, "rejected", error=BhmsError(
                    "INTERNAL", "the server restarted before the program's first step", may_have_acted=False,
                    hint="no step ran; run the program again").to_operation_error())
                return
            # A child exists although the program never recorded dispatching: consult the children, not the parent.
            self.transition(rec, "dispatching")
        last, children = self._step_summary(rec)
        if any(c.state == "unknown" for c in children):
            self.transition(rec, "unknown", error=unknown_error(
                "the server restarted during the program while a step's outcome is unknown"))
            return
        self._fail_program_internal(rec, last, children, kind="state", detail=None)

    def _fail_program_internal(self, rec: OperationRecord, last: int | None, children: list[OperationRecord], *,
                               kind: str, detail: str | None) -> None:
        acted = any(c.dispatched and c.private.get("effectClass", "none") != "none" for c in children)
        where = f"the last completed step is stepIndex {last}" if last is not None else "no step completed"
        error = BhmsError("INTERNAL", "server restarted during the program", may_have_acted=acted,
                          hint=f"{where}; inspect the child operations (operations/list parentOperationId) before "
                               "running a compensating program; programs are never resumed").to_operation_error()
        self.transition(rec, "failed", error=error, effect=program_effect(children), kind=kind, detail=detail,
                        proof=None if acted else "no effectful step was dispatched")

    def _settle_parent_after_reconcile(self, parent_id: str) -> None:
        parent = self.get(parent_id)
        if parent is None or parent.state != "unknown" or parent.op["kind"] != "program":
            return
        last, children = self._step_summary(parent)
        if any(c.state == "unknown" for c in children):
            return
        self._fail_program_internal(parent, last, children, kind="reconciliation",
                                    detail="every unknown child operation was reconciled (BHMS-PRG-017)")


__all__ = ["TRANSITIONS", "InvalidTransition", "Journal", "OperationRecord", "derived_key", "intent_digest", "iso",
           "key_conflict_error", "most_severe", "new_id", "now_ns", "program_effect", "server_key", "unknown_error"]
