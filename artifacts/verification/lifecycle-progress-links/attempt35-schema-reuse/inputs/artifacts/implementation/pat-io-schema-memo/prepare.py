"""Freeze exact schema reuse and fresh unchanged-bound capture selections."""
import ast,difflib,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-schema-memo';S=B/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-group-worker';OS=OLD/'implementation02'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
base=read(S/'baseline-inputs.json');assert sha(OS/'index.json')==base['sourceIndexSha256'];assert len(base['inheritedProjectInputs'])==217
patches=[]
for row in base['inheritedProjectInputs']:
 p=ROOT/row['path'];rel=p.relative_to(OS/'project');q=S/'project'/rel
 assert sha(p)==row['sha256']and p.stat().st_size==row['bytes']
 assert(sha(p)!=sha(q))is(rel.as_posix()=='hms/resource_topology.py')
 if sha(p)!=sha(q):patches.extend(difflib.unified_diff(p.read_text().splitlines(True),q.read_text().splitlines(True),fromfile=p.relative_to(ROOT).as_posix(),tofile=q.relative_to(ROOT).as_posix()))
(B/'schema-reuse.patch').write_text(''.join(patches))
def methods(module,cls):
 tree=ast.parse((S/'project/tests'/(module+'.py')).read_bytes());body=next(n.body for n in tree.body if isinstance(n,ast.ClassDef)and n.name==cls)
 return sorted(module+'.'+cls+'.'+n.name for n in body if isinstance(n,ast.FunctionDef)and n.name.startswith('test_'))
topology=methods('test_resource_topology','ResourceTopologyTests');memo=methods('test_resource_schema_memo','ResourceSchemaMemoTests')
assert len(topology)==21 and len(memo)==11
write(S/'source-review.json',dict(scope='Primary-agent full schema-reuse delta and eleven new regression methods reviewed before execution.',
 changedFiles=['hms/resource_topology.py'],newFiles=['tests/test_resource_schema_memo.py'],inheritedProjectFiles=217,unchangedInheritedFiles=216,
 reviewed=['Only successful JSON Schema validation is reused, keyed by exact bounded canonical bytes, profile and validator object identity. No graph, generation, claim, authority, runtime or proof validation is skipped.',
 'Every caller first receives the same canonical/strict-token/parser checks and a detached JSON tree. Warm entries cannot normalize integral floats into acceptance or retain caller mutation.',
 'Eight LRU entries hold at most512KiB of document bytes plus object overhead. Synchronization protects map access; schema validation occurs outside the lock. Invalid schemas are never cached; semantic-invalid documents still undergo semantics on every call.',
 'Replacing the private validator object misses its old entry. In-place mutation of private import-time validator schema/configuration is unsupported; this is not deployment attestation or a security boundary against in-process code modification.',
 'Existing21 pure topology checks,11 new warm/cold/eviction/type/detachment/semantic cases and12 group ledger/preflight tests selected together. Fresh actual cutoff/GPIO/PWM selections retain all existing30cases, fault schedules,60s group and180s harness deadlines and storage ceilings.',
 'Only one inherited production file differs; all216 other project files remain byte-identical. Live HMS, adjacent Harness and historical indexed sources/raw attempts untouched.'],
 independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Bounded exact schema reuse candidate\n\nThe [design](../DESIGN.md) and [source review](source-review.json) describe reuse\nof successful schema checks while retaining strict parsing and every semantic\ncheck. This responds to the retained group deadline profile. Full-group capture,\nindependent outcomes, attestation and actual storage quotas still require evidence.\n')
rows=[]
for p in sorted(S.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():
  if p.suffix=='.py':ast.parse(p.read_bytes())
  rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==221;write(S/'index.json',dict(scope='Frozen exact bounded schema validation reuse; all original group/harness ceilings unchanged.',files=rows));pin=sha(S/'index.json')
for i in range(1,5):
 old=OLD/('harness%02d'%(i+4));h=B/('harness%02d'%i);h.mkdir();(h/'references').mkdir();borrowed=[]
 for row in read(old/'index.json')['files']:assert sha(old/row['path'])==row['sha256']and(old/row['path']).stat().st_size==row['bytes']
 for name in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
  p=old/name;q=h/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(h).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(h/'borrowed-inputs.json',borrowed);t=read(old/'targets.json');previous=t['targets'][:]
 if i==1:t={'testCount':44,'targets':topology+memo+previous}
 write(h/'targets.json',t)
 for name in ['run_attempt.py','attempt_child.py']:
  before=(old/name).read_text();after=before.replace(base['sourceIndexSha256'],pin).replace('pat-io-group-worker','pat-io-schema-memo').replace('implementation02','implementation01')
  after=re.sub(r'\b217\b','218',after);after=re.sub(r'\b220\b','221',after)
  after=after.replace('hms-io-group-worker-','hms-io-schema-memo-')
  if i==1:
   after=after.replace('IoGroup12','SchemaMemo44').replace('group12','schema44').replace('!= 12','!= 44').replace('== 12','== 44').replace("'expectedTests': 12","'expectedTests': 44").replace(repr(previous),repr(t['targets']))
  ast.parse(after);(h/name).write_text(after)
  (h/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(old/name).relative_to(ROOT).as_posix(),tofile=(h/name).relative_to(ROOT).as_posix())))
 shutil.copyfile(old/'SCOPE.md',h/'SCOPE.md')
 (h/'README.md').write_text('# Exact bounded schema reuse selection\n\n[Targets](targets.json), [source](../implementation01/README.md), [scope](SCOPE.md).\nPrimary-agent source and harness review precedes execution. Original limits remain.\n')
 print(json.dumps(dict(harness=h.name,tests=t['testCount'],targetSha256=sha(h/'targets.json'))))
before=(OLD/'acquire02.py').read_text();after=before.replace('pat-io-group-worker','pat-io-schema-memo')
after=re.sub(r'\b217\b','218',after);after=re.sub(r'\b220\b','221',after);ast.parse(after)
(B/'acquire.py').write_text(after);(B/'acquire.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(OLD/'acquire02.py').relative_to(ROOT).as_posix(),tofile=(B/'acquire.py').relative_to(ROOT).as_posix())))
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=218,frozenFiles=221)))
