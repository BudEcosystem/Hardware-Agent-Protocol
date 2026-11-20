"""Configuration sidecar for original finite I/O trials, not an attestor.

Every sidecar snapshot joins an exact legacy checkpoint while both authority
and board locks remain held. Both streams consume the original shared budget.
"""
from __future__ import annotations

import copy
import hashlib
import os

from . import pat_io_trials as trials
from .contracts import canonical, parse_json
from .pat_contracts import require

PROFILE = 'hms.pat.io-configuration-record/0.1'
PUBLIC_META = ('deployment', 'revision', 'version')
# Columns, exact SQLite storage classes, and bounded row inventory. Registry
# signing-key material is not needed to explain device execution authority.
TABLES = {
    'reg_meta': ('key,value', 'text text', 3),
    'reg_types': ('digest,document', 'text blob', 128),
    'reg_instances': ('id,deployment,type_digest,identity_kind,identity_ref,retired', 'text text text text text integer', 128),
    'reg_capabilities': ('instance,capability', 'text text', 2048),
    'reg_bindings': ('instance,generation,document,active', 'text text blob integer', 128),
    'reg_binding_history': ('instance,generation,digest,document', 'text text text blob', 128),
    'reg_presence': ('instance,session,expires_ms,adapter', 'text text integer text', 128),
    'reg_endpoint_sessions': ('instance,session', 'text text', 128),
    'reg_session_history': ('instance,session', 'text text', 512),
    'reg_observations': ('instance,property,document', 'text text blob', 256),
    'reg_streams': ('instance,property,epoch', 'text text text', 256),
    'reg_stream_history': ('instance,property,epoch', 'text text text', 1024),
    'reg_grants': ('principal,deployment,target,verb', 'text text text text', 4096),
    'reg_resource_requirements': ('adapter,profile', 'text text', 16),
    'reg_resource_instances': ('instance,adapter,profile', 'text text text', 128),
}


