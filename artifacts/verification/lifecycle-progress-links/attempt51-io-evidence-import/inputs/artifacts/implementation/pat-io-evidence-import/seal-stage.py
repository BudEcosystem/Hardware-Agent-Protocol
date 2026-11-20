"""Seal original sources, attempts and documentation without changing failures."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path.cwd(); BASE=ROOT/'artifacts/implementation/pat-io-evidence-import'
CHECKPOINT=ROOT/'artifacts/verification/lifecycle-progress-links/attempt51-io-evidence-import'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_bytes())
def write(path,value):
    with path.open('x') as stream:stream.write(json.dumps(value,indent=2)+'\n')
def verify(path,row):assert not path.is_symlink() and path.is_file() and path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],str(path)
def inventory(folder):
    rows=[]
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():rows.append(dict(path=path.relative_to(folder).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    return sorted(rows,key=lambda row:row['path'])
report=read(BASE/'RESULTS.json')
assert report['goalStatus']=='active' and report['passingScopes']==23 and report['failingScopes']==1
assert not report['realBoundImportVerified'] and report['rawAndCopiedDatabaseBytesUnchanged']
assert not (BASE/'index.json').exists() and not CHECKPOINT.exists()
for name,pin in report['sourcePins'].items():
    assert sha(BASE/name/'index.json')==pin
    for row in read(BASE/name/'index.json')['files']:verify(ROOT/row['path'],row)
for item in report['attempts']:
    harness=BASE/item['harness']; attempt=BASE/item['attempt']
    assert sha(harness/'index.json')==item['harnessIndexSha256']
    for row in read(harness/'index.json')['files']:verify(harness/row['path'],row)
    result=read(attempt/'result.json'); assert result['status']==item['status'] and result['counts']==item['counts']
    rows=read(attempt/'scratch-index.json'); assert rows==inventory(attempt/'scratch')==inventory(Path(result['scratchPath']))
    for label,folder in [('inputs',attempt/'project'),('frozen',ROOT),('harness',attempt/'harness')]:
        rows=read(attempt/(label+'-before.json')); assert rows==read(attempt/(label+'-after.json'))
        for row in rows:verify(folder/row['path'],row)
links=read(ROOT/'artifacts/verification/project-links.json')
assert not links['missing'] and links['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in links['files']:assert sha(ROOT/row['path'])==row['sha256']
rows=inventory(BASE)
write(BASE/'index.json',dict(scope='Original-run I/O evidence consumer,23 passing storage scopes and one retained reducer-wrapper failure. Full HMS goal active.',files=rows))
CHECKPOINT.mkdir(); names=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
    'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
names += [path.relative_to(ROOT).as_posix() for path in BASE.iterdir() if path.is_file() and path.suffix in ('.py','.md','.json','.log')]
names += [(BASE/'results/README.md').relative_to(ROOT).as_posix()]
names += [(BASE/name/'index.json').relative_to(ROOT).as_posix() for name in report['sourcePins']]
names += [(BASE/row['harness']/'index.json').relative_to(ROOT).as_posix() for row in report['attempts']]
assert len(names)==len(set(names)); copies=[]
for name in sorted(names):
    source=ROOT/name; destination=CHECKPOINT/'inputs'/name; destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,destination)
    row=dict(source=name,copy=destination.relative_to(ROOT).as_posix(),bytes=source.stat().st_size,sha256=sha(source))
    verify(destination,row); copies.append(row)
write(CHECKPOINT/'index.json',dict(scope='Separately pinned original-run evidence consumer; fixture controls and complete legacy-data reduction, with original wrapper failure preserved.',
    stageIndexSha256=sha(BASE/'index.json'),artifactFiles=len(rows),passingScopes=23,failingScopes=1,
    completeMethodReceipts=26,storageControlsPassed=23,pureReducerMethodsReportedPassing=3,
    pureReducerWrapperPassed=False,realBoundImportVerified=False,goalStatus='active',
    markdownFiles=links['project_markdown_files'],localLinks=links['local_links_checked'],missing=[],files=copies))
print(json.dumps(dict(stageFiles=len(rows),stageIndexSha256=sha(BASE/'index.json'),documentCopies=len(copies),
    documentIndexSha256=sha(CHECKPOINT/'index.json'),goalStatus='active')))
