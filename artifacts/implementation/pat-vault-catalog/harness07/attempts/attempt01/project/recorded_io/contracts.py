"""Version and loaded-source identity for the host-only recorded profile."""
from functools import wraps
from pathlib import Path
import sqlite3

from hms.contracts import canonical, parse_json
from hms.journal import JournalError
from evidence.contracts import sha, hash_value
from evidence_compact.contracts import identity as consumer_identity

INVOCATION = 'hms.pat.io-recorded-invocation/0.1'
APPLICABILITY = 'hms.pat.io-source-applicability/0.1'
PROFILE = 'hms.pat.io-recorded-catalog/0.1'
MAX_ENTRIES = 4
MAX_MEMO_BYTES = 64 * 1024 * 1024
SOURCES = ('__init__.py', 'contracts.py', 'projection.py', 'bridge.py', 'catalog.py', 'execution.py')

class RecordedError(JournalError):
    def __init__(self, suffix):
        super().__init__('PAT_IO_RECORDED_' + suffix)

def require(condition, suffix):
    if not condition:
        raise RecordedError(suffix)

def checked(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except JournalError:
            raise
        except sqlite3.Error as error:
            raise RecordedError('STORAGE_UNAVAILABLE') from error
        except (TypeError, ValueError, KeyError, IndexError, RecursionError) as error:
            raise RecordedError('INVALID_INPUT') from error
    return call

def detached(value):
    return parse_json(canonical(value))

def _sources():
    rows = []
    for name in SOURCES:
        body = (Path(__file__).parent / name).read_bytes()
        require(len(body) <= 4 * 1024 * 1024, 'IMPLEMENTATION_CHANGED')
        rows.append(dict(path=name, bytes=len(body), sha256=sha(body)))
    return rows

_IMPORTED_SOURCES = _sources()
_CONSUMER = consumer_identity()
LOADED_IDENTITY = hash_value(b'HMS-PAT-IO-RECORDED-HOST-v0.1',
    dict(consumerIdentity=_CONSUMER, sources=_IMPORTED_SOURCES))

def identity():
    """Filesystem check for construction/preparation, never admission."""
    require(_sources() == _IMPORTED_SOURCES and consumer_identity() == _CONSUMER,
            'IMPLEMENTATION_CHANGED')
    return LOADED_IDENTITY
