"""Verify immutable evidence and current public inputs, then seal this stage once."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def read(path):return json.loads(path.read_text())
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')

def main():
    assert not (HERE/'index.json').exists()
    attempt=HERE/'attempt01';result=read(attempt/'RESULTS.json');evidence=read(HERE/'EVIDENCE-AUDIT.json')
    assert result['status']=='failed-or-inconclusive' and result['inputsStable']
    assert evidence['status']=='verified' and evidence['semanticChecks']==96 and evidence['imagesReadOnly']==19
    assert evidence['allBackingBytesUnchanged'] and not evidence['recoveryInvoked']
    assert sum(row['checks'] for row in result['scopes'].values())==96 and len(result['scopes'])==9
    assert result['librarySha256']==digest(attempt/'hierarchical-store.so')
    inputs=read(attempt/'inputs.json')
    for row in inputs['files']:
        assert digest(ROOT/row['path'])==digest(attempt/'frozen-inputs'/row['frozen'])==row['sha256']
    assert digest(Path(inputs['compiler']))==inputs['compilerSha256']
    assert digest(attempt/'frozen-inputs/dataset.json')==inputs['datasetSha256']
    dataset=read(attempt/'frozen-inputs/dataset.json');source=Path(dataset['sourceRoot'])
    assert len(dataset['files'])==4270 and len(dataset['directories'])==169
    assert all(digest(source/r['path'])==r['sha256'] for r in dataset['files'])
    audit=HERE/'audit-process01';audit_result=read(audit/'result.json')
    assert audit_result['returnCode']==0 and not audit_result['timedOut'] and audit_result['reaped']
    assert (audit/'stderr.txt').stat().st_size==0
    assert read(audit/'stdout.txt')=={k:v for k,v in evidence.items() if k not in ('images','processes')}
    for name,wanted in read(audit/'intent.json')['sourceSha256'].items():assert digest(HERE/name)==digest(audit/name)==wanted
    processes=[]
    for start_path in sorted(HERE.rglob('started.json')):
        start=read(start_path);end=read(start_path.with_name('result.json'))
        assert end['reaped'] and not Path('/proc',str(start['pid'])).exists()
        if start_path.parent==attempt/'replay_write':assert end['returnCode']==-9 and end['timedOut']
        else:assert end['returnCode']==0 and not end['timedOut']
        processes.append(dict(path=str(start_path.relative_to(HERE)),pid=start['pid'],returnCode=end['returnCode']))
    assert len(processes)==13
    for image in evidence['images']:
        for name,wanted in image['backingHashes'].items():assert digest(attempt/image['path']/name)==wanted
    prior=ROOT/'artifacts/verification/supervisor-storage-integration'
    assert digest(prior/'index.json')=='8a5cd13eeb4544fecdb1d4b81da231b8daea9beacfe7840b5989b110f90ef15a'
    previous=read(prior/'index.json')['files']
    assert len(previous)==20821 and all(digest(prior/r['path'])==r['sha256'] for r in previous)
    runtime=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(runtime)=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    public=read(runtime)['files'];assert len(public)==244 and all(digest(ROOT/r['path'])==r['sha256'] for r in public)
    chunks=list(HERE.rglob('chunk-*'));assert len(chunks)==26 and all(p.stat().st_size==16*1024**2 for p in chunks)
    documents=['README.md','PROGRESS.md','docs/control-storage.md','docs/io-driver-hub-control.md']
    save(HERE/'AUDIT.json',dict(status='verified',priorSealFilesExact=len(previous),sourceInputsExact=len(inputs['files']),
         publicRuntimeInputsExact=244,existingPublicTests=866,publicSuiteRepeated=False,reviewer='primary agent only',
         retainedImages=19,backingChunks=26,backingBytes=26*16*1024**2,processes=processes,
         currentDocuments=[dict(path=p,sha256=digest(ROOT/p)) for p in documents],
         evidenceAuditSha256=digest(HERE/'EVIDENCE-AUDIT.json'),attemptSha256=digest(attempt/'RESULTS.json')))
    save(HERE/'RESULTS.json',dict(status='partial-progress-workload-gate-failed',semanticChecks=96,semanticScopes=9,
         workflowWriter=read(attempt/'replay_write/result.json'),replay=evidence['replay'],
         independentReadOnlyAuditPassed=True,publicRuntimeInstalled=False,serviceStorageQualified=False,
         completeGoal=False,originalImagesPreserved=True,unchangedExperimentalRetry=False))
    rows=[dict(path=str(p.relative_to(HERE)),bytes=p.stat().st_size,sha256=digest(p))
          for p in sorted(HERE.rglob('*')) if p.is_file()]
    assert all(row['bytes']<=16*1024**2 for row in rows)
    allocated=sum(p.stat().st_blocks*512 for p in HERE.rglob('*') if p.is_file())
    assert allocated<1024**3
    save(HERE/'index.json',dict(files=rows))
    assert all(digest(HERE/r['path'])==r['sha256'] for r in rows)
    print(json.dumps(dict(status='sealed',files=len(rows),bytes=sum(r['bytes'] for r in rows),
          allocatedBytesBeforeIndex=allocated,indexSha256=digest(HERE/'index.json')),sort_keys=True))

if __name__=='__main__':main()
