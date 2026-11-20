import hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent;attempt=root/'attempts'/sys.argv[1];attempt.mkdir(parents=True,exist_ok=False)
tree=attempt/'tree';tree.mkdir()
for name in ('src','tests','baseline','retained'):shutil.copytree(root/name,tree/name)
shutil.copyfile(root/'before.json',tree/'before.json');shutil.copyfile(__file__,attempt/'run_attempt.py')
def pins():
 return [{'path':str(p.relative_to(tree)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(tree.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
before=pins();(attempt/'inputs-before.json').write_text(json.dumps(before,indent=2)+'\n')
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=os.pathsep.join([str(tree/'src'),str(tree/'baseline/producer')]))
start=time.monotonic()
with (attempt/'output.txt').open('w') as out:
 proc=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(tree/'tests'),'-v'],cwd=tree,env=env,stdout=out,stderr=subprocess.STDOUT)
after=pins();(attempt/'inputs-after.json').write_text(json.dumps(after,indent=2)+'\n')
result={'profile':'hms.staged-memo-tests/0.1','exitCode':proc.returncode,'seconds':time.monotonic()-start,'inputCount':len(before),'inputsStable':before==after,'scope':'Historical actual worker data; full reducer and cache/store only; no Runtime/worker/model/hardware execution.'}
(attempt/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));print((attempt/'output.txt').read_text());raise SystemExit(proc.returncode or (0 if before==after else 2))
