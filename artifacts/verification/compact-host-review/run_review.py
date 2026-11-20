#!/usr/bin/env python3
"""Reproduce only the 25 independent tests against the pinned workspace inputs."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    pins = json.loads((HERE / 'source-pins.json').read_text())
    for pin in pins:
        assert sha(ROOT / pin['path']) == pin['sha256'], pin['path']
        assert sha(ROOT / pin['snapshot']) == pin['sha256'], pin['snapshot']
    build_path = ROOT / 'artifacts/verification/endpoint-scenarios.json'
    retained_build = HERE / 'endpoint-scenarios-build-receipt.json'
    assert sha(build_path) == sha(retained_build)
    build = json.loads(retained_build.read_text())
    binary_path = 'artifacts/verification/endpoint-scenarios-build/endpoint-scenarios-pipe'
    binary_pin = next(row for row in build['outputs'] if row['path'] == binary_path)
    assert sha(ROOT / binary_path) == binary_pin['sha256'] == sha(HERE / 'endpoint-scenarios-pipe')
    command = [sys.executable, '-m', 'unittest', '-v',
               'test_endpoint_binding_review', 'test_endpoint_journal']
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(ROOT / 'tests') + os.pathsep + str(ROOT)
    started = datetime.now(timezone.utc).isoformat()
    before = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=120)
    elapsed = time.monotonic() - before
    (HERE / 'test-run.log').write_bytes(result.stdout)
    log = result.stdout.decode('utf-8', 'replace')
    names = re.findall(r'^(test_\w+) \(([^)]+)\) \.\.\. ok$', log, re.M)
    assert result.returncode == 0 and len(names) == 25 and re.search(r'Ran 25 tests in .*\n\nOK\n', log), log
    assert sum('test_endpoint_binding_review.' in owner for _, owner in names) == 14
    assert sum('test_endpoint_journal.' in owner for _, owner in names) == 11
    for pin in pins:
        assert sha(ROOT / pin['path']) == pin['sha256'], 'Input changed: ' + pin['path']
    assert sha(ROOT / binary_path) == binary_pin['sha256']
    metadata = {'started_at': started, 'finished_at': datetime.now(timezone.utc).isoformat(),
        'command': command, 'cwd': str(ROOT), 'environment_overrides': {'PYTHONPATH': environment['PYTHONPATH']},
        'exit_code': result.returncode, 'elapsed_seconds': elapsed, 'tests': 25,
        'binding_review_tests': 14, 'journal_tests': 11, 'test_names': [name for name, _ in names],
        'source_inputs_unchanged': True, 'binary_unchanged': True,
        'python': {'path': sys.executable, 'sha256': sha(Path(sys.executable).resolve()), 'version': sys.version},
        'host': platform.platform(), 'jsonschema_version': importlib.metadata.version('jsonschema'),
        'log': {'path': str((HERE / 'test-run.log').relative_to(ROOT)), 'sha256': sha(HERE / 'test-run.log')}}
    (HERE / 'test-run.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps({'passed': True, 'tests': 25, 'elapsed_seconds': elapsed,
                      'log': str((HERE / 'test-run.log').relative_to(ROOT))}))


if __name__ == '__main__':
    main()
