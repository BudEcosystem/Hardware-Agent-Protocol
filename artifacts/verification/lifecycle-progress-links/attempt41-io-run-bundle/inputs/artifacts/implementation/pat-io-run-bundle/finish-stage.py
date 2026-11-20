"""Seal bounded I/O inputs, three complete attempts and documentation evidence."""
import hashlib
import json
from pathlib import Path
import shutil
import stat

ROOT=Path.cwd(); B=ROOT/'artifacts/implementation/pat-io-run-bundle'; R=B/'results'
D=ROOT/'artifacts/verification/lifecycle-progress-links/attempt41-io-run-bundle'
assert not (R/'index.json').exists() and not D.exists()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p,v):
    with p.open('x') as f: f.write(json.dumps(v,indent=2)+'\n')
def verify(p,r):
    assert not p.is_symlink() and p.is_file() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],str(p)
def inventory(folder):
    rows=[]
    for p in sorted(folder.rglob('*')):
        assert not p.is_symlink()
        if p.is_file(): rows.append(dict(path=p.relative_to(folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    return rows
def identity(p):
    s=p.lstat(); assert stat.S_ISDIR(s.st_mode)
    return dict(path=str(p),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode))
sourcepins=['05ac1edd337b0a37d63a96adca30e60bd67cc7551b522de4115e47d40827e0d8',
    'd4923234e678a2acf389178d396128e85a1a2da7d83f78bab29d4a0d8be09452',
    '6c2fb673f490ad592a4aa412d3f0533b5933b60c6b68e49357c38f95536f7a72']
harnesspins=['b07982ea8c150c4e56f264c3d5429057dc0b3a32a27e3a7c7cc8b8749c38b9f4',
    '7004abcb03abdcbc779bd738a89e357b6a4d0dfb57afe7cea682ddf24386a595',
    'a9636b71421e5d3f924907509cef73cda8999df7a8646c2f3045e4f269abce24']
entries=[(B/('implementation%02d'%i),pin,True) for i,pin in enumerate(sourcepins,1)]
entries += [(B/('harness%02d'%i),pin,False) for i,pin in enumerate(harnesspins,1)]
old=ROOT/'artifacts/implementation/pat-io-snapshot-reuse'
entries += [(old/'implementation02','994feaf97781c64c8bc4b236bf426a7b29ff051eac798616d07bc0128d6ea306',True),
    (old/'results','85d7eb32994b47020388dff38d3f150bc02767150211ed95332c289191c0b12e',False)]
verified={}
for folder,pin,rooted in entries:
    assert sha(folder/'index.json')==pin
    rows=read(folder/'index.json')['files']
    for row in rows: verify((ROOT if rooted else folder)/row['path'],row)
    verified[folder.relative_to(ROOT).as_posix()]=len(rows)
baseline=read(B/'implementation01/baseline-inputs.json')['inheritedProjectInputs']; assert len(baseline)==228
for row in baseline:
    p=ROOT/row['path']; rel=p.relative_to(old/'implementation02/project')
    for i in (1,2,3): verify(B/('implementation%02d'%i)/'project'/rel,row)
analysis=read(B/'RESULTS.json'); assert analysis['distinctPassingMethods']==149 and len(analysis['attempts'])==3
assert analysis['qualificationPassed'] is False and analysis['supervisorIntegrated'] is False
assert sha(B/'extend-results.py')==read(B/'analysis-failure.json')['scriptSha256']
delta=read(B/'SOURCE03-IDENTITY-DELTA.json'); assert len(delta['changedFiles'])==37 and len(delta['leaves'])>37
originals={}
for item in analysis['attempts']:
    folder=R/item['attempt']; proof=read(folder/'proof.json'); a=folder/'attempt'; result=read(a/'result.json')
    assert result['childState']=='exited' and result['status']==proof['status']==item['status']
    assert not (Path('/proc')/str(result['pid'])).exists()
    assert result['errors']==result['childErrors']==[] and result['exitCode'] in (0,1)
    assert read(a/'sqlite-connections.json')==[] and proof['sqliteConnections']==0
    assert result['counts']==proof['counts']==item['counts']
    targets=read(B/proof['harness']/'targets.json')['targets']; actual=read(a/'actual-tests.json')
    assert actual['loaded']==actual['executed']==targets and actual['exactSelection']
    assert len(targets)==result['counts']['testsRun']
    if item['status']=='passed': assert result['exitCode']==result['counts']['failures']==result['counts']['errors']==0
    for prefix,base,size in [('inputs',a/'project',230),('frozen',ROOT,233),('harness',a/'harness',6)]:
        rows=read(a/(prefix+'-before.json')); assert rows==read(a/(prefix+'-after.json')) and len(rows)==size
        for row in rows: verify(base/row['path'],row)
    external=read(a/'external-before.json'); assert external==read(a/'external-after.json') and len(external['files'])==159
    for row in external['files']: verify(Path(row['resolvedPath']),row)
    origins=read(a/'imports.json'); assert origins['summary']['allOriginsMatched'] and origins['violations']==origins['prohibitedAttempts']==[]
    for row in origins['records']:
        if 'sha256' in row: assert sha(Path(row['origin']))==row['sha256']
    for label in ('compiler','driver'): assert read(a/(label+'-before.json'))==read(a/(label+'-after.json'))
    raw=Path(proof['rawScratch']['path']); assert identity(raw)==proof['rawScratch']
    before=read(a/'raw-scratch-before.json'); assert identity(raw.parent)==before['parent']
    rows=inventory(raw); assert rows==read(a/'scratch-index.json')==inventory(a/'scratch')
    assert len(rows)==proof['rawScratchFiles']==60 and sum(r['bytes'] for r in rows)==proof['rawScratchBytes']==508951
    original=B/proof['harness']/'attempts'/proof['attempt']; rows=inventory(original)
    assert rows==inventory(a) and len(rows)==proof['attemptFilesAcquired']==324
    originals[item['attempt']]=len(rows)
report=read(ROOT/'artifacts/verification/project-links.json')
assert report['missing']==[] and report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in report['files']: assert sha(ROOT/row['path'])==row['sha256']
rows=inventory(R); write(R/'index.json',dict(scope='Current149pure passes; complete earlier failed148/passed148 retained. No supervisor/device/public qualification.',files=rows))
verified[R.relative_to(ROOT).as_posix()]=len(rows); entries.append((R,sha(R/'index.json'),False))
D.mkdir()
sources=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
    'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
sources += [p.relative_to(ROOT).as_posix() for p in sorted(B.iterdir()) if p.is_file() and p.suffix in ('.py','.md','.patch','.json')]
sources += [(folder/'index.json').relative_to(ROOT).as_posix() for folder,_,_ in entries]
assert len(sources)==len(set(sources)); copies=[]
for name in sources:
    p=ROOT/name; q=D/'inputs'/name; q.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,q)
    row=dict(source=name,copy=q.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)); verify(q,row); copies.append(row)
write(D/'index.json',dict(scope='Bounded pre-run input contract complete; durable supervisor binding, trusted service, hard aggregate storage and public qualification remain. Full goal active.',
    distinctPassingMethods=149,markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'],missing=[],
    originalAttemptFilesReverified=originals,artifactEntriesReverified=verified,reportFileHashesVerified=len(report['files']),files=copies))
print(json.dumps(dict(resultsFiles=len(rows),resultsIndexSha256=sha(R/'index.json'),documentIndexSha256=sha(D/'index.json'),
    documentCopies=len(copies),artifactEntriesReverified=sum(verified.values()),identityDeltaLeaves=len(delta['leaves']),
    markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'])))
