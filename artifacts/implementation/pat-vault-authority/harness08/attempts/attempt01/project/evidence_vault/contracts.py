"""Closed vault identities and bounds, separate from the legacy consumer."""
from functools import wraps
import hashlib
from pathlib import Path
import re
import sqlite3
import uuid

from hms.contracts import canonical
from hms.journal import JournalError
from evidence.contracts import (identity as legacy_identity, document, closure,
    closure_rows, path as document_path, sha, hash_value, MAX_DOCUMENTS,
    MAX_STORE_DOCUMENTS, MAX_DOCUMENT_BYTES, MAX_RUN_BYTES, MAX_STORE_BYTES, RECORD_BYTES)

PROFILE = 'hms.pat.evidence-vault/0.1'
MANIFEST = 'hms.pat.evidence-vault-manifest/0.1'
PAGE_SIZE = 1024
MAX_PAGES = 15 * 1024
MAX_MANIFESTS = 32
MAX_LEASE_MS = 5000
SOURCE_FILES = ('__init__.py', 'contracts.py', 'connection.py', 'store.py')


class VaultError(JournalError):
    def __init__(self, suffix):
        super().__init__('PAT_EVIDENCE_VAULT_' + suffix)


def require(value, suffix):
    if not value:
        raise VaultError(suffix)


def number(value, low, high):
    require(type(value) is int and low <= value <= high, 'LIMIT')


def digest(value):
    require(type(value) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', value), 'DIGEST')
    return value


def identifier(value):
    require(type(value) is str and re.fullmatch(r'[0-9a-f]{32}', value), 'IDENTITY')
    return value


def errors(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except VaultError:
            raise
        except JournalError as error:
            raise VaultError('INVALID') from error
        except sqlite3.Error as error:
            suffix = 'CAPACITY' if getattr(error, 'sqlite_errorcode', None) == sqlite3.SQLITE_FULL else 'DATABASE'
            raise VaultError(suffix) from error
        except (OSError, ValueError, TypeError, KeyError, IndexError, RecursionError) as error:
            raise VaultError('INVALID') from error
    return checked


def _sources():
    rows = []
    for name in SOURCE_FILES:
        with Path(__file__).with_name(name).open('rb') as stream:
            body = stream.read(4 * 1024 * 1024 + 1)
        require(len(body) <= 4 * 1024 * 1024, 'IMPLEMENTATION_LIMIT')
        rows.append(dict(path='evidence_vault/' + name, bytes=len(body), sha256=hashlib.sha256(body).hexdigest()))
    return rows


_IMPORTED_SOURCES = _sources()
_LEGACY_IDENTITY = legacy_identity()


def identity():
    require(_sources() == _IMPORTED_SOURCES and legacy_identity() == _LEGACY_IDENTITY, 'IMPLEMENTATION_CHANGED')
    return hash_value(b'HMS-PAT-EVIDENCE-VAULT-IMPLEMENTATION-v0.1',
                      dict(legacyIdentity=_LEGACY_IDENTITY, sources=_IMPORTED_SOURCES))


@errors
def descriptor(authority_id, *, max_pages=MAX_PAGES, max_manifests=MAX_MANIFESTS,
               max_documents=MAX_STORE_DOCUMENTS, max_objects=MAX_STORE_DOCUMENTS,
               max_data_bytes=MAX_STORE_BYTES, max_expanded_bytes=MAX_STORE_BYTES):
    """Mint installation data. The future authority installer must retain it."""
    value = dict(profile=PROFILE, authorityId=identifier(authority_id), storeId=uuid.uuid4().hex,
                 implementationDigest=identity(), pageSize=PAGE_SIZE, maxPages=max_pages,
                 maxManifests=max_manifests, maxDocuments=max_documents, maxObjects=max_objects,
                 maxDataBytes=max_data_bytes, maxExpandedBytes=max_expanded_bytes)
    validate_descriptor(value)
    return value


def validate_descriptor(value):
    require(type(value) is dict and set(value) == {'profile', 'authorityId', 'storeId',
        'implementationDigest', 'pageSize', 'maxPages', 'maxManifests', 'maxDocuments',
        'maxObjects', 'maxDataBytes', 'maxExpandedBytes'}, 'DESCRIPTOR')
    require(value['profile'] == PROFILE and type(value['pageSize']) is int and value['pageSize'] == PAGE_SIZE,
            'DESCRIPTOR')
    identifier(value['authorityId']); identifier(value['storeId']); digest(value['implementationDigest'])
    number(value['maxPages'], 8, MAX_PAGES)
    number(value['maxManifests'], 1, MAX_MANIFESTS)
    number(value['maxDocuments'], 1, MAX_STORE_DOCUMENTS)
    number(value['maxObjects'], 1, MAX_STORE_DOCUMENTS)
    number(value['maxDataBytes'], 1, MAX_STORE_BYTES)
    number(value['maxExpandedBytes'], 1, MAX_STORE_BYTES)
    require(len(canonical(value)) <= RECORD_BYTES, 'DESCRIPTOR')


def files_index(files):
    require(type(files) is dict and 1 <= len(files) <= MAX_DOCUMENTS, 'DOCUMENTS')
    rows = []
    total = 0
    for name, body in files.items():
        document_path(name)
        require(type(body) is bytes and len(body) <= MAX_DOCUMENT_BYTES, 'DOCUMENT')
        total += len(body)
        require(total <= MAX_RUN_BYTES, 'CAPACITY')
        rows.append(dict(path=name, bytes=len(body), sha256=sha(body)))
    rows.sort(key=lambda row: row['path'])
    return closure_rows(rows), rows
