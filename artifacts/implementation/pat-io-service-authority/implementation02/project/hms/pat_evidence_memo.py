"""Process-local memoization of the full pure evidence reducer.

No DB flag authenticates semantics. Explicit warming executes the unchanged
full reducer. Ongoing lookup reuses only identical typed inputs under an exact
imported validation-code identity. The store still reads and hashes every live
closure document and compares the complete recomputed bundle. Cache-cold is an
indeterminate refusal, never inline compilation under the eligibility lock.

Trusted code may not monkeypatch imported functions, override SQLite builtins,
or mutate this module's private state. Restart/reload changes require fresh
warming; disk edits underneath imported code are unsupported. Imports pin files;
lookup performs no file, clock, provider, compiler or SQL mutation.
"""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import sys
import threading
import _sqlite3

from hms import pat_simulation_evidence as reducer
from hms.contracts import canonical, check_tree, ContractError
from hms.pat_compiler import compiler_manifest
import hms.contracts

MAX_ENTRIES = 8
MAX_CACHE_BYTES = 32 * 1024 * 1024
DEFAULT_CACHE_BYTES = 8 * 1024 * 1024


def _identity():
    root = Path(hms.contracts.__file__).resolve().parents[1]
    paths = sorted({*root.joinpath('hms').rglob('*.py'), *root.joinpath('schemas').glob('*.json'),
                    *root.joinpath('examples/wot').glob('*.json'),
                    root/'research/protocols/wot-artifacts/td-schema-1.1.json'})
    source = [{'path': str(p.relative_to(root)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]
    local = [{'name': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in (Path(__file__), Path(reducer.__file__))]
    value = {'profile': 'hms.pat-evidence-imported-validation/0.1', 'sources': source, 'local': local,
        'compilerManifest': compiler_manifest(), 'python': platform.python_version(),
        'pythonImplementation': platform.python_implementation(),
        'pythonExecutableSha256': hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
        'sqliteVersion': sqlite3.sqlite_version,
        'sqliteExtensionSha256': hashlib.sha256(Path(_sqlite3.__file__).read_bytes()).hexdigest()}
    return value, reducer.hash_document(b'HMS-PAT-EVIDENCE-VALIDATION-v0.1', value)


_IMPORTED_MANIFEST, VALIDATION_ID = _identity()


def validation_identity():
    return VALIDATION_ID


def _typed_copy(value):
    """Preserve JSON scalar types; never call caller-defined copying hooks."""
    canonical(value)  # tree/carrier bound without replacing original types
    def clone(item):
        if type(item) is dict:
            return {key: clone(child) for key, child in item.items()}
        if type(item) is list:
            return [clone(child) for child in item]
        reducer.require(type(item) in (str, int, float, bool) or item is None)
        return item
    copied = clone(value)
    canonical(copied)
    return copied


def _typed_hash(value):
    check_tree(value)
    out = hashlib.sha256(b'HMS-PAT-EVIDENCE-TYPED-INPUT-v0.1\0')
    def part(tag, data):
        out.update(tag); out.update(str(len(data)).encode('ascii')); out.update(b':'); out.update(data)
    def visit(item):
        kind = type(item)
        if kind is dict:
            part(b'D', str(len(item)).encode('ascii'))
            for key in sorted(item):
                visit(key); visit(item[key])
        elif kind is list:
            part(b'L', str(len(item)).encode('ascii'))
            for child in item: visit(child)
        elif kind is str: part(b'S', item.encode('utf-8'))
        elif kind is bool: part(b'B', b'1' if item else b'0')
        elif kind is int: part(b'I', str(item).encode('ascii'))
        elif kind is float: part(b'F', item.hex().encode('ascii'))
        elif item is None: part(b'N', b'')
        else: raise reducer.EvidenceError('PAT_EVIDENCE_INVALID')
    visit(value)
    return out.digest()


def _snapshot(trust, result, files):
    trust = _typed_copy(trust)
    reducer.require(type(result) is bytes and 0 < len(result) <= reducer.MAX_DOCUMENT)
    reducer.require(type(files) is list and 1 <= len(files) <= reducer.MAX_RECORDS)
    copied, size = [], 0
    for item in files:
        reducer.exact(item, {'path', 'body'})
        path, body = item['path'], item['body']
        reducer.require(type(path) is str and len(path) <= 256 and
            type(body) is bytes and 0 < len(body) <= reducer.MAX_DOCUMENT)
        path.encode('utf-8')
        size += len(body)
        reducer.require(size <= 16 * 1024 * 1024, 'PAT_EVIDENCE_READ_BOUND')
        copied.append({'path': path, 'body': body})
    return trust, result, copied


def _key(identity, trust, result, files):
    out = hashlib.sha256(b'HMS-PAT-EVIDENCE-PURE-MEMO-v0.1\0' + identity.encode('ascii'))
    out.update(_typed_hash(trust))
    out.update(len(result).to_bytes(8, 'big')); out.update(hashlib.sha256(result).digest())
    out.update(len(files).to_bytes(8, 'big'))
    for item in files:
        path = item['path'].encode('utf-8')
        out.update(len(path).to_bytes(8, 'big')); out.update(path)
        out.update(len(item['body']).to_bytes(8, 'big')); out.update(hashlib.sha256(item['body']).digest())
    return out.digest()


def _pack(bundle):
    reducer.exact(bundle, {'profile', 'groupDigest', 'documents'})
    reducer.require(bundle['profile'] == reducer.PROFILE and type(bundle['documents']) is dict)
    reducer.require(1 <= len(bundle['documents']) <= reducer.MAX_GROUP_DOCUMENTS)
    documents = []
    for key, body in sorted(bundle['documents'].items()):
        reducer.require(reducer.digest(body) == key)
        documents.append((key, body))
    frozen = (bundle['groupDigest'], tuple(documents))
    # All retained byte payloads, keys and conservative per-document metadata
    # charge count. Entry and document ceilings additionally bound Python object
    # overhead; this is not an allocator/RSS hard limit.
    charge = 1024 + 32 + len(frozen[0].encode('ascii')) + sum(len(key.encode('ascii')) + len(body) + 128 for key, body in documents)
    return frozen, charge


def _unpack(frozen):
    return {'profile': reducer.PROFILE, 'groupDigest': frozen[0], 'documents': dict(frozen[1])}


class ValidatedReducerMemo:
    """Bounded FIFO of successful pure results, populated only by full reduction.

    Lookup never inserts, evicts, updates LRU state or caches failures. No public
    method accepts a purported passed bundle/attestation. Returned dictionaries
    are detached; retained strings and bytes are immutable.
    """
    def __init__(self, *, entries=MAX_ENTRIES, byte_limit=DEFAULT_CACHE_BYTES):
        reducer.integer(entries, 1, MAX_ENTRIES)
        reducer.integer(byte_limit, 1, MAX_CACHE_BYTES)
        self._entries_limit, self._byte_limit = entries, byte_limit
        self._identity, self._entries, self._bytes = VALIDATION_ID, OrderedDict(), 0
        self._mutex = threading.RLock()

    def _check_identity(self):
        reducer.require(self._identity == VALIDATION_ID, 'PAT_EVIDENCE_VALIDATOR_CHANGED')

    def usage(self):
        with self._mutex:
            return {'entries': len(self._entries), 'chargedBytes': self._bytes,
                    'entryLimit': self._entries_limit, 'byteLimit': self._byte_limit,
                    'validationIdentity': self._identity}

    @reducer._validated
    def lookup(self, trust, result, files):
        self._check_identity()
        args = _snapshot(trust, result, files)
        key = _key(self._identity, *args)
        with self._mutex:
            self._check_identity()
            entry = self._entries.get(key)
            reducer.require(entry is not None, 'PAT_EVIDENCE_CACHE_COLD')
            return _unpack(entry[0])

    @reducer._validated
    def warm(self, trust, result, files):
        """Trusted setup/audit operation, explicitly outside eligibility."""
        self._check_identity()
        args = _snapshot(trust, result, files)
        key = _key(self._identity, *args)
        with self._mutex:
            self._check_identity()
            entry = self._entries.get(key)
            if entry is not None:
                return _unpack(entry[0])
        # No database pass flag/result supplied by a caller can reach insertion.
        bundle = reducer.reduce_attempt(*args)
        frozen, charge = _pack(bundle)
        reducer.require(charge <= self._byte_limit, 'PAT_EVIDENCE_CACHE_CAPACITY')
        with self._mutex:
            self._check_identity()
            prior = self._entries.get(key)
            if prior is not None:
                reducer.require(prior[0] == frozen, 'PAT_EVIDENCE_MEMO_CONFLICT')
                return _unpack(prior[0])
            while len(self._entries) >= self._entries_limit or self._bytes + charge > self._byte_limit:
                _, (_, old_charge) = self._entries.popitem(last=False)
                self._bytes -= old_charge
            self._entries[key] = (frozen, charge); self._bytes += charge
        return _unpack(frozen)

    @reducer._validated
    def warm_stored(self, full_store, group_digest):
        """Restart path: read a snapshot and run full reduction before caching.

        This must run before workers or via a separately reviewed authorized
        export/warm design, not inside an eligibility callback/authority lock.
        It owns a read transaction; it does not mutate DB evidence or run links.
        """
        reducer.require(type(full_store) is reducer.EvidenceStore and not full_store.db.in_transaction,
                        'PAT_EVIDENCE_WARM_CONTEXT')
        full_store.db.execute('BEGIN')
        try:
            return full_store._load(group_digest, _reduce=self.warm)
        finally:
            full_store.db.rollback()


class FastEvidenceStore(reducer.EvidenceStore):
    def __init__(self, connection, trust, *, memo):
        reducer.require(type(memo) is ValidatedReducerMemo)
        self._memo = memo
        super().__init__(connection, trust)

    def _load(self, key):
        # Every _read, index traversal, manifest/case/whole-closure comparison
        # remains the full store's implementation. Only pure reduction is memoed.
        return super()._load(key, _reduce=self._memo.lookup)

    def import_bundle(self, bundle):
        raise reducer.EvidenceError('PAT_EVIDENCE_USE_FULL_IMPORT')
