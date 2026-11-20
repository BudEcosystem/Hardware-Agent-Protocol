"""Run each inherited frozen scope once, with no retry or widened limit."""
import json
from pathlib import Path
import subprocess
import sys

B = Path('artifacts/implementation/pat-io-execution-handoff')
first = json.loads((B/'results/attempt01-passed-authority13/proof.json').read_bytes())
assert first['status'] == 'passed' and first['counts']['testsRun'] == 13
selections = [(19,2,'handoff06a'),(20,3,'handoff06b'),(21,4,'handoff06c'),(22,5,'handoff06d'),(23,6,'handoff06e'),(24,7,'handoff02')]
for h, number, label in selections:
    harness = 'harness%02d'%h
    attempt = 'attempt%02d-%s'%(number,label)
    done = subprocess.run([sys.executable,'-B',str(B/harness/'run_attempt.py'),attempt,'--parent-released'],
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    with (B/(attempt+'-launcher.log')).open('xb') as stream:
        stream.write(done.stdout)
    result = json.loads((B/harness/'attempts'/attempt/'result.json').read_bytes())
    assert done.returncode in (0,1) and result['childState'] == 'exited'
    assert result['errors'] == result['childErrors'] == [] and result['scratchRetained']
    destination = 'attempt%02d-%s-%s'%(number,result['status'],label)
    count = result['counts']['testsRun']
    commands = [('acquire',[harness,attempt,destination]),('audit-unsettled-storage',[destination])]
    if count == 1:
        commands.append(('audit-incomplete-states',[destination]))
    if result['status'] == 'passed':
        commands.extend([('audit-authority',[destination]),('audit-runs',[destination])])
    for tool,args in commands:
        checked = subprocess.run([sys.executable,'-I','-B',str(B/(tool+'.py')),*args],
                                 stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        with (B/(attempt+'-'+tool+'.log')).open('xb') as stream:
            stream.write(checked.stdout)
        if checked.returncode:
            print(json.dumps(dict(attempt=attempt,failedTool=tool)),flush=True)
            raise SystemExit(checked.returncode)
    print(json.dumps(dict(attempt=attempt,status=result['status'],counts=result['counts'],
                          destination=destination,elapsedSeconds=result['elapsedSeconds'])),flush=True)
    if result['status'] != 'passed':
        raise SystemExit('Retained failed attempt; inspect before any later execution')
