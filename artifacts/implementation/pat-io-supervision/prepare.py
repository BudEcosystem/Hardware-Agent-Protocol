"""Freeze adapted supervision and separate pure/process test scopes."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT=Path.cwd(); B=ROOT/'artifacts/implementation/pat-io-supervision'; S=B/'implementation01'
OLD=ROOT/'artifacts/implementation/pat-io-run-bundle'; O=OLD/'implementation03'; PRIOR=OLD/'harness03'
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
    return rows
base=read(S/'baseline-inputs.json');assert sha(O/'index.json')==base['sourceIndexSha256']=='6c2fb673f490ad592a4aa412d3f0533b5933b60c6b68e49357c38f95536f7a72'
for row in read(O/'index.json')['files']:
    p=ROOT/row['path'];assert sha(p)==row['sha256'] and p.stat().st_size==row['bytes']
assert len(base['inheritedProjectInputs'])==230 and len(base['supervisorInputs'])==4
for row in base['inheritedProjectInputs']:
    p=ROOT/row['path'];q=S/'project'/p.relative_to(O/'project');assert sha(q)==row['sha256'] and q.stat().st_size==row['bytes']
invariants=[];patches=[]
for row in base['supervisorInputs']:
    p=ROOT/row['path'];assert sha(p)==row['sha256'] and p.stat().st_size==row['bytes'];q=S/'project/supervisor'/p.name
    patches.extend(difflib.unified_diff(p.read_text().splitlines(True),q.read_text().splitlines(True),fromfile=str(p.relative_to(ROOT)),tofile=str(q.relative_to(ROOT))))
    names=({'AttemptLedger':['_row','lookup','get','admit','_change','change','archive','transaction','close','__init__']}
        if p.name=='attempt_ledger.py' else {'QualificationSupervisor':['recover','stop_owned','close','__init__','lookup','status','_archive']} if p.name=='qualification_supervisor.py' else {})
    for cls,methods in names.items():
        a=next(n for n in ast.parse(p.read_bytes()).body if isinstance(n,ast.ClassDef) and n.name==cls)
        b=next(n for n in ast.parse(q.read_bytes()).body if isinstance(n,ast.ClassDef) and n.name==cls)
        for method in methods:
            x=next(n for n in a.body if isinstance(n,ast.FunctionDef) and n.name==method);y=next(n for n in b.body if isinstance(n,ast.FunctionDef) and n.name==method)
            assert ast.dump(x,include_attributes=False)==ast.dump(y,include_attributes=False)
            invariants.append(dict(file=p.name,method=cls+'.'+method,astSha256=hashlib.sha256(ast.dump(x,include_attributes=False).encode()).hexdigest()))
(B/'complete-supervisor.patch').write_text(''.join(patches));write(B/'unchanged-ownership-methods.json',invariants)
reviewed=[
    'All230 inherited HMS/data/test files remain byte-identical. Four original supervisor modules adapted plus bundle_io and two tests. Source identity includes all five supervisor modules and seven distributions. The endpoint scenario manifest is now in the private image.',
    'Seventeen ledger/ownership/recovery/archive methods remain AST-identical. Other changes are closed I/O request/bundle fields, input retention before launch intent, fixed child entry invocation of run_io_group, selected60s parent deadline, complete output-file hashing and bounded ledger closure metadata.',
    'Exact replay and same-key conflict precede fresh source/setup reads. New admission snapshots builtin byte mappings; durable launch input contains ledger-generated attempt ID. No stored PID authorizes a signal and no old attempt reruns.',
    'Protected input writers exclusively create/fsync fixed files under no-follow private directories, then reread exact closure. Collection refuses unsafe types/links/modes and bounds every file/directory entry before root digest; all output files participate. Transport integrity is deliberately not semantic qualification.',
    'Per-input65536, max39inputs, selected32cases/60s/20MiBderived and original64MiBattempt/256MiBroot limits remain. Preflight reserves input, output, streams and controls. Hard aggregate enforcement, trusted service configuration and public mount remain absent; corresponding archive flags remain false.',
    'Pure160 target has no SQL/spawn. Separate process1 may launch exactly the supervised original Python entry and open exactly its private attempts.db in the parent; pinned child executes synthetic I/O only. Its256MiB acquisition scope covers the existing supervisor retained root and is distinct from unchanged16MiBpure acquisition.',
    'Primary-agent full delta/source/test review only. No acquired controller, device, MCU, inference, live service or adjacent Harness execution. All raw originals, failures and states must be retained.',
]
write(S/'source-review.json',dict(scope='Primary-agent complete I/O supervisor adaptation review before execution.',unchangedInheritedFiles=230,newProjectFiles=7,
    reviewed=reviewed,independentReview=False,releasedBy='primary-agent',projectExecutionDuringPreparation=False))
(S/'README.md').write_text('# Isolated I/O supervision\n\n[Design](../DESIGN.md), [source review](source-review.json).\nPublic qualification and actual quotas are not implemented.\n')
rows=inventory(S,True);assert len(rows)==240
write(S/'index.json',dict(scope='Frozen I/O supervisor adaptation and pure/process tests.',files=rows));pin=sha(S/'index.json')
assert sha(PRIOR/'index.json')=='a9636b71421e5d3f924907509cef73cda8999df7a8646c2f3045e4f269abce24'
for row in read(PRIOR/'index.json')['files']:assert sha(PRIOR/row['path'])==row['sha256']
prior=read(PRIOR/'targets.json');tree=ast.parse((S/'project/tests/test_io_supervisor_contracts.py').read_bytes())
new=sorted('test_io_supervisor_contracts.IoSupervisorContractsTests.'+n.name for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'))
assert len(new)==11
process_target='test_io_supervisor_process.IoSupervisorProcessTests.test_complete_owned_gpio_group_retains_inputs_before_launch_and_replays'
for i,targets in [(1,prior['targets']+new),(2,[process_target])]:
    count=len(targets);H=B/('harness%02d'%i);H.mkdir();(H/'references').mkdir();borrowed=[]
    for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
        p=PRIOR/name;q=H/'references'/p.name;shutil.copyfile(p,q)
        borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=q.relative_to(H).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    write(H/'borrowed-inputs.json',borrowed);write(H/'targets.json',dict(testCount=count,targets=targets))
    for name in ('run_attempt.py','attempt_child.py'):
        before=(PRIOR/name).read_text();after=before.replace(base['sourceIndexSha256'],pin).replace(OLD.name,B.name).replace('implementation03','implementation01')
        after=after.replace('IoRunBundle149','IoSupervision'+str(count)).replace('bundle149','supervision'+str(count))
        after=re.sub(r'\b233\b','240',after);after=re.sub(r'\b230\b','237',after);after=re.sub(r'\b149\b',str(count),after)
        if name=='run_attempt.py':
            assert after.count(repr(prior['targets']))==1;after=after.replace(repr(prior['targets']),repr(targets))
            if i==2:after=after.replace('MAX_SCRATCH_BYTES = 16 * 1024 * 1024','MAX_SCRATCH_BYTES = 256 * 1024 * 1024')
        elif i==2:
            begin=after.index("    if event.startswith('socket.')")
            end=after.index("    if event == 'exec':",begin)
            replacement='''    if event == 'subprocess.Popen':
        executable, argv, cwd, environment = args
        expected = scratch / 'test_complete_owned_gpio_group_retains_inputs_before_launch_and_replays' / 'supervisor'
        entry = Path(argv[3]) if type(argv) in (list,tuple) and len(argv)==7 else Path('/invalid')
        valid = (current_test == config['targets'][0] and executable == sys.executable and
            argv[0] == sys.executable and argv[1:3] == ['-I','-B'] and
            entry.name == 'worker_entry.py' and entry.parent.name == 'supervisor' and
            entry.parent.parent.parent == expected and re.fullmatch(r'code-[0-9a-f]{64}',entry.parent.parent.name) and
            str(cwd) == str(entry.parent.parent) and all(type(v) is str and v.isdecimal() for v in argv[4:]) and
            environment == {'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'})
        if not valid: prohibited.append(event); raise RuntimeError('Only exact owned I/O entry may launch')
    elif event.startswith('socket.') or event in {'os.system','os.exec','os.fork','os.forkpty','os.posix_spawn'}:
        prohibited.append(event); raise RuntimeError('Network or other subprocess forbidden')
    if event == 'sqlite3.connect':
        path = Path(os.fsdecode(os.fspath(args[0])))
        expected = scratch / 'test_complete_owned_gpio_group_retains_inputs_before_launch_and_replays' / 'supervisor' / 'attempts.db'
        if current_test != config['targets'][0] or path != expected:
            prohibited.append(event); raise RuntimeError('Only the exact private supervisor ledger may open in this test process')
        if len(sqlite_connections)>=16: raise RuntimeError('Too many parent ledger opens')
        sqlite_connections.append({'testId':current_test,'database':str(path)})
'''
            after=after[:begin]+replacement+after[end:]
        ast.parse(after);(H/name).write_text(after)
        (H/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str((PRIOR/name).relative_to(ROOT)),tofile=str((H/name).relative_to(ROOT)))))
    scope=('Pure160:149 inherited plus11 request/file-transport checks; no SQL or spawn. Original16MiB scratch bound.' if i==1 else
        'Process1: one exact owned finite GPIO group, private parent ledger and fixed child entry only. New256MiB supervisor-root acquisition scope; original60s execution/64MiBattempt/256MiBroot and180s test-parent ceilings.')
    (H/'SCOPE.md').write_text('# Exact execution scope\n\n'+scope+'\nNo physical/MCU/inference/live-service/acquired-controller execution. Preserve every original and failure.\n')
    (H/'README.md').write_text('# I/O supervision checks\n\n[Scope](SCOPE.md), [targets](targets.json), [source](../implementation01/README.md).\n')
    write(H/'review.json',dict(scope=scope,tests=count,sourceIndexSha256=pin,targetSha256=sha(H/'targets.json'),
        scratchBytesCeiling=(16 if i==1 else 256)*1024*1024,reviewed=reviewed,independentReview=False,releasedBy='primary-agent'))
    write(H/'index.json',dict(scope=scope,files=inventory(H)))
    print(json.dumps(dict(harness=H.name,tests=count,indexSha256=sha(H/'index.json'))))
print(json.dumps(dict(projectFiles=237,frozenFiles=240,sourceIndexSha256=pin,unchangedOwnershipMethods=len(invariants))))
