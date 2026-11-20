"""Acquire terminal clock attempts and original raw state; no project imports."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat

ROOT=Path.cwd().resolve();BASE=ROOT/'artifacts/implementation/pat-io-clock-challenges';OUT=BASE/'results/attempts01-02'
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
assert verify_index(BASE/'implementation01','83df5455e2a0ecd21ccc2c9aeb42ffbcc80ba6f7dd2483ff4cb4ba44ad087f40',True)==7076
summaries=[];all_methods=[]
for number,harness,name,count,pin,target in [
    ('01','harness01','attempt01-clock46',46,'c7de4e6813e4193ae0567ddc70e7a60921aecf820ef6f9ae3aada891a3f71013','66564235018590143573940df0d25e3dee8c7b86081a171cc29a1da17fc736cc'),
    ('02','harness02','attempt02-legacy4',4,'fa6f4df49dc4bf8dd2d6cfa944cc96ccc08e5107f68168ee2d13dc75b9389330','9d03a9e7089749c44851edd784aa57ca0cc31046cff0598d7158b3dbcd0a21c5')]:
    H=BASE/harness;assert verify_index(H,pin)==12;A=H/'attempts'/name;result=read(A/'result.json')
    assert result['status'] in {'passed','failed'} and result['childState']=='exited'
    assert result['currentPass'] is (result['status']=='passed') and result['exitCode'] in {0,1}
    assert not Path('/proc/'+str(result['pid'])).exists() and result['timeoutSeconds']==180
    assert result['counts']['testsRun']==count and result['counts']['skips']==result['counts']['expectedFailures']==result['counts']['unexpectedSuccesses']==0
    assert result['errors']==result['childErrors']==[]
    if result['status']=='passed':
        assert result['exitCode']==0 and result['counts']['failures']==result['counts']['errors']==0
    for prefix,folder,n in [('inputs',A/'project',7073),('frozen',ROOT,7076),('harness',A/'harness',6)]:
        rows=read(A/(prefix+'-before.json'));assert rows==read(A/(prefix+'-after.json')) and len(rows)==n
        for row in rows:verify(folder/row['path'],row)
    external=read(A/'external-before.json');assert external==read(A/'external-after.json') and len(external['files'])==159
    for row in external['files']:verify(Path(row['resolvedPath']),row)
    assert sha(A/'harness/targets.json')==target;targets=read(A/'harness/targets.json')['targets'];actual=read(A/'actual-tests.json')
    assert actual['loaded']==actual['executed']==targets and len(targets)==count;all_methods.extend(targets)
    origins=read(A/'imports.json');assert origins['summary']['allOriginsMatched'] and origins['violations']==origins['prohibitedAttempts']==[]
    for row in origins['records']:
        if 'sha256' in row:assert sha(Path(row['origin']))==row['sha256']
    for label in ('compiler','driver'):assert read(A/(label+'-before.json'))==read(A/(label+'-after.json'))
    raw=Path(result['scratchPath']);before=read(A/'raw-scratch-before.json')
    assert identity(raw)==before['identity'] and identity(raw.parent)==before['parent']
    raw_rows=inventory(raw);assert raw_rows==inventory(A/'scratch')==read(A/'scratch-index.json')
    assert len(raw_rows)<=8192 and sum(r['bytes'] for r in raw_rows)<=16*1024*1024
    cases=[];connections=set()
    runtime_targets=[t for t in targets if not t.startswith('test_pat_io_transcript.')]
    for test in runtime_targets:
        method=test.split('.')[-1];d=A/'scratch'/method
        if method=='test_unsupported_clock_plan_refuses_before_runtime':
            assert read(d/'refusal-audit.json')==dict(testId=test,refusals=2,runtimeConstructed=False)
            assert not list((d/'trial-0').iterdir());continue
        trial=d/'trial-0';dbs=list((trial/'state').glob('*.db'));assert len(dbs)==2
        connections.update((test,str(raw/method/'trial-0/state'/p.name)) for p in dbs)
        manifest=read(d/'engine-0.json');assert manifest['testId']==test and manifest['directory']==str(raw/method/'trial-0')
        assert manifest['closed'] and manifest['cleanupErrors']==[]
        streams=[]
        for folder,refs,profile in [('records',manifest['records'],'hms.pat.io-trial-record/0.3' if count==46 else 'hms.pat.io-trial-record/0.1'),
                                   ('configuration',manifest['configuration']['records'],'hms.pat.io-configuration-record/0.1')]:
            docs={}
            for i,row in enumerate(refs):
                assert row['path']=='%06d.json'%i and row['bytes']<=65536;verify(trial/folder/row['path'],row)
                doc=read(trial/folder/row['path']);assert doc['profile']==profile;docs[row['path']]=doc
            assert {p.name for p in (trial/folder).iterdir()}==set(docs);streams.append(docs)
        docs,cd=streams;pair_refs=[p['checkpoint'] for p in manifest['configuration']['snapshots']]
        assert pair_refs==[r for r in manifest['records'] if docs[r['path']]['kind']=='checkpoint']
        for pair in manifest['configuration']['snapshots']:
            cp=docs[pair['checkpoint']['path']]['value'];side=cd[pair['configuration']['path']]['value'];assert side['checkpoint']==pair['checkpoint']
            assert all(side[k]==cp[k] for k in ('phase','label','wallMs','monotonicMs','clockEpoch'))
            assert len(cp['tables'])==29 and len(side['tables'])==15
            for value,lookup in [(cp,docs),(side,cd)]:
                for table in value['tables']:
                    n=0
                    for page in table['pages']:
                        item=lookup[page['path']]['value'];assert item['first']==n and item['totalRows']==table['rowCount'] and item['table']==table['table'];n+=len(item['rows'])
                    assert n==table['rowCount']
        row=dict(testId=test,executionRecords=len(docs),configurationRecords=len(cd),checkpoints=len(pair_refs))
        if count==46:
            worker=read(d/'trial-manifest.json');requested=read(d/'requested-case.json')
            assert worker['closed'] and worker['records']==manifest['records'] and worker['configuration']==manifest['configuration']
            assert worker['qualificationPassed'] is False and worker['independentOutcomeChecked'] is False
            assert requested['case']==manifest['expectedCase'] and requested['expectedAuthority']==manifest['expectedAuthority']
            assert requested['expectedSetup']=={docs[r['path']]['kind']:docs[r['path']]['value'] for r in manifest['records'][:4]}
            assert worker['clockControls']==[v['value'] for v in docs.values() if v['kind']=='clock_control']
            assert len((d/'trial-manifest.json').read_bytes())<=65536 and manifest['configuration']['combinedRecords']+1<=4096
            assert manifest['configuration']['combinedBytes']+(d/'trial-manifest.json').stat().st_size<=16*1024*1024
            row.update(scenario=requested['case']['definition']['scenario'],inspectionError=manifest.get('inspectionError'),
                       structuralInspectionPresent='independentClockInspection' in manifest)
            if 'independentClockInspection' in manifest:
                checked=manifest['independentClockInspection'];assert checked['exactClockControlScheduleChecked']
                assert checked['qualificationPassed'] is checked['independentOutcomeChecked'] is checked['expectedResponseVerified'] is False
            if result['status']=='passed':assert row['inspectionError'] is None and row['structuralInspectionPresent']
        cases.append(row)
    assert len(cases)==(6 if count==46 else 4)
    assert {(r['testId'],r['database']) for r in read(A/'sqlite-connections.json')}==connections and len(connections)==2*len(cases)
    log=(A/'output.log').read_text();match=re.search(r'Ran '+str(count)+r' tests in ([0-9.]+)s',log);assert match
    if result['status']=='passed':assert log.endswith('\nOK\n')
    rows=inventory(A);shutil.copytree(A,OUT/('attempt'+number));assert inventory(OUT/('attempt'+number))==rows==inventory(A)
    summaries.append(dict(attempt=name,status=result['status'],counts=result['counts'],testSeconds=float(match.group(1)),elapsedSeconds=result['elapsedSeconds'],
        actualOrigins=origins['summary'],bytecodeReadsRefused=len(origins['deniedBytecodeReads']),rawScratch=before['identity'],
        rawScratchFiles=len(raw_rows),rawScratchBytes=sum(r['bytes'] for r in raw_rows),attemptFilesAcquired=len(rows),cases=cases))
assert len(all_methods)==len(set(all_methods))==50
proof=dict(scope='Clock/control captures and structural inspection, plus unchanged transcript/configured regressions. Full semantic clock history remains pending.',
    sourceFilesVerified=7073,frozenFilesVerified=7076,externalPinsVerified=159,actualOriginHashesRechecked=True,
    originalsAndCompleteCopiesRetained=True,sourceAndCompilerDriverStable=True,attempts=summaries,
    qualificationPassed=False,requiredMatrixCoverageChecked=False,independentClockOutcomeChecked=False,physicalMeasurementChecked=False)
with (OUT/'proof.json').open('x')as f:f.write(json.dumps(proof,indent=2)+'\n')
print(json.dumps([dict(attempt=s['attempt'],status=s['status'],counts=s['counts'],acquiredFiles=s['attemptFilesAcquired'],rawFiles=s['rawScratchFiles'],rawBytes=s['rawScratchBytes']) for s in summaries]))
