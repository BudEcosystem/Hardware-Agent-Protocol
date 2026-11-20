"""Original-run preparation and a current-byte, SELECT-only catalog verifier."""
from collections import OrderedDict
from dataclasses import dataclass
import threading

from hms.contracts import canonical, identifier, parse_json
from hms.journal import JournalError
from hms.pat_catalog import Evaluator
from hms.pat_compiler import evaluation_environment
from hms.pat_contracts import pat_digest
from hms.pat_io_combined_matrix import POLICY as MATRIX_POLICY
from hms.pat_io_run_bundle import parse_io_run_bundle
from evidence import reducer
from evidence.contracts import sha, hash_value
from evidence_compact.store import CompactIoEvidenceStore
from . import contracts, projection
from .contracts import require, checked, detached

CHECKS = tuple(('complete-matrix:' + name, name) for name in ('positive', 'boundary', 'negative', 'fault'))
POLICY_DIGEST = hash_value(b'HMS-PAT-IO-RECORDED-CATALOG-POLICY-v0.1', dict(
    matrixPolicy=MATRIX_POLICY, completeOriginalMatrixRequired=True,
    candidateCategories='all original domainCase.categories', fixedChallengeCategory='fault',
    originalRunRequired=True, currentSourceApplicabilityRequired=True,
    physicalObjectiveVerified=False))

@dataclass(frozen=True)
class _Prepared:
    payload: bytes
    files: tuple
    projection: tuple
    sequence: int
    configuration_sequence: int
    resolver: object
    charge: int
    unimported_runs: tuple

