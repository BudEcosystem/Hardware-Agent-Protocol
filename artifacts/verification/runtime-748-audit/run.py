"""Retain one evidence-audit attempt after a completed, passing full runtime run."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback
import uuid

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]


def pin(path):
    data = path.read_bytes()
    return {'path': str(path.relative_to(ROOT)), 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest()}


def write(path, value):
    with path.open('x') as handle:
        handle.write(json.dumps(value, indent=2) + '\n')


def main():
    current = json.loads((ROOT / 'artifacts/verification/local-runtime-current.json').read_text())
    if current['status'] != 'passed' or current['current_pass'] is not True:
        raise SystemExit('Full runtime attempt must pass before this audit.')
    attempt = BASE / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-' + uuid.uuid4().hex[:12])
    attempt.mkdir()
    sources = [Path(__file__), ROOT / 'scripts/audit_endpoint_evidence.py',
               ROOT / 'artifacts/verification/local-runtime-current.json',
               ROOT / current['receipt']['path']]
    for source in sources:
        target = attempt / 'before' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as output:
            output.write(source.read_bytes())
    prior_report = ROOT / 'artifacts/verification/endpoint-evidence-audit.json'
    if prior_report.exists():
        (attempt / 'previous-audit.json').write_bytes(prior_report.read_bytes())
    write(attempt / 'started.json', {'startedUtc': datetime.now(timezone.utc).isoformat(),
          'command': [sys.executable, '-B', 'scripts/audit_endpoint_evidence.py'],
          'runtime': current['receipt'], 'scope': 'Retained hash/provenance audit; no tests or devices.'})
    result = {'exitCode': None, 'exception': None}
    try:
        with (attempt / 'stdout.txt').open('xb') as out, (attempt / 'stderr.txt').open('xb') as err:
            completed = subprocess.run([sys.executable, '-B', 'scripts/audit_endpoint_evidence.py'],
                                       cwd=ROOT, stdout=out, stderr=err)
        result['exitCode'] = completed.returncode
    except BaseException:
        result['exception'] = traceback.format_exc()
    finally:
        result['auditorUnchanged'] = (ROOT / 'scripts/audit_endpoint_evidence.py').read_bytes() == (
            attempt / 'before/scripts/audit_endpoint_evidence.py').read_bytes()
        result['runtimePointerUnchanged'] = (ROOT / 'artifacts/verification/local-runtime-current.json').read_bytes() == (
            attempt / 'before/artifacts/verification/local-runtime-current.json').read_bytes()
        result['runnerUnchanged'] = Path(__file__).read_bytes() == (
            attempt / 'before' / Path(__file__).relative_to(ROOT)).read_bytes()
        if prior_report.exists():
            (attempt / 'report-after.json').write_bytes(prior_report.read_bytes())
        result['passed'] = (result['exitCode'] == 0 and result['exception'] is None and
                            result['auditorUnchanged'] and result['runtimePointerUnchanged'] and result['runnerUnchanged'])
        write(attempt / 'result.json', result)
        write(attempt / 'index.json', {'schema': 'hms-retained-audit-attempt/1',
              'files': [pin(path) for path in sorted(attempt.rglob('*')) if path.is_file()],
              'result': result})
    print(json.dumps({'attempt': str(attempt.relative_to(ROOT)), **result}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
