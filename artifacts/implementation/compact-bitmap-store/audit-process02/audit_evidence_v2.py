"""Independent compact-profile evidence audit; read-only backing and no recovery."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path

HERE=Path(os.environ['HMS_AUDIT_STAGE']);ROOT=HERE.parents[2];ATTEMPT=HERE/'attempt01';FROZEN=ATTEMPT/'frozen-inputs'
PRIOR=ROOT/'artifacts/implementation/inline-hierarchical-store'
ATTRIBUTION=ROOT/'artifacts/verification/full-storage-attribution'
SCOPES=['hierarchy','data','namespace','bounds','recovery','corruption','orphan_recovery','owner_loss','fault']
TARGETS={'bitmap-codec':77,'bitmap-edges':27,'bitmap-corruption':12,'bitmap-interruption':33}
OLD_PROFILE='hms.hierarchical-chunk-store.inline512/0.1'
NEW_PROFILE='hms.hierarchical-chunk-store.compact-bitmap/0.1'
NATIVE_HASH='6b48f9b9c9a829a8c5c71236c309e7e78f55f096e7c627542a739095ff57ec7a'
MOUNT_HASH='450f1d2bfd948ca0f7292884e753ccc11fd9f82dc285e150cf535864b75572bd'
CHUNK=4096;MAX_FILE=16*1024**2


def read(path):return json.loads(path.read_text())
def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def save(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
def hashes(path):return {p.name:digest(p) for p in sorted(path.iterdir())}
def body_row(body):return dict(bytes=len(body),sha256=hashlib.sha256(body).hexdigest())


def group_members(pgid):
    members=[]
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():continue
        try:
            fields=(entry/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[2])==pgid:members.append(dict(pid=int(entry.name),state=fields[0]))
        except (FileNotFoundError,ProcessLookupError,PermissionError):pass
    return members


def seal(directory,expected,files=None):
    assert digest(directory/'index.json')==expected
    value=read(directory/'index.json')
    if files is not None:assert len(value['files'])==files
    assert all(not (directory/r['path']).is_symlink() and (directory/r['path']).stat().st_size==r['bytes']
               and digest(directory/r['path'])==r['sha256'] for r in value['files'])
    assert all((directory/r['path']).is_symlink() and os.readlink(directory/r['path'])==r['target'] for r in value.get('symlinks',[]))
    return dict(indexSha256=expected,filesExact=len(value['files']),symlinksExact=len(value.get('symlinks',[])))


def public():
    path=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(path)=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    rows=read(path)['files'];assert len(rows)==244 and all(digest(ROOT/r['path'])==r['sha256'] for r in rows)
    return dict(receiptSha256=digest(path),filesExact=244)


def inspect_records(reader,path,anchor,names):
    image=reader.ReadOnlyImage(path,anchor);native=None
    try:
        native=reader.Native(image,ATTEMPT/'hierarchical-store.so',NATIVE_HASH);native.call('hm_mount')
        values={name:native.read(name) for name in names}
        assert native.fault is None and all(native.counts[k]==0 for k in ['programCalls','erases','syncs'])
        image.stable();return values,dict(native.counts)
    finally:
        if native is not None:native.dispose()
        image.close()


def complete_checks(report,name):
    work=ATTEMPT/name;row=report['scopes'][name];checks=read(work/'checks.json')
    assert checks==read(work/'stdout.txt') and digest(work/'checks.json')==row['receiptSha256']
    assert checks['status']=='passed' and len(checks['checks'])==len(set(checks['checks']))==row['checks']
    assert read(work/'result.json')['returnCode']==0 and not (work/'stderr.txt').read_bytes()
    return checks


def main():
    report=read(ATTEMPT/'RESULTS.json');inputs=read(ATTEMPT/'inputs.json');before=public()
    assert report['inputsStable'] and report['comparisonEquivalent'] and report['profile']==NEW_PROFILE
    assert not any(report[k] for k in ['publicRuntimeChanged','serviceStorageQualified','actualMountChanges','sqliteTested',
              'checksDisabled','durabilityBarriersDisabled','syncSelectionChanged','geometryChanged'])
    assert report['inlineLimit']==512 and report['payloadChunkBytes']==4096
    for row in inputs['files']:assert digest(ROOT/row['path'])==digest(ATTEMPT/row['frozen'])==row['sha256']
    assert digest(FROZEN/'dataset.json')==inputs['datasetSha256']=='475f09d59534a09b6094707def7112709c050548b958b776362bf0ce86ee0a46'
    assert digest(ATTEMPT/'hierarchical-store.so')==report['librarySha256']==NATIVE_HASH
    assert digest(ATTEMPT/'mount-probe.so')==report['mountLibrarySha256']==MOUNT_HASH
    assert digest(Path(inputs['interpreter']))==inputs['interpreterSha256']
    prior=seal(PRIOR,'a820ce8adda0d8e3dbb1827f2b47c48f94c7969cccc299fbd10e36fbce54f982',340)
    assert prior['symlinksExact']==1
    attribution=seal(ATTRIBUTION,'3f673fabcdab31e027b1d535d63a1a8302350a755fde4be94bb8ed53fecdd165',96)
    native=inputs['unchangedNativeControls'];assert native['cases']==12 and native['assertions']==1294 and not native['rerun']
    assert digest(PRIOR/'attempt01/native-controls/stdout.txt')==native['stdoutSha256']
    assert digest(PRIOR/'attempt01/native-controls/result.json')==native['resultSha256']
    prior_native=read(PRIOR/'attempt01/native-controls/stdout.txt');assert prior_native['status']=='passed' and prior_native['cases']==12 and prior_native['assertions']==1294
    assert digest(PRIOR/'attempt01/native-controls/ram-live.bin')==digest(PRIOR/'attempt01/native-controls/ram-durable.bin')
    required=['mount-controls','profile-controls','provider-controls']+list(TARGETS)+SCOPES+['comparison-original','comparison-candidate']
    launched={p.parent.name for p in ATTEMPT.glob('*/started.json')}
    assert set(required)<=launched<=set(required+['replay_write','replay_read'])
    assert 'replay_read' not in launched or 'replay_write' in report['scopes']
    processes=[]
    for path in sorted(ATTEMPT.glob('*/started.json')):
        start=read(path);end=read(path.with_name('result.json'));intent=read(path.with_name('intent.json'))
        assert start['pid']==start['processGroup'] and end['reaped'] and not Path('/proc',str(start['pid'])).exists()
        assert end['groupAbsentAfterCleanup'] and not end['groupMembersAfterCleanup'] and not group_members(start['processGroup'])
        assert end['groupSignalAnchor']=='waitable unreaped owned leader; no signals after wait4'
        assert end['cleanupError'] is None
        assert intent['addressSpaceBytes']==512*1024**2 and intent['fileBytes']==16*1024**2 and intent['descriptors']==128
        assert (intent['wallSeconds'],intent['cpuSeconds'])==((180,120) if path.parent.name.startswith('replay_') else (60,40))
        if path.parent.name in report['scopes']:assert end['returnCode']==0 and not end['timedOut'] and end['monitorError'] is None
        else:assert end['returnCode']!=0 or end['timedOut'] or end['monitorError'] is not None
        processes.append(dict(scope=path.parent.name,pid=start['pid'],processGroup=start['processGroup'],**end))
    assert sum(report['scopes'][name]['checks'] for name in SCOPES)==96
    checks={name:complete_checks(report,name) for name in SCOPES+list(TARGETS)+['mount-controls','profile-controls']}
    for name,count in TARGETS.items():assert len(checks[name]['checks'])==count
    assert sum(TARGETS.values())==149
    assert report['scopes']['mount-controls']['checks']==52 and report['scopes']['profile-controls']['checks']==8
    assert read(ATTEMPT/'provider-controls/stdout.txt')==report['scopes']['provider-controls']==dict(tests=24,failures=0,errors=0,passed=True)
    # Reviewed unittest progress plus the expected CPython test13 fork warning.
    # Bind exact bytes; do not discard arbitrary stderr or change the test result.
    assert digest(ATTEMPT/'provider-controls/stderr.txt') == '2b9c206ae57a84935b8e6671df5970b283455f72639845139455836c922011d2'
    spec=importlib.util.spec_from_file_location('hms_compact_retained_reader',Path(__file__).parent/'retained_reader.py')
    reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    images={};extra_callbacks={};corrupt_images={}
    for scope in SCOPES+['bitmap-edges','bitmap-interruption','replay_write']:
        for anchor in sorted((ATTEMPT/scope).glob('*-anchor.json')):
            path=anchor.with_name(anchor.name.removesuffix('-anchor.json'))
            assert path.is_dir();name=str(path.relative_to(ATTEMPT))
            images[name]=reader.inspect(path,anchor,NATIVE_HASH,replaced_owner=name=='owner_loss/image')
    bodies=reader.bodies
    expected=bytearray(bytes(range(256))*32);expected[4090:4106]=b'X'*16
    expected=expected[:4100]+b'\0'*(12000-4100)+b'Z'
    assert bodies(images['data/image'])=={'data':bytes(expected)}
    assert bodies(images['hierarchy/image'])=={'experiment/stage/position':b'12.5 um','experiment/stage/'+'é'*127+'a':b''}
    assert images['hierarchy/image']['directories']=={'experiment','experiment/stage'}
    assert bodies(images['namespace/image'])=={'right/target':b'NEW'} and images['namespace/image']['directories']=={'left','right'}
    assert bodies(images['bounds/image'])=={'f':b''} and '/'.join(['x'*255]*16) in images['bounds/image']['directories']
    for phase in ['identity_reserved','inode_durable','entry_staged','entry_published']:
        original=images['recovery/'+phase];recovered=images['recovery/'+phase+'-recovered']
        wanted={'kept/new':b''} if phase=='entry_published' else {}
        assert bodies(original)==bodies(recovered)==wanted and original['directories']==recovered['directories']=={'kept'}
        assert not recovered['unlinked'] and not recovered['pending']
        lineage=read(ATTEMPT/'recovery'/(phase+'-recovered-lineage.json'))
        assert original['backingHashes']==lineage['sourceHashes']==lineage['targetHashes']
        assert read(ATTEMPT/'recovery'/(phase+'-checkpoint.json'))['phase']==phase
    old=images['orphan_recovery/image'];new=images['orphan_recovery/recovered']
    assert bodies(old)==bodies(new)=={'live':b'LIVE'} and len(old['unlinked'])==2 and not new['unlinked'] and len(new['nodes'])==2
    lineage=read(ATTEMPT/'orphan_recovery/recovered-lineage.json');assert old['backingHashes']==lineage['sourceHashes']==lineage['targetHashes']
    corrupt=images['corruption/image'];assert corrupt['files']['dir/data']['missing']==[0] and 'super.tmp' in corrupt['root']
    assert corrupt['backingHashes']==read(ATTEMPT/'corruption/corrupt-image-hashes.json')
    graph=images['corruption/graph'];assert len(graph['duplicates'])==1 and 'super.tmp' in graph['root']
    assert bodies(images['owner_loss/image'])=={'data':b'A'*4096}
    fault=images['fault/image'];assert bodies(fault)['data'] in (b'A'*4096,b'B'+b'A'*4095)
    assert fault['backingHashes']==read(ATTEMPT/'fault/failed-image-hashes.json')
    assert len([name for name in images if name.split('/')[0] in SCOPES])==18
    edge=images['bitmap-edges/image'];transitions=b'QQQ'+b'\0'*(9*CHUNK-2)
    transitions=transitions[:8*CHUNK]+b'Z'+transitions[8*CHUNK+1:]
    expected_edges=dict(transitions=transitions,maximum=b'\0'*(MAX_FILE-1)+b'!')
    assert bodies(edge)==expected_edges and not edge['directories'] and not edge['unlinked'] and not edge['pending']
    assert checks['bitmap-edges']['details']['expectedFiles']=={n:body_row(v) for n,v in expected_edges.items()}
    partial=b'A'*(CHUNK-6)+b'X'*6+b'A'*CHUNK
    for phase,wanted in [('state-staged',b'A'),('state-renamed',b'A'+b'\0'*(8*CHUNK-1)+b'Z'),
                         ('partial-overwrite',partial),('shrink-cleanup',b'A'*(7*CHUNK-3))]:
        original=images['bitmap-interruption/'+phase];recovered=images['bitmap-interruption/'+phase+'-recovered']
        final=wanted+b'\0'*(9*CHUNK-len(wanted)) if phase=='shrink-cleanup' else wanted
        assert bodies(original)=={'data':wanted} and bodies(recovered)=={'data':final}
        assert not original['unlinked'] and not original['pending'] and not recovered['unlinked'] and not recovered['pending']
        assert not original['directories'] and not recovered['directories'] and set(original['nodes'])==set(recovered['nodes'])=={1,2}
        work=ATTEMPT/'bitmap-interruption';lineage=read(work/(phase+'-recovered-lineage.json'));receipt=read(work/(phase+'-expected.json'))
        assert original['backingHashes']==lineage['sourceHashes']==lineage['targetHashes']==receipt['originalBackingHashes']
        assert receipt['originalCommittedFile']==body_row(wanted) and receipt['recoveredFile']==body_row(final)
        assert receipt['cut']==phase and not receipt['physicalPowerLoss'] and not receipt['multiChunkWriteAtomic']
        bits=base64.b64decode(recovered['nodes'][2]['metadata']['chunks'],validate=True)
        names={'state'}|{f'c{number:08x}' for number in range(4096) if bits[number//8]&(1<<(number%8))}
        assert set(recovered['physical'][2])==names
        if phase=='state-staged':
            assert set(original['physical'][2])=={'state','state.tmp','c00000000','c00000008'}
            records,counts=inspect_records(reader,work/phase,work/(phase+'-anchor.json'),['objects/b02/i0000000000000002/state.tmp'])
            assert reader.unpack(next(iter(records.values())))==dict(id=2,kind='file',size=8*CHUNK+1,chunks='AQE=')
            extra_callbacks['bitmap-interruption/'+phase]=counts
        elif phase=='shrink-cleanup':assert set(original['physical'][2])=={'state'}|{f'c{n:08x}' for n in range(9)}
        else:assert set(original['physical'][2])==names
    for name,wire,error in [('wrong-length',base64.b64encode(b'\1'+b'\0'*511).decode('ascii'),'INVALID_CHUNK_MAP'),
                            ('noncanonical','AR==','INVALID_CHUNK_MAP'),('tail-bit','Ag==','CHUNK_OUTSIDE_FILE')]:
        work=ATTEMPT/'bitmap-corruption';path=work/name;anchor=work/(name+'-anchor.json');receipt=read(work/(name+'-refusal.json'))
        expected_disk=dict(id=2,kind='file',size=1,chunks=wire)
        assert receipt['corruptDiskInode']==expected_disk and receipt['error']==error and receipt['validEnvelopeChecksum'] and not receipt['recoveryInvoked']
        assert all(receipt['callbacks'][k]==0 for k in ['programCalls','erases','syncs'])
        before_hashes=hashes(path);assert before_hashes==receipt['backingHashes']
        try:reader.inspect(path,anchor,NATIVE_HASH)
        except AssertionError:pass
        else:raise AssertionError('Normal reader admitted malformed compact bitmap: '+name)
        assert hashes(path)==before_hashes
        value=reader.inspect_corrupt_inode(path,anchor,NATIVE_HASH,expected_disk)
        assert value['backingHashes']==before_hashes
        corrupt_images['bitmap-corruption/'+name]=dict(**value,normalReaderRefused=True,expectedError=error)
    profile=checks['profile-controls'];assert not profile['recoveryInvoked']
    assert all(profile['refusedOwnerCallbacks'][key]==0 for key in ['programCalls','erases','syncs'])
    for name,expected_profile,encoding in [('good',NEW_PROFILE,'compact'),('wrong-super',OLD_PROFILE,'fixed512')]:
        work=ATTEMPT/'profile-controls';anchor=work/(name+'-anchor.json');assert read(anchor)['storeProfile']==NEW_PROFILE
        value=reader.inspect(work/name,anchor,NATIVE_HASH,expected_profile=expected_profile,bitmap_encoding=encoding)
        images['profile-controls/'+name]=value
        assert not value['directories'] and not value['unlinked'] and not value['pending'] and set(value['physical'])==set(value['nodes'])
        if name=='good':assert bodies(value)=={'kept':b'PAT'}
        else:
            assert bodies(value)=={} and value['root']['super.tmp']==(1,len(b'RETAIN ON REFUSAL')) and value['backingHashes']==profile['wrongSuperBackingHashes']
            records,counts=inspect_records(reader,work/name,anchor,['super.tmp']);assert records['super.tmp']==b'RETAIN ON REFUSAL'
            extra_callbacks['profile-controls/'+name]=counts
    comparisons={};superblocks={}
    for name,expected_profile,encoding in [('comparison-original',OLD_PROFILE,'fixed512'),('comparison-candidate',NEW_PROFILE,'compact')]:
        work=ATTEMPT/name;receipt=read(work/'diagnostic.json')
        assert digest(work/'diagnostic.json')==report['scopes'][name]['receiptSha256'] and receipt['status']=='passed'
        assert read(work/'stdout.txt')=={k:v for k,v in receipt.items() if k not in ['spans','steps','expectedFiles','backingHashes']}
        assert not (work/'stderr.txt').read_bytes() and read(work/'anchor.json')['storeProfile']==expected_profile
        value=reader.inspect(work/'image',work/'anchor.json',NATIVE_HASH,expected_profile=expected_profile,bitmap_encoding=encoding)
        images[name+'/image']=value;actual=bodies(value)
        rows=[dict(path=n,**body_row(b)) for n,b in sorted(actual.items())]
        assert rows==receipt['expectedFiles'] and len(rows)==40 and len(value['directories'])==20
        assert not value['unlinked'] and not value['pending'] and set(value['nodes'])==set(value['physical']) and value['backingHashes']==receipt['backingHashes']
        records,counts=inspect_records(reader,work/'image',work/'anchor.json',['super'])
        superblocks[name]=reader.unpack(records['super']);extra_callbacks[name+'/image']=counts;comparisons[name]=receipt
    left,right=comparisons.values();assert left['expectedFiles']==right['expectedFiles'] and len(left['steps'])==len(right['steps'])==426
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
    assert read(ATTEMPT/'comparison-original/image/manifest')==read(ATTEMPT/'comparison-candidate/image/manifest')
    dataset=read(FROZEN/'dataset.json');source=Path(dataset['sourceRoot'])
    assert len(dataset['files'])==4270 and len(dataset['directories'])==169 and sum(r['bytes'] for r in dataset['files'])==35508922
    assert all(digest(source/r['path'])==r['sha256'] for r in dataset['files'])
    replay=None
    if 'replay_write/image' in images:
        observed=images['replay_write/image'];lines=(ATTEMPT/'replay_write/progress.jsonl').read_bytes().splitlines(keepends=True);rows=[];tail=b''
        for index,line in enumerate(lines):
            if not line.endswith(b'\n'):assert index==len(lines)-1;tail=line;break
            rows.append(json.loads(line))
        directories_complete=bool(rows and 'directoriesComplete' in rows[0])
        if directories_complete:assert rows.pop(0)['directoriesComplete']==169
        assert rows==dataset['files'][:len(rows)]
        actual=bodies(observed);wanted={r['path']:r for r in rows};assert set(wanted)<=set(actual)
        for name,row in wanted.items():assert body_row(actual[name])=={k:row[k] for k in ['bytes','sha256']}
        extra=set(actual)-set(wanted);assert len(extra)<=1
        if extra:
            assert len(rows)<4270 and extra=={dataset['files'][len(rows)]['path']}
            for name in extra:assert (source/name).read_bytes()[:len(actual[name])]==actual[name]
        assert observed['directories']==set(dataset['directories']) if directories_complete else observed['directories']<=set(dataset['directories'])
        complete='replay_write' in report['scopes']
        if complete:assert len(rows)==4270 and not extra and not tail and not observed['unlinked'] and not observed['pending'] and set(observed['physical'])==set(observed['nodes'])
        else:assert 'replay_read' not in launched
        replay=dict(completeWriterReceipt=complete,completedFileBodiesVerified=len(rows),completeBodyBytes=sum(r['bytes'] for r in rows),
            directoriesVerified=len(observed['directories']),extraPublishedFiles=[dict(path=n,committedBytes=len(actual[n])) for n in sorted(extra)],
            unlinkedInodes=sorted(observed['unlinked']),incompletePhysicalInodes=sorted(set(observed['physical'])-set(observed['nodes'])),
            pendingEntries=observed['pending'],partialProgressTailBytes=len(tail),dependentColdReaderRun='replay_read' in launched,
            completeColdReaderReceipt='replay_read' in report['scopes'])
    for name in ['replay_write','replay_read']:
        if name in report['scopes']:
            value=complete_checks(report,name);assert len(value['checks'])==(2 if name=='replay_write' else 4)
    if report['status']=='passed':assert replay and replay['completeWriterReceipt'] and replay['completeColdReaderReceipt']
    else:assert report['status']=='failed-or-inconclusive' and set(report['scopes'])!=set(launched)
    expected_image_names=set()
    for scope in SCOPES+['bitmap-edges','bitmap-interruption','bitmap-corruption','profile-controls','replay_write']:
        expected_image_names|={str(p.with_name(p.name.removesuffix('-anchor.json')).relative_to(ATTEMPT)) for p in (ATTEMPT/scope).glob('*-anchor.json')}
    expected_image_names|={name+'/image' for name in comparisons}
    assert set(images)|set(corrupt_images)==expected_image_names
    assert len(images)+len(corrupt_images)==34+(1 if 'replay_write/image' in images else 0)
    for row in inputs['files']:assert digest(ROOT/row['path'])==digest(ATTEMPT/row['frozen'])==row['sha256']
    assert public()==before and all(not group_members(item['processGroup']) for item in processes)
    result=dict(status='verified',prior=prior,attribution=attribution,publicInputsExact=244,originalHierarchyChecks=96,
        targetBitmapChecks=149,targetScopeChecks=TARGETS,mountControls=52,originalProviderTests=24,profileControls=8,
        nativeControlCasesRevalidated=12,nativeControlAssertionsRevalidated=1294,nativeControlsRerun=False,
        imagesReadOnly=len(images)+len(corrupt_images),validOrStructuralImagesReadOnly=len(images),expectedMalformedBitmapImagesReadOnly=len(corrupt_images),
        corruptImages=corrupt_images,extraReadOnlyCallbacks=extra_callbacks,processes=processes,replay=replay,
        comparison=dict(originalCPU=left['cpuSeconds'],candidateCPU=right['cpuSeconds'],originalWall=left['elapsedSeconds'],candidateWall=right['elapsedSeconds'],
            steps=426,logicalBodiesAndNormalizedInodeMetadataIdentical=True,physicalEncodingsDiffer=True,
            originalFsync=left['providerSyncCalls']['fsync'],candidateFsync=right['providerSyncCalls']['fsync'],
            originalCallbacks={k:left[k] for k in ['firstOwnerCallbacks','coldOwnerCallbacks']},
            candidateCallbacks={k:right[k] for k in ['firstOwnerCallbacks','coldOwnerCallbacks']},productionSpeedupEstablished=False),
        recoveryInvoked=False,allBackingBytesUnchanged=True,physicalPowerLossTested=False,serviceStorageQualified=False,
        images=[dict(path=name,files=len(value['files']),directories=len(value['directories']),unlinkedInodes=sorted(value['unlinked']),
            incompletePhysicalInodes=sorted(set(value['physical'])-set(value['nodes'])),pendingEntries=value['pending'],
            backingHashes=value['backingHashes'],callbacks=value['callbacks']) for name,value in images.items()])
    save(HERE/'EVIDENCE-AUDIT.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('images','processes','corruptImages')},sort_keys=True),flush=True)


if __name__=='__main__':main()
