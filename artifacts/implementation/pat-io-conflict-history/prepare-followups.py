"""Split the failed-retention52 invocation without changing source or limits."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path.cwd().resolve(); BASE=ROOT/'artifacts/implementation/pat-io-conflict-history'; OLD=BASE/'harness01'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p,v):
    with p.open('x') as stream:stream.write(json.dumps(v,indent=2)+'\n')
assert sha(OLD/'index.json')=='1874885a7b2c42dd8a721505f16fb36a619cc8b7d6afcaee04ef56ae61569ac5'
for row in read(OLD/'index.json')['files']:
    p=OLD/row['path']; assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
result=read(OLD/'attempts/attempt01-conflict52/result.json')
assert result['status']=='failed' and result['counts']==dict(testsRun=52,failures=0,errors=0,skips=0,expectedFailures=0,unexpectedSuccesses=0)
assert result['errors']==[dict(phase='scratch-retention',type='ValueError',message='Retained tree exceeds collection bound')]
all_targets=read(OLD/'targets.json')['targets']; plans=[]
for name,count,new in [('harness02',48,True),('harness03',4,False)]:
    H=BASE/name; H.mkdir(exist_ok=False); (H/'references').mkdir()
    targets=[t for t in all_targets if t.startswith('test_pat_io_configuration_capture.') is not new]
    assert len(targets)==count
    write(H/'targets.json',dict(testCount=count,targets=targets))
    borrowed=[]
    for item in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
        p=OLD/item; target='references/'+('conflict52-' if '/' not in item else '')+p.name
        shutil.copyfile(p,H/target);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=target,bytes=p.stat().st_size,sha256=sha(p)))
    write(H/'borrowed-inputs.json',borrowed)
    scope=('Nine original conflict runtime cases and39 inherited pure transcript tests' if new else 'Four unchanged original configured runtime cases, including16 steps')
    for item in ['run_attempt.py','attempt_child.py']:
        before=(OLD/item).read_text(); after=before.replace('ConflictHistory52','ConflictHistory'+str(count)).replace('conflict52','conflict'+str(count))
        after=after.replace('!= 52','!= '+str(count)).replace('== 52','== '+str(count)).replace("'expectedTests': 52","'expectedTests': "+str(count))
        if item=='run_attempt.py':
            start=after.index("                sum(name.startswith('test_pat_io_transcript")
            end=after.index(":\n            raise ValueError('Closed",start)
            condition=("                sum(name.startswith('test_pat_io_transcript.IoTranscriptTests.') for name in targets['targets']) != 39 or\n                sum(name.startswith('test_pat_io_conflict_history.IoConflictHistoryTests.') for name in targets['targets']) != 9)" if new else "                sum(name.startswith('test_pat_io_configuration_capture.IoConfigurationCaptureTests.') for name in targets['targets']) != 4)")
            after=after[:start]+condition+after[end:]
            after=after.replace('Thirteen original private SQLite runtime simulations plus39 inherited pure transcript tests',scope)
        ast.parse(after);(H/item).write_text(after)
        (H/(item+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(OLD/item).relative_to(ROOT).as_posix(),tofile=(H/item).relative_to(ROOT).as_posix())))
    (H/'README.md').write_text('# Separate conflict'+str(count)+' verification\n\n'+scope+'. Source and original limits are unchanged.\nSee [scope](SCOPE.md), [targets](targets.json) and the\n[frozen candidate](../implementation01/README.md). The earlier52-test attempt\nreported all methods passing but failed16 MiB scratch acquisition. It remains\na failed attempt with its original raw output retained.\n')
    (H/'SCOPE.md').write_text('# Unchanged execution boundaries\n\n'+scope+'. Only selected original trial SQLite files may\nconnect. Keep180 seconds,16 MiB scratch,8192 inventory files,256 MiB input,\n16 MiB file,4 MiB JSON and8 MiB log bounds. Preserve original raw state.\nNetwork, subprocesses, physical devices, MCU/emulator, inference and live services\nremain prohibited. No source, effect bound or qualification claim changes.\nParent review/release follows full adaptation-diff inspection.\n')
    plans.append(dict(harness=name,testCount=count,targetsSha256=sha(H/'targets.json'),runtimeTests=9 if new else 4,pureTests=39 if new else 0))
assert set(read(BASE/'harness02/targets.json')['targets']).isdisjoint(read(BASE/'harness03/targets.json')['targets'])
assert set(read(BASE/'harness02/targets.json')['targets'])|set(read(BASE/'harness03/targets.json')['targets'])==set(all_targets)
write(BASE/'followup-plan.json',dict(reason='52 methods passed but combined raw16817257 bytes exceeded16777216-byte collection limit.',
    sourceIndexSha256='eccd20743c61cb37d73c3f2f0df770d4c0b7529132287426eac7b8921875c524',
    sourceChanged=False,limitsWidened=False,originalAttemptStatus='failed',selections=plans))
print(json.dumps(plans))
