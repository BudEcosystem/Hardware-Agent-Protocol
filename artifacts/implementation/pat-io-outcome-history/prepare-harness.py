"""Freeze new source and prepare a pure24 harness without project imports."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path.cwd().resolve(); BASE = ROOT/'artifacts/implementation/pat-io-outcome-history'
SOURCE = BASE/'implementation01'; OLD = ROOT/'artifacts/implementation/pat-io-refusal-history/harness04-refusal29'
NEW = BASE/'harness01'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def write(path,value):
    with path.open('x') as stream: stream.write(json.dumps(value,indent=2)+'\n')
rows=[]
baseline=read(SOURCE/'baseline-inputs.json')
old_project=ROOT/'artifacts/implementation/pat-io-refusal-history/implementation01/project'
for row in baseline['inheritedProjectInputs']:
    path=SOURCE/'project'/(ROOT/row['path']).relative_to(old_project)
    assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
for path in sorted(SOURCE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file(): rows.append(dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
assert len(rows)==7065
write(SOURCE/'index.json',dict(scope='Frozen independent static-policy/single-trial-outcome candidate; all7060 inherited project inputs unchanged.',files=rows))
source_pin=sha(SOURCE/'index.json')
assert sha(OLD/'index.json')=='aa8fda81ff5e0c33671332d094eca9c7372eeee67ae39cd33648833c315cbe8e'
for row in read(OLD/'index.json')['files']:
    path=OLD/row['path']; assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
NEW.mkdir(exist_ok=False); (NEW/'references').mkdir(); borrowed=[]
for name in ['run_attempt.py','attempt_child.py','references/approved-external-roots.json']:
    path=OLD/name; relative='references/'+('refusal29-' if '/' not in name else '')+path.name
    shutil.copyfile(path,NEW/relative)
    borrowed.append(dict(source=path.relative_to(ROOT).as_posix(),copy=relative,bytes=path.stat().st_size,sha256=sha(path)))
write(NEW/'borrowed-inputs.json',borrowed)
tree=ast.parse((SOURCE/'project/tests/test_pat_io_outcome_history.py').read_text())
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='IoOutcomeHistoryTests')
targets=['test_pat_io_outcome_history.IoOutcomeHistoryTests.'+n.name for n in cls.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
targets.sort(); assert len(targets)==24
write(NEW/'targets.json',dict(testCount=24,targets=targets))
for name in ['run_attempt.py','attempt_child.py']:
    before=(OLD/name).read_text(); after=before.replace('RefusalHistory29','OutcomeHistory24').replace('refusal29','outcome24')
    after=after.replace('pat-io-refusal-history','pat-io-outcome-history')
    after=after.replace('43834d85b3843409f0402663331dd636339f224aabdf1047c655d512eef65ac1',source_pin)
    after=after.replace('7060','7062').replace('!= 29','!= 24').replace('== 29','== 24').replace("'expectedTests': 29","'expectedTests': 24")
    after=after.replace('test_pat_io_refusal_history.IoRefusalHistoryTests.','test_pat_io_outcome_history.IoOutcomeHistoryTests.')
    ast.parse(after); (NEW/name).write_text(after)
    (NEW/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=(OLD/name).relative_to(ROOT).as_posix(),tofile=(NEW/name).relative_to(ROOT).as_posix())))
(NEW/'README.md').write_text('# Isolated outcome24 pure harness\n\nRun exactly24 new methods against the [frozen source](../implementation01/README.md).\nSee [scope](SCOPE.md) and [selection](targets.json). Historical regressions remain\nseparate; every inherited project/data input is unchanged. Results are retained\nseparately. Launch the parent with python3 -B; it creates the child with -I -S -B.\n')
(NEW/'SCOPE.md').write_text('# Original outcome24 scope\n\nRun only24 independent static-policy and outcome methods over existing acquired\nfixtures. No Runtime, SQLite connection, network, physical port/device, MCU or\nemulator, inference, public service or acquired controller executes. All7060\ninherited project/data files remain unchanged; the project closure is7062 files.\n\nKeep the original180-second execution deadline,16 MiB scratch,8192 inventory\nfiles,256 MiB input collection,16 MiB file,4 MiB receipt and8 MiB log bounds.\nThe child uses -I -S -B, exact package/origin checks and cooperative I/O hooks;\nthis is not an OS sandbox. Original raw scratch remains retained. No protocol\nor effect bound changes. Full matrix qualification and promotion remain false.\nPrimary-agent source and adaptation review is required before release.\n')
print(json.dumps(dict(sourceIndexSha256=source_pin,projectFiles=7062,frozenFiles=len(rows),tests=24,harnessPrepared=True)))
