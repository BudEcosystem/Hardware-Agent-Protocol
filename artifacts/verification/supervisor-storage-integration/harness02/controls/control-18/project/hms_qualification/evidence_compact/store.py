"""Atomic exact-body deduplication for an original execution-store association.

Public calls accept only logical evaluator/run names. Reading history is not
catalog eligibility; complete semantic inspection runs outside Journal locks.
"""
import re
from hms.contracts import canonical, SAFE_INTEGER
from hms.registry import _resource_stored_row
import hms_qualification.supervisor.io_service_execution as execution_module
import hms_qualification.supervisor.io_services as services
from hms_qualification.evidence import archive, reducer
from hms_qualification.evidence.contracts import EVALUATION, MAX_RUNS, MAX_DOCUMENTS, MAX_STORE_DOCUMENTS, MAX_DOCUMENT_BYTES, MAX_RUN_BYTES, MAX_STORE_BYTES, RECORD_BYTES, EvidenceError, require, errors, number, exact, path, document, sha, hash_value, closure, closure_rows
from .contracts import PROFILE, identity

ANCHOR = 'io_evidence_compact'
DOMAIN = b'HMS-PAT-IO-COMPACT-IMPORTED-RECEIPT-v0.1'
_DDL = {
    'ioec_meta': 'CREATE TABLE ioec_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), record BLOB NOT NULL)',
    'ioec_runs': 'CREATE TABLE ioec_runs (sequence INTEGER PRIMARY KEY, evaluator TEXT NOT NULL, run TEXT NOT NULL, receipt BLOB NOT NULL, UNIQUE(evaluator,run))',
    'ioec_documents': 'CREATE TABLE ioec_documents (sequence INTEGER NOT NULL, path TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(sequence,path))',
    'ioec_bodies': 'CREATE TABLE ioec_bodies (digest TEXT PRIMARY KEY, body BLOB NOT NULL)',
}


