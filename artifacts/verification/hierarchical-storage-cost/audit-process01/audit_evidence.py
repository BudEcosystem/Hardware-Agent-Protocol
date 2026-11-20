"""Read-only evidence joins and independent reconstruction; no recovery."""
from collections import Counter,defaultdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

HERE=Path(os.environ['HMS_AUDIT_STAGE']);ROOT=HERE.parents[2];ATTEMPT=HERE/'attempt01'
FROZEN=ATTEMPT/'frozen-inputs'

def read(path):return json.loads(path.read_text())
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,value):
    with (HERE/name).open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')

def main():
    result=read(ATTEMPT/'RESULTS.json');inputs=read(ATTEMPT/'inputs.json')
    assert result['status']=='passed' and result['instrumentationEquivalent'] and result['stepsPerMode']==426
    assert result['inputsStable'] and not result['disabledChecks'] and not result['disabledFsync']
    for row in inputs['files']:assert digest(ROOT/row['path'])==digest(FROZEN/row['frozen'])==row['sha256']
    spec=importlib.util.spec_from_file_location('hms_storage_cost_retained_reader',Path(__file__).parent/'retained_reader.py')
    reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    reader.ATTEMPT=FROZEN  # Only select the exact library location; reader code stays unchanged.
    observed=[];reports={};anchors=[];processes=[]
    for mode in ['coarse','nested']:
        work=ATTEMPT/mode;report=read(work/'diagnostic.json');reports[mode]=report
        assert digest(work/'diagnostic.json')==result['modes'][mode]['receiptSha256']
        assert read(work/'stdout.txt')=={k:v for k,v in report.items() if k not in ['spans','steps','expectedFiles','backingHashes']}
        terminal=read(work/'result.json');start=read(work/'started.json')
        assert terminal['returnCode']==0 and terminal['reaped'] and not terminal['timedOut']
        assert not Path('/proc',str(start['pid'])).exists()
        processes.append(dict(mode=mode,pid=start['pid'],**terminal))
        snapshot=reader.inspect(work/'image',work/'anchor.json',digest(FROZEN/'hierarchical-store.so'))
        bodies=reader.bodies(snapshot)
        assert len(bodies)==40 and len(snapshot['directories'])==20 and not snapshot['unlinked'] and not snapshot['pending']
        rows=[dict(path=name,bytes=len(body),sha256=hashlib.sha256(body).hexdigest()) for name,body in sorted(bodies.items())]
        assert rows==report['expectedFiles'] and sum(r['bytes'] for r in rows)==623624
        assert snapshot['backingHashes']==report['backingHashes']
        observed.append(dict(mode=mode,backingHashes=snapshot['backingHashes'],logicalRows=rows,callbacks=snapshot['callbacks']))
        anchors.extend(tuple(pair) for pair in read(work/'anchor.json')['objects'].values())
    assert len(anchors)==len(set(anchors))==22
    coarse,nested=reports['coarse'],reports['nested']
    for key in ['expectedFiles','backingHashes','firstOwnerCallbacks','coldOwnerCallbacks']:assert coarse[key]==nested[key]
    for left,right in zip(coarse['steps'],nested['steps']):
        assert {k:v for k,v in left.items() if k not in ['wallNs','cpuNs']}=={k:v for k,v in right.items() if k not in ['wallNs','cpuNs']}
    assert len(coarse['steps'])==len(nested['steps'])==426
    totals=defaultdict(Counter);phase=defaultdict(Counter)
    for name,row in nested['spans'].items():
        group,label=name.split('/',1);totals[label].update(row)
        phase[group]['allSelfWallNs']+=row['selfWallNs'];phase[group]['allSelfCpuNs']+=row['selfCpuNs']
        if label.startswith('logical.'):
            phase[group]['logicalWallNs']+=row['wallNs'];phase[group]['logicalCpuNs']+=row['cpuNs']
    for row in phase.values():
        assert row['allSelfWallNs']==row['logicalWallNs'] and row['allSelfCpuNs']==row['logicalCpuNs']
    callbacks=Counter(nested['firstOwnerCallbacks']);callbacks.update(nested['coldOwnerCallbacks'])
    provider_calls=sum(callbacks[k] for k in ['readCalls','programCalls','erases','syncs'])
    assert provider_calls==23775==totals['provider._perform']['calls']
    assert totals['provider._verify']['calls']==provider_calls+2
    assert totals['provider.mount_check']['calls']==provider_calls+5==23780
    assert totals['os.fsync']['calls']==callbacks['syncs']*8+12==13724
    assert callbacks['readCalls']==19816 and callbacks['readBytes']==81166336
    analysis=dict(status='verified-attribution-screen',coarseCpuSeconds=coarse['cpuSeconds'],nestedCpuSeconds=nested['cpuSeconds'],
        coarseWallSeconds=coarse['elapsedSeconds'],nestedWallSeconds=nested['elapsedSeconds'],callbackCounts=dict(callbacks),
        mountCheckCalls=totals['provider.mount_check']['calls'],mountCheckCpuSeconds=totals['provider.mount_check']['cpuNs']/1e9,
        mountCheckWallSeconds=totals['provider.mount_check']['wallNs']/1e9,
        mountCheckPercentOfNestedProcessCPU=100*totals['provider.mount_check']['cpuNs']/1e9/nested['cpuSeconds'],
        fsyncCalls=totals['os.fsync']['calls'],fsyncCpuSeconds=totals['os.fsync']['cpuNs']/1e9,fsyncWallSeconds=totals['os.fsync']['wallNs']/1e9,
        phases=dict(phase),inclusiveAndExclusiveSpans=dict(totals),intrusiveTiming=True,
        rootCauseOfPriorWholeWorkflowEstablished=False,productionSpeedupEstablished=False)
    save('ANALYSIS.json',analysis)
    baseline=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(baseline)=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    rows=read(baseline)['files'];assert len(rows)==244 and all(digest(ROOT/r['path'])==r['sha256'] for r in rows)
    output=dict(status='verified',images=observed,distinctObjectAnchors=22,processes=processes,logicalFilesPerImage=40,
        fullBodyBytesPerImage=623624,stepsPerMode=426,allBackingBytesUnchanged=True,recoveryInvoked=False,
        mutationCallbacksAllowed=False,publicInputsExact=244,analysisSha256=digest(HERE/'ANALYSIS.json'),fullWorkflowQualified=False)
    save('EVIDENCE-AUDIT.json',output)
    print(json.dumps({k:v for k,v in output.items() if k not in ('images','processes')},sort_keys=True),flush=True)

if __name__=='__main__':main()