class RecordedIoBridge:
    @checked
    def __init__(self, consumer, runtime, evaluator_ids, *, entries=contracts.MAX_ENTRIES,
                 byte_limit=contracts.MAX_MEMO_BYTES):
        require(type(consumer) is CompactIoEvidenceStore, 'AUTHORITY_MISMATCH')
        execution = consumer.execution
        execution.configurations._runtime(runtime)
        require(type(evaluator_ids) is tuple and 1 <= len(evaluator_ids) <= 16 and
                len(set(evaluator_ids)) == len(evaluator_ids), 'REGISTRATION')
        for name in evaluator_ids:
            identifier(name)
        require(type(entries) is int and 1 <= entries <= contracts.MAX_ENTRIES and
                type(byte_limit) is int and 1 <= byte_limit <= contracts.MAX_MEMO_BYTES, 'PREPARATION_CAPACITY')
        require(not consumer._db.in_transaction, 'TRANSACTION_REENTRY')
        self.consumer, self.execution, self.runtime = consumer, execution, runtime
        self.journal, self._db = consumer.journal, consumer._db
        self._runtime_catalog, self._supervisor = runtime.catalog, execution.supervisor
        self._identity = contracts.identity()
        self._evaluator_ids = evaluator_ids
        self._entries_limit, self._byte_limit = entries, byte_limit
        self._entries, self._bytes, self._mutex = OrderedDict(), 0, threading.RLock()

    def _enabled(self):
        return (self._identity == contracts.LOADED_IDENTITY and self.consumer.consumer_identity == contracts._CONSUMER and
                self.consumer.execution is self.execution and self.execution.supervisor is self._supervisor and
                self.runtime.journal is self.journal and self.runtime.catalog is self._runtime_catalog)

    def _deny_legacy(self, *args):
        raise contracts.RecordedError('EXPLICIT_INVOCATION_REQUIRED')

    def evaluators(self):
        """Installed registrations carry no mutable hidden evaluator/run key."""
        return tuple(Evaluator(name, self._identity, POLICY_DIGEST, CHECKS, self._deny_legacy,
            enabled=self._enabled, evidence_profile=contracts.PROFILE, verify_evidence=self.verify_catalog)
            for name in self._evaluator_ids)

    def usage(self):
        with self._mutex:
            return dict(entries=len(self._entries), chargedBytes=self._bytes,
                        entryLimit=self._entries_limit, byteLimit=self._byte_limit)

    def _key(self, evaluator, run):
        identifier(evaluator); identifier(run)
        require(evaluator in self._evaluator_ids, 'EVALUATOR_UNTRUSTED')
        require(self._enabled(), 'IMPLEMENTATION_CHANGED')
        return evaluator, run

    @staticmethod
    def _result(matrix, files):
        require(matrix['policy'] == MATRIX_POLICY, 'POLICY_CHANGED')
        groups = {category: [] for _, category in CHECKS}
        for i, case in enumerate(matrix['cases']):
            categories = case['domainCase']['categories'] if case['kind'] == 'candidate' else ['fault']
            for category in categories:
                require(category in groups, 'POLICY_CHANGED')
                groups[category].append(dict(caseId=case['caseId'], inspectionDigest=sha(files['inspection/case-%02d.json' % i])))
        require(all(groups.values()), 'MATRIX_INCOMPLETE')
        checks = [dict(id=name, category=category, outcome='passed',
            evidenceDigest=hash_value(b'HMS-PAT-IO-COMPLETE-CATEGORY-v0.1', groups[category]))
            for name, category in CHECKS]
        return dict(checks=checks, unresolvedEffects=0, limitations=[
            'Complete finite synthetic-I/O matrix only; physical behavior is not qualified',
            'Observed timing and retained evidence do not establish protected control capacity or general disk quotas'])

    def _payload(self, imported, reservation, files):
        prepared = reservation['preparedRun']; request = prepared['request']; bundle = prepared['bundle']
        parsed = parse_io_run_bundle(bundle['header'], bundle['documents'], expected_context=request['context'],
                                     expected_bundle_digest=request['bundleDigest'])
        inputs = parsed['expected_inputs']; artifact = inputs['candidate']; matrix = inputs['matrix']
        role = matrix['candidateContract']['role']; descriptor = inputs['descriptor']
        require(set(artifact['roles']) == {role}, 'PROFILE_UNSUPPORTED')
        static = evaluation_environment(artifact, {role: descriptor}, deployment=self.execution.deployment)
        anchor = imported['receipt']['anchor']
        require(pat_digest(artifact) == anchor['artifactDigest'], 'ARTIFACT_CHANGED')
        invocation = dict(profile=contracts.INVOCATION, original=anchor,
            importReceiptDigest=imported['receiptDigest'], consumerIdentity=self.consumer.consumer_identity,
            hostImplementationDigest=self._identity, evaluationPolicyDigest=POLICY_DIGEST,
            evidenceClosure=imported['receipt']['closure'], matrixDigest=request['bundleHeader']['matrixDigest'],
            caseIds=request['bundleHeader']['caseIds'])
        applicability = dict(profile=contracts.APPLICABILITY, authorityId=anchor['authorityId'],
            deployment=anchor['deployment'], configurationReceiptDigest=anchor['configurationReceiptDigest'],
            configurationDigest=anchor['configurationDigest'], configurationRevision=anchor['configurationRevision'],
            roleInstances={role: descriptor['binding']['instanceId']}, dependencies=static['dependencies'])
        return dict(artifact=artifact, invocation=invocation, applicability=applicability,
                    environment=static['evaluationEnvironment'], result=self._result(matrix, files))

    def _checkpoint(self, phase, value):
        """Installed test seam, never a caller-supplied callback."""

    @checked
    def prepare(self, context, artifact_digest, evaluator, run):
        """Resolve the original run and fully validate it outside admission."""
        require(not self._db.in_transaction, 'TRANSACTION_REENTRY')
        require(contracts.identity() == self._identity, 'IMPLEMENTATION_CHANGED')
        key = self._key(evaluator, run)
        self.consumer._begin(context, evaluator, run)
        with self.execution._execution():
            with self.journal._transaction():
                self.execution.configurations._authorize(context)
                state = self.consumer._state()
                require(key in state['keys'], 'IMPORT_UNAVAILABLE')
                imported, files = self.consumer._read_group(state, key)
                original = self.consumer._binding(state['execution'], key)
                require(imported['receipt']['anchor']['artifactDigest'] == artifact_digest, 'KEY_CONFLICT')
                saved, charge = projection.snapshot(self._db)
                configuration = state['execution']['runs']['configurations']['records'][original[0]['reservation']['configurationSequence']]
                anchor = imported['receipt']['anchor']
                unimported = tuple(sorted(other for other, record in state['execution']['runs']['keys'].items()
                    if record['reservation']['artifactDigest'] == artifact_digest and
                    record['reservation']['configurationReceiptDigest'] == anchor['configurationReceiptDigest'] and
                    other not in state['keys']))
            outputs = {name[len('original/output/'):]: body for name, body in files.items() if name.startswith('original/output/')}
            inspected = reducer.reduce_original(*original, outputs, self.consumer.consumer_identity)
            require(inspected['documents'] == files, 'SEMANTICS_CHANGED')
            payload = self._payload(imported, original[0], files)
            resolver = self.execution.configurations._resolver(self.runtime, configuration['configuration'], configuration['pin'])
            wire = canonical(payload)
            require(len(wire) <= 32768, 'READ_BOUND')
            frozen_files = tuple(sorted(files.items()))
            charge += len(wire) + 512 * len(unimported) + sum(len(name.encode('utf-8')) + len(body) + 512 for name, body in frozen_files)
            require(charge <= self._byte_limit, 'PREPARATION_CAPACITY')
            item = _Prepared(wire, frozen_files, saved, imported['receipt']['sequence'],
                             original[0]['reservation']['configurationSequence'], resolver, charge, unimported)
            require(contracts.identity() == self._identity, 'IMPLEMENTATION_CHANGED')
            self._checkpoint('before_preparation_publication', payload)
            with self.journal._transaction():
                self.execution.configurations._authorize(context)
                state = self.consumer._state()
                current, current_files = self.consumer._read_group(state, key)
                require(current == imported and current_files == files and projection.snapshot(self._db)[0] == saved,
                        'PREPARATION_CHANGED')
                with self._mutex:
                    previous = self._entries.get(key)
                    if previous is not None:
                        require(previous.payload == wire, 'PREPARATION_CONFLICT')
                        self._bytes -= previous.charge
                        del self._entries[key]
                    while len(self._entries) >= self._entries_limit or self._bytes + charge > self._byte_limit:
                        _, evicted = self._entries.popitem(last=False)
                        self._bytes -= evicted.charge
                    self._entries[key] = item
                    self._bytes += charge
            return detached(payload)

    def _entry(self, invocation):
        require(type(invocation) is dict and invocation.get('profile') == contracts.INVOCATION, 'INVOCATION_INVALID')
        original = invocation['original']; key = self._key(original['evaluatorId'], original['runId'])
        item = self._entries.get(key)
        require(item is not None, 'PREPARATION_UNAVAILABLE')
        payload = parse_json(item.payload)
        require(canonical(payload['invocation']) == canonical(invocation), 'INVOCATION_CHANGED')
        return item, payload

    def _current(self, context, item, payload):
        require(not item.unimported_runs, 'QUALIFICATION_UNRESOLVED')
        original = payload['invocation']['original']; app = payload['applicability']
        require(context.deployment == original['deployment'] == self.execution.deployment and
                original['authorityId'] == self.execution.authority_id == self.journal.authority_id, 'AUTHORITY_MISMATCH')
        head = projection.point(self._db, 'iosc_heads', (('sequence', projection.I),),
                                ' WHERE evaluator=?', (original['evaluatorId'],))
        require(head == (item.configuration_sequence,), 'CONTEXT_CHANGED')
        bindings = item.resolver.for_roles(context, payload['artifact'], app['roleInstances'])
        current = evaluation_environment(payload['artifact'], bindings, deployment=context.deployment)
        require(canonical(current['dependencies']) == canonical(app['dependencies']) and
                canonical(current['evaluationEnvironment']) == canonical(payload['environment']), 'CONTEXT_CHANGED')

    @checked
    def verify(self, context, payload, *, current):
        """Installed code only: no preparation insert/eviction or external I/O."""
        require(self._db.in_transaction and type(current) is bool, 'TRANSACTION_REQUIRED')
        with self._mutex:
            item, saved = self._entry(payload['invocation'])
            require(canonical(payload) == item.payload, 'RECORD_CHANGED')
            require(context.deployment == saved['applicability']['deployment'], 'AUTHORITY_MISMATCH')
            if current:
                self._current(context, item, saved)
            require(projection.snapshot(self._db)[0] == item.projection, 'EVIDENCE_CHANGED')
            projection.verify_files(self._db, item.sequence, item.files)
        return True

    @checked
    def verify_catalog(self, context, receipt):
        payload = dict(artifact=self._catalog_artifact(receipt['artifactDigest']), invocation=receipt['invocation'],
            applicability=receipt['applicability'], environment=receipt['environment'], result=receipt['result'])
        return self.verify(context, payload, current=True)

    @checked
    def verify_recording_catalog(self, context, receipt):
        payload = dict(artifact=self._catalog_artifact(receipt['artifactDigest']), invocation=receipt['invocation'],
            applicability=receipt['applicability'], environment=receipt['environment'], result=receipt['result'])
        return self.verify(context, payload, current=False)

    def _catalog_artifact(self, digest):
        raw = projection.point(self._db, 'pc_artifacts', (('document', ('blob', 65536)),),
                               ' WHERE digest=?', (digest,))[0]
        value = parse_json(raw)
        require(canonical(value) == raw and pat_digest(value) == digest, 'ARTIFACT_CHANGED')
        return value
