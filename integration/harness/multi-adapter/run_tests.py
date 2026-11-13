"""Run sixteen existing a162 flows with one repaired copied-test assertion."""
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'installed-support'
prior = json.loads((HERE / 'prior-verification.json').read_text())
env = os.environ.copy()
env['PYTHONDONTWRITEBYTECODE'] = '1'
for key, value in prior['tests']['environment'].items():
    env[key] = value.replace(str(PRIOR), str(HERE))
if any((HERE / 'verification' / name).exists() for name in ('focused-tests.command.json', 'focused-tests.log')):
    raise SystemExit('Refuse to overwrite a completed or failed test run')
for key in ('HMS_CAPTURE', 'HMS_TIMINGS', 'HMS_SDK_CAPTURE', 'HMS_COMPACT_CAPTURE', 'HMS_COMPACT_DIAGNOSTICS'):
    if Path(env[key]).exists():
        raise SystemExit('Refuse to overwrite retained output: ' + key)
repair = json.loads((HERE / 'assertion-repair.json').read_text())
command = list(prior['tests']['command'])
assert command.count(repair['original']['path']) == 1
command[command.index(repair['original']['path'])] = repair['copied_test']['path']
result = subprocess.run([sys.executable, '-B', str(HERE / 'run-command.py'),
                         'focused-tests', *command], env=env)
raise SystemExit(result.returncode)
