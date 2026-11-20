"""Run remaining reviewed controls once, after the actual scope is terminal."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys

base = Path(__file__).resolve().parent
actual = json.loads((base/'harness83/attempts/attempt01-actual/result.json').read_bytes())
assert actual['childState'] == 'exited' and actual['status'] == 'passed'
assert actual['rawScratchInventoryTerminal'] and not actual['rawScratchMayContainUnsettledFixtureWork']

def run(number):
    harness = base / ('harness%02d' % number)
    assert not (harness/'attempts/attempt01').exists()
    assert (harness/'index.json').is_file() and (harness/'review.json').is_file()
    with (base/('source04-control-%02d-launcher.log' % number)).open('xb') as stream:
        completed = subprocess.run([sys.executable, str(harness/'run_attempt.py'), 'attempt01', '--parent-released'],
            stdout=stream, stderr=subprocess.STDOUT, check=False)
    result = json.loads((harness/'attempts/attempt01/result.json').read_bytes())
    return dict(harness=number, exitCode=completed.returncode, status=result['status'], counts=result['counts'], errors=result['errors'])

with ThreadPoolExecutor(max_workers=2) as pool:
    futures = [pool.submit(run, number) for number in range(84, 102)]
    results = []
    for future in as_completed(futures):
        result = future.result(); results.append(result)
        print(json.dumps(result), flush=True)
with (base/'source04-control-launch-results.json').open('x') as stream:
    json.dump(sorted(results, key=lambda value:value['harness']), stream, indent=2)
    stream.write('\n')
