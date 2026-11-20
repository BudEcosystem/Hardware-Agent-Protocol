"""Seal all attempts, exact private image/output audits and current progress."""
import hashlib
import json
from pathlib import Path
import shutil
import stat

ROOT=Path.cwd();B=ROOT/'artifacts/implementation/pat-io-supervision';R=B/'results'
D=ROOT/'artifacts/verification/lifecycle-progress-links/attempt42-io-supervision'
assert not (R/'index.json').exists() and not D.exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):
    with p.open('x') as f:f.write(json.dumps(v,indent=2)+'\n')
def verify(p,row):assert not p.is_symlink() and p.is_file() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],str(p)
def inventory(folder):
    rows=[]
    for p in folder.rglob('*'):
        assert not p.is_symlink()
        if p.is_file():rows.append(dict(path=p.relative_to(folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    return sorted(rows,key=lambda row:row['path'])
def identity(p):
    s=p.lstat();assert stat.S_ISDIR(s.st_mode)
    return dict(path=str(p),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode))
sources=['9a6f80b9e6eb9893b719d3e93e723f5efd7babe77a22f3e191e5e37a37ba7f3f',
    '89adcc8637d7e0725061f0cf670c7ae1bfecd56350db2f43e775778ceadf99ba',
    '30e8155181a738ace3d02de0f89402d82927dfcbf605fcd5ba1138278a6d70f4']
harnesses=['dbacb4f869df4c97665a3778ee536f2a8dfe130d2daa29a39810f0596429948e',
    'c7eecf1b2eda74db28661778dad01f5cb327c16d286f16c89a095792a5daabef',
    '3372405afb3dcc0cf1e2c3f4d36b74af5d3b1f1b2f5814f2cba45e04ee22033e',
    'a4b75e4d45d0b82daee6552c53f20eb2d5e3de37d7dbcad35a1686a138009aae',
    '2d1da9fd0e926f2f5f920878a31b4cdf44bd7f6d3eb1b78a7136b2eaef89ffc4',
    '43aa9ea2124658a35a9e8e16bab41f525fbe36c74c292a9dcd080a835f849c87']
entries=[(B/('implementation%02d'%i),pin,True) for i,pin in enumerate(sources,1)]
entries += [(B/('harness%02d'%i),pin,False) for i,pin in enumerate(harnesses,1)]
old=ROOT/'artifacts/implementation/pat-io-run-bundle'
entries += [(old/'implementation03','6c2fb673f490ad592a4aa412d3f0533b5933b60c6b68e49357c38f95536f7a72',True),
    (old/'results','e7d4fcae43f47efee2403a991acb84ed51116c61b823fbebfaceebd1d61cb364',False)]
counts={}
for folder,pin,rooted in entries:
    assert sha(folder/'index.json')==pin;rows=read(folder/'index.json')['files']
    for row in rows:verify((ROOT if rooted else folder)/row['path'],row)
    counts[folder.relative_to(ROOT).as_posix()]=len(rows)
assert not (B/'harness02/attempts').exists()
baseline=read(B/'implementation01/baseline-inputs.json')['inheritedProjectInputs'];assert len(baseline)==230
for row in baseline:
    rel=(ROOT/row['path']).relative_to(old/'implementation03/project')
    for i in (1,2,3):verify(B/('implementation%02d'%i)/'project'/rel,row)
analysis=read(B/'RESULTS.json');assert analysis['distinctPassingMethods']==161 and len(analysis['attempts'])==5
assert analysis['qualificationPassed'] is False and analysis['publicQualificationMounted'] is False
passed=set();originals={};identities={}
for item in analysis['attempts']:
    folder=R/item['destination'];p=read(folder/'proof.json');a=folder/'attempt';result=read(a/'result.json')
    assert p['counts']==result['counts']==item['counts'] and p['status']==result['status']==item['status']
    assert result['childState']=='exited' and not (Path('/proc')/str(result['pid'])).exists()
    assert result['errors']==result['childErrors']==[] and result['exitCode'] in (0,1)
    h=B/p['harness'];targets=read(h/'targets.json')['targets'];actual=read(a/'actual-tests.json')
    assert actual['loaded']==actual['executed']==targets and actual['exactSelection']
    if p['status']=='passed':
        assert result['exitCode']==p['counts']['failures']==p['counts']['errors']==0;passed.update(targets)
    for prefix,base,size in [('inputs',a/'project',237),('frozen',ROOT,240),('harness',a/'harness',6)]:
        rows=read(a/(prefix+'-before.json'));assert rows==read(a/(prefix+'-after.json')) and len(rows)==size
        for row in rows:verify(base/row['path'],row)
    external=read(a/'external-before.json');assert external==read(a/'external-after.json') and len(external['files'])==159
    for row in external['files']:verify(Path(row['resolvedPath']),row)
    origins=read(a/'imports.json');assert origins['summary']['allOriginsMatched'] and origins['violations']==origins['prohibitedAttempts']==[]
    for row in origins['records']:
        if 'sha256' in row:assert sha(Path(row['origin']))==row['sha256']
    for label in ('compiler','driver'):
        value=read(a/(label+'-before.json'));assert value==read(a/(label+'-after.json'))
        if label in identities:assert value==identities[label]
        else:identities[label]=value
    raw=Path(p['rawScratch']['path']);assert identity(raw)==p['rawScratch']
    before=read(a/'raw-scratch-before.json');assert identity(raw.parent)==before['parent']
    rows=inventory(raw);assert rows==inventory(a/'scratch')==read(a/'scratch-index.json')
    assert len(rows)==p['rawScratchFiles'] and sum(r['bytes'] for r in rows)==p['rawScratchBytes']<=read(h/'review.json')['scratchBytesCeiling']
    assert len(read(a/'sqlite-connections.json'))==p['sqliteConnections']==item['parentSqliteConnections']
    original=h/'attempts'/p['attempt'];rows=inventory(original)
    assert rows==inventory(a) and len(rows)==p['attemptFilesAcquired'];originals[item['destination']]=len(rows)
assert len(passed)==161
failure=read(R/'attempt05-passed-gpio/failure.json');assert failure['allRawCopyAndIndexEntriesEqual']
assert failure['scriptSha256']==sha(ROOT/failure['script'])
owned=read(R/'attempt06-acquired-gpio/owned-audit.json');assert owned['codeImageExactClosure'] and owned['ledgerDatabaseUnchanged']
assert owned['outputClosure']==analysis['outputClosure'] and owned['cases']==30 and owned['claims']==owned['owners']==0
assert read(R/'attempt06-acquired-gpio/storage-audit.json')['databaseBytesUnchanged']
report=read(ROOT/'artifacts/verification/project-links.json');assert report['missing']==[] and report['checker_sha256']==sha(ROOT/'scripts/check_project_links.py')
for row in report['files']:assert sha(ROOT/row['path'])==row['sha256']
rows=inventory(R);write(R/'index.json',dict(scope='161distinct passes including actual owned GPIO and independent semantics; all failures retained. No quota/public/physical qualification.',files=rows))
counts[R.relative_to(ROOT).as_posix()]=len(rows);entries.append((R,sha(R/'index.json'),False))
D.mkdir()
names=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','scripts/check_project_links.py',
    'artifacts/verification/project-links.json','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md']
names += [p.relative_to(ROOT).as_posix() for p in sorted(B.iterdir()) if p.is_file() and p.suffix in ('.md','.py','.json','.patch')]
names += [(folder/'index.json').relative_to(ROOT).as_posix() for folder,_,_ in entries]
assert len(names)==len(set(names));copies=[]
for name in names:
    p=ROOT/name;q=D/'inputs'/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
    row=dict(source=name,copy=q.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p));verify(q,row);copies.append(row)
write(D/'index.json',dict(scope='Owned synthetic GPIO process path verified; PWM/failure recovery, fixed service configuration, enforced storage and public qualification remain. Full goal active.',
    distinctPassingMethods=161,markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'],missing=[],
    originalAttemptFilesReverified=originals,artifactEntriesReverified=counts,reportFileHashesVerified=len(report['files']),files=copies))
print(json.dumps(dict(resultsFiles=len(rows),resultsIndexSha256=sha(R/'index.json'),documentIndexSha256=sha(D/'index.json'),
    documentCopies=len(copies),artifactEntriesReverified=sum(counts.values()),markdownFiles=report['project_markdown_files'],localLinks=report['local_links_checked'])))
