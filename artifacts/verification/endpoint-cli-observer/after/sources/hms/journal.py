"""Single-owner experimental operation ledger; no transport or physical driver.

Policy, clock and evidence sources are trusted in-process services, never JSON
claims. The caller must supply them. This module is not an authentication server.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import asdict, dataclass
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Callable, Protocol
import uuid

from .contracts import (SAFE_INTEGER, canonical, identifier, intent_digest,
                        parse_invoke)

TERMINAL = {"completed", "failed", "canceled", "rejected_before_dispatch", "rejected_before_start"}
SUCCESSORS = {
    "dispatching": {"running", "completed", "failed", "canceled", "rejected_before_start", "outcome_unknown"},
    "running": {"completed", "failed", "canceled", "outcome_unknown"},
    "outcome_unknown": {"running", "completed", "failed", "canceled", "rejected_before_start"},
}


class JournalError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ObservationAgeExpired(JournalError):
    """Trusted policy: otherwise valid evidence has a known expired age.

    The public refusal remains OBSERVATION_STALE. Internal schedulers can wait
    for a new observation before admission, within the original deadline. This
    marker must not be used for unknown clocks, invalid quality or identity loss.
    """
    def __init__(self):
        super().__init__("OBSERVATION_STALE")


@dataclass(frozen=True)
class Context:
    principal: str
    deployment: str

    def __post_init__(self):
        identifier(self.principal, "principal")
        identifier(self.deployment, "deployment")


@dataclass(frozen=True)
class Admission:
    resources: tuple[str, ...]
    policy_revision: str
    lease_expires_ms: int


@dataclass(frozen=True)
class Evidence:
    kind: str
    source: str
    reference: str
    assertions: tuple[str, ...]

    def __post_init__(self):
        if (type(self.assertions) is not tuple or
                any(type(value) is not str for value in self.assertions)):
            raise JournalError("INVALID_EVIDENCE")

    def payload(self):
        if self.kind not in {"sensor", "controller", "simulation", "runtime"}:
            raise JournalError("INVALID_EVIDENCE")
        identifier(self.source)
        identifier(self.reference)
        allowed = {"running", "completed", "failed", "terminated", "cancel_ack",
                   "resources_quiescent", "physical_verified", "verification_failed", "disputed", "start_excluded"}
        if not self.assertions or set(self.assertions) - allowed:
            raise JournalError("INVALID_EVIDENCE")
        if "physical_verified" in self.assertions and self.kind not in {"sensor", "controller"}:
            raise JournalError("PHYSICAL_EVIDENCE_REQUIRED")
        if {"physical_verified", "verification_failed"} <= set(self.assertions):
            raise JournalError("CONTRADICTORY_VERIFICATION")
        return asdict(self) | {"assertions": list(self.assertions)}


@dataclass(frozen=True)
class Ticket:
    operation_id: str
    attempt_id: str
    owner_epoch: int


@dataclass(frozen=True)
class RecordTime:
    value: int
    status: str


class Policy(Protocol):
    def authorize(self, context: Context, verb: str, target: str) -> None:
        """Raise on denial. Context comes from the embedding authentication layer."""

    def admit(self, context: Context, intent: dict, now_ms: int) -> Admission:
        """Validate commissioned binding, arguments, physical rules and scopes."""

    def recheck(self, context: Context, operation: dict, now_ms: int) -> None:
        """Recheck current authority, binding, fresh preconditions and limits."""

    def evidence(self, operation: dict, evidence: Evidence) -> None:
        """Authenticate the evidence source and capability-specific assertions."""


_DDL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE series (
 principal TEXT NOT NULL, deployment TEXT NOT NULL, next_epoch INTEGER NOT NULL,
 floor INTEGER NOT NULL, last_expiry INTEGER NOT NULL,
 PRIMARY KEY(principal, deployment));
CREATE TABLE namespaces (
 token TEXT PRIMARY KEY, principal TEXT NOT NULL, deployment TEXT NOT NULL,
 epoch INTEGER NOT NULL, expires_ms INTEGER NOT NULL,
 UNIQUE(principal, deployment, epoch));
CREATE TABLE operations (
 id TEXT PRIMARY KEY, principal TEXT NOT NULL, deployment TEXT NOT NULL,
 digest TEXT NOT NULL, intent BLOB NOT NULL, admission BLOB NOT NULL,
 state TEXT NOT NULL, cancel_state TEXT NOT NULL, verification TEXT NOT NULL,
 may_have_acted INTEGER NOT NULL, sequence INTEGER NOT NULL,
 attempt_id TEXT, owner_epoch INTEGER NOT NULL);
CREATE TABLE replay_keys (
 namespace TEXT NOT NULL REFERENCES namespaces(token), caller_key TEXT NOT NULL,
 operation_id TEXT NOT NULL REFERENCES operations(id),
 PRIMARY KEY(namespace, caller_key));
CREATE TABLE resource_floors (
 deployment TEXT NOT NULL, resource TEXT NOT NULL, fence INTEGER NOT NULL,
 PRIMARY KEY(deployment, resource));
CREATE TABLE claims (
 deployment TEXT NOT NULL, resource TEXT NOT NULL,
 operation_id TEXT NOT NULL REFERENCES operations(id), fence INTEGER NOT NULL,
 PRIMARY KEY(deployment, resource));
CREATE TABLE events (
 operation_id TEXT NOT NULL REFERENCES operations(id), sequence INTEGER NOT NULL,
 time_ms INTEGER NOT NULL, clock_status TEXT NOT NULL, kind TEXT NOT NULL, payload BLOB NOT NULL,
 PRIMARY KEY(operation_id, sequence));
"""


