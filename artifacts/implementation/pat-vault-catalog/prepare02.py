"""Split the unchanged candidate into bounded, independent control scopes."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
ORIGINAL=BASE/'harness01'
SOURCE=BASE/'implementation01'
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:
        stream.write(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')
assert sha(SOURCE/'index.json')=='39efa8125d3942e53c66395dd0e34575d45e06ee357f7c3bc1d603f482b81393'
assert sha(ORIGINAL/'index.json')=='6380a7e54b3ba978596f18f62c0b29c8318819e4fb426accf4e34a93a0606cee'
failed=read(ORIGINAL/'attempts/attempt01/result.json')
assert failed['status']=='failed' and failed['childState']=='exited' and failed['exitCode']==-9
targets=read(SOURCE/'test-selection.json');assert len(targets)==14
scopes=[]
for offset in range(0,14,3):
    chosen=targets[offset:offset+3];n=len(chosen)
    harness=BASE/('harness%02d'%(2+offset//3));harness.mkdir()
    write(harness/'targets.json',chosen)
    write(harness/'references/external-inputs.json',(ORIGINAL/'references/external-inputs.json').read_text())
    for name in ('run_attempt.py','attempt_child.py'):
        before=(ORIGINAL/name).read_text();after=before
        if name=='attempt_child.py':
            line=next(x for x in after.splitlines() if x.startswith('CONTROL_TARGETS = '))
            after=after.replace(line,'CONTROL_TARGETS = '+repr(chosen))
        after=after.replace('== 14','== '+str(n)).replace('!= 14','!= '+str(n))
        ast.parse(after)
        write(harness/name,after)
        write(harness/(name+'.patch'),''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='harness01/'+name,tofile=harness.name+'/'+name)))
    write(harness/'SCOPE.md', '# '+str(n)+' controls on unchanged source\n\n'
        'Exact [targets](targets.json) are one disjoint group from the original 14-method selection. '
        'The original killed run remains failed and retained; its missing final receipts are not reconstructed. '
        'Parent 180 seconds, child 120 CPU seconds, 512 MiB address space, 64 SQLite opens, '
        '16 MiB/file, 256 MiB retained scratch, 8,192 files, 4 MiB output and five-second vault lease remain unchanged. '
        'No worker, network, physical I/O or live service. The semantic oracle remains an explicit fixture. '
        'Separate scope passes do not establish an aggregate timing pass.\n')
    write(harness/'README.md','# Bounded catalog controls\n\n'
        '[Candidate](../implementation01/README.md), [targets](targets.json), [limits](SCOPE.md). '
        'Source and harness behavior are unchanged from harness01 except the exact selected method list and count. '
        'Each scope owns private scratch and retained receipts.\n')
    rows=[dict(path=str(p.relative_to(harness)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(harness.rglob('*')) if p.is_file()]
    write(harness/'index.json',dict(files=rows))
    scopes.append(dict(harness=harness.name,indexSha256=sha(harness/'index.json'),targets=chosen))
write(BASE/'control-scopes.json',dict(sourceIndexSha256=sha(SOURCE/'index.json'),originalFailure=failed,
    scopes=scopes,aggregateTimingPass=False))
print(json.dumps([dict(harness=x['harness'],tests=len(x['targets']),index=x['indexSha256']) for x in scopes]))
