"""Freeze source and prepare the reviewed pure61 selection without imports."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path.cwd().resolve(); BASE=ROOT/'artifacts/implementation/pat-io-combined-matrix'
SOURCE=BASE/'implementation01'; OLD=ROOT/'artifacts/implementation/pat-io-outcome-history/harness01'; NEW=BASE/'harness01'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p,v):
    with p.open('x') as stream: stream.write(json.dumps(v,indent=2)+'\n')
old_project=ROOT/'artifacts/implementation/pat-io-outcome-history/implementation01/project'
for row in read(SOURCE/'baseline-inputs.json')['inheritedProjectInputs']:
    p=SOURCE/'project'/(ROOT/row['path']).relative_to(old_project)
    assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
rows=[]
for p in sorted(SOURCE.rglob('*')):
    assert not p.is_symlink()
    if p.is_file(): rows.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
assert len(rows)==7067
write(SOURCE/'index.json',dict(scope='Frozen combined-matrix preflight candidate; all7062 inherited project/data inputs unchanged.',files=rows))
source_pin=sha(SOURCE/'index.json')
assert sha(OLD/'index.json')=='20fa738a1627d0dd7a5b2cb7524959275c1a819fe74b8b88bf4faed94db11cfa'
for row in read(OLD/'index.json')['files']:
    p=OLD/row['path']; assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
NEW.mkdir(exist_ok=False); (NEW/'references').mkdir(); borrowed=[]
for name in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
    p=OLD/name; relative='references/'+('outcome24-' if '/' not in name else '')+p.name
    shutil.copyfile(p,NEW/relative); borrowed.append(dict(source=p.relative_to(ROOT).as_posix(),copy=relative,bytes=p.stat().st_size,sha256=sha(p)))
write(NEW/'borrowed-inputs.json',borrowed)
targets=[]
for module,cls,count in [('test_pat_io_contracts','IoContractTests',31),('test_pat_io_combined_matrix','IoCombinedMatrixTests',30)]:
    tree=ast.parse((SOURCE/'project/tests'/(module+'.py')).read_text()); selected=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
    names=sorted(module+'.'+cls+'.'+n.name for n in selected.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_'))
    assert len(names)==count; targets+=names
assert len(targets)==len(set(targets))==61
write(NEW/'targets.json',dict(testCount=61,targets=targets))
for name in ['run_attempt.py','attempt_child.py']:
    before=(OLD/name).read_text(); after=before.replace('OutcomeHistory24','CombinedMatrix61').replace('outcome24','matrix61')
    after=after.replace('io-outcome-history','io-combined-matrix').replace('4e297e540c22035bd65a1b7bc1312478e0843b00a4b0f25ba0bfd683c82da2ee',source_pin)
    after=after.replace('7065','7067').replace('7062','7064').replace('!= 24','!= 61').replace('== 24','== 61').replace("'expectedTests': 24","'expectedTests': 61")
    if name=='run_attempt.py':
        old="sum(name.startswith('test_pat_io_outcome_history.IoOutcomeHistoryTests.') for name in targets['targets']) != 61"
        new="sum(name.startswith('test_pat_io_contracts.IoContractTests.') for name in targets['targets']) != 31 or\n                sum(name.startswith('test_pat_io_combined_matrix.IoCombinedMatrixTests.') for name in targets['targets']) != 30"
        assert after.count(old)==1; after=after.replace(old,new)
        after=after.replace('static-policy and single-trial-outcome validation','combined qualification preflight and inherited domain/timing validation')
    ast.parse(after); (NEW/name).write_text(after)
    (NEW/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(OLD/name).relative_to(ROOT).as_posix(),tofile=(NEW/name).relative_to(ROOT).as_posix())))
(NEW/'README.md').write_text('# Isolated combined-matrix61 pure harness\n\nRun31 unchanged domain/timing methods and30 new matrix methods on the\n[frozen source](../implementation01/README.md). See [scope](SCOPE.md) and\n[selection](targets.json). This executes planning tests, not the planned fault\ntrials. Launch the parent with python3 -B; child startup remains -I -S -B.\n')
(NEW/'SCOPE.md').write_text('# Original matrix61 scope\n\nRun only61 pure planning/domain/timing methods. Construction reads trusted\ninstallation/source pins; planning and exact validation use detached data. No\nRuntime, SQLite connection, network, physical device, MCU/emulator, inference,\npublic service or acquired controller executes. All7062 inherited project/data\ninputs remain unchanged. The project closure is7064 files.\n\nKeep the original180-second execution deadline,16 MiB scratch,8192 inventory\nfiles,256 MiB input collection,16 MiB file,4 MiB receipt and8 MiB log limits.\nThe child keeps exact selected package/origin checks and cooperative prohibited\nI/O hooks, not an OS sandbox. Preserve original raw scratch. No effect, protocol\nor evidence ceiling is widened. This is not current-source attestation, a\nqualification worker or a passing fault/resource matrix. Primary-agent review\nis required before release; helpers remain usage-limited.\n')
print(json.dumps(dict(sourceIndexSha256=source_pin,projectFiles=7064,frozenFiles=7067,tests=61)))
