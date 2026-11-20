"""Original intent -> independent immutable seal -> atomic authority reference.

Public import calls accept only evaluator/run names, never paths, callbacks or
claimed results. No code path starts a qualification worker. This experimental
profile is not the compact catalog profile and does not grant PAT eligibility.
"""
from contextlib import contextmanager

from hms.contracts import canonical, SAFE_INTEGER
from hms.journal import Journal, JournalError
from hms.registry import _resource_stored_row
import hms_qualification.supervisor.io_service_execution as execution_module
import hms_qualification.supervisor.io_services as services
from hms_qualification.evidence import archive, reducer
from hms_qualification.evidence_vault import EvidenceVault
from hms_qualification.evidence_vault import contracts as vault_contracts
from hms_qualification.evidence_vault.connection import _Snapshot
from hms_qualification.evidence_vault.store import DOMAIN as MANIFEST_DOMAIN
from . import contracts as c

ANCHOR = 'vault_evidence_import'
META_DOMAIN = b'HMS-PAT-VAULT-IMPORT-MOUNT-v0.1'
INTENT_DOMAIN = b'HMS-PAT-VAULT-IMPORT-INTENT-v0.1'
BINDING_DOMAIN = b'HMS-PAT-VAULT-ORIGINAL-BINDING-v0.1'
PUBLICATION_DOMAIN = b'HMS-PAT-VAULT-PUBLICATION-v0.1'
_DDL = {
    'evi_meta': 'CREATE TABLE evi_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), record BLOB NOT NULL)',
    'evi_intents': 'CREATE TABLE evi_intents (sequence INTEGER PRIMARY KEY, evaluator TEXT NOT NULL, run TEXT NOT NULL, intent TEXT NOT NULL UNIQUE, record BLOB NOT NULL, UNIQUE(evaluator,run))',
    'evi_publications': 'CREATE TABLE evi_publications (sequence INTEGER PRIMARY KEY, intent TEXT NOT NULL UNIQUE, record BLOB NOT NULL)',
}


