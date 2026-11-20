"""Bounded carrier rules and a conservative, separately pinned consumer."""
from functools import wraps
import hashlib
from pathlib import Path
import re
import sqlite3

from hms.contracts import canonical, parse_json
from hms.journal import JournalError
from qualification_supervisor import _image_rows

PROFILE = 'hms.pat.io-evidence-import/0.1'
EVALUATION = 'hms.pat.io-recorded-evaluation/0.1'
MAX_RUNS = 32
MAX_DOCUMENTS = 8320
MAX_STORE_DOCUMENTS = 32768
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_RUN_BYTES = 24 * 1024 * 1024
MAX_STORE_BYTES = 256 * 1024 * 1024
RECORD_BYTES = 16384
SOURCE_FILES = ('__init__.py', 'contracts.py', 'archive.py', 'reducer.py', 'store.py')


class EvidenceError(JournalError):
    def __init__(self, suffix): super().__init__('PAT_IO_EVIDENCE_' + suffix)


def require(value, suffix):
    if not value: raise EvidenceError(suffix)


def errors(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try: return function(*args, **kwargs)
        except JournalError: raise
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, IndexError, RecursionError) as error:
            raise EvidenceError('INVALID') from error
    return checked


def sha(body): return 'sha256:' + hashlib.sha256(body).hexdigest()


def hash_value(domain, value): return sha(domain + b'\0' + canonical(value))


def number(value, low, high):
    require(type(value) is int and low <= value <= high, 'LIMIT')


def exact(value, keys): require(type(value) is dict and set(value) == set(keys), 'FIELDS')


def path(value):
    require(type(value) is str and 1 <= len(value) <= 288 and
        re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', value) is not None and
        all(part not in ('.', '..') for part in value.split('/')), 'PATH')
    return value


def document(body, maximum=65536):
    require(type(body) is bytes and 0 < len(body) <= maximum, 'DOCUMENT')
    value = parse_json(body)
    require(canonical(value) == body, 'CANONICAL')
    return value


def closure_rows(rows):
    """Metadata digest; the caller must separately verify every actual body."""
    require(type(rows) is list and 1 <= len(rows) <= MAX_DOCUMENTS, 'CLOSURE')
    chain = hashlib.sha256(b'HMS-PAT-IO-IMPORTED-CLOSURE-v0.1\0')
    previous = ''; total = 0
    for row in rows:
        exact(row, ('path', 'bytes', 'sha256')); path(row['path'])
        require(row['path'] > previous, 'CLOSURE'); previous = row['path']
        number(row['bytes'], 0, MAX_DOCUMENT_BYTES)
        require(type(row['sha256']) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', row['sha256']), 'DIGEST')
        total += row['bytes']; chain.update(canonical(row) + b'\n')
    require(total <= MAX_RUN_BYTES, 'CAPACITY')
    return dict(documents=len(rows), bytes=total, digest='sha256:' + chain.hexdigest())


def closure(files):
    require(type(files) is dict and 1 <= len(files) <= MAX_DOCUMENTS, 'CLOSURE')
    require(all(type(body) is bytes for body in files.values()), 'DOCUMENT')
    return closure_rows([dict(path=name, bytes=len(body), sha256=sha(body)) for name, body in sorted(files.items())])


def _sources():
    # Includes the complete installed semantic/JSON/schema dependencies, not
    # just the reducer entry point. No caller-selected code or path is used.
    rows = _image_rows()
    rows += [('evidence/' + name, Path(__file__).with_name(name), None) for name in SOURCE_FILES]
    require(len(rows) <= 8192, 'IMPLEMENTATION_LIMIT')
    result = []; total = 0
    for name, source, expected in sorted(rows):
        with source.open('rb') as stream: body = stream.read(4 * 1024 * 1024 + 1)
        require(len(body) <= 4 * 1024 * 1024, 'IMPLEMENTATION_LIMIT')
        total += len(body); require(total <= 64 * 1024 * 1024, 'IMPLEMENTATION_LIMIT')
        actual = hashlib.sha256(body).hexdigest()
        require(expected is None or actual == expected, 'IMPLEMENTATION_CHANGED')
        result.append(dict(path=name, bytes=len(body), sha256=actual))
    return result


_IMPORTED_SOURCES = _sources()


def identity():
    require(_sources() == _IMPORTED_SOURCES, 'IMPLEMENTATION_CHANGED')
    return hash_value(b'HMS-PAT-IO-EVIDENCE-CONSUMER-v0.1', _IMPORTED_SOURCES)
