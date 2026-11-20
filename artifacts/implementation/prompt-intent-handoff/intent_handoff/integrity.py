"""Check retained parser dependencies; this is not hostile-host attestation."""
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SHA256 = '3ac668cab1a33f9897732ea06791e5ab2682ea6526a8bc5927076953d0206e5d'
MODULES = {'hms': 'hms/__init__.py', 'hms.contracts': 'hms/contracts.py',
           'hms.journal': 'hms/journal.py', 'hms.pat_contracts': 'hms/pat_contracts.py',
           'hms.api_contracts': 'hms/api_contracts.py',
           'hms._vendor': 'hms/_vendor/__init__.py',
           'hms._vendor.rfc8785': 'hms/_vendor/rfc8785/__init__.py',
           'hms._vendor.rfc8785._impl': 'hms/_vendor/rfc8785/_impl.py'}
OPTIONAL_MODULES = {'hms.registry': 'hms/registry.py', 'hms.projections': 'hms/projections.py'}


def verify(*, loaded=False):
    raw = (ROOT / 'DEPENDENCIES.sha256').read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError('dependency manifest changed')
    for line in raw.decode('ascii').splitlines():
        digest, path = line.split('  ', 1)
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
            raise ValueError('retained parser dependency changed')
    if loaded:
        for name, path in MODULES.items():
            module = sys.modules.get(name)
            if module is None or Path(module.__file__).resolve() != ROOT / 'dependencies' / path:
                raise ValueError('parser dependency loaded from an unpinned origin')
        for name, path in OPTIONAL_MODULES.items():
            module = sys.modules.get(name)
            if module is not None and Path(module.__file__).resolve() != ROOT / 'dependencies' / path:
                raise ValueError('read-validator dependency loaded from an unpinned origin')
    return 'sha256:' + MANIFEST_SHA256
