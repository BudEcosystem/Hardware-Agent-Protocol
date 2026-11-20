"""One bounded candidate attempt; stop and retain state on first failure."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ATTEMPT = HERE / 'attempt01'
PRIOR = ROOT / 'artifacts/implementation/statx-mount-provider'
COST = ROOT / 'artifacts/implementation/hierarchical-chunk-store'
ENV = {'PATH':'/usr/bin:/bin', 'LANG':'C', 'LC_ALL':'C', 'PYTHONDONTWRITEBYTECODE':'1'}
SCOPES = ['hierarchy','data','namespace','bounds','recovery','corruption','orphan_recovery','owner_loss','fault']


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True); stream.write('\n')
        stream.flush(); os.fsync(stream.fileno())


def baseline():
    path = ROOT / 'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(path) == 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    rows = read(path)['files']
    assert len(rows) == 244 and all(digest(ROOT / row['path']) == row['sha256'] for row in rows)
    return dict(receiptSha256=digest(path), filesExact=len(rows))


def sealed(directory, wanted):
    assert digest(directory / 'index.json') == wanted
    rows = read(directory / 'index.json')['files']
    assert all(digest(directory / row['path']) == row['sha256'] for row in rows)
    return dict(indexSha256=wanted, filesExact=len(rows))


def limits(cpu):
    for key, amount in [(resource.RLIMIT_CPU,cpu), (resource.RLIMIT_AS,512*1024**2),
            (resource.RLIMIT_FSIZE,16*1024**2), (resource.RLIMIT_NOFILE,128), (resource.RLIMIT_CORE,0)]:
        resource.setrlimit(key, (amount,amount))


def run(name, argv, env, wall=60, cpu=40):
    work = ATTEMPT / name; work.mkdir(mode=0o700)
    save(work / 'intent.json', dict(argv=argv, environment=env, cwd=str(work), wallSeconds=wall,
         cpuSeconds=cpu, addressSpaceBytes=512*1024**2, fileBytes=16*1024**2, descriptors=128))
    started = time.monotonic(); timed_out = False
    with (work/'stdout.txt').open('xb') as out, (work/'stderr.txt').open('xb') as err:
        proc = subprocess.Popen(argv, cwd=work, env=env, stdout=out, stderr=err,
                                start_new_session=True, preexec_fn=lambda: limits(cpu))
        save(work/'started.json', dict(pid=proc.pid, processGroup=proc.pid, unix=time.time()))
        while True:
            pid, status, usage = os.wait4(proc.pid, os.WNOHANG)
            if pid:
                break
            if time.monotonic()-started >= wall:
                timed_out=True; os.killpg(proc.pid, signal.SIGKILL)
                pid, status, usage = os.wait4(proc.pid, 0); break
            time.sleep(.1)
        proc.returncode=os.waitstatus_to_exitcode(status)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out.flush(); err.flush(); os.fsync(out.fileno()); os.fsync(err.fileno())
    result = dict(returnCode=proc.returncode, timedOut=timed_out, reaped=True,
                  elapsedSeconds=time.monotonic()-started, cpuSeconds=usage.ru_utime+usage.ru_stime,
                  peakRSSKiB=usage.ru_maxrss)
    save(work/'result.json', result)
    if proc.returncode or timed_out:
        raise RuntimeError(name + ' failed or inconclusive; matrix stopped')
    return work


def main():
    os.umask(0o077); assert not ATTEMPT.exists()
    before=baseline()
    prior=sealed(PRIOR,'4f095672f8184289086f7688c19325df79eb781aa122194f416ed961af553159')
    cost=sealed(COST,'8916d9e9a431fb0135d743daf38b746b5248cd81aee20dc4f92c9c645e33e26a')
    ATTEMPT.mkdir(mode=0o700); frozen=ATTEMPT/'frozen-inputs'; frozen.mkdir(mode=0o700)
    old=frozen/'original'; old.mkdir(mode=0o700)
    names=['PLAN.md','REVIEW.md','run_scopes.py','sync_probe.c','test_sync_probe.c','sync_identity.py','sync_controls.py','mount_identity.py',
           'mount_controls.py','fixed_block.py','provider.patch','candidate.py','hierarchical_store.py',
           'chunk_store_base.py','native.py','controls.py','controls.patch','diagnostic.py','diagnostic.patch','test_fixed_block.py']
    sources=[(HERE/name,frozen/name) for name in names]
    sources += [(PRIOR/'attempt01/frozen-inputs/dataset.json',frozen/'dataset.json')]
    sources += [(PRIOR/name,old/name) for name in ['hierarchical_store.py','chunk_store_base.py','native.py','fixed_block.py','candidate.py','mount_identity.py']]
    sources += [(HERE/'diagnostic.py',old/'diagnostic.py')]
    sources += [(PRIOR/'attempt01/mount-probe.so',ATTEMPT/'mount-probe.so')]
    sources += [(PRIOR/'attempt01/hierarchical-store.so',target/'hierarchical-store.so') for target in [ATTEMPT,frozen,old]]
    rows=[]
    for source,target in sources:
        with target.open('xb') as stream:
            stream.write(source.read_bytes()); stream.flush(); os.fsync(stream.fileno())
        rows.append(dict(path=str(source.relative_to(ROOT)), frozen=str(target.relative_to(ATTEMPT)), sha256=digest(target)))
    dataset=read(frozen/'dataset.json'); source_root=Path(dataset['sourceRoot'])
    assert len(dataset['files'])==4270 and len(dataset['directories'])==169
    assert sum(row['bytes'] for row in dataset['files'])==35508922
    assert all(digest(source_root/row['path'])==row['sha256'] for row in dataset['files'])
    compiler=Path('/usr/bin/cc').resolve(strict=True); compiler_hash=digest(compiler)
    save(ATTEMPT/'inputs.json',dict(files=rows,compiler=str(compiler),compilerSha256=compiler_hash,
         baselineBefore=before,prior=prior,cost=cost,datasetSha256=digest(frozen/'dataset.json')))
    report=dict(status='incomplete',scopes={},publicRuntimeChanged=False,serviceStorageQualified=False,
         actualMountChanges=False,sqliteTested=False,checksDisabled=False,durabilityBarriersDisabled=False,
         syncSelectionChanged=True,geometryChanged=False)
    try:
        run('compiler-version',[str(compiler),'--version'],ENV,30,20)
        dependency=run('header-dependencies',[str(compiler),'-std=c11','-M',str(frozen/'sync_probe.c')],ENV,30,20)
        paths=(dependency/'stdout.txt').read_text().replace('\\\n',' ').split(':',1)[1].split()
        headers=[Path(p).resolve(strict=True) for p in paths]
        save(ATTEMPT/'headers.json',[dict(path=str(p),sha256=digest(p)) for p in sorted(set(headers))])
        library=ATTEMPT/'sync-probe.so'
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror']
        run('build-helper',[str(compiler),*flags,'-shared','-fPIC',str(frozen/'sync_probe.c'),'-o',str(library)],ENV,30,20)
        test=ATTEMPT/'test-sync-probe'
        run('build-native-controls',[str(compiler),*flags,str(frozen/'test_sync_probe.c'),'-o',str(test)],ENV,30,20)
        report['syncLibrarySha256']=digest(library)
        report['mountLibrarySha256']=digest(ATTEMPT/'mount-probe.so')
        report['librarySha256']=digest(ATTEMPT/'hierarchical-store.so')
        assert report['librarySha256']=='7049dc14940b0f686f5cbe682e85f70944a8074936786e7f962c6ee29ed321de'
        env={**ENV,'HMS_LIBRARY':str(ATTEMPT/'hierarchical-store.so'),'HMS_LIBRARY_SHA256':report['librarySha256'],
             'HMS_MOUNT_LIBRARY':str(ATTEMPT/'mount-probe.so'),'HMS_MOUNT_LIBRARY_SHA256':report['mountLibrarySha256'],
             'HMS_SYNC_LIBRARY':str(library),'HMS_SYNC_LIBRARY_SHA256':report['syncLibrarySha256']}
        work=run('native-controls',[str(test)],ENV)
        result=read(work/'stdout.txt'); assert result['status']=='passed' and result['checks']==9
        report['scopes']['native-controls']=result
        work=run('mount-controls',[sys.executable,'-B',str(frozen/'mount_controls.py')],env)
        result=read(work/'checks.json'); assert result==read(work/'stdout.txt') and result['status']=='passed'
        assert len(result['checks'])==len(set(result['checks']))
        report['scopes']['mount-controls']=dict(checks=len(result['checks']),receiptSha256=digest(work/'checks.json'))
        work=run('provider-controls',[sys.executable,'-B',str(frozen/'test_fixed_block.py')],
                 {**env,'HMS_BLOCK_TEST_ROOT':str(ATTEMPT/'provider-controls')})
        result=read(work/'stdout.txt'); assert result==dict(tests=24,failures=0,errors=0,passed=True)
        report['scopes']['provider-controls']=result
        work=run('sync-controls',[sys.executable,'-B',str(frozen/'sync_controls.py')],env)
        result=read(work/'checks.json'); assert result==read(work/'stdout.txt') and result['status']=='passed'
        assert len(result['checks'])==len(set(result['checks']))
        report['scopes']['sync-controls']=dict(checks=len(result['checks']),receiptSha256=digest(work/'checks.json'))
        print(json.dumps(dict(status='passed',scopes=['native-controls','mount-controls','provider-controls','sync-controls'])),flush=True)
        for name in SCOPES:
            work=run(name,[sys.executable,'-B',str(frozen/'controls.py'),name],env)
            result=read(work/'checks.json'); assert result==read(work/'stdout.txt') and result['status']=='passed'
            report['scopes'][name]=dict(checks=len(result['checks']),receiptSha256=digest(work/'checks.json'))
            print(json.dumps(dict(scope=name,checks=len(result['checks']),status='passed')),flush=True)
        assert sum(report['scopes'][name]['checks'] for name in SCOPES)==96
        outputs={}
        for name,inputs,selected in [('comparison-original',old,env),('comparison-candidate',frozen,env)]:
            work=run(name,[sys.executable,'-B',str(inputs/'diagnostic.py'),'coarse'],selected)
            result=read(work/'diagnostic.json'); assert result['status']=='passed' and len(result['steps'])==426
            outputs[name]=result
            report['scopes'][name]=dict(receiptSha256=digest(work/'diagnostic.json'),
                                       cpuSeconds=result['cpuSeconds'],elapsedSeconds=result['elapsedSeconds'],providerSyncCalls=result['providerSyncCalls'])
        left,right=outputs.values()
        for key in ['expectedFiles','firstOwnerCallbacks','coldOwnerCallbacks']:
            assert left[key]==right[key],key
        assert {k:v for k,v in left['backingHashes'].items() if k!='manifest'}=={k:v for k,v in right['backingHashes'].items() if k!='manifest'}
        assert left['backingHashes']['manifest']!=right['backingHashes']['manifest']
        for a,b in zip(left['steps'],right['steps']):
            assert {k:v for k,v in a.items() if k not in ('wallNs','cpuNs')}=={k:v for k,v in b.items() if k not in ('wallNs','cpuNs')}
        assert right['providerSyncCalls']['fsync']<left['providerSyncCalls']['fsync']
        assert right['providerSyncCalls']['wait']>0 and left['providerSyncCalls']['wait']==0
        report['comparisonEquivalent']=True
        print(json.dumps(dict(scope='comparison',status='passed',timings={k:report['scopes'][k] for k in outputs})),flush=True)
        for name in ['replay_write','replay_read']:
            selected={**env,'HMS_REPLAY_WRITER':str(ATTEMPT/'replay_write')} if name=='replay_read' else env
            work=run(name,[sys.executable,'-B',str(frozen/'controls.py'),name],selected,180,120)
            result=read(work/'checks.json'); assert result==read(work/'stdout.txt') and result['status']=='passed'
            report['scopes'][name]=dict(checks=len(result['checks']),receiptSha256=digest(work/'checks.json'))
            print(json.dumps(dict(scope=name,status='passed')),flush=True)
        report['status']='passed'
    except BaseException as error:
        report['status']='failed-or-inconclusive'; report['error']=f'{type(error).__name__}: {error}'
    finally:
        assert all(digest(ROOT/row['path'])==digest(ATTEMPT/row['frozen'])==row['sha256'] for row in rows)
        assert digest(compiler)==compiler_hash
        if (ATTEMPT/'headers.json').exists():
            assert all(digest(Path(row['path']))==row['sha256'] for row in read(ATTEMPT/'headers.json'))
        if 'syncLibrarySha256' in report:
            assert digest(ATTEMPT/'sync-probe.so')==report['syncLibrarySha256']
        if 'mountLibrarySha256' in report:
            assert digest(ATTEMPT/'mount-probe.so')==report['mountLibrarySha256']
        assert all(digest(source_root/row['path'])==row['sha256'] for row in dataset['files'])
        report['baselineAfter']=baseline(); report['inputsStable']=True
        files=[p for p in HERE.rglob('*') if p.is_file()]
        report['allocatedBytes']=sum(p.stat().st_blocks*512 for p in files)
        assert all(p.stat().st_size<=16*1024**2 for p in files) and report['allocatedBytes']<1024**3
        save(ATTEMPT/'RESULTS.json',report)
    print(json.dumps(report,sort_keys=True),flush=True)
    if report['status']!='passed':
        raise SystemExit(1)


if __name__=='__main__':
    main()
