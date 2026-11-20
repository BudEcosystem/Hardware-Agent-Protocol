"""Instrument only the original worker group call; retain original stop semantics."""
import ast,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-supervision-profile';OLD=ROOT/'artifacts/implementation/pat-io-supervision-recovery';O=OLD/'implementation01';S=B/'implementation01';H=B/'harness02';PRIOR=OLD/'harness02'
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
assert sha(O/'index.json')=='d1c5ac0d86c77bd195ffebfcf75dc6e1c95ecf7a0814416073cfba691fb5685c'
(S/'project').mkdir(parents=True);inherited=[]
for r in read(O/'index.json')['files']:
 p=ROOT/r['path'];assert sha(p)==r['sha256']
 if p.is_relative_to(O/'project'):
  q=S/'project'/p.relative_to(O/'project');q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);inherited.append(r)
assert len(inherited)==239;write(S/'baseline-inputs.json',dict(sourceIndexSha256=sha(O/'index.json'),inheritedProjectInputs=inherited))
p=S/'project/supervisor/worker_entry.py';before=p.read_text()
helper='''
def _profile_group(directory, call):
    """Diagnostic only: bounded profile; SIGTERM is re-raised to this process."""
    import cProfile
    import signal
    import time
    profiler = cProfile.Profile()
    wall, cpu = time.monotonic(), time.process_time()
    finishing = False
    previous = signal.getsignal(signal.SIGTERM)
    require(previous == signal.SIG_DFL, 'QUALIFICATION_PROFILE_SIGNAL_STATE')
    def finish(reason):
        nonlocal finishing
        if finishing: return
        finishing = True
        profiler.disable()
        wall_elapsed, cpu_elapsed = time.monotonic()-wall, time.process_time()-cpu
        entries = profiler.getstats()
        require(len(entries)<=8192, 'QUALIFICATION_PROFILE_LIMIT')
        rows = []
        for entry in entries:
            code = entry.code
            if isinstance(code,str): label = code
            else:
                path = Path(code.co_filename)
                name = str(path.relative_to(worker._ROOT)) if path.is_relative_to(worker._ROOT) else str(path)
                label = name+':'+str(code.co_firstlineno)+':'+code.co_name
            require(len(label)<=512, 'QUALIFICATION_PROFILE_LIMIT')
            rows.append(dict(label=label,calls=entry.callcount,recursiveCalls=entry.reccallcount,
                cumulativeMicroseconds=int(entry.totaltime*1000000),selfMicroseconds=int(entry.inlinetime*1000000)))
        rows.sort(key=lambda r:(-r['cumulativeMicroseconds'],r['label']))
        value = dict(profile='hms.diagnostic.io-worker-profile/0.1',reason=reason,
            scope='Instrumented original run_io_group only; profiler overhead and interrupted data do not qualify performance or effects.',
            wallMicroseconds=int(wall_elapsed*1000000),cpuMicroseconds=int(cpu_elapsed*1000000),
            totalFunctions=len(rows),top40=rows[:40],top40Self=sorted(rows,key=lambda r:(-r['selfMicroseconds'],r['label']))[:40])
        write_file(directory,'worker-profile.json',canonical(value))
    def terminated(signum, frame):
        try: finish('SIGTERM')
        finally:
            signal.signal(signal.SIGTERM,signal.SIG_DFL)
            signal.raise_signal(signal.SIGTERM)
    signal.signal(signal.SIGTERM,terminated)
    profiler.enable()
    try: return call()
    finally:
        try: finish('returned-or-exception')
        finally: signal.signal(signal.SIGTERM,previous)

'''
after=before.replace('\ndef main():','\n'+helper+'\ndef main():')
anchor="    result = run_io_group(attempt / 'output', candidate=inputs['candidate'], installation=inputs['installation'],\n        descriptor=inputs['descriptor'], challenge_bindings=inputs['bindings'], limits=request['groupLimits'])"
replacement="    result = _profile_group(directory, lambda: run_io_group(attempt / 'output', candidate=inputs['candidate'], installation=inputs['installation'],\n        descriptor=inputs['descriptor'], challenge_bindings=inputs['bindings'], limits=request['groupLimits']))"
assert after.count(anchor)==1;after=after.replace(anchor,replacement);ast.parse(after);p.write_text(after)
(B/'worker-instrumentation.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str((O/'project/supervisor/worker_entry.py').relative_to(ROOT)),tofile=str(p.relative_to(ROOT)))))
changed=[]
for row in inherited:
 rel=(ROOT/row['path']).relative_to(O/'project')
 if sha(S/'project'/rel)!=row['sha256']:changed.append(rel.as_posix())
assert changed==['supervisor/worker_entry.py']
reviewed=['Primary-agent complete diagnostic worker delta review before execution.238of239project files unchanged; one worker-entry wrapper profiles only run_io_group after original input/setup validation. No test, candidate, driver, effect limit, admission, collector, source check, ownership or stop grace changes.',
 'The profile uses bounded8192function records internally and top40cumulative/top40self rows; label512characters; canonical original65536byte private exclusive/fsync writer. Profile is outside output/, counted in original64MiBattempt/256MiBroot logical storage. No bound is widened.',
 'SIGTERM is intercepted only to attempt a bounded diagnostic receipt, then restored to default and raised to the same process. No persisted PID or other process is targeted. Original supervisor may SIGKILL after1000ms. An interrupted profile/write remains failed/unknown; no state repair. SIGKILL is never intercepted.',
 'Diagnostic source identity changes explicitly through worker_entry bytes and supervisorIdentity. All other source/resource/runtime inputs remain exact. No live/physical/device/MCU/inference/acquired-controller execution. Original failed states remain untouched; this is a fresh diagnostic fixture, not replay in the old ledger.']
write(S/'source-review.json',dict(scope='Worker-only profiling instrumentation, not production optimization or qualification.',changedFiles=changed,unchangedInheritedFiles=238,reviewed=reviewed,independentReview=False,releasedBy='primary-agent'))
(S/'README.md').write_text('# Instrumented diagnostic worker\n\n[Design](../DESIGN.md), [review](source-review.json), [exact patch](../worker-instrumentation.patch). Only worker entry instrumentation changes; no production optimization or qualification.\n')
rows=inventory(S,True);assert len(rows)==242;write(S/'index.json',dict(scope='Frozen diagnostic worker; exact original test and limits.',files=rows));pin=sha(S/'index.json')
assert sha(PRIOR/'index.json')=='8d261b1dbcff5e0cd2c533a5dfad38b48a5f7ac33a826b64d443453005271e6a'
for r in read(PRIOR/'index.json')['files']:assert sha(PRIOR/r['path'])==r['sha256']
H.mkdir();(H/'references').mkdir();borrowed=[]
for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
 q=H/'references'/Path(name).name;shutil.copyfile(PRIOR/name,q);borrowed.append(dict(source=(PRIOR/name).relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=q.stat().st_size,sha256=sha(q)))
write(H/'borrowed-inputs.json',borrowed)
for name in ('attempt_child.py','targets.json','SCOPE.md'):shutil.copyfile(PRIOR/name,H/name)
before=(PRIOR/'run_attempt.py').read_text();after=before.replace(sha(O/'index.json'),pin).replace('pat-io-supervision-recovery','pat-io-supervision-profile').replace('hms-io-snapshot-reuse-recovery1-','hms-io-supervision-worker-profile-');ast.parse(after);(H/'run_attempt.py').write_text(after)
(H/'run_attempt.py.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str(PRIOR/'run_attempt.py'),tofile=str(H/'run_attempt.py'))))
(H/'README.md').write_text('# Worker-only diagnostic profile\n\nThe exact [target](targets.json) and [scope](SCOPE.md) use the [instrumented worker](../implementation01/README.md). The parent is uninstrumented. Missing/failed capture remains failed.\n')
review=read(PRIOR/'review.json');review.update(scope='Worker-only diagnostic profile; original exact PWM selection and all bounds.',sourceIndexSha256=pin);review['reviewed']+=reviewed;write(H/'review.json',review)
write(H/'index.json',dict(scope=review['scope'],files=inventory(H)));print(json.dumps(dict(sourceIndexSha256=pin,harnessIndexSha256=sha(H/'index.json'),changedFiles=changed)))
