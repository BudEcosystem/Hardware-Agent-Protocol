"""Acquire both failed timing-reader attempts without running project code."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat

ROOT=Path.cwd().resolve();BASE=ROOT/'artifacts/implementation/pat-io-timing-challenges';OUT=BASE/'results/attempts01-02'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(p,row):
    assert p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],str(p)
def inventory(folder):
    rows=[]
    for p in sorted(folder.rglob('*')):
        assert not p.is_symlink()
        if p.is_dir():continue
        assert stat.S_ISREG(p.stat().st_mode)
        rows.append(dict(path=p.relative_to(folder).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    return rows
def identity(p):
    s=p.lstat();assert stat.S_ISDIR(s.st_mode)
    return dict(path=str(p),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode))
def verify_index(folder,pin,rooted=False):
    assert sha(folder/'index.json')==pin;rows=read(folder/'index.json')['files']
    for row in rows:verify((ROOT if rooted else folder)/row['path'],row)
    return len(rows)
assert verify_index(BASE/'implementation01','adb63bce663e249d06b1c46bec3d04fed6d1111e43796dd56c9567211bcbd381',True)==7073
summaries=[]
for number,harness,name,count,pin,target in [
    ('01','harness01','attempt01-gpio9',9,'8200dc8c5c2ed0fda1ef487707da1a3a899fd279cb9fb6cf22eb26f266740c43','6bae4b76ebe7c7572737df7151c72e53e0d19723f0861ee95fbd92a9da45cd04'),
    ('02','harness02','attempt02-pwm8',8,'c7c18267b43f66707edeeaa4fc22ae362a2c8fb65c7d2d207bc2388349461fa3','a6e04e9ee69b5749b229e8614136e5be2cf950d0e70ee67dc477a07f4d78c545')]:
    H=BASE/harness;assert verify_index(H,pin)==12;A=H/'attempts'/name;result=read(A/'result.json')
    assert result['status']=='failed' and not result['currentPass'] and result['exitCode']==1 and result['childState']=='exited'
    assert not Path('/proc/'+str(result['pid'])).exists() and result['timeoutSeconds']==180
    assert result['counts']==dict(testsRun=count,failures=0,errors=2,skips=0,expectedFailures=0,unexpectedSuccesses=0)
    assert result['errors']==result['childErrors']==[]
    for prefix,folder,n in [('inputs',A/'project',7070),('frozen',ROOT,7073),('harness',A/'harness',6)]:
        rows=read(A/(prefix+'-before.json'));assert rows==read(A/(prefix+'-after.json')) and len(rows)==n
        for row in rows:verify(folder/row['path'],row)
    ext=read(A/'external-before.json');assert ext==read(A/'external-after.json') and len(ext['files'])==159
    for row in ext['files']:verify(Path(row['resolvedPath']),row)
    assert sha(A/'harness/targets.json')==target;targets=read(A/'harness/targets.json')['targets'];actual=read(A/'actual-tests.json')
    assert actual['loaded']==actual['executed']==targets and len(targets)==count
    origins=read(A/'imports.json');assert origins['summary']['allOriginsMatched'] and origins['violations']==origins['prohibitedAttempts']==[]
    for row in origins['records']:
        if 'sha256'in row:assert sha(Path(row['origin']))==row['sha256']
    for label in ['compiler','driver']:assert read(A/(label+'-before.json'))==read(A/(label+'-after.json'))
    raw=Path(result['scratchPath']);before=read(A/'raw-scratch-before.json');assert identity(raw)==before['identity'] and identity(raw.parent)==before['parent']
    raw_rows=inventory(raw);assert raw_rows==inventory(A/'scratch')==read(A/'scratch-index.json')
    assert len(raw_rows)<=8192 and sum(r['bytes']for r in raw_rows)<=16*1024*1024
    cases=[];connections=set()
    for test in targets:
        method=test.split('.')[-1];d=A/'scratch'/method
        if method=='test_timing_invalid_or_unsupported_plan_refuses_before_runtime':
            assert read(d/'refusal-audit.json')==dict(testId=test,refusals=4,runtimeConstructed=False)
            assert not list((d/'trial-0').iterdir());continue
        manifest=read(d/'engine-0.json');trial=d/'trial-0';assert manifest['testId']==test and manifest['directory']==str(raw/method/'trial-0')
        assert manifest['closed'] and manifest['cleanupErrors']==[]
        worker=read(d/'trial-manifest.json');assert worker['closed'] and worker['records']==manifest['records'] and worker['configuration']==manifest['configuration']
        assert worker['qualificationPassed'] is False and worker['requiredMatrixCoverageChecked'] is False
        requested=read(d/'requested-case.json');assert requested['case']==manifest['expectedCase'] and requested['expectedAuthority']==manifest['expectedAuthority']
        record_sets=[]
        for folder,refs,profile in [('records',manifest['records'],'hms.pat.io-trial-record/0.1'),('configuration',manifest['configuration']['records'],'hms.pat.io-configuration-record/0.1')]:
            docs={}
            for i,row in enumerate(refs):
                assert row['path']=='%06d.json'%i and row['bytes']<=65536;verify(trial/folder/row['path'],row)
                doc=read(trial/folder/row['path']);assert doc['profile']==profile;docs[row['path']]=doc
            assert {p.name for p in (trial/folder).iterdir()}==set(docs);record_sets.append(docs)
        docs,cd=record_sets;pair_refs=[p['checkpoint']for p in manifest['configuration']['snapshots']]
        assert pair_refs==[r for r in manifest['records']if docs[r['path']]['kind']=='checkpoint']
        for pair in manifest['configuration']['snapshots']:
            cp=docs[pair['checkpoint']['path']]['value'];side=cd[pair['configuration']['path']]['value'];assert side['checkpoint']==pair['checkpoint']
            assert all(side[k]==cp[k]for k in ('phase','label','wallMs','monotonicMs','clockEpoch'))
            assert len(cp['tables'])==29 and len(side['tables'])==15
            for value,lookup in [(cp,docs),(side,cd)]:
                for table in value['tables']:
                    n=0
                    for page in table['pages']:
                        item=lookup[page['path']]['value'];assert item['first']==n and item['totalRows']==table['rowCount'] and item['table']==table['table'];n+=len(item['rows'])
                    assert n==table['rowCount']
        failed=method in {'test_timing_latest_start_equal','test_timing_lease_wait_equal'}
        if failed:assert manifest['inspectionError']=='IoConfigurationError:PAT_IO_CONFIGURATION_REFUSAL_CAUSE' and 'independentTimingInspection'not in manifest
        else:assert manifest['independentTimingInspection']['expectedResponseVerified'] and not manifest['independentTimingInspection']['qualificationPassed']
        dbs=list((trial/'state').glob('*.db'));assert len(dbs)==2
        connections.update((test,str(raw/method/'trial-0/state'/p.name))for p in dbs)
        cases.append(dict(testId=test,inspectionFailed=failed,executionRecords=len(docs),configurationRecords=len(cd),checkpoints=len(pair_refs)))
    assert len(cases)==8 and sum(c['inspectionFailed']for c in cases)==2
    assert {(r['testId'],r['database'])for r in read(A/'sqlite-connections.json')}==connections and len(connections)==16
    log=(A/'output.log').read_text();match=re.search(r'Ran '+str(count)+r' tests in ([0-9.]+)s',log);assert match and log.endswith('FAILED (errors=2)\n')
    rows=inventory(A);shutil.copytree(A,OUT/('attempt'+number));assert inventory(OUT/('attempt'+number))==rows==inventory(A)
    summaries.append(dict(attempt=name,status='failed',counts=result['counts'],testSeconds=float(match.group(1)),elapsedSeconds=result['elapsedSeconds'],
        actualOrigins=origins['summary'],bytecodeReadsRefused=len(origins['deniedBytecodeReads']),rawScratch=before['identity'],
        rawScratchFiles=len(raw_rows),rawScratchBytes=sum(r['bytes']for r in raw_rows),attemptFilesAcquired=len(rows),cases=cases))
proof=dict(scope='Two failed verifier attempts: runtime captures completed, four expiry inspections refused by configuration cause handling.',
    sourceFilesVerified=7070,frozenFilesVerified=7073,externalPinsVerified=159,actualOriginHashesRechecked=True,
    originalsAndCompleteCopiesRetained=True,sourceAndCompilerDriverStable=True,attempts=summaries,
    qualificationPassed=False,requiredMatrixCoverageChecked=False,physicalMeasurementChecked=False)
with(OUT/'proof.json').open('x')as f:f.write(json.dumps(proof,indent=2)+'\n')
print(json.dumps([dict(attempt=s['attempt'],counts=s['counts'],acquiredFiles=s['attemptFilesAcquired'],rawFiles=s['rawScratchFiles'],rawBytes=s['rawScratchBytes'])for s in summaries]))
