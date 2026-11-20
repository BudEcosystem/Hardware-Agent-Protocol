"""Run the two previously frozen inherited control scopes once, sequentially.

The two owned-worker failures remain failures. These controls do not retry either
worker, replace its logical key, or establish complete process qualification.
"""
import json
import subprocess
import sys
from pathlib import Path

B = Path('artifacts/implementation/pat-io-service-runs')
for h, number, label, count in [(1, 5, 'control206', 206), (12, 6, 'authority32', 32)]:
    harness = 'harness%02d' % h
    attempt = 'attempt%02d-%s' % (number, label)
    done = subprocess.run([sys.executable, '-B', str(B/harness/'run_attempt.py'),
                           attempt, '--parent-released'], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    with (B/(attempt+'-launcher.log')).open('xb') as stream:
        stream.write(done.stdout)
    result = json.loads((B/harness/'attempts'/attempt/'result.json').read_bytes())
    assert done.returncode in (0, 1) and result['childState'] == 'exited'
    assert result['errors'] == result['childErrors'] == [] and result['scratchRetained']
    assert result['counts']['testsRun'] == count
    destination = 'attempt%02d-%s-%s' % (number, result['status'], label)
    commands = [('acquire', [harness, attempt, destination]),
                ('audit-unsettled-storage', [destination])]
    if result['status'] == 'passed':
        commands.append(('audit-control' if h == 1 else 'audit-authority', [destination]))
    for tool, args in commands:
        checked = subprocess.run([sys.executable, '-I', '-B', str(B/(tool+'.py')), *args],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        with (B/(attempt+'-'+tool+'.log')).open('xb') as stream:
            stream.write(checked.stdout)
        if checked.returncode:
            print(json.dumps(dict(attempt=attempt, failedTool=tool)), flush=True)
            raise SystemExit(checked.returncode)
    print(json.dumps(dict(attempt=attempt, status=result['status'], counts=result['counts'],
                          elapsedSeconds=result['elapsedSeconds'])), flush=True)
    if result['status'] != 'passed':
        raise SystemExit('Retained failed control scope; inspect before further execution')
