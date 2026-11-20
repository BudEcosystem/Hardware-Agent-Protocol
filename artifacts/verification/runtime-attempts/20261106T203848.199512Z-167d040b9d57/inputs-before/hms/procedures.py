"""Durable, bounded ordered procedures over installed HMS operation routes.

The store coordinates immutable child requests; the existing Journal and adapter
workers retain operation/evidence authority. No material, branching, rollback,
physical stop, or aggregate scientific-outcome guarantee is implied.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from .contracts import (SAFE_INTEGER, ContractError, canonical, identifier,
                        intent_digest, parse_invoke, parse_json)
from .journal import Context, JournalError, ObservationAgeExpired, RecordTime, TERMINAL


PROFILE = "hms.bound-sequence/0.1"
_ACTIVE = {"accepted", "running"}
_FINAL = {"completed", "failed", "canceled", "expired"}
_DIGEST_PREFIX = b"HMS-PROCEDURE-JCS-SHA256-v0.1\x00"
_DDL = (
    "CREATE TABLE IF NOT EXISTS pr_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE IF NOT EXISTS pr_procedures (
        id TEXT PRIMARY KEY, principal TEXT NOT NULL, deployment TEXT NOT NULL,
        digest TEXT NOT NULL, request BLOB NOT NULL, state TEXT NOT NULL,
        reason TEXT, cursor INTEGER NOT NULL, cancel_requested INTEGER NOT NULL,
        cancel_delivery BLOB NOT NULL, sequence INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS pr_steps (
        procedure_id TEXT NOT NULL REFERENCES pr_procedures(id),
        ordinal INTEGER NOT NULL, step_id TEXT NOT NULL, request BLOB NOT NULL,
        digest TEXT NOT NULL, operation_id TEXT UNIQUE REFERENCES operations(id),
        PRIMARY KEY(procedure_id, ordinal), UNIQUE(procedure_id, step_id))""",
    # Reservations deliberately outlive namespace pruning. They preserve audit
    # ownership, not permission to admit below the Journal's namespace floor.
    """CREATE TABLE IF NOT EXISTS pr_keys (
        namespace TEXT NOT NULL, caller_key TEXT NOT NULL,
        procedure_id TEXT NOT NULL REFERENCES pr_procedures(id), step_id TEXT,
        PRIMARY KEY(namespace, caller_key))""",
    """CREATE TABLE IF NOT EXISTS pr_events (
        procedure_id TEXT NOT NULL REFERENCES pr_procedures(id),
        sequence INTEGER NOT NULL, time_ms INTEGER NOT NULL,
        clock_status TEXT NOT NULL, kind TEXT NOT NULL, payload BLOB NOT NULL,
        PRIMARY KEY(procedure_id, sequence))""",
)


