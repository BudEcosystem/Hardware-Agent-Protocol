"""Join retained receipts and exact bytes; never load or recover storage images."""
import ast
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ATTEMPT = HERE / 'attempt01'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    assert not (HERE / 'index.json').exists()
    prior = ROOT / 'artifacts/implementation/inline-hierarchical-store'
    prior_sha = 'a820ce8adda0d8e3dbb1827f2b47c48f94c7969cccc299fbd10e36fbce54f982'
    assert digest(prior / 'index.json') == prior_sha
    prior_index = read(prior / 'index.json')
    for row in prior_index['files']:
        assert digest(prior / row['path']) == row['sha256']
    for row in prior_index['symlinks']:
        path = prior / row['path']
        assert path.is_symlink() and os.readlink(path) == row['target']
    assert len(prior_index['files']) == 340 and len(prior_index['symlinks']) == 1

    inputs = read(ATTEMPT / 'inputs.json')
    result = read(ATTEMPT / 'RESULTS.json')
    audit = read(HERE / 'EVIDENCE-AUDIT.json')
    assert result['status'] == 'failed-or-inconclusive'
    assert result['screenEquivalent'] and result['inputsStable'] and result['instrumentationIntrusive']
    for key in ('checksDisabled', 'durabilityBarriersDisabled', 'geometryChanged',
                'nativeInternalFunctionsMeasured', 'productionSourcesChanged',
                'publicRuntimeChanged', 'serviceStorageQualified'):
        assert result[key] is False
    for row in inputs['files']:
        assert digest(ROOT / row['path']) == digest(ATTEMPT / row['frozen']) == row['sha256']
    for row in inputs['host']['files']:
        assert digest(Path(row['path'])) == row['sha256']
    assert digest(HERE / 'METRICS.json') == audit['metricsSha256'] == 'd4618a6f6a4ef5af5a574f20d3e6eb7c8a5c152b57254447365243a1e0103af3'
    assert audit['status'] == 'verified' and audit['imagesReadOnly'] == 3
    assert audit['allBackingBytesUnchanged'] and audit['screenCallbackAndRawEquality']
    assert audit['screenLogicalSteps'] == 426 and not audit['recoveryInvoked']
    assert audit['priorFocusedChecksRevalidated'] == 192 and not audit['priorFocusedChecksRerun']
    replay = audit['replay']
    assert replay['completedFileBodiesVerified'] == 1318 and replay['completeBodyBytes'] == 5930147
    assert replay['directoriesVerified'] == 169 and replay['partialProgressTailBytes'] == 0
    assert not replay['completeWriterReceipt'] and not replay['dependentColdReaderRun']
    assert all(not replay[k] for k in ('incompletePhysicalInodes', 'pendingEntries', 'unlinkedInodes'))
    assert len(replay['extraPublishedFiles']) == 1 and replay['extraPublishedFiles'][0]['committedBytes'] == 0
    assert replay['extraPublishedFiles'][0]['path'].endswith('/output/case-12/records/000042.json')
    assert not (ATTEMPT / 'replay_read').exists()
    for row in audit['images']:
        assert {p.name: digest(p) for p in (ATTEMPT / row['path']).iterdir()} == row['backingHashes']
        assert all(row['callbacks'][k] == 0 for k in ('programCalls', 'erases', 'syncs'))
    intent = read(HERE / 'audit-process01/intent.json')
    for name, sha in intent['sourceSha256'].items():
        assert digest(HERE / name) == digest(HERE / 'audit-process01' / name) == sha
    assert not (HERE / 'audit-process01/stderr.txt').read_bytes()
    assert read(HERE / 'audit-process01/stdout.txt') == {
        k: v for k, v in audit.items() if k not in ('images', 'processes')}

    processes = []
    for path in sorted(ATTEMPT.glob('*/started.json')) + [HERE / 'audit-process01/started.json']:
        start, end = read(path), read(path.with_name('result.json'))
        assert end['reaped'] and not Path('/proc', str(start['pid'])).exists()
        if path.parent.name == 'replay_write':
            assert end['returnCode'] == -9 and end['timedOut'] and 180 <= end['elapsedSeconds'] < 182
        else:
            assert end['returnCode'] == 0 and not end['timedOut']
        processes.append(dict(scope=path.parent.name, pid=start['pid'], **end))
    assert len(processes) == 4 and processes[:-1] == audit['processes']

    dataset_path = ATTEMPT / 'frozen-inputs/dataset.json'
    dataset = read(dataset_path)
    assert digest(dataset_path) == inputs['datasetSha256'] == '475f09d59534a09b6094707def7112709c050548b958b776362bf0ce86ee0a46'
    assert len(dataset['files']) == 4270 and len(dataset['directories']) == 169
    assert sum(r['bytes'] for r in dataset['files']) == 35508922
    assert all(digest(Path(dataset['sourceRoot']) / r['path']) == r['sha256'] for r in dataset['files'])
    shape = read(HERE / 'dataset-shape.json')
    assert shape['datasetSha256'] == inputs['datasetSha256'] and shape['files'] == 4270
    assert shape['currentFullBitmapMetadata']['within512Bytes'] == 0
    assert shape['hypotheticalBitmapSizedToDeclaredFile']['within512Bytes'] == 4269
    shape_check = read(HERE / 'shape-verification.json')
    assert shape_check['matchesRetainedObservation'] is True
    assert shape_check['scriptSha256'] == digest(HERE / 'analyze_shape.py')
    assert shape_check['datasetSha256'] == digest(dataset_path)
    assert shape_check['observationSha256'] == digest(HERE / 'dataset-shape.json')
    baseline = ROOT / 'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    baseline_sha = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    assert digest(baseline) == baseline_sha
    public = read(baseline)['files']
    assert len(public) == 244 and all(digest(ROOT / r['path']) == r['sha256'] for r in public)
    for path in HERE.glob('*.py'):
        ast.parse(path.read_bytes(), filename=str(path))
    save(HERE / 'RESULTS.json', dict(status='diagnostic-equivalence-passed-full-writer-timeout',
         screenEquivalent=True, writerComplete=False, coldReaderRun=False,
         instrumentationIntrusive=True, nativeInternalFunctionsMeasured=False,
         serviceStorageQualified=False, publicRuntimeChanged=False, publicInputsExact=244,
         evidenceAuditSha256=digest(HERE / 'EVIDENCE-AUDIT.json'), metricsSha256=audit['metricsSha256']))
    save(HERE / 'AUDIT.json', dict(status='verified', processes=processes,
         priorIndexSha256=prior_sha, priorFilesExact=340, priorSymlinksExact=1,
         sourceInputsExact=len(inputs['files']), publicReceiptSha256=baseline_sha,
         publicInputsExact=244, primaryAgentReview=True, goalComplete=False))
    rows = []
    for path in sorted(HERE.rglob('*')):
        assert not path.is_symlink()
        if path.is_file():
            info = path.stat()
            assert info.st_size <= 16 * 1024**2
            rows.append(dict(path=str(path.relative_to(HERE)), bytes=info.st_size,
                             allocatedBytes=info.st_blocks * 512, sha256=digest(path)))
    allocated = sum(r['allocatedBytes'] for r in rows)
    assert allocated < 1024**3
    save(HERE / 'index.json', dict(files=rows, filesBeforeIndex=len(rows),
         allocatedBytesBeforeIndex=allocated, status='sealed-diagnostic-full-writer-incomplete',
         publicRuntimeChanged=False))
    assert all(digest(HERE / r['path']) == r['sha256'] for r in rows)
    print(json.dumps(dict(indexSha256=digest(HERE / 'index.json'), files=len(rows),
                         bytes=sum(r['bytes'] for r in rows), allocatedBytesBeforeIndex=allocated)))


if __name__ == '__main__':
    main()
