"""Independent read-only reconstruction and process/source joins."""
import fcntl
import stat
import hashlib
import importlib.util
import json
import os
from pathlib import Path

HERE=Path(os.environ['HMS_AUDIT_STAGE']);ROOT=HERE.parents[2];ATTEMPT=HERE/'attempt01'
FROZEN=ATTEMPT/'frozen-inputs'
SCOPES=['hierarchy','data','namespace','bounds','recovery','corruption','orphan_recovery','owner_loss','fault']

def read(path):return json.loads(path.read_text())
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def inspect_raw(anchor_path):
    anchor=read(anchor_path);path=anchor_path.with_name(anchor_path.name.removesuffix('-anchor.json'))
    count=len(anchor['files']);names={'owner','manifest'}|{f'chunk-{i:02d}' for i in range(count)}
    assert {p.name for p in path.iterdir()}==names
    before={name:digest(path/name) for name in sorted(names)};fds={}
    try:
        for name in ['.']+sorted(names):
            fd=os.open(path/name,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|(os.O_DIRECTORY if name=='.' else 0));fds[name]=fd
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            info=os.fstat(fd);named=(path/name).stat(follow_symlinks=False)
            assert (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino)==tuple(anchor['objects'][name])
            assert info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==(0o700 if name=='.' else 0o600)
            if name!='.':
                assert stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_blocks*512>=info.st_size
                if name.startswith('chunk-'):assert info.st_size==16*1024**2
        assert os.pread(fds['owner'],34,0)==(anchor['identity']+'\n').encode()
        assert before['manifest']==anchor['manifestSha256']
        manifest=json.loads(os.pread(fds['manifest'],4096,0));assert manifest['profile']=='hms.block-image.linux-ext4.tracked-sync/0.1'
        if path.name=='failed-partial-write':assert os.pread(fds['chunk-00'],16,0)==b'P'*7+b'\xff'*9
        if path.name=='failed-wait':assert os.pread(fds['chunk-01'],16,0)==b'W'*16
        assert {p.name for p in path.iterdir()}==names
        for name,fd in fds.items():
            info=os.fstat(fd);named=(path/name).stat(follow_symlinks=False)
            assert (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino)==tuple(anchor['objects'][name])
        assert {name:digest(path/name) for name in sorted(names)}==before
        return dict(path=str(path.relative_to(ATTEMPT)),chunks=count,backingHashes=before,providerReopened=False)
    finally:
        for fd in fds.values():os.close(fd)


