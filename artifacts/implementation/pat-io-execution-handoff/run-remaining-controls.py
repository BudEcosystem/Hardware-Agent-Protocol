"""Run the still-unstarted frozen control scopes once, stopping on any failure."""
import json, subprocess, sys
from pathlib import Path
B=Path('artifacts/implementation/pat-io-execution-handoff')
selections=[(27,11,'history-order','history'),(28,12,'history-identity','history'),
    (29,13,'history-reopen','history'),(30,14,'history-chain','history'),
    (17,15,'canonical19','canonical'),(12,16,'authority32','authority'),
    (14,17,'runs15','runs'),(15,18,'runs14','runs')]
assert json.loads((B/'results/attempt10-passed-history-clock/history-audit.json').read_bytes())['retainedCorruption']=='regressed-time'
for h,n,label,kind in selections:
    harness='harness%02d'%h; attempt='attempt%02d-%s'%(n,label)
    assert not (B/harness/'attempts'/attempt).exists()
    done=subprocess.run([sys.executable,'-B',str(B/harness/'run_attempt.py'),attempt,'--parent-released'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    with (B/(attempt+'-launcher.log')).open('xb') as f:f.write(done.stdout)
    result=json.loads((B/harness/'attempts'/attempt/'result.json').read_bytes())
    assert done.returncode in (0,1) and result['childState']=='exited'
    if result['status']=='timed_out':
        destination='attempt%02d-timeout-%s'%(n,label)
        commands=[('acquire-timeout',[harness,attempt,destination]),('audit-unsettled-storage',[destination])]
    else:
        assert result['errors']==result['childErrors']==[]
        destination='attempt%02d-%s-%s'%(n,result['status'],label)
        commands=[('acquire',[harness,attempt,destination]),('audit-unsettled-storage',[destination])]
        if result['status']=='passed':
            if kind=='canonical':commands.append(('audit-canonical-controls',[destination]))
            else:
                commands.append(('audit-authority',[destination]))
                if kind in {'history','runs'}:commands.append(('audit-runs',[destination]))
                if kind=='history':commands.append(('audit-history',[destination]))
    for tool,args in commands:
        checked=subprocess.run([sys.executable,'-I','-B',str(B/(tool+'.py')),*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        with (B/(attempt+'-'+tool+'.log')).open('xb') as f:f.write(checked.stdout)
        if checked.returncode:
            print(json.dumps(dict(attempt=attempt,failedTool=tool)),flush=True);raise SystemExit(checked.returncode)
    print(json.dumps(dict(attempt=attempt,status=result['status'],counts=result['counts'],destination=destination,elapsedSeconds=result['elapsedSeconds'])),flush=True)
    if result['status']!='passed':raise SystemExit('Retained failure; inspect before any later execution')
