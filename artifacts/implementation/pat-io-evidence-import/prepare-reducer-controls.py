"""Freeze unchanged consumer plus historical-data reducer controls."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path.cwd(); BASE=ROOT/'artifacts/implementation/pat-io-evidence-import'
STAGE=BASE/'implementation02'; PRIOR=BASE/'harness01'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def write(path,value):
    with path.open('x') as stream: stream.write(json.dumps(value,indent=2)+'\n')
def inventory(folder,rooted=False):
    rows=[]
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():
            if path.suffix=='.py': ast.parse(path.read_bytes())
            rows.append(dict(path=path.relative_to(ROOT if rooted else folder).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    return sorted(rows,key=lambda row:row['path'])
old=BASE/'implementation01/project'
for path in old.rglob('*'):
    if path.is_file(): assert sha(path)==sha(STAGE/'project'/path.relative_to(old))
assert len(inventory(STAGE/'project'))==4240
review=[
    'All259 implementation01 project files remain unchanged, including every production consumer/producer file and every earlier test.',
    '3978 original files are byte-pinned to the previously sealed document-validation result, including the complete30-case captured group, pre-run inputs and legacy attempt ledger. A read-only immutable connection extracts its original row; no source/research program is executed during preparation.',
    'Two generated data/provenance documents and one test module are added. The test association is explicitly synthetic. No version2 authority/handoff, store publication or actual worker success is claimed.',
    'Three exact pure-reducer controls: complete30-case semantic reduction, incomplete group even after recomputing transport checksum, and substituted attempt return. No SQL, network, process launch, planning or runtime execution is allowed in these tests.',
    'Original180-second scope,16MiB scratch retention,8192 input files,256MiB acquired input ceiling,16MiB single file and4MiB JSON limits remain unchanged. No execution/effect/worker limits are enlarged.',
    'Primary-agent review only. Actual bound-worker import, source-independent catalog admission, further corruption controls and fresh eligibility remain unfinished.'
]
write(STAGE/'source-review.json',dict(reviewed=review,independentReview=False,releasedBy='primary-agent',
    unchangedInheritedProjectFiles=259,newProductionFiles=0,newTestMethods=3,projectExecutionDuringPreparation=False))
(STAGE/'README.md').write_text('# Complete archived-data reducer controls\n\n[Review](source-review.json), [fixture provenance](project/tests/fixtures/recorded-io-group/PROVENANCE.json). All259 inherited files remain unchanged. A synthetic association around the original legacy30-case capture tests only pure reduction. No new supervisor/handoff or store import is claimed.\n')
rows=inventory(STAGE,True); assert len(rows)==4243
write(STAGE/'index.json',dict(scope='Unchanged consumer and complete legacy-data reduction controls.',files=rows)); pin=sha(STAGE/'index.json')
module='test_io_evidence_reducer.IoEvidenceReducerTests.'
tree=ast.parse((STAGE/'project/tests/test_io_evidence_reducer.py').read_bytes())
cls=next(node for node in tree.body if isinstance(node,ast.ClassDef))
targets=sorted(module+node.name for node in cls.body if isinstance(node,ast.FunctionDef) and node.name.startswith('test_'))
assert len(targets)==3
harness=BASE/'harness24'; harness.mkdir(); (harness/'references').mkdir(); borrowed=[]
for name in ('run_attempt.py','attempt_child.py','references/approved-external-roots.json'):
    source=PRIOR/name; dest=harness/'references'/Path(name).name; shutil.copyfile(source,dest)
    borrowed.append(dict(source=source.relative_to(ROOT).as_posix(),copy=dest.relative_to(harness).as_posix(),bytes=source.stat().st_size,sha256=sha(source)))
write(harness/'borrowed-inputs.json',borrowed); write(harness/'targets.json',dict(testCount=3,targets=targets))
old_targets=read(PRIOR/'targets.json')['targets']
for name in ('run_attempt.py','attempt_child.py'):
    original=(PRIOR/name).read_text(); text=original.replace('25678ecd4d7c3daf4719b51d97fa323da2d2cba3b899d72ee77c7e65bb4adb4c',pin)
    text=text.replace('pat-io-evidence-import/implementation01','pat-io-evidence-import/implementation02').replace("here.parent / 'implementation01'","here.parent / 'implementation02'")
    for before,after in [('len(expected) != 262','len(expected) != 4243'),("'frozenPreparationInputCount': 262","'frozenPreparationInputCount': 4243"),
        ("'projectInputCount': 259","'projectInputCount': 4240"),('len(selected) != 259','len(selected) != 4240'),('exactly 259 files','exactly 4240 files'),
        ("value['testsRun'] == 1","value['testsRun'] == 3"),("'expectedTests': 1","'expectedTests': 3"),("targets['testCount'] != 1","targets['testCount'] != 3"),
        ("len(targets['targets']) != 1","len(targets['targets']) != 3"),("len(set(targets['targets'])) != 1","len(set(targets['targets'])) != 3"),
        ("len(config['targets']) != 1","len(config['targets']) != 3"),("len(set(config['targets'])) != 1","len(set(config['targets'])) != 3")]: text=text.replace(before,after)
    assert text.count(repr(old_targets))==1; text=text.replace(repr(old_targets),repr(targets))
    if name=='attempt_child.py':
        begin=text.index("    if event == 'sqlite3.connect':"); end=text.index("    if event == 'exec':",begin)
        text=text[:begin]+"    if event == 'sqlite3.connect':\n        prohibited.append(event); raise RuntimeError('Pure archived-data reducer must not open a database')\n"+text[end:]
    ast.parse(text); (harness/name).write_text(text)
    (harness/(name+'.patch')).write_text(''.join(difflib.unified_diff(original.splitlines(True),text.splitlines(True),fromfile=str(PRIOR/name),tofile=str(harness/name))))
scope='Three pure-reducer controls over a legacy complete30-case capture; synthetic association only, no worker/database/store authority.'
(harness/'SCOPE.md').write_text('# Exact reducer scope\n\n'+scope+'\n\n[Targets](targets.json), [source](../implementation02/README.md). Original180-second/16MiB scratch limits.\n')
(harness/'README.md').write_text('# Pure archived-data reduction\n\n[Scope](SCOPE.md), [source](../implementation02/README.md).\n')
write(harness/'review.json',dict(scope=scope,tests=3,sourceIndexSha256=pin,targetSha256=sha(harness/'targets.json'),
    reviewed=review,independentReview=False,releasedBy='primary-agent',sqliteConnectionsMaximum=0,projectInputCount=4240,frozenPreparationInputCount=4243))
write(harness/'index.json',dict(scope=scope,files=inventory(harness)))
print(json.dumps(dict(sourceIndexSha256=pin,unchangedPriorProjectFiles=259,projectFiles=4240,frozenFiles=4243,tests=3)))
