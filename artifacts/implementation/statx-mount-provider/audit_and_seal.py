"""Final byte/receipt audit and single immutable stage index; no image opens."""
import ast
import hashlib
import json
import os
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ATTEMPT=HERE/'attempt01'


def read(path):return json.loads(path.read_text())
def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def save(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
def exact(directory,wanted):
    assert digest(directory/'index.json')==wanted
    rows=read(directory/'index.json')['files']
    assert all(digest(directory/row['path'])==row['sha256'] for row in rows)
    return dict(path=str(directory.relative_to(ROOT)),indexSha256=wanted,filesExact=len(rows))
def functions(path):
    return [ast.dump(node,include_attributes=False) for node in ast.parse(path.read_text()).body
            if isinstance(node,(ast.FunctionDef,ast.ClassDef))]


def main():
    assert not (HERE/'index.json').exists()
    prior=ROOT/'artifacts/implementation/hierarchical-chunk-store'
    seals=[exact(prior,'8916d9e9a431fb0135d743daf38b746b5248cd81aee20dc4f92c9c645e33e26a'),
        exact(ROOT/'artifacts/verification/hierarchical-storage-cost','68016f79f80a3e85a853f87ed0ef8e62d8862298c64718656098087d0b5cdadb'),
        exact(ROOT/'research/host-contract/mount-identity','425ee4e745b8c3e91ab789f3899f61fb2755d7e3e9263ac67481a2fa54357a34'),
        exact(ROOT/'research/host-contract/mount-predicate-source','9bd45ebb58469630668347c7f763bbf903811ef5f70afd8e34601d0374721970')]
    inputs=read(ATTEMPT/'inputs.json');result=read(ATTEMPT/'RESULTS.json');audit=read(HERE/'EVIDENCE-AUDIT.json')
    assert result['status']=='failed-or-inconclusive' and result['inputsStable'] and result['comparisonEquivalent']
    assert audit['status']=='verified' and audit['imagesReadOnly']==21 and audit['allBackingBytesUnchanged']
    assert not audit['recoveryInvoked'] and not result['publicRuntimeChanged']
    assert audit['nativeControls']==69 and audit['mountControls']==52 and audit['originalProviderTests']==24 and audit['semanticChecks']==96
    assert audit['replay']['completedFileBodiesVerified']==1277 and audit['replay']['completeBodyBytes']==5868766
    assert audit['replay']['directoriesVerified']==169 and not audit['replay']['completeWriterReceipt']
    assert not (ATTEMPT/'replay_read').exists()
    assert all(digest(ROOT/row['path'])==digest(ATTEMPT/row['frozen'])==row['sha256'] for row in inputs['files'])
    assert digest(Path(inputs['compiler']))==inputs['compilerSha256']
    assert all(digest(Path(row['path']))==row['sha256'] for row in read(ATTEMPT/'headers.json'))
    assert all(digest(Path(row['path']))==row['sha256'] for row in read(HERE/'host-observation.json')['files'])
    assert digest(ATTEMPT/'mount-probe.so')==result['mountLibrarySha256']
    assert digest(ATTEMPT/'hierarchical-store.so')==result['librarySha256']
    for name in ['hierarchical_store.py','chunk_store_base.py','native.py']:
        assert (HERE/name).read_bytes()==(prior/name).read_bytes()
    assert (HERE/'test_fixed_block.py').read_bytes()==(ROOT/'artifacts/implementation/fixed-block-storage/test_fixed_block.py').read_bytes()
    assert functions(HERE/'controls.py')==functions(prior/'controls.py')
    assert functions(HERE/'diagnostic.py')==functions(ROOT/'artifacts/verification/hierarchical-storage-cost/diagnostic.py')
    assert (HERE/'retained_reader.py').read_bytes()==(prior/'audit_evidence.py').read_bytes()
    assert (HERE/'run_audit.py').read_bytes()==(ROOT/'artifacts/verification/hierarchical-storage-cost/run_audit.py').read_bytes()
    for name in ['audit_evidence.py','run_audit.py','AUDIT-PLAN.md','retained_reader.py']:
        assert digest(HERE/name)==digest(HERE/'audit-process01'/name)==read(HERE/'audit-process01/intent.json')['sourceSha256'][name]
    processes=[]
    for path in sorted(ATTEMPT.glob('*/started.json'))+[HERE/'audit-process01/started.json']:
        start=read(path);end=read(path.with_name('result.json'))
        assert end['reaped'] and not Path('/proc',str(start['pid'])).exists()
        if path.parent.name=='replay_write':
            assert end['timedOut'] and end['returnCode']==-9 and 180<=end['elapsedSeconds']<182
        else:
            assert not end['timedOut'] and end['returnCode']==0
        processes.append(dict(scope=path.parent.name,pid=start['pid'],**end))
    assert len(processes)==20
    assert not (HERE/'audit-process01/stderr.txt').read_bytes()
    assert read(HERE/'audit-process01/stdout.txt')=={k:v for k,v in audit.items() if k not in ('images','processes')}
    baseline=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(baseline)=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    public=read(baseline)['files'];assert len(public)==244 and all(digest(ROOT/row['path'])==row['sha256'] for row in public)
    for row in audit['images']:
        assert {p.name:digest(p) for p in (ATTEMPT/row['path']).iterdir()}==row['backingHashes']
    docs=[dict(path=name,sha256=digest(ROOT/name)) for name in ['README.md','PROGRESS.md','docs/control-storage.md','docs/io-driver-hub-control.md']]
    save(HERE/'RESULTS.json',dict(status='focused-controls-passed-full-replay-timeout',focusedChecks=241,
         comparisonEquivalent=True,writerComplete=False,coldReaderRun=False,fullWorkflowQualified=False,
         publicRuntimeChanged=False,publicInputsExact=244,evidenceAuditSha256=digest(HERE/'EVIDENCE-AUDIT.json')))
    save(HERE/'AUDIT.json',dict(status='verified',priorSeals=seals,sourceInputs=len(inputs['files']),processes=processes,
         publicInputsExact=244,publicReceiptSha256=digest(baseline),currentDocuments=docs,
         primaryAgentReview=True,independentHelperReview=False,goalComplete=False))
    rows=[]
    for path in sorted(HERE.rglob('*')):
        if path.is_file():
            info=path.stat();assert info.st_size<=16*1024**2
            rows.append(dict(path=str(path.relative_to(HERE)),bytes=info.st_size,allocatedBytes=info.st_blocks*512,sha256=digest(path)))
    allocated=sum(row['allocatedBytes'] for row in rows);assert allocated<1024**3
    save(HERE/'index.json',dict(files=rows,allocatedBytesBeforeIndex=allocated,filesBeforeIndex=len(rows),
         status='sealed-incomplete-full-workflow',publicRuntimeChanged=False))
    assert all(digest(HERE/row['path'])==row['sha256'] for row in rows)
    print(json.dumps(dict(indexSha256=digest(HERE/'index.json'),files=len(rows),bytes=sum(row['bytes'] for row in rows),allocatedBytesBeforeIndex=allocated),sort_keys=True))


if __name__=='__main__':main()
