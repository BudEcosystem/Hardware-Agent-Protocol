"""Pin compact storage separately from the unchanged producer/legacy reader."""
import hashlib
from pathlib import Path

from hms_qualification.evidence.contracts import identity as legacy_identity, require, hash_value

PROFILE = 'hms.pat.io-evidence-compact/0.1'
SOURCE_FILES = ('__init__.py', 'contracts.py', 'store.py')


def _sources():
    rows = []
    for name in SOURCE_FILES:
        with Path(__file__).with_name(name).open('rb') as stream:
            body = stream.read(4 * 1024 * 1024 + 1)
        require(len(body) <= 4 * 1024 * 1024, 'IMPLEMENTATION_LIMIT')
        rows.append(dict(path='evidence_compact/' + name, bytes=len(body), sha256=hashlib.sha256(body).hexdigest()))
    return rows


_IMPORTED_SOURCES = _sources()
_LEGACY_IDENTITY = legacy_identity()


def identity():
    require(_sources() == _IMPORTED_SOURCES and legacy_identity() == _LEGACY_IDENTITY, 'IMPLEMENTATION_CHANGED')
    return hash_value(b'HMS-PAT-IO-COMPACT-CONSUMER-v0.1', dict(legacyConsumerIdentity=_LEGACY_IDENTITY, sources=_IMPORTED_SOURCES))
