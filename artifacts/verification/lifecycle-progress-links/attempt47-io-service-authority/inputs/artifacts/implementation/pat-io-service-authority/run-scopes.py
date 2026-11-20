"""Run each reviewed corrected process selection once, with acquisition/audits."""
import json,subprocess,sys
from pathlib import Path
B=Path('artifacts/implementation/pat-io-service-authority')
for h,name,count in [(25,'attempt02-authority32',32),(14,'attempt03-control206',206)]:
 result=json.loads((B/('harness%02d'%h)/'attempts'/name/'result.json').read_bytes())
 assert result['status']=='passed'and result['counts']['testsRun']==count
for h,n,label in [(26,4,'authority-owned'),(24,5,'configured'),(15,6,'pwm'),(20,7,'crash-archived'),(16,8,'cutoff'),(17,9,'pidfd'),(18,10,'deadline'),(19,11,'crash-admitted'),(21,12,'crash-launching'),(22,13,'crash-settled'),(23,14,'crash-spawned')]:
 harness='harness%02d'%h;attempt='attempt%02d-%s'%(n,label)
 done=subprocess.run([sys.executable,'-B',str(B/harness/'run_attempt.py'),attempt,'--parent-released'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 with(B/(attempt+'-launcher.log')).open('xb')as f:f.write(done.stdout)
 result=json.loads((B/harness/'attempts'/attempt/'result.json').read_bytes())
 assert done.returncode in(0,1)and result['childState']=='exited'and result['errors']==result['childErrors']==[]and result['scratchRetained']
 dest='attempt%02d-%s-%s'%(n,result['status'],label)
 commands=[('acquire',[harness,attempt,dest]),('audit-incomplete-states',[dest]),('audit-unsettled-storage',[dest])]
 if result['status']=='passed':commands.append(('audit-process',[dest]))
 if result['status']=='passed'and h==24:commands.append(('audit-service',[dest]))
 if result['status']=='passed'and h==26:commands.extend([('audit-authority',[dest]),('audit-authority-service',[dest])])
 for name,args in commands:
  output=subprocess.run([sys.executable,'-I','-B',str(B/(name+'.py')),*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  with(B/(attempt+'-'+name+'.log')).open('xb')as f:f.write(output.stdout)
  if output.returncode:
   print(json.dumps(dict(attempt=attempt,tool=name,failed=True,log=str(B/(attempt+'-'+name+'.log')))),flush=True);raise SystemExit(output.returncode)
 print(json.dumps(dict(completed=attempt,status=result['status'],destination=dest,counts=result['counts'],elapsedSeconds=result['elapsedSeconds'])),flush=True)
