"""Freeze original I/O recovery tests and ten closed execution scopes."""
import ast,difflib,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-supervision-recovery';S=B/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-supervision';O=OLD/'implementation03'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x') as f:f.write(json.dumps(v,indent=2)+'\n')
def inventory(folder,rooted=False):
 rows=[]
 for p in sorted(folder.rglob('*')):
  assert not p.is_symlink()
  if p.is_file():
   if p.suffix=='.py':ast.parse(p.read_bytes())
   rows.append(dict(path=p.relative_to(ROOT if rooted else folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 return sorted(rows,key=lambda r:r['path'])
base=read(S/'baseline-inputs.json');assert sha(O/'index.json')==base['sourceIndexSha256']=='30e8155181a738ace3d02de0f89402d82927dfcbf605fcd5ba1138278a6d70f4'
for r in read(O/'index.json')['files']:assert sha(ROOT/r['path'])==r['sha256']
assert len(base['inheritedProjectInputs'])==237
for r in base['inheritedProjectInputs']:
 p=ROOT/r['path'];q=S/'project'/p.relative_to(O/'project');assert sha(q)==r['sha256'] and q.stat().st_size==r['bytes']
reviewed=[
 'All237 inherited project files, including all five production supervisor modules, remain byte-identical. Two original test files add20 explicit methods. Every Python source AST parsed without execution.',
 'Eleven control methods use separate predeclared private ledgers. Original160 tests stay SQL/spawn-free. New control methods may open only their exact ledger paths; at most16 opens per method and32 total; all subprocess execution forbidden.',
 'Corrupt controls are retained and never restored. Missing/replaced lease fixtures retain the original lease under another filename. Diagnostic PID12345 and fake clock never authorize signaling or denote actual workers.',
 'One PWM, three worker-failure and five owner-crash selections are separate180s runs. Original group/effect/storage limits unchanged except explicitly reduced maxRecords500 and maxWallMs1 negative cases. Original16MiB control and256MiB process acquisition scopes retained.',
 'Only an exact fixed original worker or declared fixed crash driver can launch. The crash driver allows at most one exact worker and its own ledger, denies bytecode/network/other launch. Driver streams each65536bytes,90s; recovery waits70s for original lease, without signaling a persisted PID.',
 'Process collection acquires owner lock, reads bounded original ledger immutably, and acquires matching private writer lease before inventory/copy. No owned handle is synthesized from persisted PID; missing/active/replaced lease refuses collection and leaves raw state.',
 'Full PWM and completed owner-loss groups use independent semantic reader. Delivery of failed group is not qualification. Archive semantic/quota flags remainfalse and unresolvedEffects remainsunknown. Exact replay and same-key conflict never relaunch.',
 'Primary-agent complete new source/harness review only. No acquired-controller/device/MCU/inference/live-service/adjacent-Harness execution. All raw originals and failures retained.']
write(S/'source-review.json',dict(scope='Original I/O recovery tests on unchanged production supervisor',unchangedInheritedFiles=237,newProjectFiles=2,reviewed=reviewed,independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# I/O recovery fixtures\n\n[Design](../DESIGN.md), [source review](source-review.json). All inherited production bytes unchanged.\n')
rows=inventory(S,True);assert len(rows)==242
write(S/'index.json',dict(scope='Frozen I/O PWM, failure and owner-loss tests; unchanged production.',files=rows));pin=sha(S/'index.json')
module='test_io_supervisor_recovery';tree=ast.parse((S/'project/tests'/ (module+'.py')).read_bytes())
def methods(cls):
 node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
 return sorted(module+'.'+cls+'.'+n.name for n in node.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'))
control=methods('IoControlRecoveryTests');assert len(control)==11
process=methods('IoPwmSupervisionTests')+methods('IoWorkerFailureTests')+methods('IoOwnerCrashTests');assert len(process)==9
scopes=[read(OLD/'harness05/targets.json')['targets']+control]+[[t]for t in process]
labels=['supervisor','held','missing','replaced']+['case-%02d'%n for n in range(11)]
quiescence='''
def acquire_process_quiescence(scratch):
    """Hold actual owner/writer locks through inventory; no PID authority."""
    root = scratch / PROCESS_METHOD / 'supervisor'
    held, proof = [], {'scope':'owner and exact writer lease, not exit-code attestation','records':[]}
    try:
        if not root.exists():
            proof['ledgerAbsent']=True
            return held, proof
        owner = root / 'supervisor.owner'
        if not owner.exists():
            if (root/'attempts.db').exists():raise RuntimeError('Ledger without owner lock')
            proof['ledgerAbsent']=True
            return held,proof
        fd=os.open(owner,os.O_RDWR|os.O_NOFOLLOW);held.append(fd)
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o600:
            raise RuntimeError('Unsafe original owner lock')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        ledger=root/'attempts.db'
        if not ledger.exists():
            proof['ledgerAbsent']=True
            return held,proof
        before=row(ledger,'attempts.db')
        db=_sqlite3.connect('file:'+str(ledger)+'?mode=ro&immutable=1',uri=True)
        try:
            meta=db.execute('SELECT typeof(record),length(record) FROM qs_attempts LIMIT 2').fetchall()
            if len(meta)>1 or any(t!='blob' or n>65536 for t,n in meta):raise RuntimeError('Unexpected process ledger record closure')
            records=db.execute('SELECT id,record FROM qs_attempts LIMIT 2').fetchall()
        finally:db.close()
        if row(ledger,'attempts.db')!=before:raise RuntimeError('Read-only ledger changed')
        for identifier,raw in records:
            record=json.loads(raw)
            if not re.fullmatch(r'[0-9a-f]{32}',identifier) or record['attemptId']!=identifier:raise RuntimeError('Attempt association')
            lease=record['lease'];entry={'attemptId':identifier,'state':record['state'],'lease':lease}
            if lease is not None:
                fd=os.open(root/identifier/'writer.lease',os.O_RDWR|os.O_NOFOLLOW);held.append(fd);info=os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o600 or
                    lease!={'device':str(info.st_dev),'inode':str(info.st_ino)}):raise RuntimeError('Writer lease identity unknown')
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);entry['writerQuiescent']=True
            else:
                if record['state'] not in {'admitted','interrupted','archived'}:raise RuntimeError('Unarmed state unknown')
                entry['launchIntentAbsent']=True
            proof['records'].append(entry)
        proof['ledger']=before;proof['ownerQuiescent']=True
        return held,proof
    except BaseException:
        for fd in held:os.close(fd)
        raise

'''
for i,targets in enumerate(scopes,1):
 count=len(targets);iscontrol=i==1;crash=not iscontrol and '.IoOwnerCrashTests.' in targets[0]
 prior=OLD/('harness05'if iscontrol else'harness06');expected='2d1da9fd0e926f2f5f920878a31b4cdf44bd7f6d3eb1b78a7136b2eaef89ffc4'if iscontrol else'43aa9ea2124658a35a9e8e16bab41f525fbe36c74c292a9dcd080a835f849c87'
 assert sha(prior/'index.json')==expected
 for r in read(prior/'index.json')['files']:assert sha(prior/r['path'])==r['sha256']
 H=B/('harness%02d'%i);H.mkdir();(H/'references').mkdir();borrowed=[]
 for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
  p=prior/name;q=H/'references'/p.name;shutil.copyfile(p,q);borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 write(H/'borrowed-inputs.json',borrowed);write(H/'targets.json',dict(testCount=count,targets=targets))
 for name in ('run_attempt.py','attempt_child.py'):
  before=(prior/name).read_text();after=before.replace(base['sourceIndexSha256'],pin).replace(OLD.name,B.name).replace('implementation03','implementation01')
  after=re.sub(r'\b240\b','242',after);after=re.sub(r'\b237\b','239',after)
  if iscontrol:after=re.sub(r'\b160\b','171',after)
  after=after.replace('supervision160','recovery171').replace('Supervision160','Recovery171').replace('supervision1','recovery1').replace('Supervision1','Recovery1')
  if name=='run_attempt.py':
   oldtargets=read(prior/'targets.json')['targets'];assert after.count(repr(oldtargets))==1;after=after.replace(repr(oldtargets),repr(targets))
   if not iscontrol:
    method=targets[0].rsplit('.',1)[1]
    after=after.replace('import argparse','import argparse\nimport fcntl\nimport re')
    after=after.replace('\ndef main():','\nPROCESS_METHOD = '+repr(method)+'\n'+quiescence+'\ndef main():')
    begin=after.index('            rows = inventory(scratch, max_bytes=MAX_SCRATCH_BYTES)');end=after.index('            # Keep the original root',begin)
    block=after[begin:end];replacement="            leases, proof = acquire_process_quiescence(scratch)\n            try:\n                write_json(attempt/'writer-quiescence.json',proof)\n"+''.join('    '+line for line in block.splitlines(True))+"            finally:\n                for fd in leases:os.close(fd)\n"
    after=after[:begin]+replacement+after[end:]
  else:
   begin=after.index("    if event.startswith('socket.')") if iscontrol else after.index("    if event == 'subprocess.Popen':")
   end=after.index("    if event == 'exec':",begin)
   if iscontrol:
    replacement="""    if event.startswith('socket.') or event in {'subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn'}:
        prohibited.append(event); raise RuntimeError('Control selection forbids network and subprocesses')
    if event == 'sqlite3.connect':
        path=Path(os.fsdecode(os.fspath(args[0])))
        allowed=current_test in CONTROL_TARGETS
        method=current_test.rsplit('.',1)[1] if allowed else 'invalid'
        if not allowed or path.parent.parent!=scratch/method or path.parent.name not in CONTROL_LABELS or path.name!='attempts.db':
            prohibited.append(event); raise RuntimeError('Only declared control fixture ledgers may open')
        if len(sqlite_connections)>=32 or sum(c['testId']==current_test for c in sqlite_connections)>=16:
            raise RuntimeError('Declared control ledger inventory bound')
        sqlite_connections.append({'testId':current_test,'database':str(path)})
"""
    after=after.replace('def audit(event, args):','CONTROL_TARGETS = '+repr(control)+'\nCONTROL_LABELS = '+repr(labels)+'\n\ndef audit(event, args):')
    begin=after.index("    if event.startswith('socket.')");end=after.index("    if event == 'exec':",begin)
   else:
    method=targets[0].rsplit('.',1)[1]
    replacement=after[begin:end].replace('test_complete_owned_gpio_group_retains_inputs_before_launch_and_replays',method)
    if crash:
     a=replacement.index('        expected = scratch');b=replacement.index('        if not valid:',a)
     replacement=replacement[:a]+"""        expected = scratch / METHOD / 'prepared'
        valid = (current_test == config['targets'][0] and executable == sys.executable and
            argv == [sys.executable,'-I','-S','-B',str(root/'tests/io_supervisor_crash_driver.py'),str(expected)] and
            str(cwd)==str(root) and environment=={'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'})
""".replace('METHOD',repr(method))+replacement[b:]
   after=after[:begin]+replacement+after[end:]
  ast.parse(after);(H/name).write_text(after)
  (H/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str((prior/name).relative_to(ROOT)),tofile=str((H/name).relative_to(ROOT)))))
 scope='Control171:160 inherited plus11 I/O control/recovery tests; no subprocesses.'if iscontrol else ('Owner-loss process1, fixed original crash driver and worker.'if crash else'Owned process1, exact original supervisor worker.')
 (H/'SCOPE.md').write_text('# Exact execution scope\n\n'+scope+'\nTarget: '+', '.join(targets[-11:]if iscontrol else targets)+'\n\nSee [design](../DESIGN.md). Preserve raw originals and failures. No physical execution.\n')
 (H/'README.md').write_text('# I/O recovery checks\n\n[Scope](SCOPE.md), [targets](targets.json), [source](../implementation01/README.md).\n')
 write(H/'review.json',dict(scope=scope,tests=count,sourceIndexSha256=pin,targetSha256=sha(H/'targets.json'),scratchBytesCeiling=(16 if iscontrol else 256)*1024*1024,controlTargets=control if iscontrol else[],controlLabels=labels if iscontrol else[],crashDriver=crash,reviewed=reviewed,independentReview=False,releasedBy='primary-agent'))
 write(H/'index.json',dict(scope=scope,files=inventory(H)))
 print(json.dumps(dict(harness=H.name,tests=count,indexSha256=sha(H/'index.json'),target=targets[-1])))
print(json.dumps(dict(projectFiles=239,frozenFiles=242,sourceIndexSha256=pin)))