class Journal:
    """Local POSIX file, one process owner, serialized short transactions.

    Opening performs conservative recovery. A missing DB is an error unless
    create=True is explicit; creation always chooses a new authority identity.
    Do not put the DB on a network filesystem or restore it independently of
    its authority/replay state. Policies must not block, do I/O, or reenter.
    """
    def __init__(self, path, policy: Policy, *, clock_ms: Callable[[], int], create=False):
        self.path = Path(path).resolve()
        self.policy = policy
        self.clock_ms = clock_ms
        self._mutex = threading.RLock()
        self._closed = False
        self._poisoned = False
        self._observed_clock = 0
        # Trusted procedure-manager hooks, called only inside submit's existing
        # transaction. They must not perform I/O, reenter, sample authority time,
        # or commit. The record hook makes the child link atomic with admission.
        self.submission_guard = None
        self.submission_record = None
        self._db = None
        self._lock_fd = os.open(str(self.path) + ".owner", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise JournalError("OWNER_BUSY") from error
            if create:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(fd)
            elif not self.path.is_file():
                raise JournalError("MISSING_AUTHORITY_DATABASE")
            self._db = sqlite3.connect(str(self.path), isolation_level=None,
                                       check_same_thread=False, timeout=0.2)
            self._db.row_factory = sqlite3.Row
            if self._db.execute("PRAGMA journal_mode=DELETE").fetchone()[0] != "delete":
                raise JournalError("UNSUPPORTED_DURABILITY_MODE")
            self._db.execute("PRAGMA synchronous=EXTRA")
            self._db.execute("PRAGMA foreign_keys=ON")
            if (self._db.execute("PRAGMA synchronous").fetchone()[0] != 3 or
                    self._db.execute("PRAGMA foreign_keys").fetchone()[0] != 1):
                raise JournalError("UNSUPPORTED_DURABILITY_MODE")
            if create:
                self._db.executescript("BEGIN IMMEDIATE;\n" + _DDL)
                try:
                    for key, value in {"version": "hms-ledger/0.1", "authority": uuid.uuid4().hex,
                                       "owner_epoch": "0", "last_clock": "0"}.items():
                        self._db.execute("INSERT INTO meta VALUES (?, ?)", (key, value))
                    self._db.execute("COMMIT")
                except BaseException:
                    if self._db.in_transaction:
                        self._db.execute("ROLLBACK")
                    raise
            if self._meta("version") != "hms-ledger/0.1":
                raise JournalError("UNSUPPORTED_DATABASE")
            self.authority_id = self._meta("authority")
            with self._transaction():
                self.owner_epoch = int(self._meta("owner_epoch")) + 1
                if self.owner_epoch > SAFE_INTEGER:
                    raise JournalError("OWNER_EPOCH_EXHAUSTED")
                self._set_meta("owner_epoch", str(self.owner_epoch))
                # Recovery records may still be written if wall time regressed;
                # fresh admission is denied by _now until it catches up.
                now = self._record_now()
                rows = self._db.execute("SELECT id FROM operations WHERE state IN ('dispatching','running')").fetchall()
                for row in rows:
                    self._db.execute("UPDATE operations SET state='outcome_unknown' WHERE id=?", (row[0],))
                    self._event(row[0], now, "recovery_unknown", {"reason": "owner_reopened"})
        except BaseException:
            self.close()
            raise

    def close(self):
        with self._mutex:
            if not self._closed:
                if self._db is not None:
                    self._db.close()
                os.close(self._lock_fd)
                self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @contextmanager
    def _transaction(self):
        with self._mutex:
            if self._closed:
                raise JournalError("CLOSED")
            if self._poisoned:
                raise JournalError("JOURNAL_UNHEALTHY")
            if self._db.in_transaction:
                raise JournalError("POLICY_REENTRANCY")
            self._db.execute("BEGIN IMMEDIATE")
            self._transaction_start_changes = self._db.total_changes
            try:
                yield
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                # A refused evidence transition can also have observed expiry.
                # Preserve that clock floor independently of business rollback.
                try:
                    if self._observed_clock > int(self._meta("last_clock")):
                        self._db.execute("BEGIN IMMEDIATE")
                        self._set_meta("last_clock", str(self._observed_clock))
                        self._db.execute("COMMIT")
                except BaseException:
                    self._poisoned = True
                    if self._db.in_transaction:
                        self._db.execute("ROLLBACK")
                raise

    def _meta(self, key):
        row = self._db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if row is None:
            raise JournalError("MISSING_AUTHORITY_METADATA")
        return row[0]

    def _set_meta(self, key, value):
        self._db.execute("UPDATE meta SET value=? WHERE key=?", (value, key))

    def _clock(self):
        try:
            value = self.clock_ms()
        except Exception as error:
            raise JournalError("INVALID_CLOCK") from error
        if type(value) is not int or not 0 <= value <= SAFE_INTEGER:
            raise JournalError("INVALID_CLOCK")
        self._observed_clock = max(self._observed_clock, value)
        return value

    def _now(self):
        now = self._clock()
        persisted_floor = int(self._meta("last_clock"))
        if now < max(persisted_floor, self._observed_clock):
            raise JournalError("CLOCK_REGRESSION")
        if now > persisted_floor:
            # All calls occur before business writes, under the process mutex
            # and exclusive owner lock. Persist observed time independently so
            # a refused expired request cannot revive after clock rollback.
            if self._db.total_changes != self._transaction_start_changes:
                raise JournalError("CLOCK_CHECK_AFTER_MUTATION")
            self._set_meta("last_clock", str(now))
            self._db.execute("COMMIT")
            self._db.execute("BEGIN IMMEDIATE")
            self._transaction_start_changes = self._db.total_changes
        return now

    def authority_time(self):
        """Validate and retain the clock floor before an external effect check.

        Callers must retain the authority mutex through their policy check and
        effect boundary. This is a host-clock check, not clock synchronization.
        """
        with self._transaction():
            return self._now()

    def effect_veto_time(self, checkpoint):
        """Supplement a durable checkpoint with a fresh, noncommitting veto.

        Trusted adapters retain this mutex across the checkpoint, all boundary
        checks and the effect. This sample may only withdraw already admitted
        authority; it is not an admission clock, lease renewal or event time.
        A durable COMMIT can block, so authority_time's pre-COMMIT sample cannot
        serve as the final deadline check. Retain the observed floor on the
        ensuing refusal/settlement path. Exact operation identity still governs
        a crash between effect and settlement. This supplies no hard real-time
        bound across the final effect or its storage commit.
        """
        with self._mutex:
            if self._closed:
                raise JournalError("CLOSED")
            if self._poisoned:
                raise JournalError("JOURNAL_UNHEALTHY")
            floor = int(self._meta("last_clock"))
            if (type(checkpoint) is not int or not 0 <= checkpoint <= floor or
                    self._db.in_transaction):
                raise JournalError("INVALID_EFFECT_CHECKPOINT")
            now = self._clock()
            if now < max(floor, self._observed_clock):
                raise JournalError("CLOCK_REGRESSION")
            return now

    def _record_now(self):
        """Record truth/cancellation even when the host clock is unavailable.

        This does not grant new execution authority. Sequence orders records;
        a clamped audit timestamp is explicitly marked by _event.
        """
        floor = max(int(self._meta("last_clock")), self._observed_clock)
        try:
            observed = self._clock()
            now = max(observed, floor)
            status = "regressed_clamped" if observed < floor else "unqualified_host_clock"
        except Exception:
            now = floor
            status = "unavailable_clamped"
        self._set_meta("last_clock", str(now))
        return RecordTime(now, status)

    def _event(self, operation_id, now, kind, payload):
        clock_status = now.status if isinstance(now, RecordTime) else "unqualified_host_clock"
        now = now.value if isinstance(now, RecordTime) else now
        self._db.execute("UPDATE operations SET sequence=sequence+1 WHERE id=?", (operation_id,))
        seq = self._db.execute("SELECT sequence FROM operations WHERE id=?", (operation_id,)).fetchone()[0]
        self._db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
                         (operation_id, seq, now, clock_status, kind, canonical(payload)))

    def _operation(self, operation_id):
        row = self._db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
        if row is None:
            raise JournalError("NOT_FOUND")
        result = dict(row)
        result["intent"] = json.loads(result["intent"])
        result["admission"] = json.loads(result["admission"])
        result["may_have_acted"] = bool(result["may_have_acted"])
        result["claims"] = [dict(row) for row in self._db.execute(
            "SELECT resource, fence FROM claims WHERE operation_id=? ORDER BY resource", (operation_id,))]
        return result

    def _context(self, op):
        return Context(op["principal"], op["deployment"])

    def _access(self, context, verb, op):
        # This first prototype has owner-scoped results. Delegated operators
        # and cross-principal read access need a separate authenticated seam.
        if context != self._context(op):
            raise JournalError("ACCESS_DENIED")
        self.policy.authorize(context, verb, op["intent"]["instanceId"])

    def status(self, context: Context, operation_id: str):
        with self._mutex:
            op = self._operation(operation_id)
            self._access(context, "read", op)
            return op

    def issue_namespace(self, context: Context, expires_ms: int):
        with self._transaction():
            self.policy.authorize(context, "namespace", context.deployment)
            now = self._now()
            if type(expires_ms) is not int or not now < expires_ms <= SAFE_INTEGER:
                raise JournalError("INVALID_NAMESPACE_EXPIRY")
            self._db.execute("INSERT OR IGNORE INTO series VALUES (?, ?, 1, 1, 0)",
                             (context.principal, context.deployment))
            series = self._db.execute("SELECT * FROM series WHERE principal=? AND deployment=?",
                                      (context.principal, context.deployment)).fetchone()
            if expires_ms < series["last_expiry"] or series["next_epoch"] > SAFE_INTEGER:
                raise JournalError("NAMESPACE_ORDER")
            epoch = series["next_epoch"]
            token = f"replay:{self.authority_id}:{epoch}:{uuid.uuid4().hex}"
            self._db.execute("INSERT INTO namespaces VALUES (?, ?, ?, ?, ?)",
                             (token, context.principal, context.deployment, epoch, expires_ms))
            self._db.execute("UPDATE series SET next_epoch=?, last_expiry=? WHERE principal=? AND deployment=?",
                             (epoch + 1, expires_ms, context.principal, context.deployment))
            return {"token": token, "epoch": epoch, "expiresUnixMs": expires_ms,
                    "authorityId": self.authority_id}

    def _namespace(self, context, token):
        parts = token.split(":")
        if len(parts) != 4 or parts[0] != "replay" or parts[1] != self.authority_id:
            raise JournalError("INVALID_REPLAY_NAMESPACE")
        row = self._db.execute("SELECT * FROM namespaces WHERE token=?", (token,)).fetchone()
        if row is None or (row["principal"], row["deployment"]) != (context.principal, context.deployment):
            raise JournalError("INVALID_REPLAY_NAMESPACE")
        floor = self._db.execute("SELECT floor FROM series WHERE principal=? AND deployment=?",
                                 (context.principal, context.deployment)).fetchone()[0]
        if row["epoch"] < floor:
            raise JournalError("EXPIRED_REPLAY_NAMESPACE")
        return row

    def prune_expired_namespaces(self, context: Context):
        with self._transaction():
            self.policy.authorize(context, "namespace", context.deployment)
            now = self._now()
            # Expiries are immutable and ordered, so this is a contiguous prefix.
            row = self._db.execute("SELECT MAX(epoch) FROM namespaces WHERE principal=? AND deployment=? AND expires_ms<=?",
                                   (context.principal, context.deployment, now)).fetchone()
            if row[0] is None:
                return 0
            floor = row[0] + 1
            self._db.execute("UPDATE series SET floor=MAX(floor,?) WHERE principal=? AND deployment=?",
                             (floor, context.principal, context.deployment))
            tokens = [r[0] for r in self._db.execute(
                "SELECT token FROM namespaces WHERE principal=? AND deployment=? AND epoch<?",
                (context.principal, context.deployment, floor))]
            for token in tokens:
                self._db.execute("DELETE FROM replay_keys WHERE namespace=?", (token,))
                self._db.execute("DELETE FROM namespaces WHERE token=?", (token,))
            # Operation/effect/event records and unresolved claims remain intact.
            return len(tokens)

    def submit(self, context: Context, wire: bytes, *, _managed=None):
        request = parse_invoke(wire)
        intent = request["intent"]
        digest = intent_digest(intent)
        with self._transaction():
            namespace = self._namespace(context, request["replayNamespace"])
            previous = self._db.execute("SELECT operation_id FROM replay_keys WHERE namespace=? AND caller_key=?",
                                       (namespace["token"], request["operationKey"])).fetchone()
            if previous:
                op = self._operation(previous[0])
                self._access(context, "read", op)
                if op["digest"] != digest:
                    raise JournalError("KEY_CONFLICT")
                return op
            now = self._now()
            if _managed is not None and (self.submission_guard is None or self.submission_record is None):
                raise JournalError("PROCEDURE_MANAGER_UNAVAILABLE")
            if self.submission_guard is not None:
                self.submission_guard(context, request, intent, digest, _managed, now)
            if now >= namespace["expires_ms"]:
                raise JournalError("EXPIRED_REPLAY_NAMESPACE")
            if now >= intent["timing"]["latestStartUnixMs"]:
                raise JournalError("START_EXPIRED")
            self.policy.authorize(context, "invoke", intent["instanceId"])
            admission = self.policy.admit(context, json.loads(canonical(intent)), now)
            if (type(admission) is not Admission or type(admission.resources) is not tuple or
                    not 1 <= len(admission.resources) <= 32 or
                    len(set(admission.resources)) != len(admission.resources) or
                    type(admission.lease_expires_ms) is not int or
                    not now < admission.lease_expires_ms <= SAFE_INTEGER):
                raise JournalError("INVALID_ADMISSION")
            identifier(admission.policy_revision)
            for resource in admission.resources:
                identifier(resource)
                if self._db.execute("SELECT 1 FROM claims WHERE deployment=? AND resource=?",
                                    (context.deployment, resource)).fetchone():
                    raise JournalError("RESOURCE_BUSY")
            operation_id = "op:" + uuid.uuid4().hex
            admission_data = asdict(admission) | {"resources": sorted(admission.resources)}
            self._db.execute("INSERT INTO operations VALUES (?, ?, ?, ?, ?, ?, 'accepted', 'not_requested', 'unverified', 0, 0, NULL, ?)",
                             (operation_id, context.principal, context.deployment, digest,
                              canonical(intent), canonical(admission_data), self.owner_epoch))
            self._db.execute("INSERT INTO replay_keys VALUES (?, ?, ?)",
                             (namespace["token"], request["operationKey"], operation_id))
            for resource in sorted(admission.resources):
                self._db.execute("INSERT OR IGNORE INTO resource_floors VALUES (?, ?, 0)",
                                 (context.deployment, resource))
                fence = self._db.execute("SELECT fence FROM resource_floors WHERE deployment=? AND resource=?",
                                         (context.deployment, resource)).fetchone()[0] + 1
                if fence > SAFE_INTEGER:
                    raise JournalError("FENCE_EXHAUSTED")
                self._db.execute("UPDATE resource_floors SET fence=? WHERE deployment=? AND resource=?",
                                 (fence, context.deployment, resource))
                self._db.execute("INSERT INTO claims VALUES (?, ?, ?, ?)",
                                 (context.deployment, resource, operation_id, fence))
            self._event(operation_id, now, "accepted", {"digest": digest})
            if self.submission_record is not None:
                self.submission_record(operation_id, _managed, now)
            return self._operation(operation_id)

    def claim_dispatch(self, operation_id: str, *, _reserve=None) -> Ticket | None:
        """Persist possible-send ownership. A ticket is not a physical receipt.

        An installed adapter may supply _reserve(operation, ticket, now) to
        validate and store its exact dispatch mapping in this SAME transaction.
        It may use this connection only; no transport, blocking I/O, reentry or
        separate commit is allowed. Nothing may be handed off until return.
        """
        with self._transaction():
            op = self._operation(operation_id)
            if op["state"] != "accepted":
                raise JournalError("NOT_DISPATCHABLE")
            now = self._now()
            timing = op["intent"]["timing"]
            if now >= timing["latestStartUnixMs"] or now >= op["admission"]["lease_expires_ms"]:
                self._db.execute("UPDATE operations SET state='rejected_before_dispatch' WHERE id=?", (operation_id,))
                self._db.execute("DELETE FROM claims WHERE operation_id=?", (operation_id,))
                self._event(operation_id, now, "rejected_before_dispatch", {"reason": "start_or_lease_expired"})
                return None
            if now < timing["notBeforeUnixMs"]:
                raise JournalError("NOT_YET_STARTABLE")
            if len(op["claims"]) != len(op["admission"]["resources"]):
                raise JournalError("MISSING_RESOURCE_CLAIM")
            context = self._context(op)
            self.policy.authorize(context, "invoke", op["intent"]["instanceId"])
            self.policy.recheck(context, copy.deepcopy(op), now)
            attempt = uuid.uuid4().hex
            ticket = Ticket(operation_id, attempt, self.owner_epoch)
            if _reserve is not None:
                _reserve(copy.deepcopy(op), ticket, now)
            self._db.execute("UPDATE operations SET state='dispatching', may_have_acted=1, attempt_id=?, owner_epoch=? WHERE id=?",
                             (attempt, self.owner_epoch, operation_id))
            self._event(operation_id, now, "dispatch_claimed", {"attemptId": attempt, "ownerEpoch": self.owner_epoch})
            return ticket

    def reject_before_dispatch(self, operation_id: str, reason: str):
        """Trusted dispatcher refusal, with atomic proof no ticket was issued."""
        identifier(reason)
        with self._transaction():
            op = self._operation(operation_id)
            if op["state"] != "accepted":
                raise JournalError("NOT_DISPATCHABLE")
            self._db.execute("UPDATE operations SET state='rejected_before_dispatch' WHERE id=?", (operation_id,))
            self._db.execute("DELETE FROM claims WHERE operation_id=?", (operation_id,))
            self._event(operation_id, self._record_now(), "rejected_before_dispatch", {"reason": reason})
            return self._operation(operation_id)

    def work_items(self, states: tuple[str, ...], *, limit=64):
        """Bounded internal scheduler view; never expose without result authority."""
        allowed = {"accepted", "dispatching", "running", "outcome_unknown"} | TERMINAL
        if (type(states) is not tuple or not states or set(states) - allowed or
                type(limit) is not int or not 1 <= limit <= 256):
            raise JournalError("INVALID_WORK_QUERY")
        with self._mutex:
            marks = ",".join("?" for _ in states)
            rows = self._db.execute(f"SELECT id FROM operations WHERE state IN ({marks}) ORDER BY rowid LIMIT ?",
                                    (*states, limit)).fetchall()
            return [self._operation(row[0]) for row in rows]

    def _ticket(self, ticket):
        op = self._operation(ticket.operation_id)
        if (ticket.owner_epoch != self.owner_epoch or op["owner_epoch"] != self.owner_epoch or
                ticket.attempt_id != op["attempt_id"]):
            raise JournalError("STALE_WORKER")
        return op

    def _execution(self, op, state, evidence, now):
        if state not in SUCCESSORS.get(op["state"], set()) or state == "outcome_unknown":
            raise JournalError("INVALID_TRANSITION")
        data = evidence.payload()
        assertions = frozenset(data["assertions"])
        self.policy.evidence(copy.deepcopy(op), evidence)
        required = {"running": "running", "completed": "completed", "failed": "failed", "canceled": "terminated",
                    "rejected_before_start": "start_excluded"}[state]
        if required not in assertions or data["kind"] == "runtime":
            raise JournalError("COMPLETION_EVIDENCE_REQUIRED")
        excluded = "start_excluded" in assertions
        if excluded and (state not in {"canceled", "rejected_before_start"} or
                         op["state"] not in {"dispatching", "outcome_unknown"} or
                         assertions & {"disputed", "physical_verified", "verification_failed"} or
                         self._db.execute("SELECT 1 FROM events WHERE operation_id=? AND kind IN ('execution_evidence','reconciled') AND json_extract(CAST(payload AS TEXT),'$.state')='running' LIMIT 1", (op["id"],)).fetchone()):
            raise JournalError("INVALID_START_EXCLUSION")
        if "disputed" in assertions and state not in {"completed", "failed", "canceled"}:
            raise JournalError("INVALID_DISPUTE")
        verification = ("disputed" if "disputed" in assertions or op["verification"] == "disputed" else
                        "failed" if "verification_failed" in assertions else
                        "verified" if "physical_verified" in assertions else op["verification"])
        if (state == "completed" and op["intent"]["requiredEffect"] == "physical_verified" and
                (verification != "verified" or "physical_verified" not in assertions)):
            raise JournalError("PHYSICAL_EVIDENCE_REQUIRED")
        cancel = "confirmed" if state == "canceled" else op["cancel_state"]
        self._db.execute("UPDATE operations SET state=?, cancel_state=?, verification=?, owner_epoch=? WHERE id=?",
                         (state, cancel, verification, self.owner_epoch, op["id"]))
        if excluded:
            self._db.execute("UPDATE operations SET may_have_acted=0, verification='unverified' WHERE id=?", (op["id"],))
            self._db.execute("DELETE FROM claims WHERE operation_id=?", (op["id"],))
        self._event(op["id"], now, "reconciled" if op["state"] == "outcome_unknown" else "execution_evidence",
                    {"state": state, "evidence": data})

    def record_execution(self, ticket: Ticket, state: str, evidence: Evidence):
        with self._transaction():
            op = self._ticket(ticket)
            if op["state"] == "outcome_unknown":
                raise JournalError("RECONCILIATION_REQUIRED")
            self._execution(op, state, evidence, self._record_now())
            return self._operation(op["id"])

    def mark_unknown(self, ticket: Ticket, reason: str):
        identifier(reason)
        with self._transaction():
            op = self._ticket(ticket)
            if op["state"] not in {"dispatching", "running"}:
                raise JournalError("INVALID_TRANSITION")
            self._db.execute("UPDATE operations SET state='outcome_unknown' WHERE id=?", (op["id"],))
            self._event(op["id"], self._record_now(), "outcome_unknown", {"reason": reason})

    def reconcile(self, operation_id: str, state: str, evidence: Evidence):
        with self._transaction():
            op = self._operation(operation_id)
            if op["state"] != "outcome_unknown":
                raise JournalError("RECONCILIATION_NOT_APPLICABLE")
            self._execution(op, state, evidence, self._record_now())
            return self._operation(operation_id)

    def monitoring_ticket(self, operation_id: str):
        with self._mutex:
            op = self._operation(operation_id)
            if op["state"] != "running" or op["owner_epoch"] != self.owner_epoch:
                raise JournalError("NOT_MONITORABLE")
            return Ticket(operation_id, op["attempt_id"], self.owner_epoch)

    def request_cancel(self, context: Context, operation_id: str):
        with self._transaction():
            return self._request_cancel_in_tx(context, operation_id)

    def _request_cancel_in_tx(self, context: Context, operation_id: str):
        """Trusted same-transaction cancellation; authorize before any writes."""
        if not self._db.in_transaction:
            raise JournalError("CANCEL_TRANSACTION_REQUIRED")
        op = self._operation(operation_id)
        self._access(context, "cancel", op)
        if op["state"] in TERMINAL:
            raise JournalError("ALREADY_TERMINAL")
        if op["cancel_state"] in {"requested", "acknowledged", "confirmed"}:
            return op
        now = self._record_now()
        if op["state"] == "accepted":
            self._db.execute("UPDATE operations SET state='canceled', cancel_state='confirmed' WHERE id=?", (operation_id,))
            self._db.execute("DELETE FROM claims WHERE operation_id=?", (operation_id,))
            self._event(operation_id, now, "canceled_before_dispatch", {"proof": "exclusive_accepted_state"})
        else:
            self._db.execute("UPDATE operations SET cancel_state='requested' WHERE id=?", (operation_id,))
            self._event(operation_id, now, "cancel_requested", {})
        return self._operation(operation_id)

    def acknowledge_cancel(self, ticket: Ticket, accepted: bool, evidence: Evidence):
        with self._transaction():
            op = self._ticket(ticket)
            data = evidence.payload()
            self.policy.evidence(copy.deepcopy(op), evidence)
            if (type(accepted) is not bool or "cancel_ack" not in data["assertions"] or
                    op["cancel_state"] != "requested"):
                raise JournalError("INVALID_CANCEL_ACK")
            self._db.execute("UPDATE operations SET cancel_state=? WHERE id=?",
                             ("acknowledged" if accepted else "rejected", op["id"]))
            self._event(op["id"], self._record_now(), "cancel_ack", {"accepted": accepted, "evidence": data})
            return self._operation(op["id"])

    def release_resources(self, operation_id: str, evidence: Evidence):
        with self._transaction():
            op = self._operation(operation_id)
            data = evidence.payload()
            self.policy.evidence(copy.deepcopy(op), evidence)
            if (op["state"] not in TERMINAL or op["verification"] == "disputed" or
                    "disputed" in data["assertions"] or "resources_quiescent" not in data["assertions"]):
                raise JournalError("QUIESCENCE_REQUIRED")
            self._db.execute("DELETE FROM claims WHERE operation_id=?", (operation_id,))
            self._event(operation_id, self._record_now(), "resources_released", {"evidence": data})

    def dispute(self, operation_id: str, evidence: Evidence):
        with self._transaction():
            op = self._operation(operation_id)
            data = evidence.payload()
            self.policy.evidence(copy.deepcopy(op), evidence)
            if op["state"] not in TERMINAL or not op["may_have_acted"] or "disputed" not in data["assertions"]:
                raise JournalError("INVALID_DISPUTE")
            self._db.execute("UPDATE operations SET verification='disputed' WHERE id=?", (operation_id,))
            self._event(operation_id, self._record_now(), "evidence_dispute", {"evidence": data})

    def events(self, context: Context, operation_id: str, *, after=0, limit=100):
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise JournalError("INVALID_CURSOR")
        with self._mutex:
            op = self._operation(operation_id)
            self._access(context, "read", op)
            if after > op["sequence"]:
                raise JournalError("INVALID_CURSOR")
            rows = self._db.execute("SELECT * FROM events WHERE operation_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                                    (operation_id, after, limit)).fetchall()
            result = [dict(row) | {"payload": json.loads(row["payload"])} for row in rows]
            return {"events": result, "next": result[-1]["sequence"] if result else after,
                    "head": op["sequence"], "gap": False}
