"""Independent read-only reconstruction and process/source joins."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat

HERE=Path(os.environ['HMS_AUDIT_STAGE']);ROOT=HERE.parents[2];ATTEMPT=HERE/'attempt01'
FROZEN=ATTEMPT/'frozen-inputs'
SCOPES=['hierarchy','data','namespace','bounds','recovery','corruption','orphan_recovery','owner_loss','fault']
OLD_PROFILE='hms.hierarchical-chunk-store/0.1'
NEW_PROFILE='hms.hierarchical-chunk-store.inline512/0.1'
OLD_LIBRARY_HASH='7049dc14940b0f686f5cbe682e85f70944a8074936786e7f962c6ee29ed321de'

def read(path):return json.loads(path.read_text())
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

class ReadOnlySnapshot:
    """Held descriptor for the native probe's finite RAM-model dump."""
    block_count=512
    def __init__(self,path):
        self.path=path;self.fd=None
        try:
            assert path.resolve(strict=True)==path
            self.fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
            fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            info=os.fstat(self.fd);named=path.stat(follow_symlinks=False)
            assert (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino)
            assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600
            assert info.st_uid==os.getuid() and info.st_nlink==1
            assert info.st_size==2*1024**2 and info.st_blocks*512>=info.st_size
            self.identity=(info.st_dev,info.st_ino,info.st_size)
            self.before=self.hash()
        except BaseException:self.close();raise
    def hash(self):
        value=hashlib.sha256()
        for offset in range(0,2*1024**2,65536):
            part=os.pread(self.fd,65536,offset);assert len(part)==65536;value.update(part)
        return value.hexdigest()
    def read(self,block,offset,size):
        assert 0<=block<self.block_count and 0<=offset<=4096 and 0<=size<=4096-offset
        assert offset%4096==size%4096==0
        value=os.pread(self.fd,size,block*4096+offset);assert len(value)==size;return value
    def write(self,*args):raise AssertionError('AUDIT_WRITE_FORBIDDEN')
    def erase(self,*args):raise AssertionError('AUDIT_ERASE_FORBIDDEN')
    def sync(self):raise AssertionError('AUDIT_SYNC_FORBIDDEN')
    def stable(self):
        held=os.fstat(self.fd);named=self.path.stat(follow_symlinks=False)
        assert (held.st_dev,held.st_ino,held.st_size)==(named.st_dev,named.st_ino,named.st_size)==self.identity
        assert self.hash()==self.before==digest(self.path)
    def close(self):
        if self.fd is not None:os.close(self.fd);self.fd=None

def inspect_snapshots(reader,report):
    snapshots=[]
    expected={'renamed':bytes([0])*32}|{f'n{i:03d}':bytes([i%251])*32 for i in range(2,300)}
    assert len(expected)==299
    for name in ['ram-live.bin','ram-durable.bin']:
        image=ReadOnlySnapshot(ATTEMPT/'native-controls'/name);native=None
        try:
            native=reader.Native(image,ATTEMPT/'hierarchical-store.so',report['librarySha256'])
            native.call('hm_mount')
            assert {n:(k,s) for n,k,s in native.entries('/',3)}=={'boundary':(1,0),'many':(2,0)}
            assert native.read('boundary')==b''
            assert {n:(k,s) for n,k,s in native.entries('many',300)}=={n:(1,32) for n in expected}
            for entry,body in expected.items():assert native.read('many/'+entry)==body
            assert native.stat('many/n000') is None and native.stat('many/n001') is None
            used=native.call('hm_used');assert used==report['scopes']['native-controls']['usedBlocks']
            native.dispose()
            assert native.fault is None and all(native.counts[k]==0 for k in ['programCalls','erases','syncs'])
            image.stable()
            snapshots.append(dict(path=str(image.path.relative_to(ATTEMPT)),bytes=2*1024**2,
                sha256=image.before,files=300,payloadBytes=299*32,usedBlocks=used,callbacks=dict(native.counts)))
        finally:
            if native is not None:native.dispose()
            image.close()
    assert snapshots[0]['sha256']==snapshots[1]['sha256']
    return snapshots

def inspect_root_records(reader,path,anchor,library,library_hash,names):
    image=reader.ReadOnlyImage(path,anchor);native=None
    try:
        native=reader.Native(image,library,library_hash);native.call('hm_mount')
        values={name:native.read(name) for name in names}
        native.dispose()
        assert native.fault is None and all(native.counts[k]==0 for k in ['programCalls','erases','syncs'])
        image.stable()
        return values,dict(native.counts)
    finally:
        if native is not None:native.dispose()
        image.close()