class ConfiguredIoTrialEngine(trials.IoTrialEngine):
    def __init__(self, *args, **kwargs):
        self.configuration_records, self.configuration_bytes = [], 0
        self._configuration_cache, self._configuration_snapshots = {}, []
        self._configuration_directory = None
        self._resolver_configuration = None
        super().__init__(*args, **kwargs)

    def _binding_configuration(self, registration, identity):
        self._resolver_configuration = {'profile': 'hms.pat.io-resolver-configuration/0.1',
            'resolverProfile': 'hms.pat.bindings.sqlite-finite-io/0.1',
            'registrations': [copy.deepcopy(registration)], 'registrationIdentity': identity}

    def _reserve(self, size):
        require(len(self.records) + len(self.configuration_records) < trials.MAX_RECORDS and
                self.output_bytes + self.configuration_bytes + size <= trials.MAX_OUTPUT_BYTES,
                'PAT_IO_CONFIGURATION_EVIDENCE_LIMIT')

    def _write(self, kind, value, *, reuse=False):
        data = canonical({'profile': self._record_profile, 'kind': kind, 'value': value})
        sha = hashlib.sha256(data).hexdigest()
        if not (reuse and sha in self._objects): self._reserve(len(data))
        return super()._write(kind, value, reuse=reuse)

    def _configuration_write(self, kind, value, *, reuse=False):
        self._check_budget()
        data = canonical({'profile': PROFILE, 'kind': kind, 'value': value})
        sha = hashlib.sha256(data).hexdigest()
        if reuse and sha in self._configuration_cache:
            return copy.deepcopy(self._configuration_cache[sha])
        self._reserve(len(data))
        reference = {'path': '%06d.json' % len(self.configuration_records), 'bytes': len(data), 'sha256': sha}
        if self._group_budget is not None:
            self._group_budget.record(len(data))
        with (self._configuration_directory / reference['path']).open('xb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        self.configuration_records.append(reference); self.configuration_bytes += len(data)
        if reuse: self._configuration_cache[sha] = reference
        return copy.deepcopy(reference)

    def _configuration_table(self, db, table, specification):
        fields, kinds, limit = specification; columns, kinds = fields.split(','), kinds.split()
        schema = db.execute('PRAGMA table_info(' + table + ')').fetchmany(33)
        require([r[1] for r in schema] == columns, 'PAT_IO_CONFIGURATION_STORAGE_SHAPE')
        where, params = (' WHERE key IN (?,?,?)', PUBLIC_META) if table == 'reg_meta' else ('', ())
        if table == 'reg_meta':
            keys = db.execute('SELECT key FROM reg_meta ORDER BY key LIMIT 5').fetchall()
            require([r[0] for r in keys] == ['cursor_key', 'deployment', 'revision', 'version'], 'PAT_IO_CONFIGURATION_STORAGE_SHAPE')
        count = db.execute('SELECT count(*) FROM ' + table + where, params).fetchone()[0]
        require(type(count) is int and count <= limit, 'PAT_IO_CONFIGURATION_STORAGE_LIMIT')
        actual_types = db.execute('SELECT DISTINCT ' + ','.join('typeof(' + c + ')' for c in columns) + ' FROM ' + table + where + ' LIMIT 2', params).fetchall()
        require(not count or len(actual_types) == 1 and tuple(actual_types[0]) == tuple(kinds), 'PAT_IO_CONFIGURATION_STORAGE_TYPE')
        sizes = db.execute('SELECT ' + ','.join('max(length(CAST(' + c + ' AS BLOB)))' for c in columns) + ' FROM ' + table + where, params).fetchone()
        require(all(v is None or type(v) is int and v <= 65536 for v in sizes), 'PAT_IO_CONFIGURATION_STORAGE_LIMIT')
        rows = db.execute('SELECT ' + fields + ' FROM ' + table + where + ' ORDER BY ' + fields + ' LIMIT ?', (*params, limit + 1)).fetchall()
        require(len(rows) == count, 'PAT_IO_CONFIGURATION_STORAGE_CHANGED')
        def cell(value, kind):
            if kind == 'blob':
                require(type(value) is bytes and canonical(parse_json(value)) == value, 'PAT_IO_CONFIGURATION_STORAGE_DOCUMENT')
                return {'type': 'blob-utf8', 'value': value.decode('utf-8')}
            require(type(value) is (int if kind == 'integer' else str), 'PAT_IO_CONFIGURATION_STORAGE_TYPE')
            return {'type': 'integer' if kind == 'integer' else 'text', 'value': value}
        pages = []
        projection = 'public_registry_metadata' if table == 'reg_meta' else 'complete'
        for offset in range(0, max(1, count), 8):
            pages.append(self._configuration_write('table_page', {'table': table, 'projection': projection,
                'columns': columns, 'first': offset, 'totalRows': count,
                'rows': [[cell(value, kind) for value, kind in zip(row, kinds)] for row in rows[offset:offset + 8]]}, reuse=True))
        return {'table': table, 'projection': projection, 'rowCount': count, 'pages': pages}

    def capture(self, label):
        self._check_budget()
        require(self.runtime is not None, 'PAT_IO_TRIAL_CLOSED')
        with self.runtime.journal._mutex, self.runtime.io_board.lock:
            authority, board = self.runtime.journal._db, self.runtime.io_board.db
            require(not authority.in_transaction and not board.in_transaction, 'PAT_IO_TRIAL_UNCOMMITTED_CAPTURE')
            before = (authority.total_changes, board.total_changes)
            if self._configuration_directory is None:
                self._configuration_directory = self.directory / 'configuration'
                self._configuration_directory.mkdir(mode=0o700)
                self._configuration_write('header', {'transcriptProfile': self._record_profile,
                    'setupRecords': copy.deepcopy(self.records[:4]), 'registryMetadataKeys': list(PUBLIC_META),
                    'sharedLimits': {'records': trials.MAX_RECORDS, 'bytes': trials.MAX_OUTPUT_BYTES,
                                     'documentBytes': 65536, 'schedulerTicks': trials.MAX_TICKS}})
            require(self._resolver_configuration is not None, 'PAT_IO_CONFIGURATION_RESOLVER_MISSING')
            # The outer locks remain held across both the legacy checkpoint and
            # configuration reads/writes. Neither store may have an open TX.
            checkpoint = super().capture(label)
            resolver = self._configuration_write('resolver_configuration', self._resolver_configuration, reuse=True)
            tables = [self._configuration_table(authority, name, spec) for name, spec in TABLES.items()]
            require((authority.total_changes, board.total_changes) == before and
                    not authority.in_transaction and not board.in_transaction, 'PAT_IO_CONFIGURATION_CAPTURE_MUTATED')
            ref = self._configuration_write('snapshot', {'checkpoint': checkpoint, 'phase': self.phase, 'label': label,
                **self._clock_values(), 'clockEpoch': self.runtime.registry.receipt_epoch,
                'authorityId': self.runtime.journal.authority_id, 'ownerEpoch': self.runtime.journal.owner_epoch,
                'session': self.runtime.io_board.session, 'resolver': resolver, 'tables': tables})
            self._configuration_snapshots.append({'checkpoint': checkpoint, 'configuration': ref})
            return checkpoint

    def configuration_manifest(self):
        """Retain association and accounting; this is not independent validation."""
        return {'profile': 'hms.pat.io-configuration-manifest/0.1',
            'records': copy.deepcopy(self.configuration_records), 'snapshots': copy.deepcopy(self._configuration_snapshots),
            'configurationBytes': self.configuration_bytes,
            'combinedRecords': len(self.records) + len(self.configuration_records),
            'combinedBytes': self.output_bytes + self.configuration_bytes,
            'configurationAttested': False, 'independentOutcomeChecked': False, 'qualificationPassed': False}
