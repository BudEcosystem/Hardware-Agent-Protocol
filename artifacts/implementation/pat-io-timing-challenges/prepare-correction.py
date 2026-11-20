"""Freeze the expiry-cause correction; preserve first attempts/source unchanged."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path.cwd().resolve();BASE=ROOT/'artifacts/implementation/pat-io-timing-challenges';SOURCE=BASE/'implementation02'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
    with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
old_project=BASE/'implementation01/project';changed=[];unchanged=0
for row in read(SOURCE/'baseline-inputs.json')['inheritedProjectInputs']:
    rel=(ROOT/row['path']).relative_to(old_project);p=SOURCE/'project'/rel
    if p.stat().st_size==row['bytes'] and sha(p)==row['sha256']:unchanged+=1
    else:changed.append(rel.as_posix())
assert unchanged==7067 and set(changed)=={'hms/pat_io_configuration_history.py','hms/pat_io_refusal_history.py','tests/test_pat_io_timing_challenges.py'}
write(SOURCE/'source-review.json',dict(scope='Primary-agent complete expiry-cause correction review after actual retained failures.',
    inheritedInputsUnchanged=unchanged,changedFiles=changed,
    reviewed=['Actual adapter expiry emits start_or_lease_expired before dispatch; operation fold already supports that independently.',
      'Configuration checker requires old accepted state, actual expiry time, exact event and no dispatch/effects; no generic error whitelist.',
      'Refusal composition requires expiry response, no board change, no ticket/effect, released claims and retained read authority; expiry precedes permission and parent handoff gates.',
      'Expiry receives no caller-supplied private operation-fold handoff; existing fold derives its reason directly. Existing permission refusal error precedence remains intact.',
      'New rehashed expiry-reason/effect attacks join all16 actual timing cases;77 inherited configuration/refusal tests are selected separately.',
      'Worker, independent timing checker, runtime/provider/compiler, historical data and all old test files remain unchanged. Initial failures remain preserved.'],
    projectExecutionDuringPreparation=False,independentReview=False,releasedBy='primary-agent'))
(SOURCE/'README.md').write_text('# Corrected timing refusal composition\n\nThe first [candidate](../implementation01/README.md) captured valid no-handoff\nexpiry behavior, but configuration/refusal composition assumed permission loss.\nThis source changes only those two independent readers and adds four rehashed\nexpiry attacks to the new test file. All 7,067 other inherited files remain\nunchanged. No runtime/provider/compiler behavior or effect bound changes.\nSee [review](source-review.json). Full group qualification remains unfinished.\n')
rows=[]
for p in sorted(SOURCE.rglob('*')):
    assert not p.is_symlink()
    if p.is_file():
        if p.suffix=='.py':ast.parse(p.read_bytes())
        rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==7073
write(SOURCE/'index.json',dict(scope='Frozen expiry-cause correction; producer runtime unchanged.',files=rows));source_pin=sha(SOURCE/'index.json')
plans=[]
for name,old,count,cls,pin in [
    ('harness03','harness01',9,'GpioTimingChallengeTests','8200dc8c5c2ed0fda1ef487707da1a3a899fd279cb9fb6cf22eb26f266740c43'),
    ('harness04','harness02',8,'PwmTimingChallengeTests','c7c18267b43f66707edeeaa4fc22ae362a2c8fb65c7d2d207bc2388349461fa3'),
    ('harness05','harness01',77,None,'8200dc8c5c2ed0fda1ef487707da1a3a899fd279cb9fb6cf22eb26f266740c43')]:
    OLD=BASE/old;H=BASE/name;assert sha(OLD/'index.json')==pin
    for row in read(OLD/'index.json')['files']:
        p=OLD/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
    H.mkdir(exist_ok=False);(H/'references').mkdir();borrowed=[]
    for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
        p=OLD/item;relative='references/'+(old+'-'if'/'not in item else'')+p.name
        shutil.copyfile(p,H/relative);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=relative,bytes=p.stat().st_size,sha256=sha(p)))
    write(H/'borrowed-inputs.json',borrowed)
    if count!=77:targets=read(OLD/'targets.json')['targets']
    else:
        targets=[]
        for module,klass,n in [('test_pat_io_configuration_history','IoConfigurationHistoryTests',48),('test_pat_io_refusal_history','IoRefusalHistoryTests',29)]:
            tree=ast.parse((SOURCE/'project/tests'/(module+'.py')).read_bytes());node=next(x for x in tree.body if isinstance(x,ast.ClassDef)and x.name==klass)
            selected=sorted(module+'.'+klass+'.'+x.name for x in node.body if isinstance(x,ast.FunctionDef)and x.name.startswith('test_'));assert len(selected)==n;targets+=selected
    assert len(targets)==count;write(H/'targets.json',dict(testCount=count,targets=targets))
    for item in ['run_attempt.py','attempt_child.py']:
        before=(OLD/item).read_text();after=before.replace('adb63bce663e249d06b1c46bec3d04fed6d1111e43796dd56c9567211bcbd381',source_pin)
        after=after.replace('/implementation01/','/implementation02/').replace("here.parent / 'implementation01'","here.parent / 'implementation02'")
        if count==77:
            after=after.replace('TimingChallenges9','TimingRegression77').replace('timing9','regression77')
            after=after.replace('!= 9','!= 77').replace('== 9','== 77').replace("'expectedTests': 9","'expectedTests': 77")
            if item=='run_attempt.py':
                start=after.index("                sum(name.startswith('test_pat_io_timing_challenges")
                end=after.index(":\n            raise ValueError('Closed",start)
                after=after[:start]+"                sum(name.startswith('test_pat_io_configuration_history.IoConfigurationHistoryTests.') for name in targets['targets']) != 48 or\n                sum(name.startswith('test_pat_io_refusal_history.IoRefusalHistoryTests.') for name in targets['targets']) != 29)"+after[end:]
                after=after.replace('Eight original GPIO timing cases and one pre-runtime refusal method','77 unchanged pure configuration/refusal history tests; no runtime construction or SQL connection')
            else:after=after.replace("current_test.startswith('test_pat_io_timing_challenges.GpioTimingChallengeTests.')",'False  # No selected pure target may open SQLite')
        ast.parse(after);(H/item).write_text(after)
        (H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(OLD/item).relative_to(ROOT).as_posix(),tofile=(H/item).relative_to(ROOT).as_posix())))
    scope='77 unchanged pure configuration/refusal methods'if count==77 else 'Eight original timing runtime cases'+(' plus one pre-runtime refusal method'if count==9 else'')
    (H/'README.md').write_text('# Corrected '+str(count)+'-method selection\n\n'+scope+' on the [corrected source](../implementation02/README.md).\nSee [scope](SCOPE.md) and [selection](targets.json). Original first-attempt\nfailures remain intact; no effect or execution bound changes.\n')
    (H/'SCOPE.md').write_text('# Unchanged execution boundaries\n\n'+scope+'. Keep the original 180-second deadline,\n16 MiB scratch, 8,192 inventory files, 256 MiB input, 16 MiB file, 4 MiB JSON\nand 8 MiB log limits. '+('No SQLite connection is allowed.'if count==77 else'Only selected trial-0/state authority/board databases may connect.')+' Preserve raw output and failures.\nNo network, subprocesses, physical devices, MCU/emulator, inference or live\nservices. Primary-agent source/diff review precedes execution. Full matrix\nexecution, group budgets, source attestation and qualification remain open.\n')
    plans.append(dict(harness=name,tests=count,targetSha256=sha(H/'targets.json')))
write(BASE/'correction-plan.json',dict(sourceIndexSha256=source_pin,sourceChangedOnly=changed,workerUnchanged=True,limitsWidened=False,
    originalAttempts='failed: two expiry cause errors each, all raw data retained',selections=plans))
print(json.dumps(dict(sourceIndexSha256=source_pin,projectFiles=7070,frozenFiles=7073,selections=plans)))