def main():
    report=read(ATTEMPT/'RESULTS.json');inputs=read(ATTEMPT/'inputs.json')
    assert report['inputsStable'] and report['comparisonEquivalent']
    assert sum(report['scopes'][name]['checks'] for name in SCOPES)==96
    for row in inputs['files']:assert digest(ROOT/row['path'])==digest(ATTEMPT/row['frozen'])==row['sha256']
    assert digest(FROZEN/'dataset.json')==inputs['datasetSha256']
    assert digest(ATTEMPT/'hierarchical-store.so')==report['librarySha256']
    assert digest(ATTEMPT/'mount-probe.so')==report['mountLibrarySha256']
    assert digest(ATTEMPT/'sync-probe.so')==report['syncLibrarySha256']
    assert digest(Path(inputs['compiler']))==inputs['compilerSha256']
    assert all(digest(Path(row['path']))==row['sha256'] for row in read(ATTEMPT/'headers.json'))
    processes=[]
    for path in sorted(ATTEMPT.glob('*/started.json')):
        start=read(path);end=read(path.with_name('result.json'))
        assert end['reaped'] and not Path('/proc',str(start['pid'])).exists()
        processes.append(dict(scope=path.parent.name,pid=start['pid'],**end))
    for scope in SCOPES+['mount-controls','sync-controls']+[name for name in ['replay_write','replay_read'] if name in report['scopes']]:
        row=report['scopes'][scope];work=ATTEMPT/scope;checks=read(work/'checks.json')
        assert read(work/'stdout.txt')==checks and digest(work/'checks.json')==row['receiptSha256']
        assert checks['status']=='passed' and len(checks['checks'])==row['checks']
        assert read(work/'result.json')['returnCode']==0 and not (work/'stderr.txt').read_bytes()
    assert read(ATTEMPT/'native-controls/stdout.txt')==report['scopes']['native-controls']
    assert report['scopes']['native-controls']['checks']==9
    assert read(ATTEMPT/'provider-controls/stdout.txt')==dict(tests=24,failures=0,errors=0,passed=True)
    spec=importlib.util.spec_from_file_location('hms_statx_retained_reader',Path(__file__).parent/'retained_reader.py')
    reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    global bodies
    bodies=reader.bodies
    images={}
    for scope in SCOPES+['replay_write']:
        for anchor in sorted((ATTEMPT/scope).glob('*-anchor.json')):
            path=anchor.with_name(anchor.name.removesuffix('-anchor.json'))
            if not path.is_dir():continue
            name=str(path.relative_to(ATTEMPT))
            images[name]=reader.inspect(path,anchor,report['librarySha256'],replaced_owner=name=='owner_loss/image')
    expected=bytearray(bytes(range(256))*32);expected[4090:4106]=b'X'*16
    expected=expected[:4100]+b'\0'*(12000-4100)+b'Z'
    assert bodies(images['data/image'])=={'data':bytes(expected)}
    assert bodies(images['hierarchy/image'])=={'experiment/stage/position':b'12.5 um','experiment/stage/'+'é'*127+'a':b''}
    assert images['hierarchy/image']['directories']=={'experiment','experiment/stage'}
    assert bodies(images['namespace/image'])=={'right/target':b'NEW'}
    assert images['namespace/image']['directories']=={'left','right'}
    assert bodies(images['bounds/image'])=={'f':b''}
    assert '/'.join(['x'*255]*16) in images['bounds/image']['directories']
    for phase in ['identity_reserved','inode_durable','entry_staged','entry_published']:
        original=images['recovery/'+phase];recovered=images['recovery/'+phase+'-recovered']
        wanted={'kept/new':b''} if phase=='entry_published' else {}
        assert bodies(original)==bodies(recovered)==wanted
        assert original['directories']==recovered['directories']=={'kept'}
        assert not recovered['unlinked'] and not recovered['pending']
        lineage=read(ATTEMPT/'recovery'/(phase+'-recovered-lineage.json'))
        assert original['backingHashes']==lineage['sourceHashes']==lineage['targetHashes']
        assert read(ATTEMPT/'recovery'/(phase+'-checkpoint.json'))['phase']==phase
    old=images['orphan_recovery/image'];new=images['orphan_recovery/recovered']
    assert bodies(old)==bodies(new)=={'live':b'LIVE'} and len(old['unlinked'])==2 and not new['unlinked']
    assert len(new['nodes'])==2
    assert old['backingHashes']==read(ATTEMPT/'orphan_recovery/recovered-lineage.json')['sourceHashes']
    corrupt=images['corruption/image'];assert corrupt['files']['dir/data']['missing']==[0] and 'super.tmp' in corrupt['root']
    assert corrupt['backingHashes']==read(ATTEMPT/'corruption/corrupt-image-hashes.json')
    graph=images['corruption/graph'];assert len(graph['duplicates'])==1 and 'super.tmp' in graph['root']
    assert bodies(images['owner_loss/image'])=={'data':b'A'*4096}
    fault=images['fault/image'];assert bodies(fault)['data'] in (b'A'*4096,b'B'+b'A'*4095)
    assert fault['backingHashes']==read(ATTEMPT/'fault/failed-image-hashes.json')
    dataset=read(FROZEN/'dataset.json');replay=None
    if 'replay_write/image' in images:
        observed=images['replay_write/image'];source=Path(dataset['sourceRoot'])
        raw=(ATTEMPT/'replay_write/progress.jsonl').read_bytes();lines=raw.splitlines(keepends=True)
        rows=[];tail=b''
        for index,line in enumerate(lines):
            if not line.endswith(b'\n'):assert index==len(lines)-1;tail=line;break
            rows.append(json.loads(line))
        directories_complete=bool(rows and 'directoriesComplete' in rows[0])
        if directories_complete:assert rows.pop(0)['directoriesComplete']==len(dataset['directories'])
        assert rows==dataset['files'][:len(rows)]
        actual=bodies(observed);wanted={r['path']:r for r in rows}
        assert set(wanted)<=set(actual)
        for name,row in wanted.items():assert len(actual[name])==row['bytes'] and hashlib.sha256(actual[name]).hexdigest()==row['sha256']
        extra=set(actual)-set(wanted)
        assert len(extra)<=1 and (not extra or extra=={dataset['files'][len(rows)]['path']})
        for name in extra:
            full=(source/name).read_bytes();assert full[:len(actual[name])]==actual[name]
        if directories_complete:assert observed['directories']==set(dataset['directories'])
        else:assert observed['directories']<=set(dataset['directories'])
        complete='replay_write' in report['scopes']
        if complete:assert len(rows)==4270 and not extra and not tail
        else:assert not (ATTEMPT/'replay_read').exists()
        replay=dict(completeWriterReceipt=complete,completedFileBodiesVerified=len(rows),completeBodyBytes=sum(r['bytes'] for r in rows),
            directoriesVerified=len(observed['directories']),extraPublishedFiles=[dict(path=n,committedBytes=len(actual[n])) for n in sorted(extra)],
            unlinkedInodes=sorted(observed['unlinked']),incompletePhysicalInodes=sorted(set(observed['physical'])-set(observed['nodes'])),
            pendingEntries=observed['pending'],partialProgressTailBytes=len(tail),dependentColdReaderRun=(ATTEMPT/'replay_read').exists())
    comparisons={}
    for name in ['comparison-original','comparison-candidate']:
        work=ATTEMPT/name;receipt=read(work/'diagnostic.json')
        assert digest(work/'diagnostic.json')==report['scopes'][name]['receiptSha256']
        assert read(work/'stdout.txt')=={k:v for k,v in receipt.items() if k not in ['spans','steps','expectedFiles','backingHashes']}
        value=reader.inspect(work/'image',work/'anchor.json',report['librarySha256']);images[name+'/image']=value
        actual=bodies(value)
        rows=[dict(path=n,bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for n,b in sorted(actual.items())]
        assert rows==receipt['expectedFiles'] and len(rows)==40 and len(value['directories'])==20
        assert not value['unlinked'] and not value['pending'] and value['backingHashes']==receipt['backingHashes']
        comparisons[name]=receipt
    left,right=comparisons.values()
    for key in ['expectedFiles','firstOwnerCallbacks','coldOwnerCallbacks']:assert left[key]==right[key]
    assert len(left['steps'])==len(right['steps'])==426
    for a,b in zip(left['steps'],right['steps']):
        assert {k:v for k,v in a.items() if k not in ['wallNs','cpuNs']}=={k:v for k,v in b.items() if k not in ['wallNs','cpuNs']}
    assert {k:v for k,v in left['backingHashes'].items() if k!='manifest'}=={k:v for k,v in right['backingHashes'].items() if k!='manifest'}
    a=read(ATTEMPT/'comparison-original/image/manifest');b=read(ATTEMPT/'comparison-candidate/image/manifest')
    assert a.pop('profile')=='hms.block-image.linux-ext4.statx-mount/0.1' and b.pop('profile')=='hms.block-image.linux-ext4.tracked-sync/0.1' and a==b
    assert left['providerSyncCalls']==dict(fsync=13724,wait=0)
    assert sum(right['providerSyncCalls'].values())==13726
    assert right['providerSyncCalls']['fsync']<13724 and right['providerSyncCalls']['wait']>0
    raw_images=[inspect_raw(anchor) for anchor in sorted((ATTEMPT/'sync-controls').glob('*-anchor.json'))]
    assert len(raw_images)==7 and sum(row['chunks'] for row in raw_images)==13
    runtime=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(runtime)=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    runtime_rows=read(runtime)['files'];assert len(runtime_rows)==244 and all(digest(ROOT/r['path'])==r['sha256'] for r in runtime_rows)
    result=dict(status='verified',nativeControls=9,mountControls=report['scopes']['mount-controls']['checks'],
        syncControls=report['scopes']['sync-controls']['checks'],rawImages=raw_images,
        originalProviderTests=24,semanticChecks=96,imagesReadOnly=len(images),processes=processes,replay=replay,publicInputsExact=244,
        comparison=dict(originalCPU=left['cpuSeconds'],candidateCPU=right['cpuSeconds'],originalWall=left['elapsedSeconds'],candidateWall=right['elapsedSeconds'],steps=426,chunkBytesIdentical=True,productionSpeedupEstablished=False,
            originalSyncCalls=left['providerSyncCalls'],candidateSyncCalls=right['providerSyncCalls']),
        recoveryInvoked=False,allBackingBytesUnchanged=True,physicalPowerLossTested=False,serviceStorageQualified=False,
        images=[dict(path=name,files=len(value['files']),directories=len(value['directories']),unlinkedInodes=sorted(value['unlinked']),
            incompletePhysicalInodes=sorted(set(value['physical'])-set(value['nodes'])),pendingEntries=value['pending'],
            backingHashes=value['backingHashes'],callbacks=value['callbacks']) for name,value in images.items()])
    with (HERE/'EVIDENCE-AUDIT.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('images','processes','rawImages')},sort_keys=True),flush=True)

if __name__=='__main__':main()
