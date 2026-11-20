"""Run each remaining reviewed control once, at most two independent scopes."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys

base = Path(__file__).resolve().parent
def run(number):
    harness = base / ('harness%02d' % number)
    command = [sys.executable, str(harness / 'run_attempt.py'), 'attempt01', '--parent-released']
    assert not (harness / 'attempts/attempt01').exists()
    with (base / ('control-%02d-launcher.log' % number)).open('xb') as stream:
        process = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
    path = harness / 'attempts/attempt01/result.json'
    value = json.loads(path.read_bytes()) if path.is_file() else {}
    return dict(control=number, exitCode=process.returncode, status=value.get('status'),
                counts=value.get('counts'), errors=value.get('errors'))

with ThreadPoolExecutor(max_workers=2) as pool:
    futures = [pool.submit(run, number) for number in range(2, 24)]
    results = []
    for future in as_completed(futures):
        result = future.result(); results.append(result); print(json.dumps(result), flush=True)
with (base / 'control-launch-results.json').open('x') as stream:
    json.dump(sorted(results, key=lambda row: row['control']), stream, indent=2); stream.write('\n')