def _shape(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise ContractError("invalid procedure " + label)


def parse_procedure(request):
    """Snapshot and validate this profile without granting runtime authority."""
    request = parse_json(canonical(request))
    _shape(request, ("protocol", "replayNamespace", "procedureKey", "procedure"), "envelope")
    if request["protocol"] != "hms.procedure/0.1":
        raise ContractError("invalid procedure protocol")
    identifier(request["replayNamespace"])
    identifier(request["procedureKey"])
    document = request["procedure"]
    _shape(document, ("profile", "timing", "steps"), "document")
    if document["profile"] != PROFILE:
        raise ContractError("unsupported procedure profile")
    timing = document["timing"]
    _shape(timing, ("notBeforeUnixMs", "latestStartUnixMs", "latestCompletionUnixMs"), "timing")
    if (any(type(v) is not int or not 0 <= v <= SAFE_INTEGER for v in timing.values()) or
            not timing["notBeforeUnixMs"] <= timing["latestStartUnixMs"] <= timing["latestCompletionUnixMs"]):
        raise ContractError("invalid procedure timing")
    steps = document["steps"]
    if type(steps) is not list or not 1 <= len(steps) <= 16:
        raise ContractError("procedure requires 1..16 steps")
    identities, keys = set(), {request["procedureKey"]}
    for ordinal, step in enumerate(steps):
        _shape(step, ("stepId", "request"), "step")
        identifier(step["stepId"])
        child = parse_invoke(canonical(step["request"]))
        if (step["stepId"] in identities or child["operationKey"] in keys or
                child["replayNamespace"] != request["replayNamespace"]):
            raise ContractError("duplicate procedure identity or namespace mismatch")
        identities.add(step["stepId"])
        keys.add(child["operationKey"])
        window = child["intent"]["timing"]
        if (window["notBeforeUnixMs"] < timing["notBeforeUnixMs"] or
                window["latestCompletionUnixMs"] > timing["latestCompletionUnixMs"] or
                (ordinal == 0 and window["latestStartUnixMs"] > timing["latestStartUnixMs"])):
            raise ContractError("child timing outside procedure window")
    return request


def procedure_digest(request):
    return "sha256:" + hashlib.sha256(_DIGEST_PREFIX + canonical(request)).hexdigest()


class ProcedureStore:
    """One store per Journal, constructed before any operation workers start.

    Construction creates versioned tables, interrupts active parent controls, and
    installs pure submission/recheck callbacks. It does not query any adapter.
    """
    def __init__(self, journal):
        self.journal = journal
        self._db = journal._db
        self._last_selected = 0
        if (getattr(journal, "submission_guard", None) is not None or
                getattr(journal, "submission_record", None) is not None or
                getattr(journal.policy, "procedure_guard", None) is not None):
            raise JournalError("PROCEDURE_ALREADY_ATTACHED")
        with journal._transaction():
            expected = {"pr_meta", "pr_procedures", "pr_steps", "pr_keys", "pr_events"}
            present = {r[0] for r in self._db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'pr_%'")}
            if present and present != expected:
                raise JournalError("INCOMPLETE_PROCEDURE_DATABASE")
            if not present:
                for statement in _DDL:
                    self._db.execute(statement)
                self._db.execute("INSERT INTO pr_meta VALUES ('version', ?)", (PROFILE,))
            version = self._db.execute("SELECT value FROM pr_meta WHERE key='version'").fetchone()
            if version is None or version[0] != PROFILE:
                raise JournalError("UNSUPPORTED_PROCEDURE_DATABASE")
            rows = self._db.execute("SELECT id FROM pr_procedures WHERE state IN ('accepted','running')").fetchall()
            if rows:
                now = journal._record_now()
                for row in rows:
                    self._change(self._row(row[0]), "interrupted", "OWNER_REOPENED", now)
        journal.submission_guard = self._submission_guard
        journal.submission_record = self._submission_record
        journal.policy.procedure_guard = self._dispatch_guard

    def _row(self, procedure_id):
        row = self._db.execute("SELECT * FROM pr_procedures WHERE id=?", (procedure_id,)).fetchone()
        if row is None:
            raise JournalError("PROCEDURE_NOT_FOUND")
        result = dict(row)
        result["request"] = json.loads(result["request"])
        result["cancel_delivery"] = json.loads(result["cancel_delivery"])
        return result

    def _steps(self, procedure_id):
        return [dict(row) | {"request": json.loads(row["request"])} for row in self._db.execute(
            "SELECT * FROM pr_steps WHERE procedure_id=? ORDER BY ordinal", (procedure_id,))]

    @staticmethod
    def _context(row):
        return Context(row["principal"], row["deployment"])

    def _owner(self, context, row):
        if (context.principal, context.deployment) != (row["principal"], row["deployment"]):
            raise JournalError("ACCESS_DENIED")

    def _read_access(self, context, row):
        self._owner(context, row)
        for instance in {s["request"]["intent"]["instanceId"] for s in row["request"]["procedure"]["steps"]}:
            self.journal.policy.authorize(context, "read", instance)

    def _event(self, procedure_id, now, kind, payload):
        sequence = self._db.execute("SELECT sequence FROM pr_procedures WHERE id=?", (procedure_id,)).fetchone()[0]
        if sequence >= SAFE_INTEGER:
            raise JournalError("PROCEDURE_SEQUENCE_EXHAUSTED")
        clock_status = now.status if isinstance(now, RecordTime) else "unqualified_host_clock"
        timestamp = now.value if isinstance(now, RecordTime) else now
        self._db.execute("UPDATE pr_procedures SET sequence=sequence+1 WHERE id=?", (procedure_id,))
        self._db.execute("INSERT INTO pr_events VALUES (?, ?, ?, ?, ?, ?)",
                         (procedure_id, sequence + 1, timestamp, clock_status, kind, canonical(payload)))

    def _change(self, row, state, reason, now):
        if (row["state"], row["reason"]) != (state, reason):
            self._db.execute("UPDATE pr_procedures SET state=?, reason=? WHERE id=?", (state, reason, row["id"]))
            self._event(row["id"], now, "state_changed", {"state": state, "reason": reason})

    def _operations(self, steps):
        return [self.journal._operation(step["operation_id"]) if step["operation_id"] else None for step in steps]

    @staticmethod
    def _successful(operation):
        return (operation is not None and operation["state"] == "completed" and
                operation["verification"] not in {"failed", "disputed"} and not operation["claims"] and
                (operation["intent"]["requiredEffect"] != "physical_verified" or
                 operation["verification"] == "verified"))

    def _prefix_gate(self, steps, ordinal):
        for step in steps[:ordinal]:
            if not step["operation_id"] or not self._successful(self.journal._operation(step["operation_id"])):
                raise JournalError("PROCEDURE_DEPENDENCY_UNRESOLVED")

    def _control_gate(self, row, now):
        if row["cancel_requested"]:
            raise JournalError("PROCEDURE_CANCELED")
        if row["state"] == "interrupted":
            raise JournalError("PROCEDURE_PAUSED")
        if row["state"] not in _ACTIVE:
            raise JournalError("PROCEDURE_NOT_RUNNABLE")
        timing = row["request"]["procedure"]["timing"]
        if now >= timing["latestCompletionUnixMs"]:
            raise JournalError("PROCEDURE_DEADLINE")
        if now < timing["notBeforeUnixMs"]:
            raise JournalError("PROCEDURE_NOT_YET_STARTABLE")

    def _managed_step(self, managed):
        if (type(managed) is not tuple or len(managed) != 2 or
                any(type(v) is not str for v in managed)):
            raise JournalError("INVALID_PROCEDURE_MANAGEMENT")
        row = self._row(managed[0])
        steps = self._steps(row["id"])
        step = next((s for s in steps if s["step_id"] == managed[1]), None)
        if step is None:
            raise JournalError("INVALID_PROCEDURE_MANAGEMENT")
        return row, steps, step

    def _submission_guard(self, context, request, intent, digest, managed, now):
        reservation = self._db.execute("SELECT * FROM pr_keys WHERE namespace=? AND caller_key=?",
                                       (request["replayNamespace"], request["operationKey"])).fetchone()
        if managed is None:
            if reservation is not None:
                raise JournalError("PROCEDURE_KEY_RESERVED")
            return
        row, steps, step = self._managed_step(managed)
        self._owner(context, row)
        if (reservation is None or reservation["procedure_id"] != row["id"] or
                reservation["step_id"] != step["step_id"] or step["operation_id"] is not None or
                step["ordinal"] != row["cursor"] or digest != step["digest"] or
                canonical(request) != canonical(step["request"])):
            raise JournalError("INVALID_PROCEDURE_MANAGEMENT")
        self._control_gate(row, now)
        self._prefix_gate(steps, step["ordinal"])

    def _submission_record(self, operation_id, managed, now):
        if managed is None:
            return
        row, _, step = self._managed_step(managed)
        operation = self.journal._operation(operation_id)
        if (step["operation_id"] is not None or step["ordinal"] != row["cursor"] or
                operation["digest"] != step["digest"] or
                (operation["principal"], operation["deployment"]) != (row["principal"], row["deployment"])):
            raise JournalError("INVALID_PROCEDURE_MANAGEMENT")
        self._db.execute("UPDATE pr_steps SET operation_id=? WHERE procedure_id=? AND ordinal=?",
                         (operation_id, row["id"], step["ordinal"]))
        self._db.execute("UPDATE pr_procedures SET state='running', reason=NULL, cursor=? WHERE id=?",
                         (step["ordinal"], row["id"]))
        self._event(row["id"], now, "child_admitted", {"stepId": step["step_id"],
                    "ordinal": step["ordinal"], "operationId": operation_id})

    def _dispatch_guard(self, context, operation, now):
        # Reconciliation/evidence is intentionally independent of this gate.
        # Parent withdrawal inhibits unstarted work. Once handed off, the
        # child's own cancel permission/state and deadline remain authoritative.
        step = self._db.execute("SELECT procedure_id, ordinal FROM pr_steps WHERE operation_id=?",
                                (operation["id"],)).fetchone()
        if step is None:
            return
        row = self._row(step["procedure_id"])
        self._owner(context, row)
        if operation["state"] == "accepted":
            self._control_gate(row, now)
        self._prefix_gate(self._steps(row["id"]), step["ordinal"])

    def submit(self, context, request):
        request = parse_procedure(request)
        digest = procedure_digest(request)
        with self.journal._transaction():
            namespace = self.journal._namespace(context, request["replayNamespace"])
            key = self._db.execute("SELECT * FROM pr_keys WHERE namespace=? AND caller_key=?",
                                   (request["replayNamespace"], request["procedureKey"])).fetchone()
            if key is not None:
                row = self._row(key["procedure_id"])
                self._read_access(context, row)
                if key["step_id"] is not None or row["digest"] != digest:
                    raise JournalError("KEY_CONFLICT")
                return self._status(row)
            now = self.journal._now()
            timing = request["procedure"]["timing"]
            if now >= namespace["expires_ms"]:
                raise JournalError("EXPIRED_REPLAY_NAMESPACE")
            if now >= timing["latestStartUnixMs"]:
                raise JournalError("START_DEADLINE")
            if timing["latestCompletionUnixMs"] > namespace["expires_ms"]:
                raise JournalError("PROCEDURE_NAMESPACE_TOO_SHORT")
            for step in request["procedure"]["steps"]:
                self.journal.policy.validate_bound(context, step["request"]["intent"], now)
            keys = [(request["procedureKey"], None)] + [
                (s["request"]["operationKey"], s["stepId"]) for s in request["procedure"]["steps"]]
            for caller_key, _ in keys:
                if (self._db.execute("SELECT 1 FROM replay_keys WHERE namespace=? AND caller_key=?",
                                     (request["replayNamespace"], caller_key)).fetchone() or
                        self._db.execute("SELECT 1 FROM pr_keys WHERE namespace=? AND caller_key=?",
                                         (request["replayNamespace"], caller_key)).fetchone()):
                    raise JournalError("KEY_CONFLICT")
            procedure_id = "procedure:" + uuid.uuid4().hex
            delivery = {"operationId": None, "status": "no_active_child", "code": None}
            self._db.execute("INSERT INTO pr_procedures VALUES (?, ?, ?, ?, ?, 'accepted', NULL, 0, 0, ?, 0)",
                             (procedure_id, context.principal, context.deployment, digest, canonical(request), canonical(delivery)))
            for ordinal, step in enumerate(request["procedure"]["steps"]):
                self._db.execute("INSERT INTO pr_steps VALUES (?, ?, ?, ?, ?, NULL)",
                                 (procedure_id, ordinal, step["stepId"], canonical(step["request"]),
                                  intent_digest(step["request"]["intent"])))
            for caller_key, step_id in keys:
                self._db.execute("INSERT INTO pr_keys VALUES (?, ?, ?, ?)",
                                 (request["replayNamespace"], caller_key, procedure_id, step_id))
            self._event(procedure_id, now, "accepted", {"requestDigest": digest, "stepCount": len(keys) - 1})
            return self._status(self._row(procedure_id))

    def _status(self, row):
        steps = self._steps(row["id"])
        operations = self._operations(steps)
        projections = []
        for step, operation in zip(steps, operations):
            projections.append({
                "stepId": step["step_id"], "ordinal": step["ordinal"],
                "requestDigest": step["digest"], "operationId": step["operation_id"],
                "executionState": operation["state"] if operation else "unstarted",
                "cancellationState": operation["cancel_state"] if operation else "not_requested",
                "effectVerification": operation["verification"] if operation else "unverified",
                "mayHaveActed": operation["may_have_acted"] if operation else False,
                "heldResources": len(operation["claims"]) if operation else 0,
                "eventSequence": operation["sequence"] if operation else 0})
        verification = {op["verification"] for op in operations if op}
        aggregate = "disputed" if "disputed" in verification else "failed" if "failed" in verification else "unverified"
        return {"protocol": "hms.procedure-status/0.1", "procedureId": row["id"],
                "requestDigest": row["digest"], "profile": PROFILE,
                "timing": row["request"]["procedure"]["timing"], "executionState": row["state"],
                "reason": row["reason"], "cancelRequested": bool(row["cancel_requested"]),
                "cancelBlockedCode": row["cancel_delivery"]["code"] if row["cancel_delivery"]["status"] == "denied" else None,
                "cursor": row["cursor"], "stepCount": len(steps), "eventSequence": row["sequence"],
                "mayHaveActed": any(op["may_have_acted"] for op in operations if op),
                "aggregateVerification": aggregate,
                "unresolvedOperations": [op["id"] for op in operations if op and
                    (op["state"] not in TERMINAL or op["claims"] or op["verification"] in {"failed", "disputed"})],
                "steps": projections}

    def status(self, context, procedure_id):
        identifier(procedure_id)
        with self.journal._mutex:
            row = self._row(procedure_id)
            self._read_access(context, row)
            return self._status(row)

    def cancel(self, context, procedure_id):
        identifier(procedure_id)
        with self.journal._transaction():
            row = self._row(procedure_id)
            self._owner(context, row)
            now = self.journal._record_now()
            if not row["cancel_requested"]:
                self._db.execute("UPDATE pr_procedures SET cancel_requested=1 WHERE id=?", (procedure_id,))
                self._event(procedure_id, now, "cancel_requested", {})
            if row["state"] not in _FINAL:
                self._change(row, "canceled", "CLIENT_CANCEL", now)
            steps = self._steps(procedure_id)
            active = steps[row["cursor"]] if row["cursor"] < len(steps) else None
            delivery = {"operationId": active["operation_id"] if active else None,
                        "status": "no_active_child", "code": None}
            if delivery["operationId"]:
                operation = self.journal._operation(delivery["operationId"])
                if operation["state"] in TERMINAL:
                    delivery["status"] = "already_terminal"
                else:
                    try:
                        self.journal._request_cancel_in_tx(context, operation["id"])
                        delivery["status"] = "recorded"
                    except JournalError as error:
                        # The private Journal helper authorizes before any
                        # writes. Expected denial cannot undo owner withdrawal.
                        if error.code != "ACCESS_DENIED":
                            raise
                        delivery.update(status="denied", code=error.code)
            if delivery != row["cancel_delivery"]:
                self._db.execute("UPDATE pr_procedures SET cancel_delivery=? WHERE id=?", (canonical(delivery), procedure_id))
                self._event(procedure_id, now, "cancel_delivery", delivery)
            row = self._row(procedure_id)
            return {"protocol": "hms.procedure-cancel/0.1", "procedureId": procedure_id,
                    "executionState": row["state"], "cancelRequested": bool(row["cancel_requested"]),
                    "cancelBlockedCode": delivery["code"] if delivery["status"] == "denied" else None,
                    "eventSequence": row["sequence"], "delivery": delivery}

    def resume(self, context, procedure_id):
        identifier(procedure_id)
        with self.journal._transaction():
            row = self._row(procedure_id)
            self._read_access(context, row)
            if row["state"] != "interrupted" or row["cancel_requested"]:
                raise JournalError("PROCEDURE_NOT_RESUMABLE")
            now = self.journal._now()
            timing = row["request"]["procedure"]["timing"]
            if now >= timing["latestCompletionUnixMs"]:
                raise JournalError("PROCEDURE_DEADLINE")
            steps = self._steps(procedure_id)
            self._prefix_gate(steps, row["cursor"])
            for step in steps[row["cursor"]:]:
                operation = self.journal._operation(step["operation_id"]) if step["operation_id"] else None
                if operation and not self._successful(operation) and operation["state"] != "accepted":
                    raise JournalError("PROCEDURE_DEPENDENCY_UNRESOLVED")
                if operation and operation["state"] == "accepted":
                    if now >= min(operation["intent"]["timing"]["latestStartUnixMs"], operation["admission"]["lease_expires_ms"]):
                        raise JournalError("START_DEADLINE")
                if not operation or operation["state"] == "accepted":
                    if now >= step["request"]["intent"]["timing"]["latestStartUnixMs"]:
                        raise JournalError("START_DEADLINE")
                    self.journal.policy.validate_bound(context, step["request"]["intent"], now)
            self._change(row, "running" if any(s["operation_id"] for s in steps) else "accepted", None, now)
            return self._status(self._row(procedure_id))

    def events(self, context, procedure_id, after=0, limit=100):
        identifier(procedure_id)
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise JournalError("INVALID_CURSOR")
        with self.journal._mutex:
            row = self._row(procedure_id)
            self._read_access(context, row)
            if after > row["sequence"]:
                raise JournalError("INVALID_CURSOR")
            events = [dict(event) | {"payload": json.loads(event["payload"])} for event in self._db.execute(
                "SELECT * FROM pr_events WHERE procedure_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (procedure_id, after, limit))]
            return {"protocol": "hms.procedure-events/0.1", "procedureId": procedure_id,
                    "events": events, "next": events[-1]["sequence"] if events else after,
                    "head": row["sequence"], "gap": False}

    def _advance(self, row, now):
        """Reconcile child facts and select at most one immutable next request."""
        steps = self._steps(row["id"])
        operations = self._operations(steps)
        for operation in operations:
            if operation and operation["verification"] in {"failed", "disputed"}:
                self._change(row, "failed", "CHILD_EVIDENCE_INVALID", now)
                return None
        cursor = 0
        while cursor < len(operations) and self._successful(operations[cursor]):
            cursor += 1
        if cursor < row["cursor"]:
            self._change(row, "failed", "PROCEDURE_DEPENDENCY_UNRESOLVED", now)
            return None
        if cursor != row["cursor"]:
            self._db.execute("UPDATE pr_procedures SET cursor=? WHERE id=?", (cursor, row["id"]))
            self._event(row["id"], now, "cursor_advanced", {"cursor": cursor})
        if cursor == len(steps):
            self._change(row, "completed", None, now)
            return None
        operation = operations[cursor]
        if operation and operation["state"] in TERMINAL and operation["state"] != "completed":
            self._change(row, "failed", "CHILD_" + operation["state"].upper(), now)
            return None
        if operation and operation["state"] == "outcome_unknown":
            self._change(row, "interrupted", "CHILD_OUTCOME_UNKNOWN", now)
            return None
        timing = row["request"]["procedure"]["timing"]
        if now >= timing["latestCompletionUnixMs"] or (cursor == 0 and not operation and now >= timing["latestStartUnixMs"]):
            self._change(row, "expired", "PROCEDURE_DEADLINE", now)
            return None
        if now < timing["notBeforeUnixMs"] or operation is not None:
            return None
        return steps[cursor]

    def tick(self):
        """Bounded host-only work; at most one child per selected parent per tick."""
        with self.journal._mutex:
            rows = self._db.execute("SELECT id, rowid FROM pr_procedures WHERE state IN ('accepted','running') AND rowid>? ORDER BY rowid LIMIT 64",
                                    (self._last_selected,)).fetchall()
            if not rows and self._last_selected:
                self._last_selected = 0
                rows = self._db.execute("SELECT id, rowid FROM pr_procedures WHERE state IN ('accepted','running') ORDER BY rowid LIMIT 64").fetchall()
            if rows:
                self._last_selected = rows[-1][1]
            for selected in rows:
                try:
                    with self.journal._transaction():
                        row = self._row(selected[0])
                        now = self.journal._now()
                        step = self._advance(row, now)
                    if step is None:
                        continue
                    operation = self.journal.submit(self._context(row), canonical(step["request"]),
                                                    _managed=(row["id"], step["step_id"]))
                    # Existing-key replay bypasses submit hooks. It is only
                    # valid if the original atomic link already identifies it.
                    linked = self._db.execute("SELECT operation_id FROM pr_steps WHERE procedure_id=? AND ordinal=?",
                                              (row["id"], step["ordinal"])).fetchone()[0]
                    if linked != operation["id"]:
                        raise JournalError("PROCEDURE_LINK_MISMATCH")
                except JournalError as error:
                    if isinstance(error, ObservationAgeExpired):
                        # No child admission has committed. Wait for new valid
                        # evidence with the SAME reserved key and timing. Unknown
                        # clocks/quality/identity and false predicates remain
                        # substantive refusals, not automatic retries.
                        continue
                    if error.code in {"RESOURCE_BUSY", "NOT_YET_STARTABLE", "PROCEDURE_NOT_YET_STARTABLE",
                                      "PROCEDURE_PAUSED", "CLOCK_REGRESSION", "INVALID_CLOCK"}:
                        continue
                    with self.journal._transaction():
                        row = self._row(selected[0])
                        if row["state"] in _ACTIVE:
                            now = self.journal._record_now()
                            state = "expired" if error.code in {"START_DEADLINE", "START_EXPIRED", "EXPIRED_REPLAY_NAMESPACE", "PROCEDURE_DEADLINE"} else "failed"
                            self._change(row, state, error.code, now)
