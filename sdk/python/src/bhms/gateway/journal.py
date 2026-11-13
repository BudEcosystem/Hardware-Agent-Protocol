"""The gateway's forwarding journal (spec/bhms/07-leases-and-authority.md BHMS-AUTH-014, 06-operations.md §6.4, §6.9).

The gateway is a BHMS server, so the operations it admits are ordinary records of the one runtime store
(:class:`~bhms.runtime.operations.Journal` over :class:`~bhms.runtime.store.Store`; there is no second persistence layer).
:class:`ForwardJournal` adds what forwarding needs:

* :func:`upstream_key` — the deterministic key a client's ``operationKey`` becomes upstream:
  ``"g-" + lowercase base32(sha256(gateway_id "\\n" principal "\\n" client_key))[:26]`` (130 bits). It depends only on
  the gateway's identity, the client principal and the client's key, so a restarted gateway re-sends the *same* upstream
  key and the upstream deduplicates (BHMS-OPS-030); two principals (or two gateways) sending the same client key cannot
  collide.
* :meth:`ForwardJournal.admit` — the intent is durable in the ``dispatching`` state (a barrier commit) *before* anything
  is sent upstream (BHMS-OPS-003), together with the exact upstream request, so an in-doubt forward can be re-sent verbatim.
* :meth:`ForwardJournal.mirror` — applies an upstream operation snapshot to the gateway's record along the legal
  transitions of §6.3 only: ``accepted`` upstream (queued) is ``dispatching`` here, ``rejected`` upstream is ``failed`` with
  proof of no effect (a dispatched operation cannot be ``rejected``), a stale snapshot never regresses a state, and
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
import hashlib
import logging
from typing import Any

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

    def _record(self, *, principal: str, key: str, key_origin: str, request_digest: str, arguments: dict[str, Any],
                device_id: str, action: str, private: dict[str, Any], require: dict[str, Any] | None,
                lease_id: str | None, fence: int | None, deadline_ns: int | None,
                admitted: dict[str, Any] | None) -> OperationRecord:
        """Record a request the gateway has forwarded: ``accepted`` then ``dispatching`` (the command left for the
        upstream), without fsync barriers — the deterministic upstream key, not this record, is what makes a lost
        record harmless (see the module docstring)."""
        rec = self.create(principal=principal, key=key, key_origin=key_origin, kind="action",
                          request_digest=request_digest, arguments=arguments, private=private, device_id=device_id,
                          action=action, admitted=admitted, require=require, lease_id=lease_id, fence=fence,
                          deadline_ns=deadline_ns)
        self.transition(rec, "dispatching", barrier=False)
        return rec

    def admit_forwarded(self, *, upstream_op: dict[str, Any], **request: Any) -> OperationRecord:
        """Record an operation the upstream admitted, in the state the upstream reports."""
        rec = self._record(**request)
        self.mirror(rec, upstream_op, source="forward reply")
        return rec

    def admit_in_doubt(self, *, cause: str, **request: Any) -> OperationRecord:
        """Record a forward whose answer was lost: the operation is ``unknown`` (BHMS-OPS-004) and is reconciled by
        re-sending the same upstream key once the upstream answers."""
        rec = self._record(**request)
        self.link_lost(rec, cause)
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
            if theirs in ("accepted", "dispatching", None) or (current == "unknown" and theirs == "unknown"):
                pass  # still queued or still unknown upstream: nothing new to record
            elif current == "running" and theirs == "running":
                pass  # a stale or repeated snapshot never regresses or repeats a state
            else:
                self._advance(rec, upstream_op, theirs, source)
                changed = True
            if not rec.terminal:
                changed = self._sync_cancel_and_effect(rec, upstream_op) or changed
        except InvalidTransition as exc:
            log.error("cannot mirror upstream state %s onto %s (%s): %s", theirs, rec.id, rec.state, exc)
            self.annotate(rec, "correction", f"upstream reported {theirs} but the gateway could not apply it: {exc}")
        return changed

    def _advance(self, rec: OperationRecord, up: dict[str, Any], theirs: str, source: str) -> None:
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

    def _sync_cancel_and_effect(self, rec: OperationRecord, up: dict[str, Any]) -> bool:
        changed = False
        cancel = up.get("cancel") or {}
        state = cancel.get("state", "none")
        if state != "none" and rec.op["cancel"]["state"] != state and state != "confirmed":
            self.set_cancel(rec, state, reason=cancel.get("reason"))
            changed = True
        effect = up.get("effect")
        if effect and effect != rec.op["effect"] and not rec.terminal and rec.state != "unknown":
            try:
                self.set_effect(rec, effect, evidence=up.get("evidence"))
                changed = True
            except InvalidTransition:
                pass
        return changed

    def link_lost(self, rec: OperationRecord, cause: str) -> bool:
        """Move a ``dispatching``/``running`` operation to ``unknown`` because the upstream link failed (BHMS-OPS-004)."""
        if rec.state not in ("dispatching", "running"):
            return False
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
