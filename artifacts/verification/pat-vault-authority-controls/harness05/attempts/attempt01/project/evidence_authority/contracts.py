"""Distinct import identity; neither the compact catalog nor its SQL scope changes."""
import hashlib
from pathlib import Path

from evidence.contracts import (errors, require, number, exact, document, sha,
    hash_value, closure, RECORD_BYTES, MAX_RUNS, EVALUATION, EvidenceError)
from evidence_vault.contracts import identity as vault_identity

PROFILE = 'hms.pat.vault-import/0.1'
INTENT = 'hms.pat.vault-import-intent/0.1'
PUBLICATION = 'hms.pat.vault-publication/0.1'
MAX_CONTROL_BYTES = 256 * 1024
# Logical accounting for the two bounded records and their index overhead.
# This is NOT reserved filesystem space or a guarantee that COMMIT can succeed.
INTENT_CHARGE = 2 * RECORD_BYTES + 1024
SOURCE_FILES = ('__init__.py', 'contracts.py', 'store.py')


def _sources():
    result = []
    for name in SOURCE_FILES:
        with Path(__file__).with_name(name).open('rb') as stream:
            body = stream.read(4 * 1024 * 1024 + 1)
        require(len(body) <= 4 * 1024 * 1024, 'IMPLEMENTATION_LIMIT')
        result.append(dict(path='evidence_authority/' + name, bytes=len(body),
                           sha256=hashlib.sha256(body).hexdigest()))
    return result


_IMPORTED = _sources()
_VAULT = vault_identity()


def identity():
    require(_sources() == _IMPORTED and vault_identity() == _VAULT, 'IMPLEMENTATION_CHANGED')
    return hash_value(b'HMS-PAT-VAULT-IMPORT-IMPLEMENTATION-v0.1',
                      dict(vaultIdentity=_VAULT, sources=_IMPORTED))
