"""Deterministic structured PAT runs with atomic, immutable procedure linkage.

The installed resolver is trusted pure, bounded code, not caller JSON. Routing
uses static authorization and evaluated dependencies, never transient presence,
observations or resource availability. Existing invoke/read permissions authorize
composition; catalog publication and promotion retain their separate authority.
No model, synthesis, driver I/O or business action runs in this module.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid

from .contracts import SAFE_INTEGER, canonical, identifier
from .journal import JournalError
from .pat_catalog import MAX_ENTRIES
from .pat_compiler import _binding, compile_pat, compiler_digest
from .pat_contracts import PatError, closed, matches_static, parse_pat, scalar, snapshot


PROFILE = "hms.pat-execution/0.1"
MAX_ASSIGNMENTS = 16
MAX_TOTAL_ASSIGNMENTS = 128
_DDL = (
    "CREATE TABLE px_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE px_instances (
        id TEXT PRIMARY KEY, principal TEXT NOT NULL, deployment TEXT NOT NULL,
        namespace TEXT NOT NULL, run_key TEXT NOT NULL, request_digest TEXT NOT NULL,
        request BLOB NOT NULL, procedure_id TEXT NOT NULL UNIQUE REFERENCES pr_procedures(id),
        artifact_digest TEXT NOT NULL, artifact BLOB NOT NULL,
        evaluation_digest TEXT NOT NULL, evaluation BLOB NOT NULL,
        decision_digest TEXT NOT NULL, decision BLOB NOT NULL,
        catalog_revision INTEGER NOT NULL, compiler_digest TEXT NOT NULL,
        environment_digest TEXT NOT NULL, environment BLOB NOT NULL,
        run_binding_digest TEXT NOT NULL, bindings BLOB NOT NULL,
        parameters BLOB NOT NULL, compiled_digest TEXT NOT NULL, compiled_request BLOB NOT NULL,
        compilation BLOB NOT NULL, registry_revision INTEGER NOT NULL,
        inventory_digest TEXT NOT NULL, resolver_identity TEXT, selection BLOB NOT NULL,
        UNIQUE(namespace, run_key))""",
    """CREATE TABLE px_triggers (namespace TEXT NOT NULL, run_key TEXT NOT NULL,
        instance_id TEXT NOT NULL UNIQUE REFERENCES px_instances(id),
        PRIMARY KEY(namespace, run_key))""",
)


def _hash(domain, value):
    return "sha256:" + hashlib.sha256(domain + b"\0" + canonical(value)).hexdigest()


def parse_run(value):
    request = snapshot(value, "PAT_INVALID_RUN")
    closed(request, {"protocol", "replayNamespace", "runKey", "taskKind", "inputProfile",
                     "parameters", "evidenceMode", "originUnixMs", "latestCompletionUnixMs"}, "PAT_INVALID_RUN")
    if request["protocol"] != "hms.pat-run/0.1" or request["evidenceMode"] != "simulation":
        raise PatError("PAT_UNSUPPORTED_RUN")
    try:
        for key in ("replayNamespace", "runKey", "taskKind", "inputProfile"):
            identifier(request[key])
        if type(request["parameters"]) is not dict or len(request["parameters"]) > 32:
            raise PatError("PAT_INVALID_RUN")
        for key, value in request["parameters"].items():
            identifier(key)
            if not scalar(value):
                raise PatError("PAT_INVALID_RUN")
        origin, deadline = request["originUnixMs"], request["latestCompletionUnixMs"]
        if (type(origin) is not int or type(deadline) is not int or
                not 0 <= origin < deadline <= SAFE_INTEGER):
            raise PatError("PAT_INVALID_RUN")
    except ValueError as error:
        raise PatError("PAT_INVALID_RUN") from error
    return request


def run_digest(request):
    return _hash(b"HMS-PAT-RUN-v0.1", parse_run(request))