class VaultEvidenceStore:
    @c.errors
    def __init__(self, execution, vault, *, create=False, owner=None, max_intents=None,
                 max_control_bytes=None):
        c.require(type(execution) is execution_module.IoServiceExecutionStore and
                  type(execution.journal) is Journal and type(vault) is EvidenceVault, 'AUTHORITY_MISMATCH')
        c.require(type(create) is bool and (create or owner is None and max_intents is None and
                  max_control_bytes is None), 'REOPEN_OPTIONS')
        self.execution, self.vault = execution, vault
        self.journal, self._db = execution.journal, execution._db
        self.consumer_identity = c.identity()
        self.descriptor = vault.descriptor()
        c.require(self.descriptor['authorityId'] == execution.authority_id == self.journal.authority_id and
                  self._db is self.journal._db and self._db is not vault._db, 'AUTHORITY_MISMATCH')
        capacity = c.MAX_CONTROL_BYTES if max_control_bytes is None else max_control_bytes
        count = c.MAX_RUNS if max_intents is None else max_intents
        c.number(capacity, c.INTENT_CHARGE + c.RECORD_BYTES + 1024, c.MAX_CONTROL_BYTES)
        c.number(count, 1, c.MAX_RUNS)
        with execution._execution():
            # Lock order: execution -> vault read ownership -> short Journal TX.
            # No journal transaction may acquire the vault or read source files.
            with self._installation_snapshot() as snapshot:
                with self.journal._transaction():
                    state = execution._load()
                    c.require(self.journal._meta('authority') == execution.authority_id, 'AUTHORITY_MISMATCH')
                    present, anchor = self._schema(allow_absent=True), self._anchor()
                    if create:
                        execution.configurations._authorize(owner)
                        if present or anchor is not None:
                            self._state(); raise c.EvidenceError('ALREADY_EXISTS')
                        meta = dict(profile=c.PROFILE, authorityId=execution.authority_id,
                            deployment=execution.deployment, supervisorAuthorityId=state['meta']['supervisorAuthorityId'],
                            consumerIdentity=self.consumer_identity, vault=self.descriptor,
                            maxIntents=min(count, self.descriptor['maxManifests'], state['meta']['maxHandoffs']),
                            maxControlBytes=capacity, intentCharge=c.INTENT_CHARGE,
                            createdAtUnixMs=self.journal._now())
                        for sql in _DDL.values(): self._db.execute(sql)
                        self._db.execute('INSERT INTO evi_meta VALUES(1,?)', (canonical(meta),))
                        self._db.execute('INSERT INTO reg_meta VALUES(?,?)', (ANCHOR, self._anchor_value(meta)))
                    self._state()
                    snapshot.check(self.vault)

    @contextmanager
    def _installation_snapshot(self):
        # Explicit empty-store inspection; no invented evidence manifest.
        vault = self.vault
        with vault._mutex:
            vault._ready()
            vault._db.execute('PRAGMA query_only=ON')
            try:
                vault._db.execute('BEGIN')
                vault._state()
                lease = _Snapshot(vault, canonical(vault.descriptor()), {}, vault_contracts.MAX_LEASE_MS)
                vault._lease = lease
                try:
                    yield lease
                    lease.check(vault)
                    vault._identities()
                finally:
                    lease._active = False
                    vault._lease = None
            finally:
                try:
                    if vault._db.in_transaction: vault._db.execute('ROLLBACK')
                    vault._db.execute('PRAGMA query_only=OFF')
                except BaseException:
                    vault._poisoned = True
                    raise

    def _anchor(self):
        row = _resource_stored_row(self._db, 'reg_meta', {'key': ANCHOR}, {'value': ('text', 128)})
        return None if row is None else row['value']

    @staticmethod
    def _anchor_value(meta):
        return c.PROFILE + '|' + c.hash_value(META_DOMAIN, meta)

    def _schema(self, *, allow_absent=False):
        c.require(self._db.execute("SELECT 1 FROM sqlite_temp_master WHERE name GLOB 'evi_*' OR tbl_name GLOB 'evi_*' LIMIT 1").fetchone() is None, 'SCHEMA')
        suffix = " FROM sqlite_master WHERE name GLOB 'evi_*' OR tbl_name GLOB 'evi_*' LIMIT 8"
        checks = self._db.execute('SELECT typeof(name),length(CAST(name AS BLOB)),typeof(type),length(CAST(type AS BLOB)),typeof(tbl_name),length(CAST(tbl_name AS BLOB)),typeof(sql),length(CAST(sql AS BLOB))' + suffix).fetchall()
        if not checks and allow_absent: return False
        c.require(len(checks) == 6, 'SCHEMA')
        for row in checks:
            c.require(all(row[i] == 'text' and type(row[i+1]) is int and 1 <= row[i+1] <= 128 for i in (0, 2, 4)), 'SCHEMA')
            c.require((row[6] == 'null' and row[7] is None) or
                (row[6] == 'text' and type(row[7]) is int and 1 <= row[7] <= 4096), 'SCHEMA')
        expected = {(name, 'table', name, sql) for name, sql in _DDL.items()} | {
            ('sqlite_autoindex_evi_intents_1', 'index', 'evi_intents', None),
            ('sqlite_autoindex_evi_intents_2', 'index', 'evi_intents', None),
            ('sqlite_autoindex_evi_publications_1', 'index', 'evi_publications', None)}
        c.require({tuple(row) for row in self._db.execute('SELECT name,type,tbl_name,sql' + suffix)} == expected, 'SCHEMA')
        return True

    @staticmethod
    def _association(state, key):
        reservation, association = state['runs']['keys'].get(key), state['keys'].get(key)
        c.require(reservation is not None and association is not None, 'HANDOFF_MISSING')
        return reservation, association

    def _original(self, state, key):
        # Call only outside the control transaction: supervisor lookup may do I/O.
        c.require(not self._db.in_transaction, 'TRANSACTION_REENTRY')
        reservation, association = self._association(state, key)
        row = self.execution._row(reservation, association)
        c.require(row is not None, 'ATTEMPT_MISSING')
        return reservation, association, row

    @staticmethod
    def _configuration(state, key, intent):
        current = state['runs']['configurations']['latest'].get(key[0])
        c.require(current is not None and current['receiptDigest'] ==
                  intent['anchor']['configurationReceiptDigest'], 'CONFIGURATION_CHANGED')

    def _state(self):
        c.require(self._db.in_transaction, 'TRANSACTION_REQUIRED')
        execution = self.execution._load(); self._schema()
        c.require(self.journal._meta('authority') == self.execution.authority_id, 'AUTHORITY_MISMATCH')
        scan = self.execution.configurations._scan
        rows = scan('evi_meta', {'singleton': ('integer', 1), 'record': ('blob', c.RECORD_BYTES)}, 1)
        c.require(len(rows) == 1, 'INVALID_RETAINED'); meta = c.document(rows[0]['record'], c.RECORD_BYTES)
        c.exact(meta, ('profile', 'authorityId', 'deployment', 'supervisorAuthorityId', 'consumerIdentity',
            'vault', 'maxIntents', 'maxControlBytes', 'intentCharge', 'createdAtUnixMs'))
        c.require(meta['profile'] == c.PROFILE and meta['authorityId'] == self.execution.authority_id and
            meta['deployment'] == self.execution.deployment and meta['supervisorAuthorityId'] == execution['meta']['supervisorAuthorityId'] and
            meta['consumerIdentity'] == self.consumer_identity and canonical(meta['vault']) == canonical(self.descriptor) and
            self._anchor() == self._anchor_value(meta), 'MOUNT_CHANGED')
        c.number(meta['maxIntents'], 1, min(c.MAX_RUNS, self.descriptor['maxManifests'], execution['meta']['maxHandoffs']))
        c.number(meta['maxControlBytes'], c.INTENT_CHARGE + c.RECORD_BYTES + 1024, c.MAX_CONTROL_BYTES)
        c.require(type(meta['intentCharge']) is int and meta['intentCharge'] == c.INTENT_CHARGE, 'INVALID_RETAINED')
        c.number(meta['createdAtUnixMs'], 0, SAFE_INTEGER)
        base_charge = len(rows[0]['record']) + 1024
        rows = scan('evi_intents', {'sequence': ('integer', c.MAX_RUNS), 'evaluator': ('text', 128),
            'run': ('text', 128), 'intent': ('text', 71), 'record': ('blob', c.RECORD_BYTES)}, meta['maxIntents'])
        rows.sort(key=lambda row: row['sequence'])
        c.require([row['sequence'] for row in rows] == list(range(1, len(rows)+1)), 'INVALID_RETAINED')
        keys, intents = {}, {}; previous = None; now = meta['createdAtUnixMs']
        for row in rows:
            key = row['evaluator'], row['run']; services.name(key[0]); services.name(key[1])
            value = c.document(row['record'], c.RECORD_BYTES)
            c.exact(value, ('profile', 'sequence', 'storeId', 'consumerIdentity', 'anchor', 'bindingDigest',
                'principal', 'createdAtUnixMs', 'previousIntentDigest'))
            c.number(value['sequence'], 1, meta['maxIntents']); services.name(value['principal'])
            c.number(value['createdAtUnixMs'], now, SAFE_INTEGER); now = value['createdAtUnixMs']
            c.require(value['profile'] == c.INTENT and value['sequence'] == row['sequence'] and
                value['storeId'] == self.descriptor['storeId'] and value['consumerIdentity'] == self.consumer_identity and
                value['previousIntentDigest'] == previous and row['intent'] == c.hash_value(INTENT_DOMAIN, value) and
                value['bindingDigest'] == c.hash_value(BINDING_DOMAIN, value['anchor']), 'INVALID_RETAINED')
            reservation, association = self._association(execution, key)
            anchor = value['anchor']; saved = reservation['reservation']; handoff = association['receipt']
            c.require((anchor['evaluatorId'], anchor['runId']) == key and
                all(anchor[name] == saved[name] for name in ('authorityId', 'deployment', 'artifactDigest',
                    'configurationReceiptDigest', 'requestDigest', 'bundleDigest')) and
                anchor['reservationDigest'] == reservation['reservationDigest'] and
                anchor['handoffDigest'] == association['receiptDigest'] and
                anchor['attemptId'] == handoff['attemptId'] and
                anchor['supervisorAuthorityId'] == handoff['supervisorAuthorityId'], 'ASSOCIATION_CHANGED')
            c.require(key not in keys and row['intent'] not in intents, 'INVALID_RETAINED')
            previous = row['intent']; item = dict(intent=value, intentDigest=previous)
            keys[key] = item; intents[previous] = item
        charge = base_charge + len(keys) * c.INTENT_CHARGE
        c.require(charge <= meta['maxControlBytes'], 'CAPACITY')
        rows = scan('evi_publications', {'sequence': ('integer', c.MAX_RUNS), 'intent': ('text', 71),
            'record': ('blob', c.RECORD_BYTES)}, meta['maxIntents'])
        rows.sort(key=lambda row: row['sequence'])
        c.require([row['sequence'] for row in rows] == list(range(1, len(rows)+1)), 'INVALID_RETAINED')
        publications = {}; last = None; published_at = meta['createdAtUnixMs']
        for row in rows:
            value = c.document(row['record'], c.RECORD_BYTES)
            c.exact(value, ('profile', 'sequence', 'intentDigest', 'manifestDigest', 'evaluationDigest', 'closure',
                'principal', 'committedAtUnixMs', 'previousPublicationDigest'))
            c.number(value['sequence'], 1, meta['maxIntents']); services.name(value['principal'])
            c.number(value['committedAtUnixMs'], published_at, SAFE_INTEGER); published_at = value['committedAtUnixMs']
            c.require(value['profile'] == c.PUBLICATION and value['sequence'] == row['sequence'] and
                value['intentDigest'] == row['intent'] and row['intent'] in intents and row['intent'] not in publications and
                value['committedAtUnixMs'] >= intents[row['intent']]['intent']['createdAtUnixMs'] and
                value['previousPublicationDigest'] == last, 'INVALID_RETAINED')
            vault_contracts.digest(value['manifestDigest']); vault_contracts.digest(value['evaluationDigest'])
            c.exact(value['closure'], ('documents', 'bytes', 'digest'))
            c.number(value['closure']['documents'], 1, vault_contracts.MAX_DOCUMENTS)
            c.number(value['closure']['bytes'], 0, vault_contracts.MAX_RUN_BYTES)
            vault_contracts.digest(value['closure']['digest'])
            last = c.hash_value(PUBLICATION_DOMAIN, value)
            publications[row['intent']] = dict(receipt=value, receiptDigest=last)
        return dict(meta=meta, execution=execution, keys=keys, publications=publications, charge=charge,
            lastIntent=previous, lastIntentTime=now, lastPublication=last, lastPublicationTime=published_at)

    def _begin(self, evaluator, run):
        c.require(not self._db.in_transaction, 'TRANSACTION_REENTRY')
        services.name(evaluator); services.name(run)
        c.require(c.identity() == self.consumer_identity, 'IMPLEMENTATION_CHANGED')
        c.require(canonical(self.vault.descriptor()) == canonical(self.descriptor), 'MOUNT_CHANGED')
        return evaluator, run

    def _authorized(self, context):
        self.execution.configurations._authorize(context)
        return self._state()

    def _checkpoint(self, phase, value):
        """Installed failure-injection seam; never an import argument."""

    def _intent(self, context, key, state):
        original = self._original(state['execution'], key)
        anchor = reducer.anchor(*original)
        if key in state['keys']:
            item = state['keys'][key]
            c.require(item['intent']['anchor'] == anchor, 'ASSOCIATION_CHANGED')
            return item, original
        with self.journal._transaction():
            current = self._authorized(context)
            c.require(self._association(current['execution'], key) == original[:2], 'ASSOCIATION_CHANGED')
            c.require(key not in current['keys'], 'CONCURRENT_IMPORT')
            sequence = len(current['keys']) + 1; c.number(sequence, 1, current['meta']['maxIntents'])
            c.require(current['charge'] + c.INTENT_CHARGE <= current['meta']['maxControlBytes'], 'CAPACITY')
            now = self.journal._now(); c.number(now, current['lastIntentTime'], SAFE_INTEGER)
            value = dict(profile=c.INTENT, sequence=sequence, storeId=self.descriptor['storeId'],
                consumerIdentity=self.consumer_identity, anchor=anchor, bindingDigest=c.hash_value(BINDING_DOMAIN, anchor),
                principal=context.principal, createdAtUnixMs=now, previousIntentDigest=current['lastIntent'])
            self._configuration(current['execution'], key, value)
            wire = canonical(value); c.require(len(wire) <= c.RECORD_BYTES, 'CAPACITY')
            digest = c.hash_value(INTENT_DOMAIN, value)
            self._db.execute('INSERT INTO evi_intents VALUES(?,?,?,?,?)', (sequence, *key, digest, wire))
            self._checkpoint('before_intent_commit', value)
        item = dict(intent=value, intentDigest=digest)
        self._checkpoint('after_intent_commit', item)
        return item, original

    def _validated_files(self, item, original, snapshot):
        manifest, files = snapshot.manifest(), snapshot.documents()
        intent = item['intent']
        c.require(manifest['intentDigest'] == item['intentDigest'] and manifest['bindingDigest'] == intent['bindingDigest'] and
            manifest['storeId'] == intent['storeId'] and manifest['authorityId'] == self.journal.authority_id and
            manifest['scope'] == 'immutable-bytes-only' and canonical(c.closure(files)) == canonical(manifest['closure']), 'IMPORT_CHANGED')
        evaluation = c.document(files['evaluation.json'], c.RECORD_BYTES)
        c.exact(evaluation, ('profile', 'anchor', 'consumerIdentity', 'outcome', 'scope', 'inspectionDigest',
            'inspectedCases', 'unresolvedEffects', 'physicalObjectiveVerified', 'wallDeadlineAttested',
            'aggregateDiskQuotaEnforced', 'catalogActivated'))
        c.require(evaluation['profile'] == c.EVALUATION and evaluation['anchor'] == intent['anchor'] == reducer.anchor(*original) and
            evaluation['consumerIdentity'] == self.consumer_identity and evaluation['outcome'] == 'passed' and
            evaluation['scope'] == 'complete-finite-synthetic-io-matrix' and
            type(evaluation['unresolvedEffects']) is int and evaluation['unresolvedEffects'] == 0 and
            all(evaluation[name] is False for name in ('physicalObjectiveVerified', 'wallDeadlineAttested',
                'aggregateDiskQuotaEnforced', 'catalogActivated')) and
            c.sha(files['inspection/summary.json']) == evaluation['inspectionDigest'], 'INVALID_RETAINED')
        c.number(evaluation['inspectedCases'], 1, 32)
        reservation, association, attempt = original
        c.require(evaluation['inspectedCases'] == len(attempt['request']['bundleHeader']['caseIds']) ==
                  len(c.document(files['inspection/summary.json'])['cases']), 'INVALID_RETAINED')
        bundle = reservation['preparedRun']['bundle']
        originals = {'original/bundle/' + name: body for name, body in bundle['documents'].items()}
        originals['original/bundle/header.json'] = bundle['header']
        for name, value in dict(reservation=reservation['reservation'], handoff=association['receipt'],
                                request=attempt['request'], attempt=attempt['record']).items():
            originals['original/control/' + name + '.json'] = canonical(value)
        originals['original/control/return.json'] = attempt['returnBytes']
        outputs = {name[len('original/output/'):]: body for name, body in files.items() if name.startswith('original/output/')}
        paths = set(originals) | {'original/output/' + name for name in outputs} | {'evaluation.json', 'inspection/summary.json'}
        paths |= {'inspection/case-%02d.json' % i for i in range(evaluation['inspectedCases'])}
        c.require(set(files) == paths and all(files[name] == body for name, body in originals.items()) and
                  archive.output_closure(outputs) == intent['anchor']['outputClosure'], 'ASSOCIATION_CHANGED')
        return manifest, files, evaluation

    @contextmanager
    def _snapshot(self, intent_digest, binding_digest):
        # The byte-vault normalizes exceptions thrown into its context manager.
        # Authority refusals belong to this importer. Let the vault validate and
        # release its held snapshot normally, then re-raise the original refusal.
        # A vault expiry/cleanup failure still takes precedence; nothing commits
        # or becomes eligible because an authority exception was deferred here.
        refusal = None
        with self.vault.snapshot(intent_digest, binding_digest) as snapshot:
            try:
                yield snapshot
            except JournalError as error:
                refusal = error
        if refusal is not None:
            raise refusal

    def _published(self, context, key, state):
        item = state['keys'][key]; record = state['publications'][item['intentDigest']]
        original = self._original(state['execution'], key)
        with self._snapshot(item['intentDigest'], item['intent']['bindingDigest']) as snapshot:
            manifest, files, evaluation = self._validated_files(item, original, snapshot)
            receipt = record['receipt']
            c.require(receipt['manifestDigest'] == c.hash_value(MANIFEST_DOMAIN, manifest) and
                receipt['closure'] == manifest['closure'] and receipt['evaluationDigest'] == c.sha(files['evaluation.json']), 'IMPORT_CHANGED')
            with self.journal._transaction():
                current = self._authorized(context)
                c.require(current['keys'].get(key) == item and current['publications'].get(item['intentDigest']) == record,
                          'IMPORT_CHANGED')
                snapshot.check(self.vault)
            return dict(**record, intent=item['intent'], intentDigest=item['intentDigest'], evaluation=evaluation)

    @c.errors
    def lookup(self, context, evaluator, run):
        key = self._begin(evaluator, run)
        with self.execution._execution():
            with self.journal._transaction(): state = self._authorized(context)
            item = state['keys'].get(key)
            if item is None or item['intentDigest'] not in state['publications']: return None
            return self._published(context, key, state)

    @c.errors
    def pending(self, context, evaluator, run):
        """Authority intent status only; no claim about current bulk availability."""
        key = self._begin(evaluator, run)
        with self.execution._execution():
            with self.journal._transaction():
                state = self._authorized(context); item = state['keys'].get(key)
                if item is None: return None
                return dict(**item, published=item['intentDigest'] in state['publications'], logicalCharge=c.INTENT_CHARGE)

    @c.errors
    def import_run(self, context, evaluator, run):
        key = self._begin(evaluator, run)
        with self.execution._execution():
            with self.journal._transaction(): state = self._authorized(context)
            item = state['keys'].get(key)
            if item is not None and item['intentDigest'] in state['publications']:
                return self._published(context, key, state)
            item, original = self._intent(context, key, state)
            self._checkpoint('before_evidence', item)
            # A sealed-but-unpublished manifest is re-inspected from its retained
            # bytes. Only absence of THIS intent permits the original archive read.
            try:
                with self._snapshot(item['intentDigest'], item['intent']['bindingDigest']) as snapshot:
                    _, retained, _ = self._validated_files(item, original, snapshot)
            except vault_contracts.VaultError as error:
                if error.code != 'PAT_EVIDENCE_VAULT_MANIFEST_UNAVAILABLE': raise
                retained = None
            if retained is None:
                outputs = archive.read_original(self.execution.supervisor, original[2], original[0]['preparedRun']['bundle'])
            else:
                outputs = {name[len('original/output/'):]: body for name, body in retained.items() if name.startswith('original/output/')}
            inspected = reducer.reduce_original(*original, outputs, self.consumer_identity)
            c.require(retained is None or retained == inspected['documents'], 'SEMANTICS_CHANGED')
            self._checkpoint('after_inspection', inspected['evaluation'])
            c.require(c.identity() == self.consumer_identity, 'IMPLEMENTATION_CHANGED')
            with self.journal._transaction():
                current = self._authorized(context)
                c.require(current['keys'].get(key) == item, 'IMPORT_CHANGED')
                self._configuration(current['execution'], key, item['intent'])
            c.require(reducer.anchor(*self._original(current['execution'], key)) == item['intent']['anchor'], 'ASSOCIATION_CHANGED')
            if retained is None:
                self.vault.seal(item['intentDigest'], item['intent']['bindingDigest'], inspected['documents'])
            self._checkpoint('after_evidence_seal', item)
            c.require(c.identity() == self.consumer_identity, 'IMPLEMENTATION_CHANGED')
            with self._snapshot(item['intentDigest'], item['intent']['bindingDigest']) as snapshot:
                with self.journal._transaction(): current = self._authorized(context)
                current_original = self._original(current['execution'], key)
                manifest, files, evaluation = self._validated_files(item, current_original, snapshot)
                c.require(files == inspected['documents'], 'IMPORT_CHANGED')
                with self.journal._transaction():
                    state = self._authorized(context)
                    c.require(state['keys'].get(key) == item and item['intentDigest'] not in state['publications'], 'IMPORT_CHANGED')
                    self._configuration(state['execution'], key, item['intent'])
                    snapshot.check(self.vault)
                    now = self.journal._now(); c.number(now, state['lastPublicationTime'], SAFE_INTEGER)
                    receipt = dict(profile=c.PUBLICATION, sequence=len(state['publications']) + 1,
                        intentDigest=item['intentDigest'], manifestDigest=c.hash_value(MANIFEST_DOMAIN, manifest),
                        evaluationDigest=c.sha(files['evaluation.json']), closure=manifest['closure'], principal=context.principal,
                        committedAtUnixMs=now, previousPublicationDigest=state['lastPublication'])
                    wire = canonical(receipt); c.require(len(wire) <= c.RECORD_BYTES, 'CAPACITY')
                    self._db.execute('INSERT INTO evi_publications VALUES(?,?,?)', (receipt['sequence'], item['intentDigest'], wire))
                    result = dict(receipt=receipt, receiptDigest=c.hash_value(PUBLICATION_DOMAIN, receipt),
                        intent=item['intent'], intentDigest=item['intentDigest'], evaluation=evaluation)
                    self._checkpoint('before_publication_commit', result)
                    snapshot.check(self.vault)
                self._checkpoint('after_publication_commit', result)
                return result
