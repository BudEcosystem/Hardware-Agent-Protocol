"""Run each remaining frozen, distinct control scope once; stop on any failure."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parent
selection = json.loads((BASE / 'control-selection.json').read_bytes())
assert selection['testCount'] == 19 and len(selection['scopes']) == 10
for scope in selection['scopes']:
    harness = BASE / scope['harness']
    assert not (harness / 'attempts').exists()
    assert hashlib.sha256((harness / 'index.json').read_bytes()).hexdigest() == scope['indexSha256']
    print(json.dumps(dict(starting=scope['harness'], tests=len(scope['targets']))), flush=True)
    result = subprocess.run([sys.executable, '-I', '-B', str(harness / 'run_attempt.py')], check=False)
    if result.returncode: raise SystemExit(result.returncode)
