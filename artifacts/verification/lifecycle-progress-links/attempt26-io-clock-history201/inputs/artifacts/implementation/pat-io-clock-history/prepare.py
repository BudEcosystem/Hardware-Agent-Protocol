"""Freeze the reviewed pure-clock candidate and exact bounded test selections."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd().resolve();BASE=ROOT/'artifacts/implementation/pat-io-clock-history';SOURCE=BASE/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-clock-challenges/harness01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
old_project=ROOT/'artifacts/implementation/pat-io-clock-challenges/implementation01/project'
changed={'hms/pat_io_board_history.py','hms/pat_io_operation_history.py','hms/pat_io_configuration_history.py','hms/pat_io_observation_history.py','hms/pat_io_authorized_history.py'}
actual=set();baseline=read(SOURCE/'baseline-inputs.json')['inheritedProjectInputs'];assert len(baseline)==7073
for row in baseline:
 p=ROOT/row['path'];relative=p.relative_to(old_project);q=SOURCE/'project'/relative
 assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 if q.stat().st_size!=row['bytes'] or sha(q)!=row['sha256']:actual.add(relative.as_posix())
assert actual==changed
write(SOURCE/'source-review.json',dict(scope='Primary-agent pre-execution semantic, source and test review.',
 inheritedInputsUnchanged=7068,changedFiles=sorted(changed),newCode=['hms/pat_io_clock_semantics.py','tests/test_pat_io_clock_semantics.py'],
 acquiredFixtureFiles=947,reviewed=[
 'Actual original board start guard excludes due equality against the original reserved run origin.',
 'Wall source regression is below the retained ledger floor. Registry monotonic regression latches until new runtime owner.',
 'Exact no-write failed phases compare all29 execution and15 configuration tables and resolver to the last good pending state.',
 'Exact private exceptions preserve event-local clocks and cached observation timestamps, with consumption checks.',
 'Board no-start still validates nil timestamps and all resource, ownership, fence and effect histories.',
 'Authority no-start resets may_have_acted only with derived receipt evidence; historical receipt references remain exact.',
 'Reopen holds original authority claims and identities until normal reconciliation; parent fold independently refuses resume and derives cancellation.',
 'Full static/correspondence/configuration/refusal/guard/board/operation/procedure/sample/outcome composition precedes expectedResponseVerified.',
 'No producer/runtime/provider/compiler business logic or old fixtures/tests changed; no current qualification/attestation/physical claim.',
 'Six positive captures, coherently rehashed semantic counterexamples, default refusal, unused-context and no-I/O tests.',
 'Original180s,16MiBscratch,8192files,256MiBinputs,4MiBJSON,8MiBlog bounds preserved; every SQLite connection is denied.'
 ],projectExecutionDuringPreparation=False,independentReview=False,releasedBy='primary-agent'))
(SOURCE/'README.md').write_text('# Pure clock-history candidate\n\nSee the [design](../DESIGN.md) and [source review](source-review.json).\nThis candidate composes complete histories for three exact clock challenges over\nsix sealed original captures. No runtime/provider execution or live integration.\nQualification and the broader system remain incomplete.\n')
rows=[]
for p in sorted(SOURCE.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():
  if p.suffix=='.py':ast.parse(p.read_bytes())
  rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==8025,len(rows)
write(SOURCE/'index.json',dict(scope='Frozen pure clock semantic candidate and original data, not qualification.',files=rows));pin=sha(SOURCE/'index.json')
assert sha(OLD/'index.json')=='c7de4e6813e4193ae0567ddc70e7a60921aecf820ef6f9ae3aada891a3f71013'
for row in read(OLD/'index.json')['files']:
 p=OLD/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
def methods(name):
 tree=ast.parse((SOURCE/'project/tests'/('test_pat_io_'+name+'.py')).read_bytes());out=[]
 for c in tree.body:
  if isinstance(c,ast.ClassDef):out += ['test_pat_io_'+name+'.'+c.name+'.'+n.name for n in c.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
 return sorted(out)
groups=[('harness01',['clock_semantics'],33),('harness02',['board_history','operation_history'],73),
        ('harness03',['configuration_history','observation_history'],75),('harness04',['authorized_history'],20)]
for name,modules,count in groups:
 targets=sorted(t for mod in modules for t in methods(mod));assert len(targets)==count
 H=BASE/name;H.mkdir();(H/'references').mkdir();borrowed=[]
 for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
  p=OLD/item;relative='references/'+('clock46-' if '/' not in item else '')+p.name
  shutil.copyfile(p,H/relative);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=relative,bytes=p.stat().st_size,sha256=sha(p)))
 write(H/'borrowed-inputs.json',borrowed);write(H/'targets.json',dict(testCount=count,targets=targets))
 for item in ['run_attempt.py','attempt_child.py']:
  before=(OLD/item).read_text();after=before.replace('ClockChallenges46','ClockHistory'+str(count)).replace('clock46','clock'+str(count))
  after=after.replace('io-clock-challenges','io-clock-history').replace('83df5455e2a0ecd21ccc2c9aeb42ffbcc80ba6f7dd2483ff4cb4ba44ad087f40',pin)
  after=after.replace('7076','8025').replace('7073','8022').replace('!= 46','!= '+str(count)).replace('== 46','== '+str(count)).replace("'expectedTests': 46","'expectedTests': "+str(count))
  if item=='run_attempt.py':
   a=after.index("                sum(name.startswith('test_pat_io_clock_challenges")
   b=after.index(":\n            raise ValueError('Closed",a)
   checks=['                sum(name.startswith('+repr('test_pat_io_'+mod+'.')+') for name in targets[\'targets\']) != '+str(len(methods(mod))) for mod in modules]
   after=after[:a]+' or\n'.join(checks)+')'+after[b:]
   after=after.replace('Six original clock runtime cases, one pre-runtime refusal and39 unchanged transcript methods','Exact pure semantic/history methods; SQLite is forbidden')
  else:
   a=after.index("        raw = os.fsdecode(os.fspath(args[0])); path = Path(raw).resolve()")
   b=after.index("    if event == 'exec':",a)
   after=after[:a]+"        prohibited.append('sqlite3.connect:forbidden')\n        raise RuntimeError('Pure clock history selection forbids every SQLite connection')\n"+after[b:]
  ast.parse(after);(H/item).write_text(after)
  (H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(OLD/item).relative_to(ROOT).as_posix(),tofile=(H/item).relative_to(ROOT).as_posix())))
 (H/'README.md').write_text('# Pure clock/history selection\n\nExact [methods](targets.json), [scope](SCOPE.md) and [frozen source](../implementation01/README.md).\nPrimary-agent diff review and release precede execution.\n')
 (H/'SCOPE.md').write_text('# Original bounded pure execution\n\nOnly '+str(count)+' exact pure data-inspection tests execute. Every SQLite connection is forbidden.\nKeep180 seconds,16 MiB scratch,8192files,256 MiB input,16 MiB file,4 MiB JSON\nand8 MiB log ceilings. Preserve original raw outputs and failures. No network,\nsubprocesses, physical ports, MCU/emulator, inference or live service.\nNo independent agent review or qualification claim.\n')
 print(json.dumps(dict(harness=name,tests=count,targetSha256=sha(H/'targets.json'))))
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=8022,frozenFiles=8025)))
