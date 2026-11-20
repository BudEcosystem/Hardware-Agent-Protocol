"""Freeze complete group inspection and exact original bounded harnesses."""
import ast,difflib,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-group-history';S=B/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-encoding'
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
baseline=read(S/'baseline-inputs.json');assert sha(OLD/'implementation01/index.json')==baseline['sourceIndexSha256']
assert len(baseline['inheritedProjectInputs'])==222
for row in baseline['inheritedProjectInputs']:
 p=ROOT/row['path'];q=S/'project'/p.relative_to(OLD/'implementation01/project')
 assert sha(p)==sha(q)==row['sha256']and p.stat().st_size==q.stat().st_size==row['bytes']
reviewed=[
 'Two new production modules only; all 222 inherited files unchanged. Trusted setup uses complete original matrix validation and explicit initial authority. It constructs all per-case setup/fault/change inputs before release, with one bounded carrier per case.',
 'Independent reader imports semantic readers, not worker/planner/compiler/runtime/setup. Closed canonical archive, explicit trusted inputs, exact case ordering, full required challenge inventory, source/compiler matching, exact record/state closure and recomputed counters precede any group success result.',
 'All 25 fixed challenges call existing complete semantic inspectors. Nominal candidate composes original replay/conflict history with independent static/outcome reconstruction and exact domain input. Negative cases independently evaluate declared parameters/context. Expected fault cancellation remains distinct from nominal completion.',
 'State files are inventoried and layout-checked, not interpreted as physical authority. Current-source identity matching is not attestation. Run association, wall deadline, hard aggregate storage, physical measurements and qualification remain false.',
 'Nine pure setup/reader-boundary tests plus two complete fresh original groups. Setup is retained before capture; full original group assertions remain. Reader runs with file/SQL/clock calls forbidden; exact inspector dispatch counts and early forged-archive refusals are checked.',
 'Original 60s capture, 180s parent, 16MiB raw scratch, 8192 files, 256MiB inputs, 16MiB file, 4MiB JSON and 8MiB log limits unchanged. No physical/MCU, inference, external controllers, live HMS or adjacent Harness execution.',
]
write(S/'source-review.json',dict(scope='Primary-agent complete new source and tests reviewed before execution.',
 newFiles=['hms/pat_io_group_setup.py','hms/pat_io_group_history.py','tests/test_pat_io_group_history.py'],unchangedInheritedFiles=222,
 reviewed=reviewed,independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Complete finite I/O group history candidate\n\n[Design](../DESIGN.md) and [source review](source-review.json).\nTrusted setup and independent archive inspection remain separate.\n')
rows=inventory(S,True);assert len(rows)==228
write(S/'index.json',dict(scope='Frozen trusted setup and independent complete group composition candidate.',files=rows));pin=sha(S/'index.json')
tree=ast.parse((S/'project/tests/test_pat_io_group_history.py').read_bytes())
def methods(cls):
 body=next(n.body for n in tree.body if isinstance(n,ast.ClassDef)and n.name==cls)
 return sorted('test_pat_io_group_history.'+cls+'.'+n.name for n in body if isinstance(n,ast.FunctionDef)and n.name.startswith('test_'))
pure=read(OLD/'harness05/targets.json')['targets']+methods('IoGroupSetupTests');actual=methods('IoGroupHistoryTests')
assert len(pure)==105 and len(actual)==2
for i,(origin,targets)in enumerate(((5,pure),(3,[actual[0]]),(4,[actual[1]])),1):
 old=OLD/('harness%02d'%origin);h=B/('harness%02d'%i);h.mkdir();(h/'references').mkdir()
 for row in read(old/'index.json')['files']:assert sha(old/row['path'])==row['sha256']
 borrowed=[]
 for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
  p=old/name;q=h/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(h).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(h/'borrowed-inputs.json',borrowed);prior=read(old/'targets.json');write(h/'targets.json',dict(testCount=len(targets),targets=targets))
 for name in ('run_attempt.py','attempt_child.py'):
  before=(old/name).read_text();after=before.replace(baseline['sourceIndexSha256'],pin).replace('pat-io-encoding','pat-io-group-history').replace('hms-io-encoding-','hms-io-group-history-')
  after=re.sub(r'\b225\b','228',after);after=re.sub(r'\b222\b','225',after)
  if name=='run_attempt.py':assert after.count(repr(prior['targets']))==1;after=after.replace(repr(prior['targets']),repr(targets))
  if i==1:after=re.sub(r'\b96\b','105',after).replace('IoEncoding96','IoGroupHistory105').replace('encoding96','history105')
  if i!=1 and name=='attempt_child.py':
   original_ids=['test_pat_io_group_worker.IoGroupWorkerTests.test_complete_gpio_group','test_pat_io_group_worker.IoGroupWorkerTests.test_complete_pwm_group','test_pat_io_group_worker.IoGroupWorkerTests.test_record_limit_retains_partial_attempt_and_stops_later_cases']
   assert after.count(repr(original_ids))==1;after=after.replace(repr(original_ids),repr(actual))
  ast.parse(after);(h/name).write_text(after)
  (h/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(old/name).relative_to(ROOT).as_posix(),tofile=(h/name).relative_to(ROOT).as_posix())))
 (h/'SCOPE.md').write_text('''# Original bounded complete-history validation scope

Only exact named methods in targets.json. Actual SQL is allowed solely for the
two named complete-history methods at their own group/case-00..29/state authority
and synthetic-board files. The pure selection makes no SQL calls. Network,
subprocess, physical/MCU, inference and live-service execution remain forbidden.
Original 180s parent, 16MiB scratch, 8192 files, 256MiB inputs, 16MiB file, 4MiB
JSON and 8MiB log bounds remain. Original capture limits are unchanged. Preserve
all failure evidence, original raw scratch and complete acquired copies.
''')
 (h/'README.md').write_text('# Exact complete-history selection\n\n[Targets](targets.json), [scope](SCOPE.md), [review](review.json).\n')
 write(h/'review.json',dict(scope='Complete new modules, tests, launcher/acquirer deltas and exact SQL scope reviewed before execution.',tests=len(targets),sourceIndexSha256=pin,targetSha256=sha(h/'targets.json'),reviewed=reviewed,independentReview=False,releasedBy='primary-agent'))
 write(h/'index.json',dict(scope='Frozen original bounded current-group history harness.',files=inventory(h)))
 parsed=ast.parse((h/'run_attempt.py').read_bytes());lists=[ast.literal_eval(n)for n in ast.walk(parsed)if isinstance(n,ast.List)and n.elts and all(isinstance(e,ast.Constant)and isinstance(e.value,str)for e in n.elts)]
 assert targets in lists
 print(json.dumps(dict(harness=h.name,tests=len(targets),indexSha256=sha(h/'index.json'))))
before=(OLD/'acquire.py').read_text();after=before.replace('pat-io-encoding','pat-io-group-history').replace("A/'project',222","A/'project',225").replace('ROOT,225','ROOT,228').replace('sourceFilesVerified=222,frozenFilesVerified=225','sourceFilesVerified=225,frozenFilesVerified=228')
after=after.replace("c['testId'].startswith('test_pat_io_group_worker.IoGroupWorkerTests.')","c['testId']in "+repr(actual))
ast.parse(after);(B/'acquire.py').write_text(after);(B/'acquire.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(OLD/'acquire.py').relative_to(ROOT).as_posix(),tofile=(B/'acquire.py').relative_to(ROOT).as_posix())))
for name in ('audit-states.py','audit-storage.py'):
 (B/name).write_text((OLD/name).read_text().replace('pat-io-encoding','pat-io-group-history'))
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=225,frozenFiles=228)))
