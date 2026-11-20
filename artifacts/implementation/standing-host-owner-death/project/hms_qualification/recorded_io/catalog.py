"""Explicit catalog mount for original-run finite-I/O evaluations.

The static compiler environment retains its legacy representation. Invocation
and source applicability are separately versioned receipt fields. No old mount
or evaluation is rewritten, and recording never starts a qualification worker.
"""
import copy
from dataclasses import replace
import sqlite3
from types import MappingProxyType

from hms.contracts import ContractError, MAX_BYTES, SAFE_INTEGER, canonical, identifier, parse_json
from hms.journal import JournalError
from hms.pat_catalog import PatCatalog, _DDL, _digest, _exact, _hash
from .bridge import RecordedIoBridge
from . import contracts, projection
from .contracts import require, checked

RECEIPT = 'hms.pat.io-catalog-evaluation/0.1'
DOMAIN = b'HMS-PAT-IO-CATALOG-EVALUATION-v0.1'
ANCHOR = 'io_recorded_catalog'
_TABLES = ('pc_meta', 'pc_deployments', 'pc_artifacts', 'pc_entries', 'pc_evaluations',
           'pc_evaluation_conflicts', 'pc_decisions', 'pc_events')

class RecordedPatCatalog(PatCatalog):
    @checked
    def __init__(self, bridge, *, create=False, owner=None):
        require(type(bridge) is RecordedIoBridge, 'AUTHORITY_MISMATCH')
        require(type(create) is bool and (create or owner is None), 'REOPEN_OPTIONS')
        require(not bridge._db.in_transaction and bridge._enabled(), 'TRANSACTION_REENTRY')
        self.bridge = bridge
        self.journal, self._db = bridge.journal, bridge._db
        self._evaluators = MappingProxyType({item.evaluator_id: item for item in bridge.evaluators()})
        self._mount_anchor = contracts.PROFILE + '|' + _hash(b'HMS-PAT-IO-RECORDED-CATALOG-MOUNT-v0.1', dict(
            authorityId=self.journal.authority_id, deployment=bridge.execution.deployment,
            hostImplementationDigest=bridge._identity, evaluators=[item.identity() for item in self._evaluators.values()]))
        with self.journal._transaction():
            present = self._db.execute("SELECT 1 FROM main.sqlite_master WHERE name GLOB 'pc_*' OR tbl_name GLOB 'pc_*' LIMIT 1").fetchone()
            anchor = projection.scan(self._db, 'reg_meta', (('value', ('text', 128)),), 1,
                                     where=' WHERE key=?', parameters=(ANCHOR,))
            if create:
                self.journal.policy.authorize(owner, 'admin', '*')
                require(owner.deployment == bridge.execution.deployment, 'AUTHORITY_MISMATCH')
                require(not present and not anchor, 'ALREADY_EXISTS')
                for statement in _DDL:
                    self._db.execute(statement)
                self._db.execute('INSERT INTO pc_meta VALUES (?,?)', ('version', contracts.PROFILE))
                self._db.execute('INSERT INTO reg_meta VALUES (?,?)', (ANCHOR, self._mount_anchor))
            self._mount()

    def _mount(self):
        require(self._db.in_transaction and self.bridge._enabled(), 'MOUNT_CHANGED')
        require(self._db.execute("SELECT 1 FROM sqlite_temp_master WHERE name GLOB 'pc_*' OR tbl_name GLOB 'pc_*' LIMIT 1").fetchone() is None,
                'SCHEMA_CHANGED')
        suffix = " FROM main.sqlite_master WHERE name GLOB 'pc_*' OR tbl_name GLOB 'pc_*' LIMIT 19"
        kinds = self._db.execute('SELECT typeof(name),typeof(type),typeof(tbl_name),typeof(sql)' + suffix).fetchall()
        require(len(kinds) == 17 and all(tuple(row[:3]) == ('text','text','text') and row[3] in ('text','null') for row in kinds), 'SCHEMA_CHANGED')
        sizes = self._db.execute('SELECT length(CAST(name AS BLOB)),length(CAST(type AS BLOB)),length(CAST(tbl_name AS BLOB)),length(CAST(sql AS BLOB))' + suffix).fetchall()
        require(len(sizes) == len(kinds), 'SCHEMA_CHANGED')
        for row, kind in zip(sizes, kinds):
            require(all(type(value) is int and 0 < value <= 128 for value in row[:3]) and
                    ((kind[3] == 'null' and row[3] is None) or
                     (kind[3] == 'text' and type(row[3]) is int and 0 < row[3] <= 4096)), 'SCHEMA_CHANGED')
        expected = {(name, 'table', name, sql) for name, sql in zip(_TABLES, _DDL)}
        expected |= {('sqlite_autoindex_' + name + '_1', 'index', name, None) for name in _TABLES}
        expected.add(('sqlite_autoindex_pc_evaluations_2', 'index', 'pc_evaluations', None))
        require({tuple(row) for row in self._db.execute('SELECT name,type,tbl_name,sql' + suffix)} == expected, 'SCHEMA_CHANGED')
        require(projection.scan(self._db, 'pc_meta', (('key', ('text',128)), ('value', ('text',128))), 1) ==
                (('version', contracts.PROFILE),), 'VERSION_UNSUPPORTED')
        require(projection.point(self._db, 'reg_meta', (('value', ('text',128)),), ' WHERE key=?', (ANCHOR,)) ==
                (self._mount_anchor,), 'MOUNT_CHANGED')

    def _authorize(self, context):
        self.journal.policy.authorize(context, 'admin', '*')
        require(context.deployment == self.bridge.execution.deployment, 'AUTHORITY_MISMATCH')
        self._mount()

    @staticmethod
    def _receipt_shape(receipt):
        _exact(receipt, {'protocol','runId','artifactDigest','artifactDomainDigest','evaluator','environment',
            'environmentDigest','outcome','result','evaluatorError','physicalObjectiveVerified','invocation','applicability'})
        require(receipt['protocol'] == RECEIPT and receipt['physicalObjectiveVerified'] is False and
                receipt['outcome'] == 'passed' and receipt['evaluatorError'] is None, 'EVALUATION_INVALID')
        invocation, app = receipt['invocation'], receipt['applicability']
        _exact(invocation, {'profile','original','importReceiptDigest','consumerIdentity','hostImplementationDigest',
            'evaluationPolicyDigest','evidenceClosure','matrixDigest','caseIds'})
        _exact(app, {'profile','authorityId','deployment','configurationReceiptDigest','configurationDigest',
                    'configurationRevision','roleInstances','dependencies'})
        original = invocation['original']
        require(invocation['profile'] == contracts.INVOCATION and app['profile'] == contracts.APPLICABILITY,
                'EVALUATION_INVALID')
        require(original['artifactDigest'] == receipt['artifactDigest'] and original['runId'] == receipt['runId'] and
                original['evaluatorId'] == receipt['evaluator']['evaluatorId'] and
                invocation['hostImplementationDigest'] == receipt['evaluator']['implementationDigest'] and
                invocation['evaluationPolicyDigest'] == receipt['evaluator']['policyDigest'], 'EVALUATION_INVALID')
        for name in ('authorityId','deployment','configurationReceiptDigest','configurationDigest','configurationRevision'):
            require(original[name] == app[name] and type(original[name]) is type(app[name]), 'EVALUATION_INVALID')
        require(app['deployment'] == receipt['environment']['deployment'] and
                receipt['environmentDigest'] == _hash(b'HMS-PAT-ENVIRONMENT-v0.1', receipt['environment']), 'EVALUATION_INVALID')
        _exact(receipt['environment'], {'profile','deployment','evidenceMode','compilerDigest','roles'})
        require(receipt['environment']['profile'] == 'hms.pat.environment/0.1' and
                receipt['environment']['evidenceMode'] == 'simulation' and
                type(app['roleInstances']) is dict and 1 <= len(app['roleInstances']) <= 16 and
                set(app['roleInstances']) == set(receipt['environment']['roles']) and
                type(app['dependencies']) is list and len(app['dependencies']) == len(app['roleInstances']), 'EVALUATION_INVALID')
        for role, instance in app['roleInstances'].items():
            identifier(role); identifier(instance)
        require({value['role'] for value in app['dependencies']} == set(app['roleInstances']) and
                all(value['instanceId'] == app['roleInstances'][value['role']] for value in app['dependencies']), 'EVALUATION_INVALID')
        for value in app['dependencies']:
            _exact(value, {'role','descriptionDigest','bindingDigest','instanceId','bindingGeneration','controlGeneration',
                'calibrationRevision','endpointSession','driverProfile','driverDigest','installationDigest','metadataDigest'})
            for field in ('role','instanceId','bindingGeneration','controlGeneration','calibrationRevision','endpointSession','driverProfile'):
                identifier(value[field])
            for field in ('descriptionDigest','bindingDigest','driverDigest','installationDigest','metadataDigest'):
                _digest(value[field])
        for name in ('importReceiptDigest','consumerIdentity','hostImplementationDigest','evaluationPolicyDigest','matrixDigest'):
            _digest(invocation[name])
        require(type(invocation['caseIds']) is list and 1 <= len(invocation['caseIds']) <= 32 and
                len(set(invocation['caseIds'])) == len(invocation['caseIds']), 'EVALUATION_INVALID')
        for value in invocation['caseIds']:
            _digest(value)

    def _stored_evaluation(self, deployment, digest, artifact=None, *, table='pc_evaluations'):
        self._mount()
        if table not in {'pc_evaluations','pc_evaluation_conflicts'}:
            raise JournalError('PAT_EVALUATION_INVALID')
        try:
            _digest(digest)
            raw = projection.point(self._db, table, (('document', ('blob', MAX_BYTES)),), ' WHERE digest=?', (digest,))[0]
            receipt = parse_json(raw)
            self._receipt_shape(receipt)
            if (canonical(receipt) != raw or _hash(DOMAIN, receipt) != digest or
                    receipt['environment']['deployment'] != deployment or
                    (artifact is not None and receipt['artifactDigest'] != artifact)):
                raise JournalError('PAT_EVALUATION_INVALID')
            _digest(receipt['artifactDigest']); identifier(receipt['runId'])
            evaluator_id = identifier(receipt['evaluator']['evaluatorId'])
            query = 'SELECT 1 FROM main.' + table + ' WHERE digest=? AND deployment=? AND artifact=?'
            args = (digest, deployment, receipt['artifactDigest'])
            if table == 'pc_evaluations':
                query += ' AND evaluator=? AND run_id=?'
                args += (evaluator_id, receipt['runId'])
            if self._db.execute(query, args).fetchone() is None:
                raise JournalError('PAT_EVALUATION_INVALID')
            if table == 'pc_evaluation_conflicts':
                prior = self._evaluation_for_key(deployment, evaluator_id, receipt['runId'])
                if prior is None or self._db.execute('SELECT 1 FROM main.pc_evaluation_conflicts WHERE digest=? AND prior_evaluation=?',
                    (digest, prior['evaluationDigest'])).fetchone() is None:
                    raise JournalError('PAT_EVALUATION_INVALID')
            return receipt
        except (ContractError, KeyError, TypeError, ValueError, IndexError) as error:
            raise JournalError('PAT_EVALUATION_INVALID') from error
        except sqlite3.Error as error:
            raise JournalError('PAT_EVALUATION_UNAVAILABLE') from error

    def evaluate(self, *args, **kwargs):
        raise contracts.RecordedError('EXPLICIT_INVOCATION_REQUIRED')

    @checked
    def record_evaluation(self, context, artifact_digest, evaluator_id, run_id):
        _digest(artifact_digest); identifier(evaluator_id); identifier(run_id)
        with self.journal._transaction():
            self._authorize(context)
            evaluator = self._evaluator(evaluator_id)
            self._entry(context.deployment, artifact_digest)
            previous = self._evaluation_for_key(context.deployment, evaluator_id, run_id)
            if previous is not None:
                require(previous['receipt']['artifactDigest'] == artifact_digest, 'KEY_CONFLICT')
                return previous
            artifact = self._artifact(artifact_digest)
        payload = self.bridge.prepare(context, artifact_digest, evaluator_id, run_id)
        require(canonical(payload['artifact']) == canonical(artifact), 'ARTIFACT_CHANGED')
        result, outcome = self._evaluation_result(payload['result'], evaluator)
        require(outcome == 'passed', 'EVALUATION_INVALID')
        receipt = dict(protocol=RECEIPT, runId=run_id, artifactDigest=artifact_digest,
            artifactDomainDigest=_hash(b'HMS-PAT-DOMAIN-v0.1', artifact), evaluator=evaluator.identity(),
            environment=payload['environment'], environmentDigest=_hash(b'HMS-PAT-ENVIRONMENT-v0.1', payload['environment']),
            outcome=outcome, result=result, evaluatorError=None, physicalObjectiveVerified=False,
            invocation=payload['invocation'], applicability=payload['applicability'])
        self._receipt_shape(receipt)
        require(len(canonical(receipt)) <= MAX_BYTES, 'READ_BOUND')
        digest = _hash(DOMAIN, receipt)
        conflict = False
        self.bridge._checkpoint('before_catalog_publication', receipt)
        with self.journal._transaction():
            self._authorize(context)
            require(canonical(self._evaluator(evaluator_id).identity()) == canonical(evaluator.identity()), 'IMPLEMENTATION_CHANGED')
            entry = self._entry(context.deployment, artifact_digest)
            recording = replace(evaluator, verify_evidence=self.bridge.verify_recording_catalog)
            valid, reason = self._verify_evidence(recording, context, receipt)
            if not valid:
                raise JournalError(reason)
            previous = self._evaluation_for_key(context.deployment, evaluator_id, run_id)
            if previous is not None:
                prior_digest = previous['evaluationDigest']
                if prior_digest == digest:
                    return previous
                prior_artifact = previous['receipt']['artifactDigest']
                if self._db.execute('SELECT 1 FROM pc_evaluation_conflicts WHERE digest=?', (digest,)).fetchone() is None:
                    now = self.journal._record_now()
                    self._db.execute('INSERT INTO pc_evaluation_conflicts VALUES (?,?,?,?,?)',
                        (digest, context.deployment, artifact_digest, prior_digest, canonical(receipt)))
                    self._db.execute("UPDATE pc_entries SET evaluation_conflict=1, state=CASE WHEN state='retired' THEN state ELSE 'suspended' END WHERE deployment=? AND artifact IN (?,?)",
                        (context.deployment, artifact_digest, prior_artifact))
                    self._event(context, now, 'evaluation_conflict', dict(artifactDigest=artifact_digest,
                        priorArtifactDigest=prior_artifact, priorEvaluationDigest=prior_digest, conflictingEvaluationDigest=digest))
                conflict = True
            else:
                now = self.journal._record_now()
                self._db.execute('INSERT INTO pc_evaluations VALUES (?,?,?,?,?,?)',
                    (digest, context.deployment, artifact_digest, evaluator_id, run_id, canonical(receipt)))
                state = {'candidate':'evaluated','evaluated':'evaluated','active':'suspended',
                         'suspended':'suspended','retired':'retired'}[entry['state']]
                self._db.execute('UPDATE pc_entries SET state=?,evaluation=?,evaluation_conflict=0 WHERE deployment=? AND artifact=?',
                                 (state, digest, context.deployment, artifact_digest))
                self._event(context, now, 'evaluation_recorded', dict(artifactDigest=artifact_digest,
                    evaluationDigest=digest, outcome=outcome, state=state))
        if conflict:
            raise JournalError('PAT_EVALUATION_KEY_CONFLICT')
        return dict(evaluationDigest=digest, receipt=receipt)

    def _eligible(self, context, entry):
        self._mount()
        if entry['state'] == 'active' and (entry['evaluation'] is None or entry['evaluation_conflict'] != 0):
            raise JournalError('PAT_EVALUATION_INVALID')
        if self._revision(context.deployment) >= SAFE_INTEGER:
            return False, 'PAT_REVISION_EXHAUSTED'
        if entry['evaluation_conflict']:
            return False, 'PAT_EVALUATION_CONFLICT'
        if entry['evaluation'] is None:
            return False, 'PAT_NOT_EVALUATED'
        receipt = self._stored_evaluation(context.deployment, entry['evaluation'], entry['artifact'])
        try:
            evaluator = self._evaluator(receipt['evaluator']['evaluatorId'])
        except JournalError:
            return False, 'PAT_EVIDENCE_UNAVAILABLE'
        if canonical(evaluator.identity()) != canonical(receipt['evaluator']):
            return False, 'PAT_EVIDENCE_UNAVAILABLE'
        return self._verify_evidence(evaluator, context, receipt)

    def _environment(self, context, artifact):
        """Compatibility view after the stronger current-applicability check."""
        from hms.pat_contracts import pat_digest
        entry = self._entry(context.deployment, pat_digest(artifact))
        valid, reason = self._eligible(context, entry)
        if not valid:
            raise JournalError(reason)
        return copy.deepcopy(self._stored_evaluation(context.deployment, entry['evaluation'])['environment'])

    def resolve(self, context, artifact, request):
        from hms.pat_contracts import pat_digest
        require(self._db.in_transaction, 'TRANSACTION_REQUIRED')
        entry = self._entry(context.deployment, pat_digest(artifact))
        require(entry['evaluation'] is not None, 'EVALUATION_UNAVAILABLE')
        receipt = self._stored_evaluation(context.deployment, entry['evaluation'], entry['artifact'])
        with self.bridge._mutex:
            prepared, _ = self.bridge._entry(receipt['invocation'])
            return prepared.resolver(context, artifact, request)
