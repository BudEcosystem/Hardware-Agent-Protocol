"""Run the unchanged sixteen-case a162 overlay once against this frozen HMS."""
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'revalidation-a1626788'
prior = json.loads((HERE / 'prior-verification.json').read_text())
env = os.environ.copy()
env['PYTHONDONTWRITEBYTECODE'] = '1'
for key, value in prior['tests']['environment'].items():
    env[key] = value.replace(str(PRIOR), str(HERE))
for key in ('HMS_CAPTURE', 'HMS_TIMINGS', 'HMS_SDK_CAPTURE', 'HMS_COMPACT_CAPTURE', 'HMS_COMPACT_DIAGNOSTICS'):
    if Path(env[key]).exists():
        raise SystemExit('Refuse to overwrite retained output: ' + key)
result = subprocess.run([sys.executable, '-B', str(HERE / 'run-command.py'),
                         'focused-tests', *prior['tests']['command']], env=env)
raise SystemExit(result.returncode)
