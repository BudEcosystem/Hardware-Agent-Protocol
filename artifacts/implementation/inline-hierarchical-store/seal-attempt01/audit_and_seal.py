"""Final exact-byte/receipt joins and a self-excluding stage index; no native opens."""
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


def main():
    assert not (HERE/'index.json').exists()
    prior=ROOT/'artifacts/implementation/statx-mount-provider'
    original=ROOT/'artifacts/implementation/hierarchical-chunk-store'
    seals=[exact(prior,'4f095672f8184289086f7688c19325df79eb781aa122194f416ed961af553159'),
        exact(original,'8916d9e9a431fb0135d743daf38b746b5248cd81aee20dc4f92c9c645e33e26a'),
        exact(ROOT/'artifacts/implementation/tracked-chunk-sync','7b478a7138f98d0c2afb63d6daab1ec4deb12d7fb0685c17aa71fa26e41741f8'),
        exact(ROOT/'research/host-contract/littlefs-core','c149f635c72262102a1d5c2ff3f2fc08c56fc6dc1fc9a1306037114d1650fd0e'),
        exact(ROOT/'research/host-contract/littlefs-inline-review','b94cdb6ce5c4f4b2e4ea9c7cfc84731135fb63b7b25b733ac00f5a7a03af11bb')]
    inputs=read(ATTEMPT/'inputs.json');result=read(ATTEMPT/'RESULTS.json');audit=read(HERE/'EVIDENCE-AUDIT.json')
    assert result['status']=='failed-or-inconclusive' and result['inputsStable'] and result['comparisonEquivalent']
    assert result['inlineLimit']==512 and result['physicalEncodingsDiffer'] and not result['syncSelectionChanged']
    assert not any(result[key] for key in ['publicRuntimeChanged','actualMountChanges','geometryChanged','checksDisabled','durabilityBarriersDisabled','sqliteTested','serviceStorageQualified'])
    assert audit['status']=='verified' and audit['imagesReadOnly']==23 and audit['allBackingBytesUnchanged']
    assert not audit['recoveryInvoked'] and not audit['physicalPowerLossTested']
    assert audit['nativeControlCases']==12 and audit['nativeControlAssertions']==1294
    assert audit['mountControls']==52 and audit['profileControls']==8 and audit['originalProviderTests']==24 and audit['semanticChecks']==96
    assert audit['replay']==dict(completeWriterReceipt=False,completedFileBodiesVerified=1182,
        completeBodyBytes=5429966,directoriesVerified=169,extraPublishedFiles=[],unlinkedInodes=[],
        incompletePhysicalInodes=[],pendingEntries=[],partialProgressTailBytes=0,dependentColdReaderRun=False)
    assert not (ATTEMPT/'replay_read').exists()
    for row in inputs['files']:assert digest(ROOT/row['path'])==digest(ATTEMPT/row['frozen'])==row['sha256']
    assert digest(Path(inputs['compiler']))==inputs['compilerSha256']
    assert all(digest(Path(row['path']))==row['sha256'] for row in read(ATTEMPT/'headers.json'))
    assert all(digest(Path(row['path']))==row['sha256'] for row in read(HERE/'host-observation.json')['files'])
    assert digest(ATTEMPT/'hierarchical-store.so')==result['librarySha256']=='6b48f9b9c9a829a8c5c71236c309e7e78f55f096e7c627542a739095ff57ec7a'
    assert digest(ATTEMPT/'original-hierarchical-store.so')==result['originalLibrarySha256']=='7049dc14940b0f686f5cbe682e85f70944a8074936786e7f962c6ee29ed321de'
    assert digest(ATTEMPT/'mount-probe.so')==result['mountLibrarySha256']=='450f1d2bfd948ca0f7292884e753ccc11fd9f82dc285e150cf535864b75572bd'
    for name in ['fixed_block.py','mount_identity.py','mount_controls.py','native.py','chunk_store_base.py','controls.py','controls.patch','test_fixed_block.py']:
        assert (HERE/name).read_bytes()==(prior/name).read_bytes()
    assert (HERE/'bridge.c').read_text()==(original/'bridge.c').read_text().replace('.inline_max=(lfs_size_t)-1','.inline_max=512')
    assert (HERE/'hierarchical_store.py').read_text()==(prior/'hierarchical_store.py').read_text().replace("PROFILE='hms.hierarchical-chunk-store/0.1'","PROFILE='hms.hierarchical-chunk-store.inline512/0.1'")
    assert (HERE/'diagnostic.py').read_bytes()==(ATTEMPT/'frozen-inputs/original/diagnostic.py').read_bytes()
    reader=(prior/'retained_reader.py').read_text()
    reader=reader.replace('def inspect(path,anchor,library_hash,*,replaced_owner=False):',"def inspect(path,anchor,library_hash,*,replaced_owner=False,\n            expected_profile='hms.hierarchical-chunk-store.inline512/0.1',library_path=None):")
    reader=reader.replace("native=Native(image,ATTEMPT/'hierarchical-store.so',library_hash);native.call('hm_mount')","native=Native(image,ATTEMPT/'hierarchical-store.so' if library_path is None else library_path,library_hash);native.call('hm_mount')")
    reader=reader.replace("assert superblock['profile']=='hms.hierarchical-chunk-store/0.1' and superblock['root']==1","assert superblock['profile']==expected_profile and superblock['root']==1")
    assert (HERE/'retained_reader.py').read_text()==reader
    assert (HERE/'run_audit.py').read_bytes()==(prior/'run_audit.py').read_bytes()
    for name in ['audit_evidence.py','run_audit.py','AUDIT-PLAN.md','retained_reader.py']:
        assert digest(HERE/name)==digest(HERE/'audit-process01'/name)==read(HERE/'audit-process01/intent.json')['sourceSha256'][name]
    processes=[]
    for path in sorted(ATTEMPT.glob('*/started.json'))+[HERE/'audit-process01/started.json']:
        start=read(path);end=read(path.with_name('result.json'))
        assert end['reaped'] and not Path('/proc',str(start['pid'])).exists()
        if path.parent.name=='replay_write':
            assert end['timedOut'] and end['returnCode']==-9 and 180<=end['elapsedSeconds']<182
        else:assert not end['timedOut'] and end['returnCode']==0
        processes.append(dict(scope=path.parent.name,pid=start['pid'],**end))
    assert len(processes)==21 and processes[:-1]==audit['processes']
    assert not (HERE/'audit-process01/stderr.txt').read_bytes()
    assert read(HERE/'audit-process01/stdout.txt')=={k:v for k,v in audit.items() if k not in ('images','processes')}
    for row in audit['images']:
        assert {p.name:digest(p) for p in (ATTEMPT/row['path']).iterdir()}==row['backingHashes']
        assert all(row['callbacks'][key]==0 for key in ['programCalls','erases','syncs'])
    assert len(audit['snapshotsReadOnly'])==2
    for row in audit['snapshotsReadOnly']:
        assert (ATTEMPT/row['path']).stat().st_size==row['bytes']==2*1024**2
        assert digest(ATTEMPT/row['path'])==row['sha256']
        assert all(row['callbacks'][key]==0 for key in ['programCalls','erases','syncs'])
    dataset=read(ATTEMPT/'frozen-inputs/dataset.json');source=Path(dataset['sourceRoot'])
    assert len(dataset['files'])==4270 and len(dataset['directories'])==169
    assert sum(row['bytes'] for row in dataset['files'])==35508922
    assert all(digest(source/row['path'])==row['sha256'] for row in dataset['files'])
    baseline=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(baseline)=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    public=read(baseline)['files'];assert len(public)==244 and all(digest(ROOT/row['path'])==row['sha256'] for row in public)
    for path in HERE.glob('*.py'):ast.parse(path.read_bytes(),filename=str(path))
    docs=[dict(path=name,sha256=digest(ROOT/name)) for name in ['README.md','PROGRESS.md','docs/control-storage.md','docs/io-driver-hub-control.md','docs/prompt-to-pat.md']]
    save(HERE/'RESULTS.json',dict(status='focused-controls-passed-full-replay-timeout',focusedChecks=192,
        comparisonEquivalent=True,writerComplete=False,coldReaderRun=False,fullWorkflowQualified=False,
        inlineLimit=512,syncSelectionChanged=False,publicRuntimeChanged=False,publicInputsExact=244,
        evidenceAuditSha256=digest(HERE/'EVIDENCE-AUDIT.json')))
    save(HERE/'AUDIT.json',dict(status='verified',priorSeals=seals,sourceInputs=len(inputs['files']),processes=processes,
        publicInputsExact=244,publicReceiptSha256=digest(baseline),currentDocuments=docs,
        primaryAgentReview=True,independentHelperReviewScopes=['evidence-audit preparation and source review','device/driver/hub and prompt-to-PAT prose review'],goalComplete=False))
    rows=[]
    for path in sorted(HERE.rglob('*')):
        assert not path.is_symlink()
        if path.is_file():
            info=path.stat();assert info.st_size<=16*1024**2
            rows.append(dict(path=str(path.relative_to(HERE)),bytes=info.st_size,allocatedBytes=info.st_blocks*512,sha256=digest(path)))
    allocated=sum(row['allocatedBytes'] for row in rows);assert allocated<1024**3
    save(HERE/'index.json',dict(files=rows,allocatedBytesBeforeIndex=allocated,filesBeforeIndex=len(rows),status='sealed-incomplete-full-workflow',publicRuntimeChanged=False))
    assert all(digest(HERE/row['path'])==row['sha256'] for row in rows)
    print(json.dumps(dict(indexSha256=digest(HERE/'index.json'),files=len(rows),bytes=sum(row['bytes'] for row in rows),allocatedBytesBeforeIndex=allocated),sort_keys=True))


if __name__=='__main__':main()