class CompactIoEvidenceStore:
    @errors
    def __init__(self, execution, *, create=False, owner=None, max_documents=None,
                 max_objects=None, max_data_bytes=None, max_expanded_data_bytes=None):
        require(type(execution) is execution_module.IoServiceExecutionStore, 'AUTHORITY_MISMATCH')
        limits = dict(maxDocuments=(max_documents, MAX_STORE_DOCUMENTS), maxObjects=(max_objects, MAX_STORE_DOCUMENTS),
            maxDataBytes=(max_data_bytes, MAX_STORE_BYTES), maxExpandedDataBytes=(max_expanded_data_bytes, MAX_STORE_BYTES))
        require(type(create) is bool and (create or owner is None and all(value is None for value, _ in limits.values())), 'REOPEN_OPTIONS')
        configured = {key: ceiling if value is None else value for key, (value, ceiling) in limits.items()}
        for key, value in configured.items(): number(value, 1, limits[key][1])
        self.execution = execution
        self.journal, self._db = execution.journal, execution._db
        self.consumer_identity = identity()
        with execution._execution():
            with self.journal._transaction():
                state = execution._load()
                present = self._schema(allow_absent=True)
                anchor_value = self._anchor()
                if create:
                    execution.configurations._authorize(owner)
                    if present or anchor_value is not None:
                        self._state(); raise EvidenceError('ALREADY_EXISTS')
                    meta = dict(profile=PROFILE, authorityId=execution.authority_id, deployment=execution.deployment,
                        supervisorAuthorityId=state['meta']['supervisorAuthorityId'], consumerIdentity=self.consumer_identity,
                        maxRuns=min(MAX_RUNS, state['meta']['maxHandoffs']),
                        createdAtUnixMs=self.journal._now(), **configured)
                    for sql in _DDL.values(): self._db.execute(sql)
                    self._db.execute('INSERT INTO ioec_meta VALUES(1,?)', (canonical(meta),))
                    self._db.execute('INSERT INTO reg_meta VALUES(?,?)', (ANCHOR, self._anchor_value(meta)))
                self._state()

    def _anchor(self):
        value = _resource_stored_row(self._db, 'reg_meta', {'key': ANCHOR}, {'value': ('text', 128)})
        return None if value is None else value['value']

    @staticmethod
    def _anchor_value(meta): return PROFILE + '|' + hash_value(b'HMS-PAT-IO-COMPACT-STORE-v0.1', meta)

    def _schema(self, *, allow_absent=False):
        require(self._db.execute("SELECT 1 FROM sqlite_temp_master WHERE name GLOB 'ioec_*' OR tbl_name GLOB 'ioec_*' LIMIT 1").fetchone() is None, 'SCHEMA')
        suffix = " FROM sqlite_master WHERE name GLOB 'ioec_*' OR tbl_name GLOB 'ioec_*' LIMIT 9"
        rows = self._db.execute('SELECT typeof(name),length(CAST(name AS BLOB)),typeof(type),length(CAST(type AS BLOB)),typeof(tbl_name),length(CAST(tbl_name AS BLOB)),typeof(sql),length(CAST(sql AS BLOB))' + suffix).fetchall()
        if not rows and allow_absent: return False
        require(len(rows) == 7, 'SCHEMA')
        for row in rows:
            require(all(row[i] == 'text' and type(row[i+1]) is int and 1 <= row[i+1] <= 128 for i in (0, 2, 4)), 'SCHEMA')
            require((row[6] == 'null' and row[7] is None) or
                    (row[6] == 'text' and type(row[7]) is int and 1 <= row[7] <= 4096), 'SCHEMA')
        expected = {(name, 'table', name, sql) for name, sql in _DDL.items()} | {
            ('sqlite_autoindex_ioec_runs_1', 'index', 'ioec_runs', None),
            ('sqlite_autoindex_ioec_documents_1', 'index', 'ioec_documents', None),
            ('sqlite_autoindex_ioec_bodies_1', 'index', 'ioec_bodies', None)}
        require({tuple(row) for row in self._db.execute('SELECT name,type,tbl_name,sql' + suffix)} == expected, 'SCHEMA')
        return True

    def _document_index(self, meta):
        # Preflight each actual body and the aggregate before fetching any
        # variable-width object key. Body bytes are not fetched by this index.
        bound = (meta['maxObjects'] + 1,)
        checks = self._db.execute('SELECT typeof(digest),length(CAST(digest AS BLOB)),typeof(body),length(body) FROM ioec_bodies LIMIT ?', bound).fetchall()
        require(len(checks) <= meta['maxObjects'], 'CAPACITY')
        for row in checks:
            require(row[0] == 'text' and row[1] == 71 and row[2] == 'blob' and
                    type(row[3]) is int and 0 <= row[3] <= MAX_DOCUMENT_BYTES, 'INVALID_RETAINED')
        require(sum(row[3] + 256 for row in checks) <= meta['maxDataBytes'], 'CAPACITY')
        objects = {}
        rows = self._db.execute('SELECT digest,length(body) FROM ioec_bodies LIMIT ?', bound).fetchall()
        require(len(rows) == len(checks), 'INVALID_RETAINED')
        for digest, size in rows:
            require(re.fullmatch(r'sha256:[0-9a-f]{64}', digest) is not None and digest not in objects, 'INVALID_RETAINED')
            objects[digest] = size
        # Reference sizes/types are bounded separately. Expansion is charged
        # for every reference, including references sharing an exact body.
        suffix = ' FROM ioec_documents LIMIT ?'; bound = (meta['maxDocuments'] + 1,)
        checks = self._db.execute("SELECT typeof(sequence),CASE WHEN typeof(sequence)='integer' THEN sequence ELSE NULL END,typeof(path),length(CAST(path AS BLOB)),typeof(digest),length(CAST(digest AS BLOB))" + suffix, bound).fetchall()
        require(len(checks) <= meta['maxDocuments'], 'CAPACITY')
        for row in checks:
            require(row[0] == 'integer' and type(row[1]) is int and 1 <= row[1] <= meta['maxRuns'] and
                    row[2] == 'text' and type(row[3]) is int and 1 <= row[3] <= 288 and
                    row[4] == 'text' and row[5] == 71, 'INVALID_RETAINED')
        require(len(checks) * 512 <= meta['maxDataBytes'], 'CAPACITY')
        rows = self._db.execute('SELECT sequence,path,digest' + suffix, bound).fetchall()
        require(len(rows) == len(checks), 'INVALID_RETAINED'); groups = {}; referenced = set(); expanded = 0
        for sequence, name, digest in rows:
            require(digest in objects, 'BODY_MISSING'); referenced.add(digest)
            size = objects[digest]; expanded += size + 512
            require(expanded <= meta['maxExpandedDataBytes'], 'CAPACITY')
            group = groups.setdefault(sequence, {})
            require(name not in group and len(group) < MAX_DOCUMENTS, 'INVALID_RETAINED')
            group[name] = dict(path=name, bytes=size, sha256=digest)
        require(referenced == set(objects), 'ORPHAN_BODY')
        return groups, objects

    def _state(self):
        require(self._db.in_transaction, 'TRANSACTION_REQUIRED')
        execution = self.execution._load(); self._schema()
        rows = self.execution.configurations._scan('ioec_meta', {'singleton': ('integer', 1), 'record': ('blob', RECORD_BYTES)}, 1)
        require(len(rows) == 1, 'INVALID_RETAINED'); meta = document(rows[0]['record'], RECORD_BYTES)
        exact(meta, ('profile', 'authorityId', 'deployment', 'supervisorAuthorityId', 'consumerIdentity',
                     'maxRuns', 'maxDocuments', 'maxObjects', 'maxDataBytes', 'maxExpandedDataBytes', 'createdAtUnixMs'))
        require(meta['profile'] == PROFILE and meta['authorityId'] == self.execution.authority_id and
            meta['deployment'] == self.execution.deployment and meta['consumerIdentity'] == self.consumer_identity and
            meta['supervisorAuthorityId'] == execution['meta']['supervisorAuthorityId'] and
            self._anchor() == self._anchor_value(meta), 'MOUNT_CHANGED')
        number(meta['maxRuns'], 1, min(MAX_RUNS, execution['meta']['maxHandoffs']))
        number(meta['maxDocuments'], 1, MAX_STORE_DOCUMENTS); number(meta['maxDataBytes'], 1, MAX_STORE_BYTES)
        number(meta['maxObjects'], 1, MAX_STORE_DOCUMENTS); number(meta['maxExpandedDataBytes'], 1, MAX_STORE_BYTES)
        number(meta['createdAtUnixMs'], 0, SAFE_INTEGER)
        rows = self.execution.configurations._scan('ioec_runs', {'sequence': ('integer', MAX_RUNS),
            'evaluator': ('text', 128), 'run': ('text', 128), 'receipt': ('blob', RECORD_BYTES)}, meta['maxRuns'])
        rows.sort(key=lambda row: row['sequence']); groups, objects = self._document_index(meta)
        require([row['sequence'] for row in rows] == list(range(1, len(rows)+1)) and
                set(groups) == {row['sequence'] for row in rows}, 'INVALID_RETAINED')
        keys = {}; previous = None; now = meta['createdAtUnixMs']; base_charge = len(canonical(meta)) + 1024
        expanded_charge = base_charge
        for row in rows:
            key = row['evaluator'], row['run']; services.name(key[0]); services.name(key[1])
            require(key not in keys, 'INVALID_RETAINED')
            receipt = document(row['receipt'], RECORD_BYTES)
            exact(receipt, ('profile', 'sequence', 'anchor', 'consumerIdentity', 'evaluationDigest', 'closure',
                            'principal', 'committedAtUnixMs', 'previousReceiptDigest'))
            require(receipt['profile'] == PROFILE and receipt['sequence'] == row['sequence'] and
                receipt['consumerIdentity'] == self.consumer_identity and receipt['previousReceiptDigest'] == previous and
                key == (receipt['anchor']['evaluatorId'], receipt['anchor']['runId']), 'INVALID_RETAINED')
            services.name(receipt['principal']); number(receipt['committedAtUnixMs'], now, SAFE_INTEGER)
            now = receipt['committedAtUnixMs']
            actual_closure = closure_rows(sorted(groups[row['sequence']].values(), key=lambda value: value['path']))
            require(receipt['closure'] == actual_closure and
                groups[row['sequence']].get('evaluation.json', {}).get('sha256') == receipt['evaluationDigest'], 'INVALID_RETAINED')
            reservation, association, attempt = self._binding(execution, key)
            require(receipt['anchor'] == reducer.anchor(reservation, association, attempt), 'ASSOCIATION_CHANGED')
            previous = hash_value(DOMAIN, receipt)
            keys[key] = dict(receipt=receipt, receiptDigest=previous)
            base_charge += len(row['receipt']) + 512
            expanded_charge += len(row['receipt']) + 512 + actual_closure['bytes'] + 512 * actual_closure['documents']
        charge = base_charge + 512 * sum(map(len, groups.values())) + sum(size + 256 for size in objects.values())
        require(charge <= meta['maxDataBytes'] and expanded_charge <= meta['maxExpandedDataBytes'], 'CAPACITY')
        return dict(meta=meta, execution=execution, keys=keys, documents=groups, charge=charge,
                    expandedCharge=expanded_charge, objects=objects, objectCount=len(objects),
                    documentCount=sum(map(len, groups.values())), lastDigest=previous, lastTime=now)

    def _binding(self, state, key):
        reservation = state['runs']['keys'].get(key); association = state['keys'].get(key)
        require(reservation is not None and association is not None, 'HANDOFF_MISSING')
        attempt = self.execution._row(reservation, association)
        require(attempt is not None, 'ATTEMPT_MISSING')
        return reservation, association, attempt

    def _read_group(self, state, key):
        record = state['keys'][key]; receipt = record['receipt']; sequence = receipt['sequence']
        expected = state['documents'][sequence]
        # _state preflighted all actual body sizes while this same TX is held.
        rows = self._db.execute('SELECT d.path,b.body FROM ioec_documents d JOIN ioec_bodies b ON b.digest=d.digest WHERE d.sequence=? LIMIT ?', (sequence, MAX_DOCUMENTS+1)).fetchall()
        require(len(rows) == len(expected), 'INVALID_RETAINED'); files = {}
        for name, body in rows:
            require(name in expected and name not in files and type(body) is bytes and
                len(body) == expected[name]['bytes'] and sha(body) == expected[name]['sha256'], 'BODY_CHANGED')
            files[name] = body
        require(closure(files) == receipt['closure'], 'BODY_CHANGED')
        evaluation = document(files['evaluation.json'], RECORD_BYTES)
        exact(evaluation, ('profile', 'anchor', 'consumerIdentity', 'outcome', 'scope', 'inspectionDigest',
            'inspectedCases', 'unresolvedEffects', 'physicalObjectiveVerified', 'wallDeadlineAttested',
            'aggregateDiskQuotaEnforced', 'catalogActivated'))
        require(evaluation['profile'] == EVALUATION and evaluation['anchor'] == receipt['anchor'] and
            evaluation['consumerIdentity'] == receipt['consumerIdentity'] and evaluation['outcome'] == 'passed' and
            evaluation['scope'] == 'complete-finite-synthetic-io-matrix' and
            type(evaluation['unresolvedEffects']) is int and evaluation['unresolvedEffects'] == 0 and
            all(evaluation[name] is False for name in ('physicalObjectiveVerified', 'wallDeadlineAttested',
                'aggregateDiskQuotaEnforced', 'catalogActivated')) and
            sha(files['inspection/summary.json']) == evaluation['inspectionDigest'], 'INVALID_RETAINED')
        summary = document(files['inspection/summary.json'])
        reservation, association, attempt = self._binding(state['execution'], key)
        bundle = reservation['preparedRun']['bundle']
        number(evaluation['inspectedCases'], 1, 32)
        require(evaluation['inspectedCases'] == len(attempt['request']['bundleHeader']['caseIds']) == len(summary['cases']), 'INVALID_RETAINED')
        originals = {'original/bundle/' + name: body for name, body in bundle['documents'].items()}
        originals['original/bundle/header.json'] = bundle['header']
        for name, value in dict(reservation=reservation['reservation'], handoff=association['receipt'],
                                request=attempt['request'], attempt=attempt['record']).items():
            originals['original/control/' + name + '.json'] = canonical(value)
        originals['original/control/return.json'] = attempt['returnBytes']
        require(all(files.get(name) == body for name, body in originals.items()), 'ASSOCIATION_CHANGED')
        outputs = {name[len('original/output/'):]: body for name, body in files.items() if name.startswith('original/output/')}
        expected_paths = set(originals) | {'original/output/' + name for name in outputs} | {'evaluation.json', 'inspection/summary.json'}
        expected_paths |= {'inspection/case-%02d.json' % i for i in range(evaluation['inspectedCases'])}
        require(set(files) == expected_paths and archive.output_closure(outputs) == receipt['anchor']['outputClosure'], 'INVALID_RETAINED')
        return dict(receipt=record['receipt'], receiptDigest=record['receiptDigest'], evaluation=evaluation), files

    def _begin(self, context, evaluator, run):
        require(not self._db.in_transaction, 'TRANSACTION_REENTRY')
        services.name(evaluator); services.name(run)
        require(identity() == self.consumer_identity, 'IMPLEMENTATION_CHANGED')
        return evaluator, run

    def _checkpoint(self, phase, value):
        """Installed test seam, never an import-call callback."""

    @errors
    def lookup(self, context, evaluator, run):
        key = self._begin(context, evaluator, run)
        with self.execution._execution():
            with self.journal._transaction():
                self.execution.configurations._authorize(context); state = self._state()
                if key not in state['keys']: return None
                return self._read_group(state, key)[0]

    @errors
    def import_run(self, context, evaluator, run):
        key = self._begin(context, evaluator, run)
        with self.execution._execution():
            with self.journal._transaction():
                self.execution.configurations._authorize(context); state = self._state()
                if key in state['keys']: return self._read_group(state, key)[0]
                reservation, association, attempt = self._binding(state['execution'], key)
                original_anchor = reducer.anchor(reservation, association, attempt)
            files = archive.read_original(self.execution.supervisor, attempt, reservation['preparedRun']['bundle'])
            inspected = reducer.reduce_original(reservation, association, attempt, files, self.consumer_identity)
            self._checkpoint('after_inspection', inspected['evaluation'])
            require(identity() == self.consumer_identity, 'IMPLEMENTATION_CHANGED')
            with self.journal._transaction():
                self.execution.configurations._authorize(context); state = self._state()
                current = self._binding(state['execution'], key)
                require(reducer.anchor(*current) == original_anchor, 'ASSOCIATION_CHANGED')
                require(key not in state['keys'], 'CONCURRENT_IMPORT')
                sequence = len(state['keys']) + 1; number(sequence, 1, state['meta']['maxRuns'])
                now = self.journal._now(); number(now, state['lastTime'], SAFE_INTEGER)
                receipt = dict(profile=PROFILE, sequence=sequence, anchor=original_anchor, consumerIdentity=self.consumer_identity,
                    evaluationDigest=sha(inspected['documents']['evaluation.json']), closure=inspected['closure'],
                    principal=context.principal, committedAtUnixMs=now, previousReceiptDigest=state['lastDigest'])
                wire = canonical(receipt); require(len(wire) <= RECORD_BYTES, 'CAPACITY')
                bodies = {}
                for body in inspected['documents'].values():
                    digest = sha(body)
                    require(digest not in bodies or bodies[digest] == body, 'BODY_CONFLICT')
                    bodies[digest] = body
                additions = {digest: body for digest, body in bodies.items() if digest not in state['objects']}
                reference_charge = len(wire) + 512 + 512 * inspected['closure']['documents']
                require(state['documentCount'] + inspected['closure']['documents'] <= state['meta']['maxDocuments'] and
                    state['objectCount'] + len(additions) <= state['meta']['maxObjects'] and
                    state['charge'] + reference_charge + sum(len(body) + 256 for body in additions.values()) <= state['meta']['maxDataBytes'] and
                    state['expandedCharge'] + reference_charge + inspected['closure']['bytes'] <= state['meta']['maxExpandedDataBytes'], 'CAPACITY')
                for digest, body in bodies.items():
                    if digest not in state['objects']: continue
                    # Actual size/type was checked by _state in this TX. A
                    # reused object's digest column is not evidence of bytes.
                    rows = self._db.execute('SELECT body FROM ioec_bodies WHERE digest=? LIMIT 2', (digest,)).fetchall()
                    require(len(rows) == 1 and type(rows[0][0]) is bytes and
                        len(rows[0][0]) == state['objects'][digest] and
                        sha(rows[0][0]) == digest and rows[0][0] == body, 'BODY_CHANGED')
                self._db.execute('INSERT INTO ioec_runs VALUES(?,?,?,?)', (sequence, *key, wire))
                self._db.executemany('INSERT INTO ioec_bodies VALUES(?,?)', sorted(additions.items()))
                self._db.executemany('INSERT INTO ioec_documents VALUES(?,?,?)',
                    [(sequence, name, sha(body)) for name, body in sorted(inspected['documents'].items())])
                result = self._read_group(self._state(), key)[0]
                self._checkpoint('before_import_commit', result)
            self._checkpoint('after_import_commit', result)
            return result

    @errors
    def reinspect(self, context, evaluator, run):
        """Recheck retained semantics without a worker or producer-directory read.

        This returns evidence only. A future catalog adapter must separately
        check current environment, grants and PAT admission requirements.
        """
        key = self._begin(context, evaluator, run)
        with self.execution._execution():
            with self.journal._transaction():
                self.execution.configurations._authorize(context); state = self._state()
                require(key in state['keys'], 'IMPORT_MISSING')
                result, files = self._read_group(state, key)
                original = self._binding(state['execution'], key)
            outputs = {name[len('original/output/'):]: body for name, body in files.items() if name.startswith('original/output/')}
            inspected = reducer.reduce_original(*original, outputs, self.consumer_identity)
            require(inspected['documents'] == files, 'SEMANTICS_CHANGED')
            require(identity() == self.consumer_identity, 'IMPLEMENTATION_CHANGED')
            with self.journal._transaction():
                self.execution.configurations._authorize(context); state = self._state()
                current, current_files = self._read_group(state, key)
                require(current == result and current_files == files, 'IMPORT_CHANGED')
            return result
