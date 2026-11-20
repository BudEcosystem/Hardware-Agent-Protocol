"""Run each inherited frozen scope once, with no retry or widened limit."""
import json
from pathlib import Path
import subprocess
import sys

B = Path('artifacts/implementation/pat-io-document-validation')
first = json.loads((B/'results/attempt01-passed-canonical19/proof.json').read_bytes())
assert first['status'] == 'passed' and first['counts']['testsRun'] == 19
selections = [(1,2,'control206'),(16,3,'reserved-owned'),(9,4,'crash-settled'),(10,5,'crash-spawned'),
              (14,6,'runs15'),(15,7,'runs14'),(12,8,'authority32'),(13,9,'authority-owned'),
              (11,10,'configured'),(2,11,'pwm'),(7,12,'crash-archived'),(3,13,'cutoff'),
              (4,14,'pidfd'),(5,15,'deadline'),(6,16,'crash-admitted'),(8,17,'crash-launching')]
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
        if count == 1:
            commands.append(('audit-process',[destination]))
        if h == 1:
            commands.append(('audit-control',[destination]))
        if h in (12,13,14,15,16):
            commands.append(('audit-authority',[destination]))
        if h == 11:
            commands.append(('audit-service',[destination]))
        if h in (13,16):
            commands.append(('audit-authority-service',[destination]))
        if h in (14,15,16):
            commands.append(('audit-runs',[destination]))
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
