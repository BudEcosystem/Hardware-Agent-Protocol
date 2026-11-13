"""The gateway's forwarding journal (spec/bhms/07-leases-and-authority.md BHMS-AUTH-014, 06-operations.md §6.4, §6.9).

The gateway is a BHMS server, so the operations it admits are ordinary records of the one runtime store
(:class:`~bhms.runtime.operations.Journal` over :class:`~bhms.runtime.store.Store`; there is no second persistence layer).
:class:`ForwardJournal` adds what forwarding needs:

* :func:`upstream_key` — the deterministic key a client's ``operationKey`` becomes upstream:
  ``"g-" + lowercase base32(sha256(gateway_id "\\n" principal "\\n" client_key))[:26]`` (130 bits). It depends only on
  the gateway's identity, the client principal and the client's key, so a restarted gateway re-sends the *same* upstream
  key and the upstream deduplicates (BHMS-OPS-030); two principals (or two gateways) sending the same client key cannot
  collide.
* :meth:`ForwardJournal.pending_put` — the intent is durable (a barrier commit) *before* anything is sent upstream
  (BHMS-OPS-003): a private *pending-forward* row keyed by ``(principal, client key)`` with the exact upstream request, the
  derived upstream key, the upstream's epoch and the resources. It is deleted when the upstream refuses before creating
  anything (BHMS-OPS-040: refusals create no operation), promoted to the visible operation in the same transaction as the
  answer is recorded (:meth:`admit_forwarded` / :meth:`admit_in_doubt`), and converted to an ``unknown`` operation by
  :meth:`convert_pending` when a same-key retry or a restart finds it (BHMS-OPS-033, BHMS-OPS-080). So a crash between send
  and answer leaves an operation (``unknown``, resources inhibited) that is reconciled by re-sending the same upstream key.
* :meth:`ForwardJournal.mirror` — applies an upstream operation snapshot to the gateway's record along the legal
  transitions of §6.3 only: ``accepted`` upstream (queued) is ``accepted`` here, ``rejected`` upstream is ``rejected`` here while
  the gateway's record is still ``accepted`` (an operation the gateway already showed as ``dispatching`` can only end
  ``failed`` with proof of no effect), a stale snapshot never regresses a state, and
  leaving ``unknown`` is a ``reconciliation`` entry naming the upstream as evidence (BHMS-OPS-005).
* :meth:`ForwardJournal.recover_forwarded` — after a restart every operation found ``dispatching`` or ``running`` is
  ``unknown`` (BHMS-OPS-080) until the router reconciles it with the upstream; the stock ``Journal.recover`` (which
  rejects ``accepted`` operations) is not used.

Private facts kept per operation (``rec.private``): ``upstream`` (name), ``upstreamDeviceId``, ``upstreamKey``,
``upstreamRequest`` (params as forwarded, without ``_meta``), ``upstreamOperationId`` (once known), ``upstreamEpoch`` (the
upstream's epoch at forward time: a re-send is only safe while it is unchanged, BHMS-OPS-081), ``resources`` (gateway
resource ids), ``effectClass``, ``cancelRequested``.

Thread-safety: one event loop.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import logging
from collections.abc import Iterator
from typing import Any

import orjson

from bhms.protocol.errors import BhmsError
from bhms.runtime.operations import InvalidTransition, Journal, OperationRecord, unknown_error

log = logging.getLogger("bhms.gateway.journal")



def upstream_key(gateway_id: str, principal: str, client_key: str) -> str:
    """The upstream ``operationKey`` for ``client_key`` sent by ``principal`` through gateway ``gateway_id``.

    Pinned by BHMS-AUTH-014: ``"g-" + base32(sha256(gateway_id + "\\n" + principal + "\\n" + client_key))[:26]``,
    lowercase, no padding (28 characters; a valid ``operationKey``).
    """
    raw = hashlib.sha256(f"{gateway_id}\n{principal}\n{client_key}".encode()).digest()
    return "g-" + base64.b32encode(raw).decode().rstrip("=").lower()[:26]


class ForwardJournal(Journal):
    """The journal of forwarded operations; see the module docstring."""

    # ------------------------------------------------------------------ pending forwards

    @staticmethod
    def _pending_key(principal: str, key: str) -> str:
        return f"pending:{principal}\n{key}"

    def __init__(self, *args: Any, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.on_discard: list[Any] = []  # called with each record a failed unit of work created
        self._deferred = None
        self._unit_records = []

    def pending_put(self, principal: str, key: str, request: dict[str, Any]) -> None:
        """Durably record the intent to forward ``request`` (everything :meth:`admit_in_doubt` needs) before sending."""
        with self.store.transaction(barrier=True):
            self.store.meta_set(self._pending_key(principal, key), orjson.dumps(request).decode())

    def pending_get(self, principal: str, key: str) -> dict[str, Any] | None:
        raw = self.store.meta_get(self._pending_key(principal, key))
        return orjson.loads(raw) if raw else None

    def pending_delete(self, principal: str, key: str) -> None:
        self.store.meta_delete(self._pending_key(principal, key))

    def pending_all(self) -> dict[str, dict[str, Any]]:
        return {k: orjson.loads(v) for k, v in self.store.meta_prefix("pending:").items() if v}

    @contextlib.contextmanager
    def _unit(self) -> Iterator[None]:
        """One atomic unit of journal work. Listeners hear about its changes only after the commit, and if it fails the
        records it created are dropped from memory (``on_discard`` tells the owner), so a rolled-back admission leaves no
        phantom operation behind."""
        self._deferred: list[tuple[OperationRecord, dict[str, Any]]] | None = []
        self._unit_records: list[OperationRecord] = []
        try:
            with self.store.transaction():
                yield
        except BaseException:
            for rec in self._unit_records:
                self._live.pop(rec.id, None)
                self._recent.pop(rec.id, None)
                for hook in self.on_discard:
                    hook(rec)
            self._deferred = None
            raise
        deferred, self._deferred = self._deferred, None
        for rec, wire in deferred:
            super()._notify(rec, wire)

    def _notify(self, rec: OperationRecord, wire: dict[str, Any] | None = None) -> None:
        if getattr(self, "_deferred", None) is not None:
            self._deferred.append((rec, wire if wire is not None else rec.wire()))
        else:
            super()._notify(rec, wire)

    def create(self, **kw: Any) -> OperationRecord:
        rec = super().create(**kw)
        if getattr(self, "_deferred", None) is not None:
            self._unit_records.append(rec)
        return rec

    def convert_pending(self, principal: str, key: str) -> OperationRecord | None:
        """Turn a pending forward into an ``unknown`` operation (the answer was never recorded); None if there is none."""
        request = self.pending_get(principal, key)
        if request is None:
            return None
        with self._unit():
            rec = self._record(**request)
            self.link_lost(rec, f"the gateway has no recorded answer from upstream {rec.private.get('upstream')} for "
                                "this forward; the upstream may have acted and is asked to reconcile")
            self.pending_delete(principal, key)
        return rec

    def convert_all_pending(self) -> list[OperationRecord]:
        """After a restart: every forward that has no recorded answer becomes an ``unknown`` operation."""
        out = []
        for stored in self.store.meta_prefix("pending:"):
            principal, _, key = stored[len("pending:"):].partition("\n")
            rec = self.convert_pending(principal, key)
            if rec is not None:
                out.append(rec)
        return out

    def _record(self, *, principal: str, key: str, key_origin: str, request_digest: str, arguments: dict[str, Any],
                device_id: str, action: str, private: dict[str, Any], require: dict[str, Any] | None,
                lease_id: str | None, fence: int | None, deadline_ns: int | None,
                admitted: dict[str, Any] | None, dispatch: bool = True) -> OperationRecord:
        """Record a request the gateway has forwarded: ``accepted`` then, unless the upstream reports that it only queued
        it (``dispatch=False``), ``dispatching`` (the command left for the upstream). The durable intent is the pending-forward row written (with a barrier) before sending; this record
        replaces it in one transaction, so no barrier is needed here."""
        return self.create(principal=principal, key=key, key_origin=key_origin, kind="action",
                           request_digest=request_digest, arguments=arguments, private=private, device_id=device_id,
                           action=action, admitted=admitted, require=require, lease_id=lease_id, fence=fence,
                           deadline_ns=deadline_ns, dispatch=dispatch, barrier=False)

    def admit_forwarded(self, *, upstream_op: dict[str, Any], **request: Any) -> OperationRecord:
        """Record an operation the upstream admitted, in the state the upstream reports; the pending row goes away in
        the same transaction."""
        with self._unit():
            rec = self._record(**request, dispatch=upstream_op.get("state") != "accepted")
            self.mirror(rec, upstream_op, source="forward reply")
            self.pending_delete(request["principal"], request["key"])
        return rec

    def admit_in_doubt(self, *, cause: str, **request: Any) -> OperationRecord:
        """Record a forward whose answer was lost: the operation is ``unknown`` (BHMS-OPS-004) and is reconciled by
        re-sending the same upstream key once the upstream answers."""
        with self._unit():
            rec = self._record(**request)
            self.link_lost(rec, cause)
            self.pending_delete(request["principal"], request["key"])
        return rec

    # ------------------------------------------------------------------ mirroring

    def mirror(self, rec: OperationRecord, upstream_op: dict[str, Any], *, source: str) -> bool:
        """Apply an upstream operation snapshot to ``rec``; returns True when anything changed.

        ``source`` says where the evidence came from (``"forward reply"``, ``"notification"``, ``"operations/get"``)
        and is written into the history entry.
        """
        if rec.terminal:
            return False
        changed = False
        up_id = upstream_op.get("operationId")
        if up_id and rec.private.get("upstreamOperationId") != up_id:
            self.mark_private(rec, upstreamOperationId=up_id)
            changed = True
        current, theirs = rec.state, upstream_op.get("state")
        try:
            if theirs == "dispatching" and current == "accepted":
                self.transition(rec, "dispatching", detail=f"{source}: upstream {rec.private.get('upstream')} sent it to the device")
                changed = True
            elif theirs in ("accepted", "dispatching", None) or (current == "unknown" and theirs == "unknown"):
                pass  # still queued or still unknown upstream: nothing new to record
            elif current == "running" and theirs == "running":
                pass  # a stale or repeated snapshot never regresses or repeats a state
            else:
                self._advance(rec, upstream_op, theirs, source)
                changed = True
            if not rec.terminal:
                changed = self._sync_cancel(rec, upstream_op) or changed
        except InvalidTransition as exc:
            log.error("cannot mirror upstream state %s onto %s (%s): %s", theirs, rec.id, rec.state, exc)
            self.annotate(rec, "correction", f"upstream reported {theirs} but the gateway could not apply it: {exc}")
        return changed

    def _advance(self, rec: OperationRecord, up: dict[str, Any], theirs: str, source: str) -> None:
        if rec.state == "accepted":
            before_dispatch = theirs == "rejected" or (theirs == "canceled" and up.get("effect") == "none")
            if theirs == "rejected":
                error = dict(up.get("error") or BhmsError("INTERNAL", "the upstream rejected the operation without an error",
                                                          may_have_acted=False).to_operation_error())
                error["mayHaveActed"] = False
                self.transition(rec, "rejected", error=error, effect="none", kind="state",
                                proof=f"{source}: upstream {rec.private.get('upstream')} rejected it before dispatch (no effect)")
                return
            if not before_dispatch:
                self.transition(rec, "dispatching", detail=f"{source}: upstream {rec.private.get('upstream')} reports {theirs}")
        reconciling = rec.state == "unknown"
        kind = "reconciliation" if reconciling else "state"
        detail = f"{source}: upstream {rec.private.get('upstream')} reports {theirs}"
        evidence = up.get("evidence")
        effect = up.get("effect")
        if theirs == "running":
            self.transition(rec, "running", kind=kind, detail=detail if reconciling else None, effect=effect)
        elif theirs == "completed":
            self.transition(rec, "completed", result=up.get("result", {}), effect=effect, evidence=evidence, kind=kind,
                            detail=detail if reconciling else None)
        elif theirs in ("failed", "rejected"):
            error = dict(up.get("error") or BhmsError("INTERNAL", "the upstream reported a failure without an error",
                                                      may_have_acted=True).to_operation_error())
            proof = None
            if not error.get("mayHaveActed"):
                proof = f"{source}: upstream {rec.private.get('upstream')} reports no effect"
            if theirs == "rejected":
                proof = f"{source}: upstream {rec.private.get('upstream')} rejected the operation before dispatch " \
                        "(no effect); the gateway had already dispatched it, so it is recorded as failed"
                error["mayHaveActed"] = False
            self.transition(rec, "failed", error=error, effect="none" if theirs == "rejected" else effect,
                            evidence=evidence, kind=kind, detail=detail if reconciling else None, proof=proof)
        elif theirs == "canceled":
            self.transition(rec, "canceled", effect=effect, evidence=evidence, kind=kind,
                            detail=detail if reconciling else None)
        elif theirs == "unknown":
            error = up.get("error") or {}
            cause = error.get("message") or "the upstream reports the outcome as unknown"
            self.transition(rec, "unknown", error=unknown_error(f"upstream {rec.private.get('upstream')}: {cause}"))

    def _sync_cancel(self, rec: OperationRecord, up: dict[str, Any]) -> bool:
        """Mirror a cancellation request the upstream recorded (``requested``/``acknowledged``/``refused``). The effect is
        mirrored only with a state change: until then the gateway, which has already dispatched, keeps ``unknown``."""
        cancel = up.get("cancel") or {}
        state = cancel.get("state", "none")
        if state not in ("none", "confirmed") and rec.op["cancel"]["state"] != state:
            self.set_cancel(rec, state, reason=cancel.get("reason"))
            return True
        return False

    def link_lost(self, rec: OperationRecord, cause: str) -> bool:
        """Move a ``dispatching``/``running`` operation to ``unknown`` because the upstream link failed (BHMS-OPS-004)."""
        if rec.state not in ("accepted", "dispatching", "running"):
            return False
        if rec.state == "accepted":
            self.transition(rec, "dispatching", detail="the upstream link failed while the operation was queued upstream")
        self.transition(rec, "unknown", error=unknown_error(cause))
        return True

    # ------------------------------------------------------------------ recovery

    def recover_forwarded(self) -> list[OperationRecord]:
        """After a restart: every operation found in flight becomes ``unknown`` (BHMS-OPS-080); returns them."""
        moved = []
        for row in self.store.operations_in_states(["accepted", "dispatching", "running"]):
            rec = self._load(row)
            if rec is None:
                continue
            if rec.state == "accepted":
                self.transition(rec, "dispatching", detail="found accepted after a restart; it may have been forwarded")
            self.link_lost(rec, f"the gateway restarted while the operation was {rec.state}; the upstream may have "
                                "acted and is asked to reconcile")
            moved.append(rec)
        return moved

    def unknown_operations(self) -> list[OperationRecord]:
        """Every ``unknown`` operation (oldest first): what reconciliation works on."""
        found = [self._load(row) for row in self.store.operations_in_states(["unknown"])]
        return [rec for rec in found if rec is not None]


__all__ = ["ForwardJournal", "upstream_key"]
