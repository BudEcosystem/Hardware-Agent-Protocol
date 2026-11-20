"""Freeze reviewed clock capture source and prepare exact bounded selections."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path.cwd().resolve();BASE=ROOT/'artifacts/implementation/pat-io-clock-challenges';SOURCE=BASE/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-timing-challenges/harness03'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
    with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
old_project=ROOT/'artifacts/implementation/pat-io-timing-challenges/implementation02/project'
baseline=read(SOURCE/'baseline-inputs.json')['inheritedProjectInputs'];assert len(baseline)==7070
changed={'hms/pat_io_trials.py','hms/pat_io_configuration_capture.py','hms/pat_io_transcript.py'}
actual_changed=set()
for row in baseline:
    relative=(ROOT/row['path']).relative_to(old_project);p=SOURCE/'project'/relative
    if p.stat().st_size!=row['bytes'] or sha(p)!=row['sha256']:actual_changed.add(relative.as_posix())
assert actual_changed==changed
write(SOURCE/'source-review.json',dict(scope='Primary-agent source, phase grammar and actual runtime path review before execution.',
    inheritedInputsUnchanged=7067,changedFiles=sorted(changed),
    newFiles=['hms/pat_io_clock_capture.py','hms/pat_io_clock_history.py','tests/test_pat_io_clock_challenges.py'],
    reviewed=['Default clock hooks preserve previous profiles; new0.3 profile is opt-in and mutually exclusive with conflict0.2.',
        'Complete combined matrix is regenerated before runtime construction. No arbitrary callback or control list is accepted.',
        'Guard delay occurs after original dispatch reservation and before original board.begin; provider and authority business logic stay unchanged.',
        'Wall and monotonic fault sources are separate. A restored monotonic source does not clear the failed Registry latch.',
        'Clock failures retain active output and claims until new-owner reopen and exact reconciliation. Original request, receipt, namespace, floors and suffix identity remain.',
        'Pure grammar/configuration structure and exact clock/call schedule checks make no full-history, independent-outcome or qualification claim.',
        'Six runtime cases plus pre-runtime refusal, rehashed control/case attacks, old-profile refusal and purity assertions; unchanged39 transcript and4 configured runtime regressions.',
        'Original timing, file, SQL-path, import and raw-retention boundaries remain unchanged. No production integration or physical execution.'],
    projectExecutionDuringPreparation=False,independentReview=False,releasedBy='primary-agent'))
(SOURCE/'README.md').write_text('# Recorded guard delay and clock-fault candidate\n\nThe [design](../DESIGN.md) adds exact clock controls and separate wall/monotonic\nrecording for the three required guard/clock challenges. Runtime/provider/compiler\nbusiness logic and all old tests/data are unchanged. See [source review](source-review.json).\nFull semantic clock-fault composition and qualification remain unfinished.\n')
rows=[]
for p in sorted(SOURCE.rglob('*')):
    assert not p.is_symlink()
    if p.is_file():
        if p.suffix=='.py':ast.parse(p.read_bytes())
        rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==7076
write(SOURCE/'index.json',dict(scope='Frozen original clock-capture candidate; no qualification or production integration.',files=rows));pin=sha(SOURCE/'index.json')
assert sha(OLD/'index.json')=='53d8141865899203d4562f52ad2f299b424764cf9d9394c8889dc6cc2238a729'
for row in read(OLD/'index.json')['files']:
    p=OLD/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
tree=ast.parse((SOURCE/'project/tests/test_pat_io_clock_challenges.py').read_bytes())
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='IoClockChallengeTests')
new=sorted('test_pat_io_clock_challenges.IoClockChallengeTests.'+n.name for n in cls.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'));assert len(new)==7
transcript=[n for n in read(ROOT/'artifacts/implementation/pat-io-conflict-history/harness02/targets.json')['targets'] if n.startswith('test_pat_io_transcript.')];assert len(transcript)==39
legacy=read(ROOT/'artifacts/implementation/pat-io-conflict-history/harness03/targets.json')['targets'];assert len(legacy)==4
for name,count,targets,sql_prefix in [('harness01',46,sorted(new+transcript),'test_pat_io_clock_challenges.IoClockChallengeTests.'),
                                    ('harness02',4,legacy,'test_pat_io_configuration_capture.IoConfigurationCaptureTests.')]:
    H=BASE/name;H.mkdir(exist_ok=False);(H/'references').mkdir();borrowed=[]
    for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
        p=OLD/item;relative='references/'+('timing9-'if'/'not in item else'')+p.name
        shutil.copyfile(p,H/relative);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=relative,bytes=p.stat().st_size,sha256=sha(p)))
    write(H/'borrowed-inputs.json',borrowed);write(H/'targets.json',dict(testCount=count,targets=targets))
    for item in ['run_attempt.py','attempt_child.py']:
        before=(OLD/item).read_text();after=before.replace('TimingChallenges9','ClockChallenges'+str(count)).replace('timing9','clock'+str(count))
        after=after.replace('io-timing-challenges','io-clock-challenges').replace('implementation02','implementation01')
        after=after.replace('6a7531015ffe1e5a758e7cbe27d94f54a6a9134e8e423d14e40b45154a7e46a0',pin)
        after=after.replace('7073','7076').replace('7070','7073').replace('!= 9','!= '+str(count)).replace('== 9','== '+str(count)).replace("'expectedTests': 9","'expectedTests': "+str(count))
        if item=='run_attempt.py':
            start=after.index("                sum(name.startswith('test_pat_io_timing_challenges")
            end=after.index(":\n            raise ValueError('Closed",start)
            selection=("                sum(name.startswith('test_pat_io_clock_challenges.IoClockChallengeTests.') for name in targets['targets']) != 7 or\n                sum(name.startswith('test_pat_io_transcript.') for name in targets['targets']) != 39)" if count==46 else
                "                sum(name.startswith('test_pat_io_configuration_capture.IoConfigurationCaptureTests.') for name in targets['targets']) != 4)")
            after=after[:start]+selection+after[end:]
            after=after.replace('Eight original GPIO timing cases and one pre-runtime refusal method',
                'Six original clock runtime cases, one pre-runtime refusal and39 unchanged transcript methods' if count==46 else 'Four unchanged configured runtime regression methods')
        else:after=after.replace('test_pat_io_timing_challenges.GpioTimingChallengeTests.',sql_prefix)
        ast.parse(after);(H/item).write_text(after)
        (H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(OLD/item).relative_to(ROOT).as_posix(),tofile=(H/item).relative_to(ROOT).as_posix())))
    (H/'README.md').write_text('# Isolated clock '+str(count)+' selection\n\nUse the [exact methods](targets.json) from the [frozen source](../implementation01/README.md).\nSee [scope](SCOPE.md). Full diff review/release precedes execution.\n')
    (H/'SCOPE.md').write_text('# Original execution boundaries\n\n'+('Six new private SQLite clock cases plus one pre-runtime refusal and39 unchanged\npure transcript methods.' if count==46 else 'Four unchanged configured private SQLite runtime regression methods.')+'\nKeep the original 180-second deadline, 16 MiB scratch, 8,192 inventory files,\n256 MiB input, 16 MiB file, 4 MiB JSON and 8 MiB log ceilings. Only exact\nselected trial-0/state authority/board databases may connect. Preserve originals,\npartial output and failures. No network/subprocesses, physical devices, MCU/emulator,\ninference or live services. Primary-agent review; helpers remain usage-limited.\nFull semantic clock-fault composition and qualification remain unfinished.\n')
    print(json.dumps(dict(harness=name,tests=count,targetSha256=sha(H/'targets.json'))))
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=7073,frozenFiles=7076)))