def main():
    report=read(ATTEMPT/'RESULTS.json');inputs=read(ATTEMPT/'inputs.json')
    assert report['inputsStable'] and report['comparisonEquivalent']
    assert sum(report['scopes'][name]['checks'] for name in SCOPES)==96
    for row in inputs['files']:assert digest(ROOT/row['path'])==digest(ATTEMPT/row['frozen'])==row['sha256']
    assert digest(FROZEN/'dataset.json')==inputs['datasetSha256']
    assert digest(ATTEMPT/'hierarchical-store.so')==report['librarySha256']
    assert digest(ATTEMPT/'original-hierarchical-store.so')==report['originalLibrarySha256']==OLD_LIBRARY_HASH
    assert digest(ATTEMPT/'mount-probe.so')==report['mountLibrarySha256']
    assert digest(Path(inputs['compiler']))==inputs['compilerSha256']
    assert all(digest(Path(row['path']))==row['sha256'] for row in read(ATTEMPT/'headers.json'))
    processes=[]
    for path in sorted(ATTEMPT.glob('*/started.json')):
        start=read(path);end=read(path.with_name('result.json'))
        assert end['reaped'] and not Path('/proc',str(start['pid'])).exists()
        processes.append(dict(scope=path.parent.name,pid=start['pid'],**end))
    for scope in SCOPES+['mount-controls','profile-controls']+[name for name in ['replay_write','replay_read'] if name in report['scopes']]:
        row=report['scopes'][scope];work=ATTEMPT/scope;checks=read(work/'checks.json')
        assert read(work/'stdout.txt')==checks and digest(work/'checks.json')==row['receiptSha256']
        assert checks['status']=='passed' and len(checks['checks'])==row['checks']
        assert read(work/'result.json')['returnCode']==0 and not (work/'stderr.txt').read_bytes()
    assert read(ATTEMPT/'native-controls/stdout.txt')==report['scopes']['native-controls']
    assert report['scopes']['native-controls']['cases']==12
    assert report['scopes']['native-controls']['status']=='passed'
    assert report['scopes']['mount-controls']['checks']==52
    assert report['scopes']['profile-controls']['checks']==8
    for name in ['native-controls','provider-controls']:
        assert read(ATTEMPT/name/'result.json')['returnCode']==0
    assert read(ATTEMPT/'provider-controls/stdout.txt')==dict(tests=24,failures=0,errors=0,passed=True)
    spec=importlib.util.spec_from_file_location('hms_inline_retained_reader',Path(__file__).parent/'retained_reader.py')
    reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    global bodies
    bodies=reader.bodies
    snapshots=inspect_snapshots(reader,report)
    images={};root_record_callbacks={}
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
    assert len([name for name in images if not name.startswith('replay_write/')])==18
    profile=read(ATTEMPT/'profile-controls/checks.json')
    assert profile['recoveryInvoked'] is False
    assert all(profile['refusedOwnerCallbacks'][key]==0 for key in ['programCalls','erases','syncs'])
    for name,expected_profile in [('good',NEW_PROFILE),('wrong-super',OLD_PROFILE)]:
        work=ATTEMPT/'profile-controls';anchor=work/(name+'-anchor.json')
        assert read(anchor)['storeProfile']==NEW_PROFILE
        value=reader.inspect(work/name,anchor,report['librarySha256'],expected_profile=expected_profile)
        images['profile-controls/'+name]=value
        assert not value['directories'] and not value['unlinked'] and not value['pending']
        assert set(value['physical'])==set(value['nodes'])
        if name=='good':assert bodies(value)=={'kept':b'PAT'}
        else:
            assert bodies(value)=={} and value['root']['super.tmp']==(1,len(b'RETAIN ON REFUSAL'))
            assert value['backingHashes']==profile['wrongSuperBackingHashes']
            values,counts=inspect_root_records(reader,work/name,anchor,ATTEMPT/'hierarchical-store.so',report['librarySha256'],['super.tmp'])
            assert values['super.tmp']==b'RETAIN ON REFUSAL'
            root_record_callbacks['profile-controls/'+name]=counts
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
    comparisons={};superblocks={}
    for name in ['comparison-original','comparison-candidate']:
        work=ATTEMPT/name;receipt=read(work/'diagnostic.json')
        terminal=read(work/'result.json')
        assert terminal['returnCode']==0 and not terminal['timedOut'] and not (work/'stderr.txt').read_bytes()
        assert digest(work/'diagnostic.json')==report['scopes'][name]['receiptSha256']
        assert read(work/'stdout.txt')=={k:v for k,v in receipt.items() if k not in ['spans','steps','expectedFiles','backingHashes']}
        original=name=='comparison-original'
        expected_profile=OLD_PROFILE if original else NEW_PROFILE
        assert read(work/'anchor.json')['storeProfile']==expected_profile
        library=ATTEMPT/('original-hierarchical-store.so' if original else 'hierarchical-store.so')
        library_hash=report['originalLibrarySha256'] if original else report['librarySha256']
        value=reader.inspect(work/'image',work/'anchor.json',library_hash,
            expected_profile=expected_profile,library_path=library);images[name+'/image']=value
        actual=bodies(value)
        rows=[dict(path=n,bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for n,b in sorted(actual.items())]
        assert rows==receipt['expectedFiles'] and len(rows)==40 and len(value['directories'])==20
        assert not value['unlinked'] and not value['pending'] and value['backingHashes']==receipt['backingHashes']
        values,counts=inspect_root_records(reader,work/'image',work/'anchor.json',library,library_hash,['super'])
        superblocks[name]=reader.unpack(values['super'])
        root_record_callbacks[name+'/image']=counts
        comparisons[name]=receipt
    left,right=comparisons.values()
    assert left['expectedFiles']==right['expectedFiles']
    assert len(left['steps'])==len(right['steps'])==426
    for a,b in zip(left['steps'],right['steps']):
        assert {k:v for k,v in a.items() if k not in ['wallNs','cpuNs','callbacks']}=={k:v for k,v in b.items() if k not in ['wallNs','cpuNs','callbacks']}
    for receipt in [left,right]:
        syncs=receipt['firstOwnerCallbacks']['syncs']+receipt['coldOwnerCallbacks']['syncs']
        assert receipt['providerSyncCalls']==dict(fsync=syncs*8+12,wait=0)
    original=images['comparison-original/image'];candidate=images['comparison-candidate/image']
    for key in ['nodes','directories','files','unlinked','pending','duplicates']:assert original[key]==candidate[key]
    old_super,new_super=superblocks.values()
    assert old_super.pop('profile')==OLD_PROFILE and new_super.pop('profile')==NEW_PROFILE and old_super==new_super
    assert left['backingHashes']!=right['backingHashes'] and report['physicalEncodingsDiffer']
    a=read(ATTEMPT/'comparison-original/image/manifest');b=read(ATTEMPT/'comparison-candidate/image/manifest')
    assert a==b and a['profile']=='hms.block-image.linux-ext4.statx-mount/0.1'
    runtime=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(runtime)=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    runtime_rows=read(runtime)['files'];assert len(runtime_rows)==244 and all(digest(ROOT/r['path'])==r['sha256'] for r in runtime_rows)
    result=dict(status='verified',nativeControlCases=12,nativeControlAssertions=report['scopes']['native-controls']['assertions'],
        mountControls=52,profileControls=8,originalProviderTests=24,semanticChecks=96,
        imagesReadOnly=len(images),snapshotsReadOnly=snapshots,rootRecordCallbacks=root_record_callbacks,
        processes=processes,replay=replay,publicInputsExact=244,
        comparison=dict(originalCPU=left['cpuSeconds'],candidateCPU=right['cpuSeconds'],originalWall=left['elapsedSeconds'],candidateWall=right['elapsedSeconds'],
            steps=426,logicalBodiesAndInodeMetadataIdentical=True,physicalEncodingsDiffer=True,
            originalFsync=left['providerSyncCalls']['fsync'],candidateFsync=right['providerSyncCalls']['fsync'],
            originalCallbacks={key:left[key] for key in ['firstOwnerCallbacks','coldOwnerCallbacks']},
            candidateCallbacks={key:right[key] for key in ['firstOwnerCallbacks','coldOwnerCallbacks']},productionSpeedupEstablished=False),
        recoveryInvoked=False,allBackingBytesUnchanged=True,physicalPowerLossTested=False,serviceStorageQualified=False,
        images=[dict(path=name,files=len(value['files']),directories=len(value['directories']),unlinkedInodes=sorted(value['unlinked']),
            incompletePhysicalInodes=sorted(set(value['physical'])-set(value['nodes'])),pendingEntries=value['pending'],
            backingHashes=value['backingHashes'],callbacks=value['callbacks']) for name,value in images.items()])
    with (HERE/'EVIDENCE-AUDIT.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('images','processes')},sort_keys=True),flush=True)

if __name__=='__main__':main()
