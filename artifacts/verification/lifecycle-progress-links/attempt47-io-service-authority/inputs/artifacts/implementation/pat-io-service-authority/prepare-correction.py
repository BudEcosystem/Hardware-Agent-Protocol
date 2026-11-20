"""Preserve implementation01 failure and freeze bounded-row conversion correction."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
R=Path.cwd();B=R/'artifacts/implementation/pat-io-service-authority';O=B/'implementation01';S=B/'implementation02'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x') as f:f.write(json.dumps(v,indent=2)+'\n')
def inventory(folder,rooted=False):
 rows=[]
 for p in folder.rglob('*'):
  assert not p.is_symlink()
  if p.is_file():
   if p.suffix=='.py':ast.parse(p.read_bytes())
   rows.append(dict(path=p.relative_to(R if rooted else folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 return sorted(rows,key=lambda x:x['path'])
oldpin=sha(O/'index.json');assert oldpin=='4450761e8fb816ba557556a31538f9cd4ff4266dae162750ba97d9195fd24cd3'
rows=read(O/'index.json')['files']
for row in rows:assert sha(R/row['path'])==row['sha256']
failed=read(B/'results/attempt01-failed-authority32/proof.json');assert failed['status']=='failed' and failed['counts']==dict(testsRun=32,failures=2,errors=30,skips=0,expectedFailures=0,unexpectedSuccesses=0)
S.mkdir();shutil.copytree(O/'project',S/'project')
rel='supervisor/io_service_store.py';p=S/'project'/rel;before=p.read_text()
after=before.replace('return _resource_stored_row(self._db, \'reg_meta\', {\'key\': ANCHOR}, {\'value\': (\'text\', 128)})', "row = _resource_stored_row(self._db, 'reg_meta', {'key': ANCHOR}, {'value': ('text', 128)})\n        return None if row is None else dict(row)")
after=after.replace("require(row == {'value': expected},", "require(row is not None and row['value'] == expected,")
after=after.replace("require(authority == {'value': self.authority_id} and deployment == {'value': self.deployment},", "require(authority is not None and authority['value'] == self.authority_id and\n                deployment is not None and deployment['value'] == self.deployment,")
assert after!=before and after.count('_resource_stored_row(')==before.count('_resource_stored_row(')==4
ast.parse(after);p.write_text(after)
assert len(inventory(S/'project'))==244
changed=[r['path'] for r in inventory(O/'project') if sha(S/'project'/r['path'])!=r['sha256']];assert changed==[rel]
(B/'bounded-row-correction.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='implementation01/'+rel,tofile='implementation02/'+rel)))
write(S/'baseline-inputs.json',dict(sourceIndexSha256=oldpin,inheritedProjectInputs=[r for r in rows if r['path'].startswith(O.relative_to(R).as_posix()+'/project/')]))
review=read(O/'source-review.json');review.update(changedInheritedFiles=changed,unchangedInheritedFiles=243,newProjectFiles=0,correction='The existing bounded point-read helper returns sqlite3.Row, not dict. Compare indexed values for mandatory metadata; detach optional anchor into dict. No payload bounds, schema/authorization expectations, test bytes, deadlines or effects changed.',retainedFailedAttempt='results/attempt01-failed-authority32',projectExecutionDuringPreparation=False)
write(S/'source-review.json',review);(S/'README.md').write_text('# Corrected authority configuration\n\n[Design](../DESIGN.md), [review](source-review.json), [retained first failure](../results/attempt01-failed-authority32/proof.json). Only bounded row conversion is corrected; all test bytes unchanged.\n')
files=inventory(S,True);assert len(files)==247;write(S/'index.json',dict(scope='Corrected authority configuration; unchanged33 new test methods.',files=files));pin=sha(S/'index.json')
for n in range(1,14):
 prior=B/('harness%02d'%n);H=B/('harness%02d'%(n+13));H.mkdir();(H/'references').mkdir()
 for row in read(prior/'index.json')['files']:assert sha(prior/row['path'])==row['sha256']
 borrowed=[]
 for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
  p=prior/name;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(R).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(H/'borrowed-inputs.json',borrowed)
 for name in ('targets.json','SCOPE.md','README.md'):
  (H/name).write_text((prior/name).read_text().replace('implementation01','implementation02'))
 for name in ('run_attempt.py','attempt_child.py'):
  before=(prior/name).read_text();after=before.replace(oldpin,pin).replace('implementation01','implementation02')
  ast.parse(after);(H/name).write_text(after)
  (H/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str((prior/name).relative_to(R)),tofile=str((H/name).relative_to(R)))))
 hreview=read(prior/'review.json');hreview.update(sourceIndexSha256=pin,targetSha256=sha(H/'targets.json'),inheritedHarnessIndexSha256=sha(prior/'index.json'),correction=review['correction'])
 write(H/'review.json',hreview);write(H/'index.json',dict(scope=hreview['scope'],files=inventory(H)))
 print(json.dumps(dict(harness=H.name,tests=hreview['tests'],indexSha256=sha(H/'index.json'))))
print(json.dumps(dict(projectFiles=244,frozenFiles=247,sourceIndexSha256=pin)))
