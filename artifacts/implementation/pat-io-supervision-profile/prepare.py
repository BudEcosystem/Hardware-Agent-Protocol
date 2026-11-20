"""Prepare bounded parent profiling on the exact unchanged PWM test and source."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-supervision-profile';OLD=ROOT/'artifacts/implementation/pat-io-supervision-recovery';O=OLD/'harness02';H=B/'harness01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
assert sha(OLD/'implementation01/index.json')=='d1c5ac0d86c77bd195ffebfcf75dc6e1c95ecf7a0814416073cfba691fb5685c'
assert sha(OLD/'results/index.json')=='a6fa56b9d35af5c9b6b29a0c00eea5f3f0ef3ec8d0045a9b2d132a583fe4d3a4'
assert sha(O/'index.json')=='8d261b1dbcff5e0cd2c533a5dfad38b48a5f7ac33a826b64d443453005271e6a'
for row in read(OLD/'implementation01/index.json')['files']:assert sha(ROOT/row['path'])==row['sha256']
for row in read(O/'index.json')['files']:assert sha(O/row['path'])==row['sha256']
p=read(OLD/'results/attempt03-failed-pwm/proof.json');assert p['status']=='failed'and p['counts']['failures']==1
H.mkdir();(H/'references').mkdir();borrowed=[]
for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
 q=H/'references'/Path(name).name;shutil.copyfile(O/name,q);borrowed.append(dict(source=(O/name).relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=q.stat().st_size,sha256=sha(q)))
write(H/'borrowed-inputs.json',borrowed)
for name in ('targets.json','SCOPE.md'):shutil.copyfile(O/name,H/name)
before=(O/'run_attempt.py').read_text();after=before.replace("stage = here.parent / 'implementation01'","stage = here.parent.parent / 'pat-io-supervision-recovery/implementation01'").replace("hms-io-snapshot-reuse-recovery1-","hms-io-supervision-parent-profile-")
assert before!=after;ast.parse(after);(H/'run_attempt.py').write_text(after);(H/'run_attempt.py.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str(O/'run_attempt.py'),tofile=str(H/'run_attempt.py'))))
before=(O/'attempt_child.py').read_text();anchor='    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(tests)\n'
replacement='''    import cProfile
    import resource
    import time
    profiler=cProfile.Profile()
    started_wall,started_cpu=time.monotonic(),time.process_time()
    children_before=resource.getrusage(resource.RUSAGE_CHILDREN)
    profiler.enable()
    try:
        result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(tests)
    finally:
        profiler.disable()
        wall,cpu=time.monotonic()-started_wall,time.process_time()-started_cpu
        children_after=resource.getrusage(resource.RUSAGE_CHILDREN)
        profile_rows=[]
        for entry in profiler.getstats():
            code=entry.code
            label=code if isinstance(code,str) else code.co_filename+':'+str(code.co_firstlineno)+':'+code.co_name
            profile_rows.append(dict(label=label,calls=entry.callcount,recursiveCalls=entry.reccallcount,cumulativeSeconds=entry.totaltime,selfSeconds=entry.inlinetime))
        profile_rows.sort(key=lambda r:(-r['cumulativeSeconds'],r['label']))
        write('profile.json',dict(scope='Instrumented original full PWM test in a fresh diagnostic fixture, unchanged source and request. Parent profile only; timings include instrumentation and are not benchmark or qualification evidence.',
            wallSeconds=wall,parentCpuSeconds=cpu,childUserSeconds=children_after.ru_utime-children_before.ru_utime,
            childSystemSeconds=children_after.ru_stime-children_before.ru_stime,totalFunctions=len(profile_rows),
            top100=profile_rows[:100],top100Self=sorted(profile_rows,key=lambda r:(-r['selfSeconds'],r['label']))[:100]))
'''
assert before.count(anchor)==1;after=before.replace(anchor,replacement);ast.parse(after);(H/'attempt_child.py').write_text(after);(H/'attempt_child.py.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str(O/'attempt_child.py'),tofile=str(H/'attempt_child.py'))))
(H/'README.md').write_text('# Parent collection profile\n\nThe exact [target](targets.json) and [scope](SCOPE.md) use the unchanged [source](../../pat-io-supervision-recovery/implementation01/README.md). Instrumentation changes timing and never repairs or replays the failed original ledger. No physical execution.\n')
review=read(O/'review.json');review['scope']='Fresh bounded diagnostic of original PWM selection; no source/test/guard changes.';review['reviewed'] += ['Primary-agent complete profiling delta review before execution. cProfile wraps the exact selected original method after imports, recording bounded top100 cumulative/self rows and parent/child CPU totals. Profile artifact bounded by original4MiB receipt limit. Original failed ledger, source, request,60s group/supervisor and180s parent deadlines, all storage/effect caps, exact entry, input and lease checks unchanged. This is instrumentation evidence, not a successful retry or performance attestation.']
write(H/'review.json',review)
rows=[]
for p in sorted(H.rglob('*')):
 if p.is_file():rows.append(dict(path=p.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
write(H/'index.json',dict(scope=review['scope'],files=rows));print(json.dumps(dict(harnessIndexSha256=sha(H/'index.json'),files=len(rows),sourceUnchanged=True)))
