"""Release fresh complete pipelines only after both wrapper corrections pass."""
import ast,difflib,hashlib,json,re,shutil
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
pin=sha(B/'implementation04/index.json');assert pin=='ad22248967c7a163ccd108d13210331399e15ffb9e166541a80694dce649547c'
for name in ('attempt08-passed107','attempt09-passed-retained-history'):
 proof=read(B/'results'/name/'proof.json');assert proof['status']=='passed'and proof['sourceIndexSha256']==pin
for number,origin in ((13,8),(14,9)):
 old=B/('harness%02d'%origin);h=B/('harness%02d'%number);h.mkdir();(h/'references').mkdir()
 for row in read(old/'index.json')['files']:assert sha(old/row['path'])==row['sha256']
 for name in ('attempt_child.py','targets.json','SCOPE.md','README.md'):shutil.copyfile(old/name,h/name)
 borrowed=[]
 for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
  p=old/name;q=h/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(h).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(h/'borrowed-inputs.json',borrowed)
 before=(old/'run_attempt.py').read_text();after=before.replace(read(old/'review.json')['sourceIndexSha256'],pin).replace('implementation02','implementation04')
 after=re.sub(r'\b228\b','4201',after);after=re.sub(r'\b225\b','4198',after)
 ast.parse(after);assert "stage = here.parent / 'implementation04'"in after
 (h/'run_attempt.py').write_text(after);(h/'run_attempt.py.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(old/'run_attempt.py').relative_to(ROOT).as_posix(),tofile=(h/'run_attempt.py').relative_to(ROOT).as_posix())))
 review=read(old/'review.json');review.update(sourceIndexSha256=pin,scope='Fresh unchanged full pipeline on source04 after pure/retained corrections pass.')
 review['reviewed']+=['Source04 adds exact resource actor handling after unavailable-resolution correction. Both focused boundary families and complete historical semantics now pass. This fresh pipeline retains the unchanged full capture assertions, purity guards and all original limits; only source/count selectors change. Complete current capture and inspection remain required.']
 write(h/'review.json',review);write(h/'index.json',dict(scope='Original bounded full-history pipeline on corrected source04.',files=inventory(h)))
 print(json.dumps(dict(harness=h.name,indexSha256=sha(h/'index.json'))))
