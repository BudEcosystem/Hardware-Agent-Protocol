"""Retained copied-input pure/store test run; never changes a live source."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
root=Path(__file__).resolve().parent
attempt=root/'attempts'/sys.argv[1]
attempt.mkdir(parents=True,exist_ok=False)
tree=attempt/'tree';tree.mkdir()
for name in ('src','tests','baseline','retained'):
    shutil.copytree(root/name,tree/name)
shutil.copyfile(root/'before.json',tree/'before.json')
shutil.copyfile(__file__,attempt/'run_attempt.py')
def pins():
    return [{'path':str(p.relative_to(tree)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(tree.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
before=pins();(attempt/'inputs-before.json').write_text(json.dumps(before,indent=2)+'\n')
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(tree/'src')+os.pathsep+str(tree/'baseline/producer'))
start=time.monotonic()
with (attempt/'output.txt').open('w') as log:
    proc=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(tree/'tests'),'-v'],cwd=tree,env=env,stdout=log,stderr=subprocess.STDOUT)
after=pins();(attempt/'inputs-after.json').write_text(json.dumps(after,indent=2)+'\n')
result={'profile':'hms.staged-evidence-test-run/0.1','exitCode':proc.returncode,'seconds':time.monotonic()-start,
        'inputsStable':before==after,'inputCount':len(before),'scope':'Copied historical producer, actual retained records; pure reduction and SQLite retention only. No Runtime/worker/model/hardware execution.'}
(attempt/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));print((attempt/'output.txt').read_text())
raise SystemExit(proc.returncode or (0 if before==after else 2))
