"""Run the eight remaining predeclared scopes once each, stopping on collection failure."""
import json,subprocess,sys
from pathlib import Path
B=Path('artifacts/implementation/pat-io-supervision-recovery')
for h,n,label in [(3,4,'cutoff'),(4,5,'pidfd'),(5,6,'deadline'),(6,7,'crash-admitted'),(7,8,'crash-archived'),(8,9,'crash-launching'),(9,10,'crash-settled'),(10,11,'crash-spawned')]:
 harness='harness%02d'%h;attempt='attempt%02d-%s'%(n,label)
 done=subprocess.run([sys.executable,'-B',str(B/harness/'run_attempt.py'),attempt,'--parent-released'])
 result=json.loads((B/harness/'attempts'/attempt/'result.json').read_bytes())
 assert done.returncode in (0,1) and result['childState']=='exited' and result['errors']==result['childErrors']==[] and result['scratchRetained']
 dest='attempt%02d-%s-%s'%(n,result['status'],label)
 for command in ([sys.executable,'-I','-B',str(B/'acquire.py'),harness,attempt,dest],
                 [sys.executable,'-I','-B',str(B/'audit-partial-states.py'),dest],
                 [sys.executable,'-I','-B',str(B/'audit-storage.py'),dest]):
  subprocess.run(command,check=True)
 if result['status']=='passed':subprocess.run([sys.executable,'-I','-B',str(B/'audit-process.py'),dest],check=True)
 print(json.dumps(dict(completed=attempt,status=result['status'],destination=dest)),flush=True)
