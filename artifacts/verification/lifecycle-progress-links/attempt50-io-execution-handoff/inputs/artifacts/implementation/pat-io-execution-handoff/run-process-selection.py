"""Execute one unstarted inherited process scope; retain failures without retry."""
import json, subprocess, sys
from pathlib import Path
B=Path('artifacts/implementation/pat-io-execution-handoff')
selections={19:(3,'cutoff'),20:(4,'pidfd'),21:(5,'deadline'),22:(6,'crash-admitted'),
    23:(8,'crash-launching'),24:(2,'pwm'),25:(7,'crash-archived'),26:(9,'crash-settled'),
    27:(10,'crash-spawned'),28:(11,'configured'),29:(13,'authority-owned'),30:(16,'reserved-owned')}
n=int(sys.argv[1]); h,label=selections[n]; harness='harness%02d'%h; attempt='attempt%02d-%s'%(n,label)
assert not (B/harness/'attempts'/attempt).exists()
done=subprocess.run([sys.executable,'-B',str(B/harness/'run_attempt.py'),attempt,'--parent-released'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
with (B/(attempt+'-launcher.log')).open('xb') as f:f.write(done.stdout)
result=json.loads((B/harness/'attempts'/attempt/'result.json').read_bytes())
assert done.returncode in (0,1) and result['childState']=='exited'
destination='attempt%02d-%s-%s'%(n,result['status'],label)
assert result['status'] in {'passed','failed'},'Inspect harness timeout before acquisition'
assert result['errors']==result['childErrors']==[] and result['counts']['testsRun']==1
commands=[('acquire',[harness,attempt,destination]),('audit-unsettled-storage',[destination]),('audit-retained-states',[destination])]
if result['status']=='passed':
    commands.append(('audit-process',[destination]))
    if h in (13,16):commands.append(('audit-authority',[destination]))
    if h==11:commands.append(('audit-service',[destination]))
    if h in (13,16):commands.append(('audit-authority-service',[destination]))
    if h==16:commands.append(('audit-runs',[destination]))
for tool,args in commands:
    checked=subprocess.run([sys.executable,'-I','-B',str(B/(tool+'.py')),*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    with (B/(attempt+'-'+tool+'.log')).open('xb') as f:f.write(checked.stdout)
    if checked.returncode:
        print(json.dumps(dict(attempt=attempt,failedTool=tool)),flush=True);raise SystemExit(checked.returncode)
print(json.dumps(dict(attempt=attempt,status=result['status'],counts=result['counts'],destination=destination,elapsedSeconds=result['elapsedSeconds'])),flush=True)
if result['status']!='passed':raise SystemExit('Retained failure; inspect and audit before later execution')
