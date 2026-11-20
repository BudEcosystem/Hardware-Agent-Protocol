"""Run each distinct inherited process method once; retain deadline failures. No retry of either new reserved-worker attempt or any failed logical operation."""
import json,subprocess,sys
from pathlib import Path
B=Path('artifacts/implementation/pat-io-service-runs')
for h,name,count in [(14,'attempt01-runs15',15),(15,'attempt02-runs14',14)]:
 result=json.loads((B/('harness%02d'%h)/'attempts'/name/'result.json').read_bytes())
 assert result['status']=='passed'and result['counts']['testsRun']==count
selections=[(10,17,'crash-spawned')]
for h,n,label in selections:
 harness='harness%02d'%h;attempt='attempt%02d-%s'%(n,label)
 done=subprocess.run([sys.executable,'-B',str(B/harness/'run_attempt.py'),attempt,'--parent-released'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 with(B/(attempt+'-launcher.log')).open('xb')as f:f.write(done.stdout)
 result=json.loads((B/harness/'attempts'/attempt/'result.json').read_bytes())
 assert done.returncode in(0,1)and result['childState']=='exited'and result['errors']==result['childErrors']==[]and result['scratchRetained']
 dest='attempt%02d-%s-%s'%(n,result['status'],label)
 commands=[('acquire',[harness,attempt,dest]),('audit-unsettled-storage',[dest])]
 count=result['counts']['testsRun']
 if count==1:commands.append(('audit-incomplete-states',[dest]))
 if result['status']=='passed':
  if count==1:commands.append(('audit-process',[dest]))
  if h==1:commands.append(('audit-control',[dest]))
  if h in(12,13,16):commands.append(('audit-authority',[dest]))
  if h==11:commands.append(('audit-service',[dest]))
  if h in(13,16):commands.append(('audit-authority-service',[dest]))
  if h==16:commands.append(('audit-runs',[dest]))
 else:
  # Proceed only after the exact already-observed deadline archive is verified.
  # Any different failure causes this read-only auditor to stop the sequence.
  commands.append(('audit-failed-process',[dest]))
 for name,args in commands:
  output=subprocess.run([sys.executable,'-I','-B',str(B/(name+'.py')),*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  with(B/(attempt+'-'+name+'.log')).open('xb')as f:f.write(output.stdout)
  if output.returncode:
   print(json.dumps(dict(attempt=attempt,tool=name,failed=True,log=str(B/(attempt+'-'+name+'.log')))),flush=True);raise SystemExit(output.returncode)
 print(json.dumps(dict(completed=attempt,status=result['status'],destination=dest,counts=result['counts'],elapsedSeconds=result['elapsedSeconds'])),flush=True)
 if result['status']!='passed':
  print('Retained deadline failure; no retry. Continuing distinct inherited recovery methods.',flush=True)
