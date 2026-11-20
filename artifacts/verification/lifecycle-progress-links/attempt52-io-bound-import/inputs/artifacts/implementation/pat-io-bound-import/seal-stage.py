"""Seal integration evidence, its retained failures and current documentation."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path.cwd(); BASE=ROOT/'artifacts/implementation/pat-io-bound-import'
CHECKPOINT=ROOT/'artifacts/verification/lifecycle-progress-links/attempt52-io-bound-import'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_bytes())
def write(path,value):
    with path.open('x') as stream:stream.write(json.dumps(value,indent=2)+'\n')
def verify(path,row):assert path.is_file() and not path.is_symlink() and path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],str(path)
def inventory(folder):
    rows=[]
    for path in folder.rglob('*'):
        assert not path.is_symlink()
        if path.is_file():rows.append(dict(path=path.relative_to(folder).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    return sorted(rows,key=lambda row:row['path'])
report=read(BASE/'RESULTS.json');assert report['goalStatus']=='active' and report['realOriginalBoundImportVerified']
assert not report['actualIntegrationScopePassed'] and report['passingScopes']==5 and report['failingExecutedScopes']==1
assert not (BASE/'index.json').exists() and not CHECKPOINT.exists()
assert sha(BASE/'implementation01/index.json')==report['sourceIndexSha256']
for row in read(BASE/'implementation01/index.json')['files']:verify(ROOT/row['path'],row)
for item in report['attempts']:
    harness=BASE/item['harness'];attempt=BASE/item['attempt']
    assert sha(harness/'index.json')==item['harnessIndexSha256']
    for row in read(harness/'index.json')['files']:verify(harness/row['path'],row)
    result=read(attempt/'result.json');assert result['status']==item['status'] and result['counts']==item['counts']
    for label,folder in [('inputs',attempt/'project'),('frozen',ROOT),('harness',attempt/'harness')]:
        rows=read(attempt/(label+'-before.json'));assert rows==read(attempt/(label+'-after.json'))
        for row in rows:verify(folder/row['path'],row)
    if item['harness']!='harness02':
        assert inventory(Path(result['scratchPath']))==inventory(attempt/'scratch')==read(attempt/'scratch-index.json')
manifest=read(BASE/'forensic01/raw-manifest.json');raw=Path(manifest['originalScratch']['path'])
for row in manifest['files']:
    verify(raw/row['path'],row)
    if 'copy' in row:verify(BASE/'forensic01'/row['copy'],row)
    else:
        digest=hashlib.sha256();total=0
        for chunk in row['chunks']:
            path=BASE/'forensic01'/chunk['path'];verify(path,chunk);digest.update(path.read_bytes());total+=chunk['bytes']
        assert total==row['bytes'] and digest.hexdigest()==row['sha256']
links=read(ROOT/'artifacts/verification/project-links.json')
assert not links['missing'] and links['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in links['files']:assert sha(ROOT/row['path'])==row['sha256']
rows=inventory(BASE)
write(BASE/'index.json',dict(scope='Real30-case bound worker/import/replay method with retained16MiB-file failure; five passing fixture scopes and unchanged production. Full HMS goal active.',files=rows))
CHECKPOINT.mkdir();names=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
    'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
names += [path.relative_to(ROOT).as_posix() for path in BASE.iterdir() if path.is_file() and path.suffix in ('.py','.md','.json','.log')]
names += [(BASE/name).relative_to(ROOT).as_posix() for name in ('results/README.md','implementation01/index.json','forensic01/audit.json','forensic01/raw-manifest.json')]
names += [(BASE/item['harness']/'index.json').relative_to(ROOT).as_posix() for item in report['attempts']]
assert len(names)==len(set(names));copies=[]
for name in sorted(names):
    source=ROOT/name;dest=CHECKPOINT/'inputs'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    row=dict(source=name,copy=dest.relative_to(ROOT).as_posix(),bytes=source.stat().st_size,sha256=sha(source));verify(dest,row);copies.append(row)
write(CHECKPOINT/'index.json',dict(scope='Actual original-run import/replay evidence with original storage failure retained, exact-deduplication sizing and unfinished full goal.',
    stageIndexSha256=sha(BASE/'index.json'),stageFiles=len(rows),preparationFailures=1,
    executedScopes=6,passingScopes=5,failingExecutedScopes=1,completeMethodReceipts=6,
    realOriginalBoundImportVerified=True,actualIntegrationScopePassed=False,compactStoreImplemented=False,
    originalAuthorityDatabaseBytes=17591296,originalSingleFileLimit=16*1024*1024,
    goalStatus='active',markdownFiles=links['project_markdown_files'],localLinks=links['local_links_checked'],missing=[],files=copies))
print(json.dumps(dict(stageFiles=len(rows),stageIndexSha256=sha(BASE/'index.json'),documentCopies=len(copies),
    documentIndexSha256=sha(CHECKPOINT/'index.json'),goalStatus='active')))
