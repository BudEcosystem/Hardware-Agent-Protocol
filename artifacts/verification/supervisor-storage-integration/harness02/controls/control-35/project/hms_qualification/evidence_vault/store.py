"""Atomic immutable manifests in an independent, explicitly bounded store.

A sealed manifest proves retained byte identity only. Authority publication,
original-run semantic validation and PAT qualification are separate consumers.
"""
from contextlib import contextmanager
import os
import sqlite3

from hms.contracts import canonical
from . import contracts as c
from .connection import _Connection, _Snapshot, _BatchSnapshot

DOMAIN = b'HMS-PAT-EVIDENCE-VAULT-MANIFEST-v0.1'
_DDL = {
    'ev_meta': 'CREATE TABLE ev_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), record BLOB NOT NULL)',
    'ev_manifests': 'CREATE TABLE ev_manifests (sequence INTEGER PRIMARY KEY, intent TEXT NOT NULL UNIQUE, binding TEXT NOT NULL, record BLOB NOT NULL)',
    'ev_documents': 'CREATE TABLE ev_documents (sequence INTEGER NOT NULL, path TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(sequence,path))',
    'ev_bodies': 'CREATE TABLE ev_bodies (digest TEXT PRIMARY KEY, body BLOB NOT NULL)',
}


class EvidenceVault(_Connection):
    @c.errors
    def __init__(self, path, expected, *, create=False):
        super().__init__(path, expected, create)
        try:
            if create:
                with self._transaction():
                    c.require(not self._db.execute('SELECT 1 FROM sqlite_master LIMIT 1').fetchall(), 'SCHEMA')
                    for sql in _DDL.values():
                        self._db.execute(sql)
                    self._db.execute('INSERT INTO ev_meta VALUES(1,?)', (self._descriptor_wire,))
                    self._state()
                os.fsync(self._dir_fd)
            else:
                # Opening an existing store validates but does not write data.
                with self._mutex:
                    self._ready()
                    self._db.execute('BEGIN')
                    try:
                        self._state()
                    finally:
                        if self._db.in_transaction:
                            self._db.execute('ROLLBACK')
        except BaseException:
            self.close()
            raise

    def descriptor(self):
        return c.document(self._descriptor_wire, c.RECORD_BYTES)

    def _schema(self):
        c.require(self._db.execute('SELECT 1 FROM sqlite_temp_master LIMIT 1').fetchone() is None, 'SCHEMA')
        checks = self._db.execute('SELECT typeof(name),length(CAST(name AS BLOB)),typeof(type),'
            'length(CAST(type AS BLOB)),typeof(tbl_name),length(CAST(tbl_name AS BLOB)),'
            'typeof(sql),length(CAST(sql AS BLOB)) FROM sqlite_master LIMIT 9').fetchall()
        c.require(len(checks) == 7, 'SCHEMA')
        for row in checks:
            c.require(all(row[i] == 'text' and type(row[i + 1]) is int and 1 <= row[i + 1] <= 128
                          for i in (0, 2, 4)), 'SCHEMA')
            c.require((row[6] == 'null' and row[7] is None) or
                      (row[6] == 'text' and type(row[7]) is int and 1 <= row[7] <= 4096), 'SCHEMA')
        expected = {(name, 'table', name, sql) for name, sql in _DDL.items()} | {
            ('sqlite_autoindex_ev_manifests_1', 'index', 'ev_manifests', None),
            ('sqlite_autoindex_ev_documents_1', 'index', 'ev_documents', None),
            ('sqlite_autoindex_ev_bodies_1', 'index', 'ev_bodies', None)}
        c.require(set(self._db.execute('SELECT name,type,tbl_name,sql FROM sqlite_master LIMIT 9')) == expected, 'SCHEMA')

    def _scan(self, table, fields, maximum):
        # Table/column identifiers originate only in this installed module.
        c.require(table in _DDL, 'SCHEMA')
        checks = []
        for name, (kind, limit) in fields.items():
            checks.append('typeof(' + name + ')')
            checks.append("CASE WHEN typeof(" + name + ")='integer' THEN " + name + ' ELSE NULL END'
                          if kind == 'integer' else 'length(CAST(' + name + ' AS BLOB))')
        suffix = ' FROM ' + table + ' LIMIT ?'
        rows = self._db.execute('SELECT ' + ','.join(checks) + suffix, (maximum + 1,)).fetchall()
        c.require(len(rows) <= maximum, 'CAPACITY')
        for row in rows:
            for i, (kind, limit) in enumerate(fields.values()):
                c.require(row[2*i] == kind and type(row[2*i + 1]) is int and
                          (0 if kind == 'blob' else 1) <= row[2*i + 1] <= limit, 'INVALID_RETAINED')
        values = self._db.execute('SELECT ' + ','.join(fields) + suffix, (maximum + 1,)).fetchall()
        c.require(len(values) == len(rows), 'INVALID_RETAINED')
        return [dict(zip(fields, row)) for row in values]

    def _index(self):
        meta = self._expected
        checks = self._db.execute('SELECT typeof(digest),length(CAST(digest AS BLOB)),'
            'typeof(body),length(body) FROM ev_bodies LIMIT ?', (meta['maxObjects'] + 1,)).fetchall()
        c.require(len(checks) <= meta['maxObjects'], 'CAPACITY')
        for row in checks:
            c.require(row[0] == 'text' and row[1] == 71 and row[2] == 'blob' and
                      type(row[3]) is int and 0 <= row[3] <= c.MAX_DOCUMENT_BYTES, 'INVALID_RETAINED')
        c.require(sum(row[3] + 256 for row in checks) <= meta['maxDataBytes'], 'CAPACITY')
        objects = {}
        for digest, size in self._db.execute('SELECT digest,length(body) FROM ev_bodies LIMIT ?',
                                            (meta['maxObjects'] + 1,)):
            c.digest(digest)
            c.require(digest not in objects, 'INVALID_RETAINED')
            objects[digest] = size
        c.require(len(objects) == len(checks), 'INVALID_RETAINED')
        refs = self._scan('ev_documents', {'sequence': ('integer', meta['maxManifests']),
            'path': ('text', 288), 'digest': ('text', 71)}, meta['maxDocuments'])
        groups = {}
        referenced = set()
        expanded = 0
        for row in refs:
            c.document_path(row['path']); c.digest(row['digest'])
            c.require(row['digest'] in objects, 'BODY_MISSING')
            group = groups.setdefault(row['sequence'], {})
            c.require(row['path'] not in group and len(group) < c.MAX_DOCUMENTS, 'INVALID_RETAINED')
            size = objects[row['digest']]
            group[row['path']] = dict(path=row['path'], bytes=size, sha256=row['digest'])
            referenced.add(row['digest'])
            expanded += size + 512
            c.require(expanded <= meta['maxExpandedBytes'], 'CAPACITY')
        c.require(referenced == set(objects), 'ORPHAN_BODY')
        return objects, groups, len(refs)

    def _state(self):
        c.require(self._db.in_transaction, 'TRANSACTION_REQUIRED')
        self._schema()
        rows = self._scan('ev_meta', {'singleton': ('integer', 1), 'record': ('blob', c.RECORD_BYTES)}, 1)
        c.require(len(rows) == 1 and rows[0]['record'] == self._descriptor_wire, 'MOUNT_CHANGED')
        meta = self._expected
        manifests = self._scan('ev_manifests', {'sequence': ('integer', meta['maxManifests']),
            'intent': ('text', 71), 'binding': ('text', 71), 'record': ('blob', c.RECORD_BYTES)}, meta['maxManifests'])
        manifests.sort(key=lambda row: row['sequence'])
        objects, groups, count = self._index()
        c.require([row['sequence'] for row in manifests] == list(range(1, len(manifests) + 1)) and
                  set(groups) == {row['sequence'] for row in manifests}, 'INVALID_RETAINED')
        keys = {}
        previous = None
        base = len(self._descriptor_wire) + 1024
        expanded = base
        for row in manifests:
            c.digest(row['intent']); c.digest(row['binding'])
            record = c.document(row['record'], c.RECORD_BYTES)
            c.require(type(record) is dict and set(record) == {'profile', 'scope', 'storeId', 'authorityId',
                'sequence', 'intentDigest', 'bindingDigest', 'closure', 'previousManifestDigest'}, 'INVALID_RETAINED')
            c.number(record['sequence'], 1, meta['maxManifests'])
            expected_closure = c.closure_rows(sorted(groups[row['sequence']].values(), key=lambda item: item['path']))
            c.require(record['profile'] == c.MANIFEST and record['scope'] == 'immutable-bytes-only' and
                record['storeId'] == meta['storeId'] and record['authorityId'] == meta['authorityId'] and
                record['sequence'] == row['sequence'] and record['intentDigest'] == row['intent'] and
                record['bindingDigest'] == row['binding'] and record['previousManifestDigest'] == previous and
                canonical(record['closure']) == canonical(expected_closure) and row['intent'] not in keys, 'INVALID_RETAINED')
            previous = c.hash_value(DOMAIN, record)
            keys[row['intent']] = dict(record=record, wire=row['record'], digest=previous)
            base += len(row['record']) + 512
            expanded += len(row['record']) + 512 + expected_closure['bytes'] + 512 * expected_closure['documents']
        charge = base + 512 * count + sum(size + 256 for size in objects.values())
        c.require(charge <= meta['maxDataBytes'] and expanded <= meta['maxExpandedBytes'], 'CAPACITY')
        return dict(keys=keys, objects=objects, groups=groups, documents=count,
                    charge=charge, expanded=expanded, lastDigest=previous)

    def _read(self, state, intent, binding):
        item = state['keys'].get(intent)
        c.require(item is not None, 'MANIFEST_UNAVAILABLE')
        c.require(item['record']['bindingDigest'] == binding, 'KEY_CONFLICT')
        sequence = item['record']['sequence']
        expected = state['groups'][sequence]
        rows = self._db.execute('SELECT d.path,b.body FROM ev_documents d JOIN ev_bodies b '
            'ON b.digest=d.digest WHERE d.sequence=? LIMIT ?', (sequence, c.MAX_DOCUMENTS + 1)).fetchall()
        c.require(len(rows) == len(expected), 'BODY_MISSING')
        files = {}
        for name, body in rows:
            c.require(name in expected and name not in files and type(body) is bytes and
                      len(body) == expected[name]['bytes'] and c.sha(body) == expected[name]['sha256'], 'BODY_CHANGED')
            files[name] = body
        c.require(canonical(c.closure(files)) == canonical(item['record']['closure']), 'BODY_CHANGED')
        return item, files

    def _checkpoint(self, phase, value):
        """Installed test seam, never a caller-provided callback."""

    @c.errors
    def seal(self, intent_digest, binding_digest, documents):
        c.digest(intent_digest); c.digest(binding_digest)
        closure, rows = c.files_index(documents)
        files = dict(documents)
        with self._transaction():
            state = self._state()
            if intent_digest in state['keys']:
                item, retained = self._read(state, intent_digest, binding_digest)
                c.require(retained == files, 'KEY_CONFLICT')
                return c.document(item['wire'], c.RECORD_BYTES)
            sequence = len(state['keys']) + 1
            c.number(sequence, 1, self._expected['maxManifests'])
            record = dict(profile=c.MANIFEST, scope='immutable-bytes-only', storeId=self._expected['storeId'],
                authorityId=self._expected['authorityId'], sequence=sequence, intentDigest=intent_digest,
                bindingDigest=binding_digest, closure=closure, previousManifestDigest=state['lastDigest'])
            wire = canonical(record)
            c.require(len(wire) <= c.RECORD_BYTES, 'CAPACITY')
            bodies = {}
            for body in files.values():
                digest = c.sha(body)
                c.require(digest not in bodies or bodies[digest] == body, 'BODY_CONFLICT')
                bodies[digest] = body
            additions = {digest: body for digest, body in bodies.items() if digest not in state['objects']}
            reference_charge = len(wire) + 512 + 512 * len(rows)
            meta = self._expected
            c.require(state['documents'] + len(rows) <= meta['maxDocuments'] and
                len(state['objects']) + len(additions) <= meta['maxObjects'] and
                state['charge'] + reference_charge + sum(len(body) + 256 for body in additions.values()) <= meta['maxDataBytes'] and
                state['expanded'] + reference_charge + closure['bytes'] <= meta['maxExpandedBytes'], 'CAPACITY')
            for digest, body in bodies.items():
                if digest in state['objects']:
                    retained = self._db.execute('SELECT body FROM ev_bodies WHERE digest=? LIMIT 2', (digest,)).fetchall()
                    c.require(len(retained) == 1 and type(retained[0][0]) is bytes and retained[0][0] == body and
                              c.sha(retained[0][0]) == digest, 'BODY_CHANGED')
            self._db.execute('INSERT INTO ev_manifests VALUES(?,?,?,?)', (sequence, intent_digest, binding_digest, wire))
            self._db.executemany('INSERT INTO ev_bodies VALUES(?,?)', sorted(additions.items()))
            self._db.executemany('INSERT INTO ev_documents VALUES(?,?,?)',
                                [(sequence, row['path'], row['sha256']) for row in rows])
            item, retained = self._read(self._state(), intent_digest, binding_digest)
            c.require(retained == files and item['wire'] == wire, 'BODY_CHANGED')
            self._checkpoint('before_manifest_commit', record)
        self._checkpoint('after_manifest_commit', record)
        return c.document(wire, c.RECORD_BYTES)

    @contextmanager
    def snapshot(self, intent_digest, binding_digest, *, lifetime_ms=c.MAX_LEASE_MS):
        """Hold checked current bytes. Future publication must check before commit.

        Expiration invalidates the handle; it does not forcibly interrupt Python
        or guarantee scheduling/stop latency. Callers must release it promptly.
        """
        try:
            c.digest(intent_digest); c.digest(binding_digest)
            c.number(lifetime_ms, 1, c.MAX_LEASE_MS)
            with self._mutex:
                self._ready()
                self._db.execute('PRAGMA query_only=ON')
                try:
                    self._db.execute('BEGIN')
                    item, files = self._read(self._state(), intent_digest, binding_digest)
                    lease = _Snapshot(self, item['wire'], files, lifetime_ms)
                    self._lease = lease
                    try:
                        yield lease
                        lease.check(self)
                        self._identities()
                    finally:
                        lease._active = False
                        self._lease = None
                finally:
                    try:
                        if self._db.in_transaction:
                            self._db.execute('ROLLBACK')
                        self._db.execute('PRAGMA query_only=OFF')
                    except BaseException:
                        self._poisoned = True
                        raise
        except c.VaultError:
            raise
        except c.JournalError as error:
            raise c.VaultError('INVALID') from error
        except sqlite3.Error as error:
            raise c.VaultError('DATABASE') from error
        except (OSError, ValueError, TypeError, KeyError, IndexError, RecursionError) as error:
            raise c.VaultError('INVALID') from error

    @contextmanager
    def snapshot_many(self, requests, *, lifetime_ms=c.MAX_LEASE_MS,
                      max_documents=c.MAX_STORE_DOCUMENTS, max_bytes=c.MAX_STORE_BYTES):
        """Hold every requested manifest or fail before yielding any view.

        Requests are exact (intent_digest, binding_digest) tuples in an exact
        tuple, with distinct intents. Limits cover the complete selected set;
        repeated bodies are charged per reference even though immutable bytes
        are shared in memory. Charge is each manifest's wire bytes plus 512,
        plus each reference's body bytes, UTF-8 path bytes and 512. This logical
        bound is not a measured Python-heap bound or a capacity reservation.
        Metadata and capacity preflight precede fetching selected body blobs.
        The lifetime begins after validation; callers must check at commit and
        promptly release the held transaction. Single and batch leases exclude
        each other. This does not establish semantic qualification.
        """
        try:
            c.require(type(requests) is tuple, 'REQUESTS')
            c.number(len(requests), 1, min(c.MAX_MANIFESTS, self._expected['maxManifests']))
            c.number(lifetime_ms, 1, c.MAX_LEASE_MS)
            c.number(max_documents, 1, c.MAX_STORE_DOCUMENTS)
            c.number(max_bytes, 1, c.MAX_STORE_BYTES)
            intents = set()
            for pair in requests:
                c.require(type(pair) is tuple and len(pair) == 2, 'REQUESTS')
                intent, binding = pair
                c.digest(intent); c.digest(binding)
                c.require(intent not in intents, 'DUPLICATE_INTENT')
                intents.add(intent)
            keys = tuple(sorted(requests))
            document_limit = min(max_documents, self._expected['maxDocuments'])
            byte_limit = min(max_bytes, self._expected['maxExpandedBytes'])
            with self._mutex:
                self._ready()
                self._db.execute('PRAGMA query_only=ON')
                try:
                    self._db.execute('BEGIN')
                    state = self._state()
                    count = charge = expanded = 0
                    for intent, binding in keys:
                        item = state['keys'].get(intent)
                        c.require(item is not None, 'MANIFEST_UNAVAILABLE')
                        c.require(item['record']['bindingDigest'] == binding, 'KEY_CONFLICT')
                        refs = state['groups'][item['record']['sequence']]
                        count += len(refs)
                        expanded += sum(row['bytes'] for row in refs.values())
                        charge += len(item['wire']) + 512 + sum(row['bytes'] + len(name.encode('utf-8')) + 512
                                                              for name, row in refs.items())
                        c.require(count <= document_limit and charge <= byte_limit, 'SNAPSHOT_CAPACITY')
                    records, bodies = {}, {}
                    for intent, binding in keys:
                        item, files = self._read(state, intent, binding)
                        refs = state['groups'][item['record']['sequence']]
                        shared = {}
                        for name, body in files.items():
                            digest = refs[name]['sha256']
                            if digest in bodies:
                                c.require(bodies[digest] == body, 'BODY_CONFLICT')
                            else:
                                bodies[digest] = body
                            shared[name] = bodies[digest]
                        records[(intent, binding)] = item['wire'], shared
                    usage = dict(manifests=len(keys), documents=count, expandedBodyBytes=expanded,
                        uniqueBodies=len(bodies), uniqueBodyBytes=sum(map(len, bodies.values())),
                        chargedBytes=charge, documentLimit=document_limit, byteLimit=byte_limit)
                    lease = _BatchSnapshot(self, records, usage, lifetime_ms)
                    self._lease = lease
                    try:
                        yield lease
                        lease.check(self)
                        self._identities()
                    finally:
                        lease._active = False
                        self._lease = None
                finally:
                    try:
                        if self._db.in_transaction:
                            self._db.execute('ROLLBACK')
                        self._db.execute('PRAGMA query_only=OFF')
                    except BaseException:
                        self._poisoned = True
                        raise
        except c.VaultError:
            raise
        except c.JournalError as error:
            raise c.VaultError('INVALID') from error
        except sqlite3.Error as error:
            raise c.VaultError('DATABASE') from error
        except (OSError, ValueError, TypeError, KeyError, IndexError, RecursionError) as error:
            raise c.VaultError('INVALID') from error
