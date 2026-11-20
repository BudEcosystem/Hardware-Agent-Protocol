"""Retain pre-start refusal and correct only the source02 stage selector."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-group-history'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
def inventory(folder):
 rows=[]
 for p in sorted(folder.rglob('*')):
  assert not p.is_symlink()
  if p.is_file():rows.append(dict(path=p.relative_to(folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 return rows
A=B/'harness04/attempts/attempt03-pure106';result=read(A/'result.json')
assert result['status']=='failed'and result['childState']=='not_started'and result['counts']is None and result['exitCode']is None
assert 'pid'not in result and 'scratchPath'not in result
assert result['errors'][0]['message']=='Frozen source-preparation index changed'
out=B/'results/attempt03-launcher-refused';out.mkdir();rows=inventory(A);shutil.copytree(A,out/'attempt');assert inventory(out/'attempt')==rows
write(out/'proof.json',dict(scope='Parent source-pin refusal before child creation or raw scratch; no test execution.',
 status='refused_before_start',childStarted=False,rawScratchCreated=False,attemptFilesAcquired=len(rows),
 originalAttempt='harness04/attempts/attempt03-pure106',completeOriginalAndCopyRetained=True))
for origin in (4,5,6):
 old=B/('harness%02d'%origin);h=B/('harness%02d'%(origin+3));h.mkdir();(h/'references').mkdir()
 for row in read(old/'index.json')['files']:assert sha(old/row['path'])==row['sha256']
 for name in ('attempt_child.py','targets.json','SCOPE.md','README.md'):shutil.copyfile(old/name,h/name)
 borrowed=[]
 for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
  p=old/name;q=h/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(h).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(h/'borrowed-inputs.json',borrowed)
 before=(old/'run_attempt.py').read_text();needle="stage = here.parent / 'implementation01'";assert before.count(needle)==1
 after=before.replace(needle,"stage = here.parent / 'implementation02'");assert 'implementation01'not in after;ast.parse(after)
 (h/'run_attempt.py').write_text(after);(h/'run_attempt.py.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(old/'run_attempt.py').relative_to(ROOT).as_posix(),tofile=(h/'run_attempt.py').relative_to(ROOT).as_posix())))
 review=read(old/'review.json');review['reviewed'].append('Parent source02 hash/prefix were correct but stage selector still named source01. Original parent refused before child/scratch creation. This fresh harness corrects only the stage selector; source02 and all limits/selections/child SQL scope unchanged.')
 write(h/'review.json',review);write(h/'index.json',dict(scope='Narrow launcher stage-selector correction after preserved pre-start refusal.',files=inventory(h)))
 print(json.dumps(dict(harness=h.name,tests=review['tests'],indexSha256=sha(h/'index.json'))))
