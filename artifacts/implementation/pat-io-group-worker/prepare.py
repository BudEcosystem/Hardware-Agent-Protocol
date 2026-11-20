"""Freeze the group coordinator and four exact bounded selections; stdlib only."""
import ast,difflib,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path.cwd().resolve();B=ROOT/'artifacts/implementation/pat-io-group-worker';S=B/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-compiler-identity/implementation01/project'
O=ROOT/'artifacts/implementation/pat-io-lifecycle-challenges/harness01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
changed=set('pat_io_trials pat_io_configuration_capture pat_io_resource_capture pat_io_authority_capture pat_io_clock_capture pat_io_lifecycle_capture pat_io_timing_worker'.split())
base=read(S/'baseline-inputs.json');assert len(base['inheritedProjectInputs'])==214
for row in base['inheritedProjectInputs']:
 p=ROOT/row['path'];rel=p.relative_to(OLD);q=S/'project'/rel
 assert sha(p)==row['sha256'] and p.stat().st_size==row['bytes']
 assert (sha(q)!=sha(p))is(rel.parent.as_posix()=='hms' and rel.stem in changed)
write(S/'source-review.json',dict(scope='Primary-agent full seven inherited changes, two new production modules and14 test methods reviewed before execution.',
 changedFiles=sorted('hms/'+n+'.py'for n in changed),newFiles=['hms/pat_io_group_budget.py','hms/pat_io_group_worker.py','tests/test_pat_io_group_worker.py'],
 inheritedFiles=214,unchangedInheritedFiles=207,
 reviewed=['Current exact matrix0.3, all25 fixed scenarios and typed candidate cases; no caller-selected cases, retries or replacement keys.',
 'Seven capture/engine changes only forward optional trusted ticket and charge existing record/configuration/admission/tick boundaries. Standalone behavior is retained when absent.',
 'One ticket per declared case and engine; exact program digest, source identity before/after, count checks, conservative child reservations, combined evidence charging and original wall origin.',
 'Pre-reserved bounded terminal receipt can record deadline/record failure; failed writes are not refunded. State remains and later cases cannot start after failure.',
 'Closed state sizes enter derived accounting, but this does not impose an OS quota or hard deadline on SQLite/WAL calls. All full attestation/outcome/qualification flags remain false.',
 '14 methods in four disjoint runs:9 ledger boundaries+2 pre-runtime refusals,complete GPIO,complete PWM,reduced-record partial attempt. Full groups are attempted under unchanged ceilings.',
 'All inherited provider/compiler/fold/source modules except the seven explicit capture boundaries are byte-identical. No live HMS/Harness, physical/MCU/inference/service execution.'],
 independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Shared I/O group capture candidate\n\nSee [design](../DESIGN.md) and [source review](source-review.json).\nThe coordinator attempts all exact current matrix cases under one shared ledger.\nIndependent group outcomes, full attestation and actual filesystem quotas remain\nunfinished; a captured group is not a qualified PAT.\n')
rows=[]
for p in sorted(S.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():
  if p.suffix=='.py':ast.parse(p.read_bytes())
  rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==220;write(S/'index.json',dict(scope='Frozen original current-group capture coordinator and shared-budget hooks.',files=rows));pin=sha(S/'index.json')
assert sha(O/'index.json')=='944ccf800e93760ee6d9c23b5e9303ab01219ff0be599b2ce281f9c667f7fbd6'
for row in read(O/'index.json')['files']:assert sha(O/row['path'])==row['sha256']and(O/row['path']).stat().st_size==row['bytes']
module='test_pat_io_group_worker';tree=ast.parse((S/'project/tests'/(module+'.py')).read_bytes());classes={n.name:n for n in tree.body if isinstance(n,ast.ClassDef)}
pure=sorted(module+'.IoGroupBudgetTests.'+f.name for f in classes['IoGroupBudgetTests'].body if isinstance(f,ast.FunctionDef)and f.name.startswith('test_'))
prefix=module+'.IoGroupWorkerTests.'
pure += [prefix+'test_changed_implementation_refuses_before_group_output',prefix+'test_parameterized_matrix_refuses_before_runtime_or_output']
assert len(pure)==11
selections=[pure,[prefix+'test_complete_gpio_group'],[prefix+'test_complete_pwm_group'],[prefix+'test_record_limit_retains_partial_attempt_and_stops_later_cases']]
for i,targets in enumerate(selections,1):
 H=B/('harness%02d'%i);H.mkdir();(H/'references').mkdir();borrowed=[]
 for name in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
  p=O/name;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(H/'borrowed-inputs.json',borrowed);write(H/'targets.json',dict(testCount=len(targets),targets=targets))
 for name in ['run_attempt.py','attempt_child.py']:
  before=(O/name).read_text();after=before.replace('0a3360ba3a6e9ee0fd5c9db8d8a38ef64761b9bda69969fae42264e4556c2e87',pin)
  after=after.replace('io-lifecycle-challenges','io-group-worker').replace('8104','220').replace('8101','217')
  after=after.replace('LifecycleChallenge6','IoGroup'+str(len(targets))).replace('lifecycle6','group'+str(len(targets)))
  after=after.replace('!= 6','!= '+str(len(targets))).replace('== 6','== '+str(len(targets))).replace("'expectedTests': 6","'expectedTests': "+str(len(targets)))
  after=after.replace("compiler's five-package identity","compiler's seven-package identity")
  after=after.replace('Five original fixed lifecycle cases, one pre-runtime refusal','Exact current group/budget selection')
  if name=='run_attempt.py':
   after=re.sub(r"targets\['targets'\] != \[.*\]\):", "targets['targets'] != "+repr(targets)+'):',after)
  else:
   after=after.replace("current_test.startswith('test_pat_io_lifecycle_challenges.IoLifecycleChallengeTests.')", "current_test in "+repr([prefix+'test_complete_gpio_group',prefix+'test_complete_pwm_group',prefix+'test_record_limit_retains_partial_attempt_and_stops_later_cases']))
   after=after.replace("len(parts) == 4", "len(parts) == 5")
   after=after.replace("parts[1:3] == ('trial-0', 'state') and (parts[3] == 'authority.db' or", "parts[1] == 'group' and re.fullmatch(r'case-[0-2][0-9]',parts[2]) is not None and parts[3] == 'state' and (parts[4] == 'authority.db' or")
   after=after.replace("parts[3]) is not None", "parts[4]) is not None")
  ast.parse(after);(H/name).write_text(after)
  (H/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(O/name).relative_to(ROOT).as_posix(),tofile=(H/name).relative_to(ROOT).as_posix())))
 (H/'README.md').write_text('# Exact group capture selection\n\n[Targets](targets.json), [candidate](../implementation01/README.md), [scope](SCOPE.md).\nComplete source and launcher/child deltas are reviewed before execution.\n')
 (H/'SCOPE.md').write_text('# Original bounded private execution scope\n\nOnly selected original synthetic group/budget tests. SQL is allowed solely for\nthe three named actual group methods at their own group/case-00..29/state stores.\nEvery other SQL path, network and subprocess is forbidden. No physical/MCU,\ninference or live-service execution. Original180s harness,16MiB scratch,8192 files,\n256MiB inputs,16MiB file,4MiB JSON and8MiB log limits remain. Original group60s,\n32cases,512children,2048ticks,4096records,16MiB producer,64KiB docs and20MiB\nderived limits remain. Preserve failures, all originals and raw scratch.\n')
 print(json.dumps(dict(harness=H.name,tests=len(targets),targetSha256=sha(H/'targets.json'))))
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=217,frozenFiles=220)))
