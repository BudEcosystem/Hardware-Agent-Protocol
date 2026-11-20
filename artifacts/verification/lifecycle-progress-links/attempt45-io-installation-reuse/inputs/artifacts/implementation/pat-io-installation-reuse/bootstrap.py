"""Copy only the uninstrumented sealed source before preparing normalization reuse."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd();O=ROOT/'artifacts/implementation/pat-io-supervision-recovery/implementation01';B=ROOT/'artifacts/implementation/pat-io-installation-reuse';S=B/'implementation01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(O/'index.json')=='d1c5ac0d86c77bd195ffebfcf75dc6e1c95ecf7a0814416073cfba691fb5685c'
(S/'project').mkdir(parents=True);rows=[]
for row in json.loads((O/'index.json').read_bytes())['files']:
 p=ROOT/row['path'];assert p.stat().st_size==row['bytes']and sha(p)==row['sha256']
 if p.is_relative_to(O/'project'):
  q=S/'project'/p.relative_to(O/'project');q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);rows.append(row)
assert len(rows)==239
(S/'baseline-inputs.json').write_text(json.dumps(dict(sourceIndexSha256=sha(O/'index.json'),inheritedProjectInputs=rows),indent=2)+'\n')
print('Copied239 uninstrumented project inputs; no project execution.')
