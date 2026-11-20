"""Freeze timing worker/independent checker and prepare two bounded selections."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path.cwd().resolve();BASE=ROOT/'artifacts/implementation/pat-io-timing-challenges';SOURCE=BASE/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-conflict-history/harness02'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
    with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
old_project=ROOT/'artifacts/implementation/pat-io-conflict-history/implementation01/project'
baseline=read(SOURCE/'baseline-inputs.json')['inheritedProjectInputs'];assert len(baseline)==7067
for row in baseline:
    p=SOURCE/'project'/(ROOT/row['path']).relative_to(old_project)
    assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
write(SOURCE/'source-review.json',dict(scope='Primary-agent complete source/test review before original simulation execution.',
    inheritedInputsUnchanged=7067,newFiles=['hms/pat_io_timing_worker.py','hms/pat_io_timing_history.py','tests/test_pat_io_timing_challenges.py'],
    reviewed=['Full supplied combined matrix is regenerated before runtime construction; only exact known case identities can execute.',
      'Eight forward-time scenarios use explicit adapter/procedure phases; no finish() substitutes a nominal schedule.',
      'Independent fixed program, case identity, named requirements, calls, clock advances, complete histories and expected effects are reconstructed.',
      'Late parent reporting preserves historical completed cycles while failing nominal timing; fault-response success differs from PAT completion.',
      'Before-start and lease equality prove no handoff and retained authority floors; wall/run stops prove precedence and idle settlement.',
      'Both GPIO and PWM run all eight scenarios. Invalid/unsupported plans refuse before constructing runtime; false named coverage and rehashed expectations refuse.',
      'Manifest serialization also consumes original record/byte allowance. Group execution, guard delay, clock faults, source attestation and qualification remain incomplete.'],
    independentReview=False,projectExecutionDuringPreparation=False,releasedBy='primary-agent'))
(SOURCE/'README.md').write_text('# Exact forward-time challenge worker and checker\n\nThis isolated candidate adds eight fixed timing schedules from the validated\ncombined matrix and an independent expected-response checker. Both installed\nGPIO/PWM primitives are exercised. All 7,067 inherited files remain unchanged.\nSee [source review](source-review.json). Group qualification, in-phase guard\ndelay, clock faults, physical providers and hub control remain unfinished.\n')
rows=[]
for p in sorted(SOURCE.rglob('*')):
    assert not p.is_symlink()
    if p.is_file():
        if p.suffix=='.py':ast.parse(p.read_bytes())
        rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==7073
write(SOURCE/'index.json',dict(scope='Frozen timing worker/checker candidate; all 7067 inherited project inputs unchanged.',files=rows))
pin=sha(SOURCE/'index.json')
assert sha(OLD/'index.json')=='4b717fa60a5a9592de1ee6e952c4ffb8c38c34e5579ff881d0e74d93b74cfc1a'
for row in read(OLD/'index.json')['files']:
    p=OLD/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
tree=ast.parse((SOURCE/'project/tests/test_pat_io_timing_challenges.py').read_bytes())
classes={n.name:n for n in tree.body if isinstance(n,ast.ClassDef)}
base=[n.name for n in classes['_TimingCases'].body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')];assert len(base)==8
for name,cls,count in [('harness01','GpioTimingChallengeTests',9),('harness02','PwmTimingChallengeTests',8)]:
    H=BASE/name;H.mkdir(exist_ok=False);(H/'references').mkdir();borrowed=[]
    for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
        p=OLD/item;relative='references/'+('conflict48-'if'/'not in item else'')+p.name
        shutil.copyfile(p,H/relative);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=relative,bytes=p.stat().st_size,sha256=sha(p)))
    write(H/'borrowed-inputs.json',borrowed)
    own=[n.name for n in classes[cls].body if isinstance(n,ast.FunctionDef)and n.name.startswith('test_')]
    targets=sorted('test_pat_io_timing_challenges.'+cls+'.'+n for n in base+own);assert len(targets)==count
    write(H/'targets.json',dict(testCount=count,targets=targets))
    for item in ['run_attempt.py','attempt_child.py']:
        before=(OLD/item).read_text();after=before.replace('ConflictHistory48','TimingChallenges'+str(count)).replace('conflict48','timing'+str(count))
        after=after.replace('io-conflict-history','io-timing-challenges').replace('eccd20743c61cb37d73c3f2f0df770d4c0b7529132287426eac7b8921875c524',pin)
        after=after.replace('7070','7073').replace('7067','7070').replace('!= 48','!= '+str(count)).replace('== 48','== '+str(count)).replace("'expectedTests': 48","'expectedTests': "+str(count))
        if item=='run_attempt.py':
            start=after.index("                sum(name.startswith('test_pat_io_transcript")
            end=after.index(":\n            raise ValueError('Closed",start)
            after=after[:start]+"                sum(name.startswith('test_pat_io_timing_challenges."+cls+".') for name in targets['targets']) != "+str(count)+")"+after[end:]
            after=after.replace('Nine original conflict runtime cases and39 inherited pure transcript tests','Eight original '+('GPIO timing cases and one pre-runtime refusal method'if count==9 else'PWM timing cases'))
        else:
            after=after.replace("current_test.startswith(('test_pat_io_conflict_history.', 'test_pat_io_configuration_capture.'))", "current_test.startswith('test_pat_io_timing_challenges."+cls+".')")
        ast.parse(after);(H/item).write_text(after)
        (H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(OLD/item).relative_to(ROOT).as_posix(),tofile=(H/item).relative_to(ROOT).as_posix())))
    (H/'README.md').write_text('# Isolated '+cls+' selection\n\nRun the [exact '+str(count)+' methods](targets.json) from the\n[frozen source](../implementation01/README.md). See [scope](SCOPE.md).\nParent startup uses python3 -B; child remains -I -S -B.\n')
    (H/'SCOPE.md').write_text('# Original timing verification scope\n\nEight original private SQLite runtime cases for one installed primitive execute.\n'+('One additional GPIO method checks invalid plans without runtime construction.\n'if count==9 else'')+'Keep the original 180-second deadline, 16 MiB scratch, 8,192 inventory files,\n256 MiB input, 16 MiB file, 4 MiB JSON and 8 MiB log limits. Only the selected\ntest and its trial-0/state authority/board database paths may connect. Preserve\nraw state, partial failures and original identities. Network, subprocesses,\nphysical devices, MCU/emulator, inference and live services remain prohibited.\n\nNo inherited runtime/provider/compiler/test/fixture changes. These are individual\nrequired scenarios, not complete group qualification or aggregate enforcement.\nPrimary-agent full diff review/release precedes execution; helpers are unavailable.\n')
    print(json.dumps(dict(harness=name,tests=count,targetSha256=sha(H/'targets.json'))))
print(json.dumps(dict(sourceIndexSha256=pin,projectFiles=7070,frozenFiles=7073)))
