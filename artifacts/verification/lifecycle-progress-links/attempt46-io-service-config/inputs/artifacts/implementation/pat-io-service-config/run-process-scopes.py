"""Run ten predeclared process selections once each, sequentially."""
import json,subprocess,sys
from pathlib import Path
B=Path('artifacts/implementation/pat-io-service-config')
control=json.loads((B/'harness01/attempts/attempt01-control206/result.json').read_bytes())
assert control['status']=='passed'and control['counts']['testsRun']==206
for h,n,label in [(11,2,'configured'),(2,3,'pwm'),(7,4,'crash-archived'),(3,5,'cutoff'),(4,6,'pidfd'),(5,7,'deadline'),(6,8,'crash-admitted'),(8,9,'crash-launching'),(9,10,'crash-settled'),(10,11,'crash-spawned')]:
 harness='harness%02d'%h;attempt='attempt%02d-%s'%(n,label)
 done=subprocess.run([sys.executable,'-B',str(B/harness/'run_attempt.py'),attempt,'--parent-released'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 with(B/(attempt+'-launcher.log')).open('xb')as f:f.write(done.stdout)
 result=json.loads((B/harness/'attempts'/attempt/'result.json').read_bytes())
 assert done.returncode in(0,1)and result['childState']=='exited'and result['errors']==result['childErrors']==[]and result['scratchRetained']
 dest='attempt%02d-%s-%s'%(n,result['status'],label)
 commands=[('acquire',[harness,attempt,dest]),('audit-incomplete-states',[dest]),('audit-unsettled-storage',[dest])]
 if result['status']=='passed':commands.append(('audit-process',[dest]))
 if result['status']=='passed'and h==11:commands.append(('audit-service',[dest]))
 for name,args in commands:
  output=subprocess.run([sys.executable,'-I','-B',str(B/(name+'.py')),*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  with(B/(attempt+'-'+name+'.log')).open('xb')as f:f.write(output.stdout)
  if output.returncode:
   print(json.dumps(dict(attempt=attempt,tool=name,failed=True,log=str(B/(attempt+'-'+name+'.log')))),flush=True);raise SystemExit(output.returncode)
 print(json.dumps(dict(completed=attempt,status=result['status'],destination=dest,counts=result['counts'],elapsedSeconds=result['elapsedSeconds'])),flush=True)
