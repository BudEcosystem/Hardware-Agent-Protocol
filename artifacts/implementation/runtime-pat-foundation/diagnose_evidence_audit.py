"""Collect stale historical references without publishing a success report."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('diagnostic_auditor', ROOT / 'scripts/audit_endpoint_evidence.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
errors = []
verify = module.verify


def collect(path, expected):
    try:
        verify(path, expected)
    except (OSError, ValueError) as error:
        errors.append(dict(path=str(path), expectedSha256=expected, error=str(error)))


class PublicationPrevented(Exception):
    pass


def forbid_write(*args, **kwargs):
    raise PublicationPrevented('Diagnostic cannot publish an audit result')


module.verify = collect
completed, failure = False, None
try:
    with redirect_stdout(io.StringIO()), patch.object(Path, 'write_text', forbid_write):
        module.main()
except PublicationPrevented:
    completed = True
except Exception as error:
    failure = repr(error)
report = dict(diagnosticOnly=True, passed=False, reachedPublicationBoundary=completed,
              publicationPrevented=True, mismatches=errors, otherFailure=failure)
with (BASE / 'evidence-diagnostic.json').open('x') as stream:
    json.dump(report, stream, indent=2); stream.write('\n')
print(json.dumps(report, indent=2))
