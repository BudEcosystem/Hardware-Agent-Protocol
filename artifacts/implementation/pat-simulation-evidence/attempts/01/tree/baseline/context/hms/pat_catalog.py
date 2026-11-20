"""Immutable PAT candidates and a revisioned, trusted local promotion catalog.

This is an in-process management service, not a JSON evaluation ingress. Only
configured evaluator code can produce a receipt. It does not execute PATs or
claim that a simulation evaluation qualifies physical hardware. Registry-backed
environment providers and evaluator callbacks are trusted code: providers run
under the Journal transaction and must be pure, bounded and non-reentrant;
evaluators run outside it and may perform controlled simulation evaluations.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
import re
import sqlite3
from types import MappingProxyType
from typing import Callable

from .contracts import ContractError, SAFE_INTEGER, canonical, identifier, parse_json
from .journal import JournalError, RecordTime
from .pat_contracts import parse_pat, pat_digest


PROFILE = "hms.pat-catalog/0.1"
MAX_ENTRIES = 128
_CATEGORIES = {"positive", "boundary", "negative", "fault"}
_OUTCOMES = {"passed", "failed", "inconclusive"}
_DDL = (
    "CREATE TABLE pc_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE pc_deployments (deployment TEXT PRIMARY KEY, revision INTEGER NOT NULL)",
    "CREATE TABLE pc_artifacts (digest TEXT PRIMARY KEY, document BLOB NOT NULL)",
    """CREATE TABLE pc_entries (deployment TEXT NOT NULL REFERENCES pc_deployments(deployment),
        artifact TEXT NOT NULL REFERENCES pc_artifacts(digest), state TEXT NOT NULL,
        evaluation TEXT, decision TEXT, evaluation_conflict INTEGER NOT NULL,
        PRIMARY KEY(deployment, artifact))""",
    """CREATE TABLE pc_evaluations (digest TEXT PRIMARY KEY,
        deployment TEXT NOT NULL REFERENCES pc_deployments(deployment),
        artifact TEXT NOT NULL REFERENCES pc_artifacts(digest), evaluator TEXT NOT NULL,
        run_id TEXT NOT NULL, document BLOB NOT NULL,
        UNIQUE(deployment, evaluator, run_id))""",
    """CREATE TABLE pc_evaluation_conflicts (digest TEXT PRIMARY KEY,
        deployment TEXT NOT NULL REFERENCES pc_deployments(deployment),
        artifact TEXT NOT NULL REFERENCES pc_artifacts(digest), prior_evaluation TEXT NOT NULL
        REFERENCES pc_evaluations(digest), document BLOB NOT NULL)""",
    """CREATE TABLE pc_decisions (digest TEXT PRIMARY KEY,
        deployment TEXT NOT NULL REFERENCES pc_deployments(deployment),
        artifact TEXT NOT NULL REFERENCES pc_artifacts(digest), document BLOB NOT NULL)""",
    """CREATE TABLE pc_events (deployment TEXT NOT NULL REFERENCES pc_deployments(deployment),
        sequence INTEGER NOT NULL, time_ms INTEGER NOT NULL, clock_status TEXT NOT NULL,
        kind TEXT NOT NULL, payload BLOB NOT NULL, PRIMARY KEY(deployment, sequence))""",
)


def _exact(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise ContractError("invalid PAT catalog fields")


def _digest(value):
    if type(value) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise ContractError("invalid PAT catalog digest")
    return value


def _integer(value, maximum=SAFE_INTEGER):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ContractError("invalid PAT catalog integer")
    return value


def _hash(domain, document):
    return "sha256:" + hashlib.sha256(domain + b"\0" + canonical(document)).hexdigest()


@dataclass(frozen=True)
class Evaluator:
    """Trusted evaluator registration, never deserialized from a caller document.

    required_checks is an immutable tuple of (check id, category). The policy
    chooses specific cases; passing a fixed count is not a qualification rule.
    enabled, evaluate and verify_evidence are installed code, never artifact
    callables. An evidence verifier runs synchronously inside the authority
    transaction. It must be bounded and pure, use only ordinary SELECT reads
    on this Journal connection, and include its code in implementation_digest.
    It must not change connection policy or access other writers/services.
    The SQL guard catches accidental misuse; trusted Python is not sandboxed.
    """
    evaluator_id: str
    implementation_digest: str
    policy_digest: str
    required_checks: tuple[tuple[str, str], ...]
    evaluate: Callable
    enabled: Callable = lambda: True
    evidence_profile: str | None = None
    verify_evidence: Callable | None = None

    def __post_init__(self):
        identifier(self.evaluator_id)
        _digest(self.implementation_digest)
        _digest(self.policy_digest)
        if (type(self.required_checks) is not tuple or not 1 <= len(self.required_checks) <= 128 or
                not callable(self.evaluate) or not callable(self.enabled)):
            raise ContractError("invalid trusted PAT evaluator")
        if (self.evidence_profile is None) != (self.verify_evidence is None):
            raise ContractError("PAT evidence profile and verifier must be configured together")
        if self.evidence_profile is not None:
            identifier(self.evidence_profile)
            if not callable(self.verify_evidence):
                raise ContractError("invalid trusted PAT evidence verifier")
        seen, categories = set(), set()
        for item in self.required_checks:
            if type(item) is not tuple or len(item) != 2:
                raise ContractError("invalid required PAT evaluation check")
            name, category = item
            identifier(name)
            if name in seen or type(category) is not str or category not in _CATEGORIES:
                raise ContractError("duplicate or unsupported evaluation check")
            seen.add(name)
            categories.add(category)
        if categories != _CATEGORIES:
            raise ContractError("PAT evaluator must include positive, boundary, negative and fault cases")
        if len(canonical(self.identity())) > 8192:
            raise ContractError("PAT evaluator identity exceeds catalog bound")

    def identity(self):
        value = {"evaluatorId": self.evaluator_id, "implementationDigest": self.implementation_digest,
                "policyDigest": self.policy_digest,
                "requiredChecks": [{"id": name, "category": category} for name, category in self.required_checks]}
        if self.evidence_profile is not None:
            value["evidenceProfile"] = self.evidence_profile
        return value


class PatCatalog:
    def __init__(self, journal, *, compiler_digest: Callable, environment: Callable,
                 evaluators: tuple[Evaluator, ...]):
        if (not callable(compiler_digest) or not callable(environment) or
                type(evaluators) is not tuple or len(evaluators) > 32 or
                any(type(e) is not Evaluator for e in evaluators) or
                len({e.evaluator_id for e in evaluators}) != len(evaluators)):
            raise ContractError("invalid PAT catalog trusted services")
        self.journal, self._db = journal, journal._db
        self._compiler_digest, self._environment_provider = compiler_digest, environment
        self._evaluators = MappingProxyType({e.evaluator_id: e for e in evaluators})
        with journal._transaction():
            expected = {"pc_meta", "pc_deployments", "pc_artifacts", "pc_entries",
                        "pc_evaluations", "pc_evaluation_conflicts", "pc_decisions", "pc_events"}
            present = {r[0] for r in self._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'pc_*'")}
            if present and present != expected:
                raise JournalError("INCOMPLETE_PAT_CATALOG")
            if not present:
                for statement in _DDL:
                    self._db.execute(statement)
                self._db.execute("INSERT INTO pc_meta VALUES ('version', ?)", (PROFILE,))
            version = self._db.execute("SELECT value FROM pc_meta WHERE key='version'").fetchone()
            if version is None or version[0] != PROFILE:
                raise JournalError("UNSUPPORTED_PAT_CATALOG")

    def _authorize(self, context):
        self.journal.policy.authorize(context, "admin", "*")

    def _revision(self, deployment):
        row = self._db.execute("SELECT revision FROM pc_deployments WHERE deployment=?", (deployment,)).fetchone()
        return row[0] if row else 0

    def _entry(self, deployment, digest):
        row = self._db.execute("SELECT * FROM pc_entries WHERE deployment=? AND artifact=?",
                               (deployment, digest)).fetchone()
        if row is None:
            raise JournalError("PAT_NOT_FOUND")
        return dict(row)

    def _artifact(self, digest):
        return json.loads(self._db.execute("SELECT document FROM pc_artifacts WHERE digest=?", (digest,)).fetchone()[0])

    def _event(self, context, now, kind, payload):
        revision = self._revision(context.deployment)
        if revision >= SAFE_INTEGER:
            raise JournalError("PAT_REVISION_EXHAUSTED")
        revision += 1
        self._db.execute("UPDATE pc_deployments SET revision=? WHERE deployment=?", (revision, context.deployment))
        stamp = now.value if isinstance(now, RecordTime) else now
        status = now.status if isinstance(now, RecordTime) else "unqualified_host_clock"
        self._db.execute("INSERT INTO pc_events VALUES (?, ?, ?, ?, ?, ?)",
                         (context.deployment, revision, stamp, status, kind,
                          canonical(payload | {"principal": context.principal})))
        return revision

    def _evaluator(self, evaluator_id):
        evaluator = self._evaluators.get(evaluator_id)
        if evaluator is None:
            raise JournalError("PAT_EVALUATOR_UNTRUSTED")
        try:
            enabled = evaluator.enabled()
        except Exception as error:
            raise JournalError("PAT_EVALUATOR_UNAVAILABLE") from error
        if enabled is not True:
            raise JournalError("PAT_EVALUATOR_UNTRUSTED")
        return evaluator

    def _environment(self, context, artifact):
        # Copy before use, so a trusted provider retaining its dictionary cannot
        # alter the snapshot after this transaction. Type checks precede JCS.
        try:
            value = self._environment_provider(context, copy.deepcopy(artifact))
            compiler = self._compiler_digest()
        except Exception as error:
            raise JournalError("PAT_ENVIRONMENT_UNAVAILABLE") from error
        _exact(value, {"profile", "deployment", "evidenceMode", "compilerDigest", "roles"})
        if (value["profile"] != "hms.pat.environment/0.1" or value["deployment"] != context.deployment or
                value["evidenceMode"] != "simulation" or value["compilerDigest"] != _digest(compiler)):
            raise JournalError("PAT_ENVIRONMENT_UNSUPPORTED")
        if type(value["roles"]) is not dict or set(value["roles"]) != set(artifact["roles"]):
            raise ContractError("PAT environment role closure mismatch")
        for name, role in value["roles"].items():
            _exact(role, {"typeDigest", "bindingDigest", "installationDigest", "argumentMetadataDigest",
                          "driverProfile", "driverDigest"})
            for field in set(role) - {"driverProfile"}:
                _digest(role[field])
            identifier(role["driverProfile"])
            if role["driverProfile"] not in artifact["roles"][name]["driverProfiles"]:
                raise JournalError("PAT_ENVIRONMENT_UNSUPPORTED")
        encoded = canonical(value)
        if len(encoded) > 16384:
            raise ContractError("PAT environment exceeds catalog bound")
        return parse_json(encoded)

    def publish(self, context, artifact):
        document = parse_pat(artifact)
        digest = pat_digest(document)
        with self.journal._transaction():
            self._authorize(context)
            row = self._db.execute("SELECT 1 FROM pc_entries WHERE deployment=? AND artifact=?",
                                   (context.deployment, digest)).fetchone()
            if row is None:
                if self._db.execute("SELECT count(*) FROM pc_entries WHERE deployment=?", (context.deployment,)).fetchone()[0] >= MAX_ENTRIES:
                    raise JournalError("PAT_CATALOG_LIMIT")
                now = self.journal._record_now()
                self._db.execute("INSERT OR IGNORE INTO pc_deployments VALUES (?, 0)", (context.deployment,))
                self._db.execute("INSERT OR IGNORE INTO pc_artifacts VALUES (?, ?)", (digest, canonical(document)))
                self._db.execute("INSERT INTO pc_entries VALUES (?, ?, 'candidate', NULL, NULL, 0)", (context.deployment, digest))
                self._event(context, now, "candidate_published", {"artifactDigest": digest})
            return self._describe(context, digest)

    @staticmethod
    def _evaluation_result(result, evaluator):
        _exact(result, {"checks", "unresolvedEffects", "limitations"})
        _integer(result["unresolvedEffects"])
        if type(result["checks"]) is not list or len(result["checks"]) > 128:
            raise ContractError("invalid PAT evaluation checks")
        if (type(result["limitations"]) is not list or len(result["limitations"]) > 32 or
                any(type(v) is not str or not 1 <= len(v) <= 512 for v in result["limitations"])):
            raise ContractError("invalid PAT evaluation limitations")
        checks = {}
        required = dict(evaluator.required_checks)
        for check in result["checks"]:
            _exact(check, {"id", "category", "outcome", "evidenceDigest"})
            identifier(check["id"])
            _digest(check["evidenceDigest"])
            if (check["id"] in checks or type(check["category"]) is not str or check["category"] not in _CATEGORIES or
                    type(check["outcome"]) is not str or check["outcome"] not in _OUTCOMES or
                    (check["id"] in required and required[check["id"]] != check["category"])):
                raise ContractError("invalid or contradictory PAT evaluation check")
            checks[check["id"]] = check
        passed = (set(required) <= set(checks) and result["unresolvedEffects"] == 0 and
                  all(c["outcome"] == "passed" for c in checks.values()))
        outcome = "passed" if passed else ("failed" if any(c["outcome"] == "failed" for c in checks.values()) else "inconclusive")
        encoded = canonical(result)
        if len(encoded) > 32768:
            raise ContractError("PAT evaluation result exceeds catalog bound")
        return parse_json(encoded), outcome

    def evaluate(self, context, artifact_digest, evaluator_id, run_id):
        """Invoke registered evaluator code; no caller-provided result is accepted.

        A run id deduplicates an already committed evaluation. Concurrent calls
        may both evaluate outside the lock; their exact results must agree or the
        second is refused. Evaluation code must not actuate physical hardware.
        """
        _digest(artifact_digest)
        identifier(evaluator_id)
        identifier(run_id)
        with self.journal._transaction():
            self._authorize(context)
            evaluator = self._evaluator(evaluator_id)
            self._entry(context.deployment, artifact_digest)
            previous = self._db.execute("SELECT * FROM pc_evaluations WHERE deployment=? AND evaluator=? AND run_id=?",
                                        (context.deployment, evaluator_id, run_id)).fetchone()
            if previous:
                if previous["artifact"] != artifact_digest:
                    raise JournalError("PAT_EVALUATION_KEY_CONFLICT")
                return {"evaluationDigest": previous["digest"], "receipt": json.loads(previous["document"])}
            artifact = self._artifact(artifact_digest)
            environment = self._environment(context, artifact)
        error = None
        try:
            result, outcome = self._evaluation_result(
                evaluator.evaluate(copy.deepcopy(artifact), copy.deepcopy(environment)), evaluator)
        except Exception as failure:
            # Failure to produce a valid receipt is itself retained, never
            # converted to a passed trial or an omitted attempt.
            result = {"checks": [], "unresolvedEffects": None,
                      "limitations": ["Evaluator did not produce a valid complete result; unresolved effects are unknown"]}
            outcome, error = "inconclusive", type(failure).__name__[:128]
        receipt = {"protocol": "hms.pat-evaluation/0.1", "runId": run_id,
                   "artifactDigest": artifact_digest, "artifactDomainDigest": _hash(b"HMS-PAT-DOMAIN-v0.1", artifact),
                   "evaluator": evaluator.identity(), "environment": environment,
                   "environmentDigest": _hash(b"HMS-PAT-ENVIRONMENT-v0.1", environment),
                   "outcome": outcome, "result": result, "evaluatorError": error,
                   "physicalObjectiveVerified": False}
        digest = _hash(b"HMS-PAT-EVALUATION-v0.1", receipt)
        conflict = False
        with self.journal._transaction():
            self._authorize(context)
            self._evaluator(evaluator_id)
            entry = self._entry(context.deployment, artifact_digest)
            previous = self._db.execute("SELECT digest, artifact FROM pc_evaluations WHERE deployment=? AND evaluator=? AND run_id=?",
                                        (context.deployment, evaluator_id, run_id)).fetchone()
            if previous:
                if previous[0] == digest:
                    return {"evaluationDigest": digest, "receipt": receipt}
                # Two concurrent executions of one evaluation key disagreed.
                # Preserve the second result and inhibit reuse before reporting
                # the conflict. Raising inside this transaction would discard
                # the new negative evidence and could leave a promoted pass.
                retained = self._db.execute("SELECT 1 FROM pc_evaluation_conflicts WHERE digest=?", (digest,)).fetchone()
                if not retained:
                    now = self.journal._record_now()
                    self._db.execute("INSERT INTO pc_evaluation_conflicts VALUES (?, ?, ?, ?, ?)",
                                     (digest, context.deployment, artifact_digest, previous[0], canonical(receipt)))
                    self._db.execute("UPDATE pc_entries SET evaluation_conflict=1, state=CASE WHEN state='retired' THEN state ELSE 'suspended' END WHERE deployment=? AND artifact IN (?, ?)",
                                     (context.deployment, artifact_digest, previous[1]))
                    self._event(context, now, "evaluation_conflict", {"artifactDigest": artifact_digest,
                                 "priorArtifactDigest": previous[1], "priorEvaluationDigest": previous[0],
                                 "conflictingEvaluationDigest": digest})
                conflict = True
            else:
                now = self.journal._record_now()
                self._db.execute("INSERT INTO pc_evaluations VALUES (?, ?, ?, ?, ?, ?)",
                                 (digest, context.deployment, artifact_digest, evaluator_id, run_id, canonical(receipt)))
                state = {"candidate": "evaluated", "evaluated": "evaluated", "active": "suspended",
                         "suspended": "suspended", "retired": "retired"}[entry["state"]]
                self._db.execute("UPDATE pc_entries SET state=?, evaluation=?, evaluation_conflict=0 WHERE deployment=? AND artifact=?",
                                 (state, digest, context.deployment, artifact_digest))
                self._event(context, now, "evaluation_recorded", {"artifactDigest": artifact_digest,
                             "evaluationDigest": digest, "outcome": outcome, "state": state})
        if conflict:
            raise JournalError("PAT_EVALUATION_KEY_CONFLICT")
        return {"evaluationDigest": digest, "receipt": receipt}

    def _verify_evidence(self, evaluator, context, receipt):
        if evaluator.verify_evidence is None:
            return True, None
        if not self._db.in_transaction:
            raise JournalError("PAT_EVIDENCE_TRANSACTION_REQUIRED")
        outer_guard = getattr(self.journal, "_pat_evidence_guard", None)
        if outer_guard is not None:
            outer_guard["denied"] = True
            raise JournalError("PAT_EVIDENCE_REENTRANT")
        before = self._db.total_changes
        guard = {"denied": False}

        def authorize(action, _first, _second, database, _source):
            if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ} and database in {None, "main"}:
                return sqlite3.SQLITE_OK
            guard["denied"] = True
            return sqlite3.SQLITE_DENY

        # Journal owns this connection and otherwise installs no authorizer.
        # The guard remains installed through fetch/evaluation, including any
        # re-preparation. Reentry cannot replace another catalog's guard.
        self.journal._pat_evidence_guard = guard
        try:
            self._db.set_authorizer(authorize)
            try:
                valid = evaluator.verify_evidence(context, copy.deepcopy(receipt))
            except Exception:
                # Callback error codes cannot masquerade as a known ineligible
                # candidate and manufacture uniqueness in PAT selection.
                return False, "PAT_EVIDENCE_UNAVAILABLE"
        finally:
            try:
                self._db.set_authorizer(None)
            finally:
                self.journal._pat_evidence_guard = None
            if guard["denied"] or not self._db.in_transaction or self._db.total_changes != before:
                # Must escape _eligible, even if the callback swallowed its SQL
                # error. Returning False could otherwise commit a mutation.
                raise JournalError("PAT_EVIDENCE_PROVIDER_IMPURE")
        if valid is False:
            return False, "PAT_EVIDENCE_INVALID"
        if valid is not True:
            return False, "PAT_EVIDENCE_INVALID_RESPONSE"
        return True, None

    def _eligible(self, context, entry):
        if self._revision(context.deployment) >= SAFE_INTEGER:
            return False, "PAT_REVISION_EXHAUSTED"
        if entry["evaluation_conflict"]:
            return False, "PAT_EVALUATION_CONFLICT"
        if entry["evaluation"] is None:
            return False, "PAT_NOT_EVALUATED"
        receipt = json.loads(self._db.execute("SELECT document FROM pc_evaluations WHERE digest=?", (entry["evaluation"],)).fetchone()[0])
        if receipt["outcome"] != "passed":
            return False, "PAT_EVALUATION_NOT_PASSED"
        try:
            evaluator = self._evaluator(receipt["evaluator"]["evaluatorId"])
            if canonical(evaluator.identity()) != canonical(receipt["evaluator"]):
                return False, "PAT_EVALUATOR_CHANGED"
            environment = self._environment(context, self._artifact(entry["artifact"]))
        except JournalError as failure:
            return False, failure.code
        except ContractError:
            return False, "PAT_ENVIRONMENT_INVALID"
        if canonical(environment) != canonical(receipt["environment"]):
            return False, "PAT_DEPENDENCIES_CHANGED"
        # Keep this outside the provider-error handler: purity violations must
        # unwind the authority transaction, not become committable descriptions.
        return self._verify_evidence(evaluator, context, receipt)

    def transition(self, context, artifact_digest, *, expected_revision, target):
        _digest(artifact_digest)
        _integer(expected_revision)
        if type(target) is not str or target not in {"active", "suspended", "retired"}:
            raise ContractError("unsupported PAT catalog transition")
        with self.journal._transaction():
            self._authorize(context)
            if self._revision(context.deployment) != expected_revision:
                raise JournalError("PAT_CATALOG_REVISION_CONFLICT")
            if expected_revision >= SAFE_INTEGER:
                raise JournalError("PAT_REVISION_EXHAUSTED")
            entry = self._entry(context.deployment, artifact_digest)
            if entry["state"] == "retired" or entry["state"] == target:
                raise JournalError("PAT_TRANSITION_NOT_ALLOWED")
            if target == "active":
                now = self.journal._now()
                eligible, reason = self._eligible(context, entry)
                if not eligible:
                    raise JournalError(reason)
            else:
                now = self.journal._record_now()
            decision = {"protocol": "hms.pat-decision/0.1", "deployment": context.deployment,
                        "principal": context.principal, "artifactDigest": artifact_digest,
                        "evaluationDigest": entry["evaluation"], "expectedRevision": expected_revision,
                        "newRevision": expected_revision + 1, "from": entry["state"], "to": target,
                        "admittedInstancePolicy": "retain_pinned_version"}
            digest = _hash(b"HMS-PAT-DECISION-v0.1", decision)
            self._db.execute("INSERT INTO pc_decisions VALUES (?, ?, ?, ?)",
                             (digest, context.deployment, artifact_digest, canonical(decision)))
            self._db.execute("UPDATE pc_entries SET state=?, decision=? WHERE deployment=? AND artifact=?",
                             (target, digest, context.deployment, artifact_digest))
            self._event(context, now, "catalog_transition", {"artifactDigest": artifact_digest,
                         "decisionDigest": digest, "state": target})
            return self._describe(context, artifact_digest)

    def _describe(self, context, digest):
        entry = self._entry(context.deployment, digest)
        eligible, reason = ((False, "PAT_RETIRED") if entry["state"] == "retired" else self._eligible(context, entry))
        return {"protocol": "hms.pat-catalog-entry/0.1", "artifactDigest": digest,
                "catalogRevision": self._revision(context.deployment), "state": entry["state"],
                "evaluationDigest": entry["evaluation"], "decisionDigest": entry["decision"],
                "evaluationConflicted": bool(entry["evaluation_conflict"]),
                "eligibleForPromotion": eligible and entry["state"] not in {"active", "retired"},
                "eligibleForNewInstances": eligible and entry["state"] == "active",
                "eligibilityReason": reason if reason else ("PAT_NOT_ACTIVE" if entry["state"] != "active" else None)}

    def describe(self, context, artifact_digest):
        _digest(artifact_digest)
        with self.journal._transaction():
            self._authorize(context)
            return self._describe(context, artifact_digest)

    def artifact(self, context, artifact_digest):
        _digest(artifact_digest)
        with self.journal._transaction():
            self._authorize(context)
            self._entry(context.deployment, artifact_digest)
            return self._artifact(artifact_digest)

    def evaluation(self, context, evaluation_digest):
        _digest(evaluation_digest)
        with self.journal._transaction():
            self._authorize(context)
            row = self._db.execute("SELECT document FROM pc_evaluations WHERE digest=? AND deployment=? UNION ALL SELECT document FROM pc_evaluation_conflicts WHERE digest=? AND deployment=?",
                                   (evaluation_digest, context.deployment, evaluation_digest, context.deployment)).fetchone()
            if row is None:
                raise JournalError("PAT_EVALUATION_NOT_FOUND")
            return json.loads(row[0])

    def snapshot(self, context):
        """Bounded complete management snapshot; not a public execution router."""
        with self.journal._transaction():
            self._authorize(context)
            rows = self._db.execute("SELECT artifact FROM pc_entries WHERE deployment=? ORDER BY artifact LIMIT ?",
                                    (context.deployment, MAX_ENTRIES + 1)).fetchall()
            if len(rows) > MAX_ENTRIES:
                raise JournalError("PAT_CATALOG_LIMIT")
            return {"protocol": "hms.pat-catalog-snapshot/0.1", "catalogRevision": self._revision(context.deployment),
                    "entries": [self._describe(context, row[0]) for row in rows]}

    def events(self, context, *, after=0, limit=100):
        _integer(after)
        _integer(limit, 100)
        if limit == 0:
            raise ContractError("positive PAT catalog event limit required")
        with self.journal._transaction():
            self._authorize(context)
            if after > self._revision(context.deployment):
                raise JournalError("PAT_INVALID_CURSOR")
            rows = self._db.execute("SELECT * FROM pc_events WHERE deployment=? AND sequence>? ORDER BY sequence LIMIT ?",
                                    (context.deployment, after, limit)).fetchall()
            events = [dict(row) | {"payload": json.loads(row["payload"])} for row in rows]
            return {"protocol": "hms.pat-catalog-events/0.1", "events": events,
                    "headSequence": self._revision(context.deployment),
                    "nextSequence": events[-1]["sequence"] if events else after}
