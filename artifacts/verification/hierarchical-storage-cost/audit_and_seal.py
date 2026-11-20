"""Final read-only joins for diagnostic, research and unchanged public runtime."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];ATTEMPT=HERE/'attempt01'
RESEARCH=ROOT/'research/host-contract/mount-identity'
PRIOR=ROOT/'artifacts/implementation/hierarchical-chunk-store'

def read(path):return json.loads(path.read_text())
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,value):
    with (HERE/name).open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')

def main():
    assert not (HERE/'index.json').exists()
    result=read(ATTEMPT/'RESULTS.json');evidence=read(HERE/'EVIDENCE-AUDIT.json')
    assert result['status']=='passed' and result['instrumentationEquivalent'] and result['inputsStable']
    assert evidence['status']=='verified' and evidence['allBackingBytesUnchanged'] and not evidence['recoveryInvoked']
    assert digest(HERE/'ANALYSIS.json')==evidence['analysisSha256']
    inputs=read(ATTEMPT/'inputs.json')
    for row in inputs['files']:assert digest(ROOT/row['path'])==digest(ATTEMPT/'frozen-inputs'/row['frozen'])==row['sha256']
    audit=HERE/'audit-process01';terminal=read(audit/'result.json')
    assert terminal['returnCode']==0 and terminal['reaped'] and not terminal['timedOut']
    assert (audit/'stderr.txt').stat().st_size==0
    assert read(audit/'stdout.txt')=={k:v for k,v in evidence.items() if k not in ('images','processes')}
    for name,wanted in read(audit/'intent.json')['sourceSha256'].items():assert digest(HERE/name)==digest(audit/name)==wanted
    assert digest(HERE/'retained_reader.py')==digest(PRIOR/'audit_evidence.py')
    for image in evidence['images']:
        for name,wanted in image['backingHashes'].items():assert digest(ATTEMPT/image['mode']/'image'/name)==wanted
    processes=[]
    for path in sorted(HERE.rglob('started.json')):
        start=read(path);end=read(path.with_name('result.json'))
        assert end['returnCode']==0 and end['reaped'] and not end['timedOut'] and not Path('/proc',str(start['pid'])).exists()
        processes.append(dict(path=str(path.relative_to(HERE)),pid=start['pid'],**end))
    assert len(processes)==3
    assert digest(PRIOR/'index.json')=='8916d9e9a431fb0135d743daf38b746b5248cd81aee20dc4f92c9c645e33e26a'
    previous=read(PRIOR/'index.json')['files'];assert len(previous)==212 and all(digest(PRIOR/r['path'])==r['sha256'] for r in previous)
    research=read(RESEARCH/'index.json')['files'];assert all(digest(RESEARCH/r['path'])==r['sha256'] for r in research)
    reading=read(RESEARCH/'READING.json');assert reading['externalLfLinesRead']==1703
    counterexample=read(RESEARCH/'COUNTEREXAMPLE.json');assert counterexample['status']=='counterexample-confirmed' and not counterexample['pinComparisonDetectsChange']
    assert counterexample['sourceSha256']==digest(PRIOR/'fixed_block.py')
    runtime=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(runtime)=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    public=read(runtime)['files'];assert len(public)==244 and all(digest(ROOT/r['path'])==r['sha256'] for r in public)
    chunks=list(HERE.rglob('chunk-*'));assert len(chunks)==16 and all(p.stat().st_size==16*1024**2 for p in chunks)
    documents=['README.md','PROGRESS.md','docs/control-storage.md','docs/io-driver-hub-control.md']
    save('AUDIT.json',dict(status='verified',sourceInputsExact=len(inputs['files']),priorFilesExact=212,
        researchFilesExact=len(research),researchIndexSha256=digest(RESEARCH/'index.json'),externalManualLfLinesRead=1703,
        publicInputsExact=244,publicTestsAlreadyPassing=866,publicSuiteRepeated=False,reviewer='primary agent only',
        backingChunks=16,backingBytes=256*1024**2,processes=processes,evidenceSha256=digest(HERE/'EVIDENCE-AUDIT.json'),
        currentDocuments=[dict(path=p,sha256=digest(ROOT/p)) for p in documents]))
    save('RESULTS.json',dict(status='diagnostic-verified-provider-replacement-required',diagnosticPassed=True,
        instrumentationEquivalent=True,readOnlyAuditPassed=True,syntheticMountParserCounterexampleConfirmed=True,
        newMountPredicateImplemented=False,fullWorkflowQualified=False,publicRuntimeChanged=False,completeGoal=False))
    rows=[dict(path=str(p.relative_to(HERE)),bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(HERE.rglob('*')) if p.is_file()]
    allocated=sum(p.stat().st_blocks*512 for p in HERE.rglob('*') if p.is_file())
    assert allocated<1024**3 and all(r['bytes']<=16*1024**2 for r in rows)
    save('index.json',dict(files=rows));assert all(digest(HERE/r['path'])==r['sha256'] for r in rows)
    print(json.dumps(dict(status='sealed',files=len(rows),bytes=sum(r['bytes'] for r in rows),allocatedBytesBeforeIndex=allocated,
                         indexSha256=digest(HERE/'index.json'),researchIndexSha256=digest(RESEARCH/'index.json')),sort_keys=True))

if __name__=='__main__':main()
