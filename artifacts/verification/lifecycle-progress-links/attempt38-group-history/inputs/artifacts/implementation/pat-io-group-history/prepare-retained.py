"""Freeze corrected-reader validation on an immutable complete earlier capture."""
import ast,difflib,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-group-history';S=B/'implementation03';OLD=B/'implementation02'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
def inventory(folder,rooted=False):
 rows=[]
 for p in sorted(folder.rglob('*')):
  assert not p.is_symlink()
  if p.is_file():
   if p.suffix=='.py':ast.parse(p.read_bytes())
   rows.append(dict(path=p.relative_to(ROOT if rooted else folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 return rows
baseline=read(S/'baseline-inputs.json');assert sha(OLD/'index.json')==baseline['sourceIndexSha256']
for row in baseline['inheritedProjectInputs']:
 p=ROOT/row['path'];q=S/'project'/p.relative_to(OLD/'project');assert sha(p)==sha(q)==row['sha256']and p.stat().st_size==q.stat().st_size==row['bytes']
for row in baseline['fixtureInputs']:
 p=ROOT/row['source'];q=S/'project'/row['copy'];assert sha(p)==sha(q)==row['sha256']and p.stat().st_size==q.stat().st_size==row['bytes']
assert len(baseline['inheritedProjectInputs'])==225 and len(baseline['fixtureInputs'])==3972
reviewed=['All 225 source02 project files unchanged. Adds one pure test and the exact 3972 retained source01 group/setup files, each rehashed against the acquired original. No producer rerun, SQL, state mutation or identity rebinding.',
 'Test uses separately retained pre-run source01 setup. Corrected source02 reader must inspect all 30 captured cases, then reject rehashed false accounting, unreported files, a forged nominal report and a changed trusted authority revision. File, SQL and clock calls forbidden during reading; fixture bytes rehashed unchanged.',
 'This proves retrospective complete-history inspection only. Source02 fresh GPIO/PWM remain failed deadline attempts. No current capture/qualification/physical/run-attestation success is inferred from historical evidence.',
 'Original 180s parent, 16MiB scratch, 8192 files, 256MiB inputs, 16MiB file, 4MiB JSON and 8MiB log bounds unchanged. Project count increases only for explicit immutable fixture acquisition. No physical/MCU, inference, external controllers, live HMS or adjacent Harness execution.']
write(S/'source-review.json',dict(scope='Primary-agent complete retained-data test and fixture provenance reviewed before execution.',unchangedInheritedFiles=225,newTestFiles=['tests/test_pat_io_group_retained.py'],fixtureFiles=3972,reviewed=reviewed,independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Corrected reader on the retained complete group\n\n[Design](../DESIGN.md), [correction](../CORRECTION.md), [review](source-review.json).\nAll source02 production code is unchanged. This is historical inspection only.\n')
rows=inventory(S,True);assert len(rows)==4201;write(S/'index.json',dict(scope='Unchanged source02 reader plus bounded complete source01 fixture and one pure test.',files=rows));pin=sha(S/'index.json')
old=B/'harness07';h=B/'harness10';h.mkdir();(h/'references').mkdir()
for row in read(old/'index.json')['files']:assert sha(old/row['path'])==row['sha256']
targets=['test_pat_io_group_retained.RetainedIoGroupTests.test_complete_retained_gpio_and_archive_adversaries'];prior=read(old/'targets.json')
write(h/'targets.json',dict(testCount=1,targets=targets));borrow=[]
for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
 p=old/name;q=h/'references'/p.name;shutil.copyfile(p,q);borrow.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(h).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
write(h/'borrowed-inputs.json',borrow)
for name in ('run_attempt.py','attempt_child.py'):
 before=(old/name).read_text();after=before.replace(baseline['sourceIndexSha256'],pin).replace('implementation02','implementation03')
 after=re.sub(r'\b228\b','4201',after);after=re.sub(r'\b225\b','4198',after);after=re.sub(r'\b106\b','1',after)
 after=after.replace('IoGroupHistory106','RetainedIoGroup1').replace('history106','retained1')
 if name=='run_attempt.py':assert after.count(repr(prior['targets']))==1;after=after.replace(repr(prior['targets']),repr(targets))
 ast.parse(after);(h/name).write_text(after);(h/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(old/name).relative_to(ROOT).as_posix(),tofile=(h/name).relative_to(ROOT).as_posix())))
(h/'SCOPE.md').write_text('''# Exact pure retained-history execution scope

Only the named pure method in targets.json. All retained database files are
immutable input bytes; no SQLite connection or runtime opening is allowed.
No network, subprocess, physical/MCU, inference or live-service execution.
Original 180s parent, 16MiB scratch, 8192 files, 256MiB inputs, 16MiB file, 4MiB
JSON and 8MiB logs remain. Preserve all failures, input originals and raw output.
''')
(h/'README.md').write_text('# Retained complete-history validation\n\n[Targets](targets.json), [scope](SCOPE.md), [review](review.json).\n')
write(h/'review.json',dict(scope='Complete pure test, 3972 pinned fixture inputs and launcher acquisition count changes reviewed.',tests=1,sourceIndexSha256=pin,targetSha256=sha(h/'targets.json'),reviewed=reviewed,independentReview=False,releasedBy='primary-agent'))
write(h/'index.json',dict(scope='Original bounded pure harness with explicit complete historical input.',files=inventory(h)))
before=(B/'acquire.py').read_text();after=before.replace("A/'project',225","A/'project',4198").replace('ROOT,228','ROOT,4201').replace('sourceFilesVerified=225,frozenFilesVerified=228','sourceFilesVerified=4198,frozenFilesVerified=4201')
ast.parse(after);(B/'acquire-retained.py').write_text(after)
print(json.dumps(dict(projectFiles=4198,frozenFiles=4201,sourceIndexSha256=pin,harnessIndexSha256=sha(h/'index.json'),targetsSha256=sha(h/'targets.json'))))
