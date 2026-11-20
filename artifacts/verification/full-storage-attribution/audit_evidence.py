"""Read-only reconstruction plus independent bounded observation accounting."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path

HERE=Path(os.environ['HMS_AUDIT_STAGE']);ROOT=HERE.parents[2];ATTEMPT=HERE/'attempt01'
FROZEN=ATTEMPT/'frozen-inputs'
PRIOR=ROOT/'artifacts/implementation/inline-hierarchical-store'
PHASES=['creation','directories','file_io','readback','close']
FIELDS=['calls','raised','cpuNs','wallNs','selfCpuNs','selfWallNs']
PUBLIC=['create','reopen','mkdir','open','pwrite','pread','close_handle','accounting','close','listdir','info']
META=['_new_inode','_initialize_inode','_save_super','_save_inode','_publish','_inventory','_recover_inventory']
NATIVE=['hm_format','hm_mount','hm_stat','hm_list','hm_entries','hm_mkdir','hm_remove','hm_sync','hm_used']
KINDS=['super','state','chunk','entry','other']
PROVIDER=['__init__','_verify','read','write','erase','sync','close']
LABELS=([f'logical.{name}' for name in PUBLIC]+[f'hierarchy.{name}' for name in META]+
    ['native.owner','native.dispose']+[f'native.{name}' for name in NATIVE]+
    [f'native.{name}.{kind}' for name in ['hm_read','hm_write','hm_rename'] for kind in KINDS]+
    [f'provider.{name}' for name in PROVIDER]+['provider.create_image','provider.mount_admit','provider.mount_current']+
    [f'os.{name}' for name in ['pread','pwrite','fsync','posix_fallocate']])
CALLBACKS={'readCalls','readBytes','programCalls','programBytes','erases','syncs'}


def read(path):return json.loads(path.read_text())
def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def save(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
def integer(value,minimum=0):return type(value) is int and value>=minimum


def sum_rows(rows):
    return {name:sum(row[index] for row in rows) for index,name in enumerate(FIELDS)}


def conservation(frame,rows):
    logical=[row for (phase,label),row in rows.items() if LABELS[label].startswith('logical.')]
    roots=sum_rows(logical);all_rows=sum_rows(list(rows.values()))
    assert roots['calls']==frame['rootCompleted']
    assert roots['cpuNs']==all_rows['selfCpuNs'] and roots['wallNs']==all_rows['selfWallNs']
    by_phase={}
    for number,phase in enumerate(PHASES):
        selected=[row for (p,label),row in rows.items() if p==number]
        logical=[row for (p,label),row in rows.items() if p==number and LABELS[label].startswith('logical.')]
        all_phase=sum_rows(selected);root_phase=sum_rows(logical)
        assert root_phase['cpuNs']==all_phase['selfCpuNs'] and root_phase['wallNs']==all_phase['selfWallNs']
        by_phase[phase]=root_phase
    return roots,by_phase


def parse_observations(work,terminal):
    path=work/'attribution.jsonl';raw=path.read_bytes();assert len(raw)<=12*1024**2
    records=raw.splitlines(keepends=True);frames=[];tail=b'';offset=0;previous_rows={};owners={}
    previous=None;last_rows={};negative_self_rows=0
    for number,line in enumerate(records):
        if not line.endswith(b'\n'):
            assert number==len(records)-1;tail=line;break
        assert len(line)<=65536
        value=json.loads(line)
        assert set(value)=={'schema','sequence','event','elapsedNs','phases','labels','rowFields','rows',
            'rootStarted','rootCompleted','current','ownerSequence','callbacks','errors','observer','stackDepth',
            'nativeInternalFunctionsMeasured'}
        assert value['schema']=='hms.storage-attribution/0.1'
        assert value['sequence']==len(frames) and value['phases']==PHASES and value['labels']==LABELS
        assert value['rowFields']==FIELDS and value['event'] in ('initial','before','after','final')
        assert not value['nativeInternalFunctionsMeasured'] and value['stackDepth']==0 and value['errors']==[]
        assert all(integer(value[key]) for key in ['sequence','elapsedNs','rootStarted','rootCompleted','ownerSequence'])
        assert value['rootCompleted']<=value['rootStarted']<=value['rootCompleted']+1
        current=value['current']
        if current is None:assert value['event']=='initial' and value['rootStarted']==0
        else:
            assert type(current) is dict and {'operation','ordinal'}<=set(current)<={'operation','ordinal','path','bytes','offset','raised'}
            assert current['operation'] in ['logical.'+name for name in PUBLIC] and current['ordinal']==value['rootStarted']
            if 'path' in current:assert type(current['path']) is str and len(current['path'].encode('utf-8'))<=4095
            if 'bytes' in current:assert integer(current['bytes']) and current['bytes']<=65536
            if 'offset' in current:assert integer(current['offset']) and current['offset']<=16*1024**2
            if 'raised' in current:assert type(current['raised']) is bool
        if value['event']=='before':assert value['rootStarted']==value['rootCompleted']+1
        if value['event'] in ('after','final'):assert value['rootStarted']==value['rootCompleted']
        observer=value['observer'];assert set(observer)=={'calls','cpuNs','wallNs','dropped','bytesWritten'}
        assert all(integer(item) for item in observer.values())
        assert observer['calls']==value['sequence'] and observer['dropped']==0 and observer['bytesWritten']==offset
        rows={}
        for entry in value['rows']:
            assert type(entry) is list and len(entry)==8 and all(type(item) is int for item in entry)
            p,n,*row=entry;assert 0<=p<len(PHASES) and 0<=n<len(LABELS) and (p,n) not in rows
            assert row[0]>0 and 0<=row[1]<=row[0] and row[2]>=0 and row[3]>=0
            assert row[4]<=row[2] and row[5]<=row[3]
            if row[4]<0 or row[5]<0:negative_self_rows+=1
            rows[p,n]=row
        assert set(previous_rows)<=set(rows)
        for key,before in previous_rows.items():assert all(rows[key][i]>=before[i] for i in range(4))
        roots,by_phase=conservation(value,rows)
        assert value['elapsedNs']>=roots['wallNs']+observer['wallNs']
        callbacks=value['callbacks']
        if callbacks is not None:
            assert set(callbacks)==CALLBACKS and all(integer(item) for item in callbacks.values())
            assert callbacks['readBytes']==4096*callbacks['readCalls'] and callbacks['programBytes']%16==0
            owner=value['ownerSequence'];assert owner>0
            if owner in owners:assert all(callbacks[key]>=item for key,item in owners[owner].items())
            owners[owner]=callbacks
        if previous is not None:
            assert value['elapsedNs']>=previous['elapsedNs'] and value['ownerSequence']>=previous['ownerSequence']
            assert value['rootStarted']>=previous['rootStarted'] and value['rootCompleted']>=previous['rootCompleted']
            assert all(observer[key]>=previous['observer'][key] for key in observer)
        frames.append(value);previous=value;previous_rows=rows;last_rows=rows;offset+=len(line)
    assert frames and frames[0]['event']=='initial' and frames[0]['rootCompleted']==0
    assert frames[0]['callbacks'] is None and frames[0]['ownerSequence']==0
    last=frames[-1];roots,by_phase=conservation(last,last_rows)
    final_path=work/'observer.json';final=read(final_path) if final_path.exists() else None
    complete_capture=last['event']=='final' and final is not None and not tail
    if final is not None:
        assert complete_capture and not final['errors'] and final['dropped']==final['residualStackDepth']==0
        assert not final['nativeInternalFunctionsMeasured'] and final['bytesWritten']==len(raw)
        assert final['calls']==len(frames)
        assert final['cpuNs']>=last['observer']['cpuNs'] and final['wallNs']>=last['observer']['wallNs']
        assert last['rootStarted']==last['rootCompleted']
    if terminal['returnCode']==0:
        assert complete_capture and not terminal['timedOut'] and roots['raised']==0
    categories={name:sum_rows([row for (phase,label),row in last_rows.items() if LABELS[label].startswith(name+'.')])
                for name in ['logical','hierarchy','native','provider','os']}
    labels={label:sum_rows([row for (phase,n),row in last_rows.items() if n==number]) for number,label in enumerate(LABELS)}
    labels={label:row for label,row in labels.items() if row['calls']}
    phase_labels={phase:{LABELS[label]:dict(zip(FIELDS,row)) for (p,label),row in last_rows.items() if p==number}
                  for number,phase in enumerate(PHASES)}
    wall_ns=round(terminal['elapsedSeconds']*1_000_000_000);cpu_ns=round(terminal['cpuSeconds']*1_000_000_000)
    assert wall_ns>=last['elapsedNs'] and cpu_ns>=roots['cpuNs']+last['observer']['cpuNs']
    prefix_gap=last['elapsedNs']-roots['wallNs']-last['observer']['wallNs']
    result=dict(logSha256=digest(path),frames=len(frames),logBytes=len(raw),partialTailBytes=len(tail),
        completeCapture=complete_capture,scopeCompleted=terminal['returnCode']==0 and not terminal['timedOut'],
        lastSequence=last['sequence'],lastEvent=last['event'],lastCurrentOperation=last['current'],
        lastOwnerSequence=last['ownerSequence'],lastCallbacks=last['callbacks'],
        lastRootStarted=last['rootStarted'],lastRootCompleted=last['rootCompleted'],
        observedPrefixElapsedWallNs=last['elapsedNs'],completedRootTotals=roots,completedRootTotalsByPhase=by_phase,
        inclusiveAndSelfTotalsByLabel=labels,inclusiveAndSelfTotalsByPhaseAndLabel=phase_labels,
        inclusiveAndSelfTotalsByCategory=categories,
        additiveSelfTotalsByCategory={name:dict(cpuNs=row['selfCpuNs'],wallNs=row['selfWallNs']) for name,row in categories.items()},
        observerBeforeLastFrame=last['observer'],observerFinalReceipt=final,
        prefixGapWallNs=prefix_gap,prefixCpuGapMeasured=False,
        processEnvelope=dict(wallNs=wall_ns,cpuNs=cpu_ns,
            wallMinusLastSnapshotElapsedNs=wall_ns-last['elapsedNs'],
            cpuMinusObservedRootsAndPriorObserverNs=cpu_ns-roots['cpuNs']-last['observer']['cpuNs']),
        unobservedSuffixMayExist=not complete_capture,negativeSelfRowsAcrossFrames=negative_self_rows,
        conservationVerified=True,nativeInternalFunctionsMeasured=False,productionSpeedupEstablished=False)
    if complete_capture:
        result['processEnvelope']['wallResidualAfterRootsAndFinalObserverNs']=wall_ns-roots['wallNs']-final['wallNs']
        result['processEnvelope']['cpuResidualAfterRootsAndFinalObserverNs']=cpu_ns-roots['cpuNs']-final['cpuNs']
    return result


def main():
    report=read(ATTEMPT/'RESULTS.json');inputs=read(ATTEMPT/'inputs.json')
    assert report['inputsStable'] and report['screenEquivalent'] and not report.get('observationInspectionErrors')
    for row in inputs['files']:assert digest(ROOT/row['path'])==digest(ATTEMPT/row['frozen'])==row['sha256']
    assert digest(FROZEN/'dataset.json')==inputs['datasetSha256']
    library_hash=inputs['librarySha256'];assert library_hash=='6b48f9b9c9a829a8c5c71236c309e7e78f55f096e7c627542a739095ff57ec7a'
    assert digest(ATTEMPT/'hierarchical-store.so')==library_hash
    assert digest(ATTEMPT/'mount-probe.so')==inputs['mountLibrarySha256']=='450f1d2bfd948ca0f7292884e753ccc11fd9f82dc285e150cf535864b75572bd'
    assert all(digest(Path(row['path']))==row['sha256'] for row in inputs['host']['files'])
    assert digest(PRIOR/'index.json')=='a820ce8adda0d8e3dbb1827f2b47c48f94c7969cccc299fbd10e36fbce54f982'
    prior=read(PRIOR/'index.json');assert len(prior['files'])==340 and len(prior['symlinks'])==1
    assert all(digest(PRIOR/row['path'])==row['sha256'] for row in prior['files'])
    assert all((PRIOR/row['path']).is_symlink() and os.readlink(PRIOR/row['path'])==row['target'] for row in prior['symlinks'])
    assert read(PRIOR/'RESULTS.json')['focusedChecks']==192
    processes=[]
    for path in sorted(ATTEMPT.glob('*/started.json')):
        start=read(path);end=read(path.with_name('result.json'));intent=read(path.with_name('intent.json'))
        assert end['reaped'] and not Path('/proc',str(start['pid'])).exists()
        assert intent['addressSpaceBytes']==512*1024**2 and intent['fileBytes']==16*1024**2 and intent['descriptors']==128
        assert (intent['wallSeconds'],intent['cpuSeconds'])==((180,120) if path.parent.name.startswith('replay_') else (60,40))
        if path.parent.name in report['scopes']:assert end['returnCode']==0 and not end['timedOut']
        else:assert end['returnCode']!=0 or end['timedOut']
        processes.append(dict(scope=path.parent.name,pid=start['pid'],**end))
    spec=importlib.util.spec_from_file_location('hms_attribution_retained_reader',Path(__file__).parent/'retained_reader.py')
    reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    images={};comparisons={}
    for name in ['comparison-original','comparison-observed']:
        work=ATTEMPT/name;receipt=read(work/'diagnostic.json')
        assert digest(work/'diagnostic.json')==report['scopes'][name]['receiptSha256']
        assert receipt['status']=='passed' and len(receipt['steps'])==426
        assert read(work/'stdout.txt')=={key:item for key,item in receipt.items() if key not in ['spans','steps','expectedFiles','backingHashes']}
        assert not (work/'stderr.txt').read_bytes()
        image=reader.inspect(work/'image',work/'anchor.json',library_hash);images[name+'/image']=image
        bodies=reader.bodies(image)
        rows=[dict(path=path,bytes=len(body),sha256=hashlib.sha256(body).hexdigest()) for path,body in sorted(bodies.items())]
        assert rows==receipt['expectedFiles'] and len(rows)==40 and len(image['directories'])==20
        assert not image['pending'] and not image['unlinked'] and set(image['physical'])==set(image['nodes'])
        assert image['backingHashes']==receipt['backingHashes']
        comparisons[name]=receipt
    left,right=comparisons.values()
    for key in ['expectedFiles','firstOwnerCallbacks','coldOwnerCallbacks','backingHashes','providerSyncCalls']:assert left[key]==right[key]
    for a,b in zip(left['steps'],right['steps']):
        assert {key:value for key,value in a.items() if key not in ('cpuNs','wallNs')}=={key:value for key,value in b.items() if key not in ('cpuNs','wallNs')}
    first,second=images.values()
    for key in ['nodes','files','directories','pending','unlinked','duplicates','physical']:assert first[key]==second[key]
    dataset=read(FROZEN/'dataset.json');source=Path(dataset['sourceRoot'])
    assert len(dataset['files'])==4270 and len(dataset['directories'])==169 and sum(row['bytes'] for row in dataset['files'])==35508922
    assert all(digest(source/row['path'])==row['sha256'] for row in dataset['files'])
    replay=None;writer=ATTEMPT/'replay_write'
    if writer.exists():
        observed=reader.inspect(writer/'image',writer/'image-anchor.json',library_hash);images['replay_write/image']=observed
        lines=(writer/'progress.jsonl').read_bytes().splitlines(keepends=True);rows=[];tail=b''
        for index,line in enumerate(lines):
            if not line.endswith(b'\n'):assert index==len(lines)-1;tail=line;break
            rows.append(json.loads(line))
        directories_complete=bool(rows and 'directoriesComplete' in rows[0])
        if directories_complete:assert rows.pop(0)['directoriesComplete']==169
        assert rows==dataset['files'][:len(rows)]
        actual=reader.bodies(observed);wanted={row['path']:row for row in rows};assert set(wanted)<=set(actual)
        for name,row in wanted.items():assert len(actual[name])==row['bytes'] and hashlib.sha256(actual[name]).hexdigest()==row['sha256']
        extra=set(actual)-set(wanted);assert len(extra)<=1
        if extra:
            assert extra=={dataset['files'][len(rows)]['path']}
            for name in extra:assert (source/name).read_bytes()[:len(actual[name])]==actual[name]
        assert observed['directories']==set(dataset['directories']) if directories_complete else observed['directories']<=set(dataset['directories'])
        complete='replay_write' in report['scopes']
        if complete:assert len(rows)==4270 and not extra and not tail
        else:assert not (ATTEMPT/'replay_read').exists()
        replay=dict(completeWriterReceipt=complete,completedFileBodiesVerified=len(rows),completeBodyBytes=sum(row['bytes'] for row in rows),
            directoriesVerified=len(observed['directories']),extraPublishedFiles=[dict(path=name,committedBytes=len(actual[name])) for name in sorted(extra)],
            unlinkedInodes=sorted(observed['unlinked']),incompletePhysicalInodes=sorted(set(observed['physical'])-set(observed['nodes'])),
            pendingEntries=observed['pending'],partialProgressTailBytes=len(tail),dependentColdReaderRun=(ATTEMPT/'replay_read').exists())
    for name in ['replay_write','replay_read']:
        if name in report['scopes']:
            work=ATTEMPT/name;checks=read(work/'checks.json')
            assert digest(work/'checks.json')==report['scopes'][name]['receiptSha256'] and checks==read(work/'stdout.txt')
            assert checks['status']=='passed' and len(checks['checks'])==report['scopes'][name]['checks']
            assert not (work/'stderr.txt').read_bytes()
    metrics={}
    for name in ['comparison-observed','replay_write']:
        work=ATTEMPT/name
        if (work/'attribution.jsonl').exists():metrics[name]=parse_observations(work,read(work/'result.json'))
    observed_metrics=metrics['comparison-observed'];assert observed_metrics['lastRootCompleted']==426 and observed_metrics['lastOwnerSequence']==2
    measured=observed_metrics['inclusiveAndSelfTotalsByLabel']
    assert measured['provider.read']['calls']==sum(right[key]['readCalls'] for key in ['firstOwnerCallbacks','coldOwnerCallbacks'])
    assert measured['provider.sync']['calls']==sum(right[key]['syncs'] for key in ['firstOwnerCallbacks','coldOwnerCallbacks'])
    assert measured['os.fsync']['calls']==right['providerSyncCalls']['fsync']
    if 'replay_write' in metrics:
        measured=metrics['replay_write']['inclusiveAndSelfTotalsByLabel'];callbacks=metrics['replay_write']['lastCallbacks']
        if callbacks is not None:
            assert metrics['replay_write']['lastOwnerSequence']==1
            assert measured['provider.read']['calls']==callbacks['readCalls']
            assert measured['provider.erase']['calls']==callbacks['erases']
            assert measured['provider.write']['calls']==callbacks['programCalls']+callbacks['erases']
            assert measured['provider.sync']['calls']==callbacks['syncs']
            assert measured['os.fsync']['calls']==callbacks['syncs']*8+12
    baseline=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(baseline)=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    public=read(baseline)['files'];assert len(public)==244 and all(digest(ROOT/row['path'])==row['sha256'] for row in public)
    metric_report=dict(schema='hms.storage-attribution-analysis/0.1',scopes=metrics,
        meanings=dict(inclusive='Contains nested observed work; categories overlap and are not additive.',
            self='Inclusive duration minus nested traced spans. Self categories partition completed root time; includes tracing overhead.',
            nativeSelf='Native boundary/ctypes/tracer residual, not individual C function time.',
            prefixGapWall='Last elapsed wall minus completed roots minus earlier observer work; includes unwrapped harness/setup/bookkeeping.',
            processRemainder='Includes startup/teardown and any unobserved suffix; cannot be assigned to one component.',
            observerBeforeLastFrame='Excludes the current frame, whose serialization starts after its elapsed timestamp.',
            observerFinalReceipt='Includes final snapshot work but excludes its own subsequent report publication.'),
        pairedScreen=dict(originalCPU=left['cpuSeconds'],observedCPU=right['cpuSeconds'],originalWall=left['elapsedSeconds'],observedWall=right['elapsedSeconds'],
            differenceIncludesInstrumentationAndRunVariation=True,semanticAndRawEquality=True,productionSpeedupEstablished=False),
        nativeInternalFunctionsMeasured=False,fullDatasetExtrapolation=False,physicalPowerLossTested=False)
    save(HERE/'METRICS.json',metric_report)
    result=dict(status='verified',priorFilesRevalidated=340,priorSymlinksRevalidated=1,priorFocusedChecksRevalidated=192,priorFocusedChecksRerun=False,
        imagesReadOnly=len(images),processes=processes,replay=replay,publicInputsExact=244,
        screenLogicalSteps=426,screenCallbackAndRawEquality=True,metricsSha256=digest(HERE/'METRICS.json'),
        recoveryInvoked=False,allBackingBytesUnchanged=True,serviceStorageQualified=False,nativeInternalFunctionsMeasured=False,
        images=[dict(path=name,files=len(value['files']),directories=len(value['directories']),unlinkedInodes=sorted(value['unlinked']),
            incompletePhysicalInodes=sorted(set(value['physical'])-set(value['nodes'])),pendingEntries=value['pending'],backingHashes=value['backingHashes'],callbacks=value['callbacks']) for name,value in images.items()])
    save(HERE/'EVIDENCE-AUDIT.json',result)
    print(json.dumps({key:value for key,value in result.items() if key not in ('images','processes')},sort_keys=True),flush=True)


if __name__=='__main__':main()