class PatExecutionStore:
    def __init__(self, journal, catalog, procedures, *, resolver):
        if catalog.journal is not journal or procedures.journal is not journal or not callable(resolver):
            raise PatError("PAT_EXECUTION_AUTHORITY_MISMATCH")
        self.journal, self.catalog, self.procedures = journal, catalog, procedures
        self._db, self.resolver = journal._db, resolver
        with journal._transaction():
            expected = {"px_meta", "px_instances", "px_triggers"}
            present = {row[0] for row in self._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'px_*'")}
            if present and present != expected:
                raise PatError("INCOMPLETE_PAT_EXECUTION")
            if not present:
                for statement in _DDL:
                    self._db.execute(statement)
                self._db.execute("INSERT INTO px_meta VALUES ('version', ?)", (PROFILE,))
            version = self._db.execute("SELECT value FROM px_meta WHERE key='version'").fetchone()
            if version is None or version[0] != PROFILE:
                raise PatError("UNSUPPORTED_PAT_EXECUTION")

    def _row(self, instance_id):
        identifier(instance_id)
        row = self._db.execute("SELECT * FROM px_instances WHERE id=?", (instance_id,)).fetchone()
        if row is None:
            raise PatError("PAT_INSTANCE_NOT_FOUND")
        return dict(row)

    @staticmethod
    def _owner(context, row):
        if (context.principal, context.deployment) != (row["principal"], row["deployment"]):
            raise JournalError("ACCESS_DENIED")

    def _linked(self, context, row, *, read=True):
        self._owner(context, row)
        try:
            procedure = self.procedures._row(row["procedure_id"])
        except JournalError as error:
            raise PatError("PAT_LINK_INVALID") from error
        if read:
            self.procedures._read_access(context, procedure)
        if ((procedure["principal"], procedure["deployment"]) != (row["principal"], row["deployment"]) or
                procedure["digest"] != row["compiled_digest"] or
                canonical(procedure["request"]) != row["compiled_request"]):
            raise PatError("PAT_LINK_INVALID")
        trigger = self._db.execute("SELECT instance_id FROM px_triggers WHERE namespace=? AND run_key=?",
                                   (row["namespace"], row["run_key"])).fetchone()
        if trigger is None or trigger[0] != row["id"]:
            raise PatError("PAT_LINK_INVALID")
        request = procedure["request"]
        expected = [(request["procedureKey"], None)] + [
            (step["request"]["operationKey"], step["stepId"]) for step in request["procedure"]["steps"]]
        for key, step_id in expected:
            reservation = self._db.execute("SELECT procedure_id,step_id FROM pr_keys WHERE namespace=? AND caller_key=?",
                                           (row["namespace"], key)).fetchone()
            if reservation is None or tuple(reservation) != (row["procedure_id"], step_id):
                raise PatError("PAT_LINK_INVALID")
        return procedure

    def _status(self, context, row):
        procedure = self._linked(context, row)
        return {"protocol": "hms.pat-instance/0.1", "instanceId": row["id"],
            "requestDigest": row["request_digest"], "artifactDigest": row["artifact_digest"],
            "evaluationDigest": row["evaluation_digest"], "decisionDigest": row["decision_digest"],
            "catalogRevision": row["catalog_revision"], "compilerDigest": row["compiler_digest"],
            "registryRevision": row["registry_revision"], "selectionInventoryDigest": row["inventory_digest"],
            "resolverIdentity": row["resolver_identity"],
            "environmentDigest": row["environment_digest"], "runBindingDigest": row["run_binding_digest"],
            "procedure": self.procedures._status(procedure)}

    def _compile(self, context, request, artifact, digest, bindings):
        keys = {step["stepId"]: "pat-step:" + _hash(b"HMS-PAT-STEP-KEY-v0.1", {
            "namespace": request["replayNamespace"], "runKey": request["runKey"],
            "artifactDigest": digest, "stepId": step["stepId"]})[7:] for step in artifact["steps"]}
        return compile_pat(artifact, request["parameters"], bindings,
            origin_ms=request["originUnixMs"], caller_deadline_ms=request["latestCompletionUnixMs"],
            replay_namespace=request["replayNamespace"], procedure_key=request["runKey"], operation_keys=keys,
            context={"taskKind": request["taskKind"], "inputProfile": request["inputProfile"],
                     "evidenceMode": request["evidenceMode"], "deployment": context.deployment})

    def _assignments(self, context, request, artifact):
        before = self._db.total_changes
        try:
            result = self.resolver(context, copy.deepcopy(artifact), copy.deepcopy(request))
        except Exception as error:
            raise PatError("PAT_BINDINGS_UNAVAILABLE") from error
        if not self._db.in_transaction or self._db.total_changes != before:
            raise PatError("PAT_RESOLVER_IMPURE")
        closed(result, {"complete", "assignments"}, "PAT_INVALID_BINDINGS")
        if result["complete"] is not True or type(result["assignments"]) is not list:
            raise PatError("PAT_INVALID_BINDINGS")
        if len(result["assignments"]) > MAX_ASSIGNMENTS:
            raise PatError("PAT_BINDING_LIMIT")
        assignments, identities = [], set()
        for value in result["assignments"]:
            binding = snapshot(value, "PAT_INVALID_BINDINGS")
            closed(binding, artifact["roles"], "PAT_INVALID_BINDINGS")
            try:
                identity = tuple(sorted((role, descriptor["binding"]["instanceId"],
                                         descriptor["binding"]["generation"]) for role, descriptor in binding.items()))
                if identity in identities:
                    raise PatError("PAT_DUPLICATE_BINDING")
                identities.add(identity)
            except (KeyError, TypeError) as error:
                raise PatError("PAT_INVALID_BINDINGS") from error
            assignments.append(binding)
        return assignments

    def _select(self, context, request, now):
        revision = self.catalog._revision(context.deployment)
        registry_revision = int(self._db.execute("SELECT value FROM reg_meta WHERE key='revision'").fetchone()[0])
        resolver_identity = getattr(self.resolver, "__dict__", {}).get("registration_identity")
        if resolver_identity is not None and (type(resolver_identity) is not str or len(resolver_identity) != 71 or
                not resolver_identity.startswith("sha256:") or any(c not in "0123456789abcdef" for c in resolver_identity[7:])):
            raise PatError("PAT_INVALID_RESOLVER_IDENTITY")
        inventory = []
        rows = self._db.execute("SELECT * FROM pc_entries WHERE deployment=? ORDER BY artifact LIMIT ?",
                                (context.deployment, MAX_ENTRIES + 1)).fetchall()
        if len(rows) > MAX_ENTRIES:
            raise PatError("PAT_CATALOG_LIMIT")
        selected, total = [], 0
        for raw in rows:
            entry = dict(raw)
            if entry["state"] != "active":
                continue
            artifact = parse_pat(self.catalog._artifact(entry["artifact"]))
            if (artifact["taskKind"], artifact["inputProfile"]) != (request["taskKind"], request["inputProfile"]):
                continue
            try:
                matched = matches_static(artifact, request["parameters"], task_kind=request["taskKind"],
                    input_profile=request["inputProfile"], evidence_mode=request["evidenceMode"])
            except PatError as error:
                if error.code in {"PAT_INVALID_PARAMETERS", "PAT_PARAMETER_OUT_OF_DOMAIN"}:
                    continue
                raise
            if not matched:
                continue
            assignments = self._assignments(context, request, artifact)
            inventory.append({"artifactDigest": entry["artifact"], "assignments": sorted(
                _hash(b"HMS-PAT-ASSIGNMENT-v0.1", bindings) for bindings in assignments)})
            total += len(assignments)
            if total > MAX_TOTAL_ASSIGNMENTS:
                raise PatError("PAT_BINDING_LIMIT")
            candidates = []
            for bindings in assignments:
                try:
                    for role, descriptor in bindings.items():
                        instance = identifier(descriptor["binding"]["instanceId"])
                        self.journal.policy.authorize(context, "read", instance)
                        for action in artifact["roles"][role]["actions"]:
                            self.journal.policy.authorize(context, "invoke:" + action, instance)
                except JournalError as error:
                    if error.code == "ACCESS_DENIED":
                        continue
                    raise
                except (KeyError, TypeError, ValueError) as error:
                    raise PatError("PAT_INVALID_BINDINGS") from error
                # Malformed metadata is not an incomplete inventory shortcut.
                for role, descriptor in bindings.items():
                    _binding(descriptor, artifact["roles"][role])
                try:
                    compiled = self._compile(context, request, artifact, entry["artifact"], bindings)
                except PatError as error:
                    # Valid primitives can have incompatible scalar limits or
                    # an explicitly different calibrated coordinate frame.
                    if error.code in {"PAT_ARGUMENT_DOMAIN", "PAT_SEMANTICS_MISMATCH"}:
                        continue
                    raise
                try:
                    for step in compiled["request"]["procedure"]["steps"]:
                        self.journal.policy.validate_bound(context, step["request"]["intent"], now)
                except JournalError as error:
                    if error.code == "ACCESS_DENIED":
                        continue
                    raise
                candidates.append((bindings, compiled))
            # Current environment services may themselves require instance
            # access. An inaccessible artifact must not block authorized work.
            if not candidates:
                continue
            if entry["evaluation"] is None or entry["evaluation_conflict"]:
                continue
            evaluation_row = self._db.execute("SELECT document FROM pc_evaluations WHERE digest=?",
                                              (entry["evaluation"],)).fetchone()
            if evaluation_row is None:
                raise PatError("PAT_EVALUATION_INVALID")
            evaluation = json.loads(evaluation_row[0])
            if evaluation["outcome"] != "passed":
                continue
            # An artifact may be evaluated for east while this principal only
            # has west authority. Do not query east's protected environment
            # merely because the generic artifact can compile for west too.
            candidates = [(bindings, compiled) for bindings, compiled in candidates
                if canonical(compiled["evaluationEnvironment"]) == canonical(evaluation["environment"])]
            if not candidates:
                continue
            eligible, reason = self.catalog._eligible(context, entry)
            if not eligible:
                if reason not in {"PAT_REVISION_EXHAUSTED", "PAT_EVALUATION_CONFLICT", "PAT_NOT_EVALUATED",
                        "PAT_EVALUATION_NOT_PASSED", "PAT_EVALUATOR_UNTRUSTED", "PAT_EVALUATOR_CHANGED",
                        "PAT_DEPENDENCIES_CHANGED"}:
                    raise PatError(reason or "PAT_SELECTION_UNAVAILABLE")
                continue
            environment = self.catalog._environment(context, artifact)
            if canonical(environment) != canonical(evaluation["environment"]):
                raise PatError("PAT_SELECTION_CHANGED")
            for bindings, compiled in candidates:
                if canonical(compiled["evaluationEnvironment"]) == canonical(environment):
                    selected.append((entry, artifact, evaluation, bindings, compiled))
        if not selected:
            raise PatError("PAT_NO_MATCH")
        if len(selected) != 1:
            raise PatError("PAT_AMBIGUOUS")
        entry, artifact, evaluation, bindings, compiled = selected[0]
        current = self.catalog._entry(context.deployment, entry["artifact"])
        eligible, _ = self.catalog._eligible(context, current)
        if (not eligible or current != entry or self.catalog._revision(context.deployment) != revision or
                compiled["compilerDigest"] != compiler_digest() or
                registry_revision != int(self._db.execute("SELECT value FROM reg_meta WHERE key='revision'").fetchone()[0]) or
                resolver_identity != getattr(self.resolver, "__dict__", {}).get("registration_identity") or
                canonical(self.catalog._environment(context, artifact)) != canonical(compiled["evaluationEnvironment"])):
            raise PatError("PAT_SELECTION_CHANGED")
        decision = json.loads(self._db.execute("SELECT document FROM pc_decisions WHERE digest=?",
                                              (entry["decision"],)).fetchone()[0])
        selection = {"profile": "hms.pat-selection/0.1", "catalogRevision": revision,
            "registryRevision": registry_revision, "resolverIdentity": resolver_identity,
            "inventory": inventory, "completenessAuthority": "trusted_installed_resolver"}
        return revision, entry, artifact, evaluation, decision, bindings, compiled, selection

    def run(self, context, value):
        request = parse_run(value)
        digest = run_digest(request)
        with self.journal._transaction():
            self.journal._namespace(context, request["replayNamespace"])
            prior = self._db.execute("SELECT instance_id FROM px_triggers WHERE namespace=? AND run_key=?",
                                    (request["replayNamespace"], request["runKey"])).fetchone()
            if prior is not None:
                row = self._row(prior[0])
                response = self._status(context, row)
                if row["request_digest"] != digest:
                    raise JournalError("KEY_CONFLICT")
                return response
            # A new run cannot adopt an existing plain procedure, even if its
            # compiled request would happen to be identical.
            for table in ("pr_keys", "replay_keys"):
                if self._db.execute(f"SELECT 1 FROM {table} WHERE namespace=? AND caller_key=?",
                        (request["replayNamespace"], request["runKey"])).fetchone():
                    raise JournalError("KEY_CONFLICT")
            now = self.journal._now()
            unchanged = self._db.total_changes
            revision, entry, artifact, evaluation, decision, bindings, compiled, selection = self._select(context, request, now)
            if not self._db.in_transaction or self._db.total_changes != unchanged:
                raise PatError("PAT_SELECTION_IMPURE")
            # Serialize every retained input before the first business write.
            documents = [canonical(value) for value in (request, artifact, evaluation, decision,
                compiled["evaluationEnvironment"], bindings, request["parameters"], compiled["request"], compiled, selection)]
            procedure = self.procedures._submit_in_tx(context, compiled["request"], compiled["requestDigest"])
            instance_id = "pat-instance:" + uuid.uuid4().hex
            self._db.execute("INSERT INTO px_instances VALUES (" + ",".join("?" for _ in range(28)) + ")", (
                instance_id, context.principal, context.deployment, request["replayNamespace"], request["runKey"],
                digest, documents[0], procedure["procedureId"], entry["artifact"], documents[1], entry["evaluation"],
                documents[2], entry["decision"], documents[3], revision, compiled["compilerDigest"],
                compiled["environmentDigest"], documents[4], compiled["runBindingDigest"], documents[5],
                documents[6], compiled["requestDigest"], documents[7], documents[8], selection["registryRevision"],
                _hash(b"HMS-PAT-SELECTION-v0.1", selection), selection["resolverIdentity"], documents[9]))
            self._db.execute("INSERT INTO px_triggers VALUES (?, ?, ?)",
                             (request["replayNamespace"], request["runKey"], instance_id))
            return self._status(context, self._row(instance_id))

    def status(self, context, instance_id):
        with self.journal._mutex:
            return self._status(context, self._row(instance_id))

    def cancel(self, context, instance_id):
        with self.journal._mutex:
            row = self._row(instance_id)
            self._linked(context, row, read=False)
            return {"protocol": "hms.pat-cancel/0.1", "instanceId": instance_id,
                    "procedure": self.procedures.cancel(context, row["procedure_id"])}

    def resume(self, context, instance_id):
        with self.journal._mutex:
            row = self._row(instance_id)
            self._linked(context, row)
            self.procedures.resume(context, row["procedure_id"])
            return self._status(context, row)
