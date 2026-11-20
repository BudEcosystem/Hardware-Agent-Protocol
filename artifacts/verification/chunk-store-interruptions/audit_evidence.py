"""Reinspect every retained image read-only and join original interruption evidence."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ATTEMPT = HERE/'attempt01'
FROZEN = ATTEMPT/'frozen-inputs'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (40, 40))
    resource.setrlimit(resource.RLIMIT_AS, (512*1024**2, 512*1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16*1024**2, 16*1024**2))
    assert not (HERE/'EVIDENCE-AUDIT.json').exists()
    inputs = read(ATTEMPT/'inputs.json')
    assert len(inputs['files']) == 15
    for row in inputs['files']:
        assert sha(ROOT/row['path']) == sha(FROZEN/row['frozen']) == row['sha256']
    cases = read(FROZEN/'cases.json')['cases']
    attempt = read(ATTEMPT/'RESULTS.json')
    assert attempt['status'] == 'passed' and attempt['inputsStable']
    assert [r['caseId'] for r in attempt['cases']] == [c['id'] for c in cases]
    assert len(cases) == 22 and attempt['selectedInterruptions'] == 24 and attempt['retainedImages'] == 46
    sys.path.insert(0, str(FROZEN))
    spec = importlib.util.spec_from_file_location('hms_interruption_inspector', FROZEN/'matrix.py')
    inspector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inspector)
    for name in ['chunk_store', 'readonly_image']:
        assert Path(sys.modules[name].__file__).resolve() == FROZEN/f'{name}.py'
    image_rows = []
    stop_rows = []
    final_rows = []
    object_ids = set()
    all_pids = []
    for case in cases:
        work = ATTEMPT/case['id']
        intent = read(work/'operation-intent.json')
        assert intent['case'] == case and intent['retries'] == 0
        assert intent['casesSha256'] == sha(FROZEN/'cases.json')
        assert intent['originalAdapterSha256'] == sha(FROZEN/'chunk_store.py')
        intent_sha = sha(work/'operation-intent.json')
        scope = read(work/'scope-result.json')
        scope_start = read(work/'scope-started.json')
        assert scope['returnCode'] == 0 and scope['reaped'] and not scope['timedOut'] and scope['elapsedSeconds'] < 60
        assert read(work/'scope-intent.json')['case'] == case
        assert read(work/'scope-stdout.txt') == read(work/'case-result.json')
        assert (work/'scope-stderr.txt').stat().st_size == 0
        all_pids.append(scope_start['pid'])
        result = read(work/'case-result.json')
        assert result['status'] == 'passed' and result['intentSha256'] == intent_sha
        assert result['selectedInterruptions'] == len(case['cuts'])
        assert result['logical'] in case['expected']
        recorded_case = next(r for r in attempt['cases'] if r['caseId'] == case['id'])
        assert sha(work/'case-result.json') == recorded_case['resultSha256']
        roles = ['original'] + [f'recovery-{n}' for n in range(1, len(case['cuts'])+1)]
        prior_role = None
        prior_snapshot = None
        for index, name in enumerate(roles):
            role = work/name
            final = index == len(roles)-1
            owner_intent = read(role/'owner-intent.json')
            started = read(role/'owner-started.json')
            ended = read(role/'owner-result.json')
            assert owner_intent['intentSha256'] == intent_sha
            assert started['pidfdOpened'] and ended['reaped'] and ended['error'] is None and ended['elapsedSeconds'] < 15
            assert (role/'stderr.txt').stat().st_size == 0 and (role/'stdout.txt').stat().st_size == 0
            all_pids.append(started['pid'])
            if not final:
                assert ended['returnCode'] == -9 and ended['selectedStopObserved']
                checkpoint = read(role/'checkpoint.json')
                stopped = read(role/'stopped.json')
                point = case['cuts'][index]
                assert checkpoint['point'] == point and checkpoint['caseId'] == case['id']
                assert checkpoint['observedPhase'] == point['phase'] and checkpoint['observedOrdinal'] == point['ordinal']
                assert checkpoint['intentSha256'] == stopped['intentSha256'] == intent_sha
                assert checkpoint['process']['pid'] == stopped['pid'] == started['pid']
                assert checkpoint['process']['startTicks'] == stopped['startTicks'] == started['startTicks']
                assert stopped['state'] in {'T', 't'} and stopped['checkpointSha256'] == sha(role/'checkpoint.json')
                assert not (role/'checkpoint.pending').exists()
                frame = checkpoint['call']
                if point['phase'] in {'stage-before-program-2', 'chunk-before-program-2'}:
                    assert frame['name'] == 'hm_write' and frame['programCallbacksSeen'] == 2
                    assert (frame['path'] == 'state.tmp') == (point['phase'] == 'stage-before-program-2')
                elif point['phase'] == 'rename-before-sync':
                    assert frame['name'] == 'hm_rename' and frame['path'] == 'state.tmp'
                    assert frame['syncCallbacksSeen'] == 1 and frame['programCallbacksSeen'] > 0
                else:
                    expected_native = {'directory-created': 'hm_mkdir', 'namespace-staged': 'hm_write',
                                       'namespace-published': 'hm_rename', 'chunk-written': 'hm_write',
                                       'chunk-removed': 'hm_remove', 'directory-removed': 'hm_remove'}
                    assert frame['name'] == expected_native[point['phase']]
                stop_rows.append({'caseId': case['id'], 'role': name, 'point': point,
                                  'pid': started['pid'], 'startTicks': started['startTicks'],
                                  'checkpointSha256': sha(role/'checkpoint.json'), 'call': frame})
                retained = read(role/'interrupted.json')
            else:
                assert ended['returnCode'] == 0 and not ended['selectedStopObserved']
                recovered = read(role/'recovered.json')
                assert recovered['intentSha256'] == intent_sha and recovered['closed']
                assert recovered['process']['pid'] == started['pid']
                assert recovered['process']['startTicks'] == started['startTicks']
                assert recovered['logical'] == result['logical']
                retained = read(role/'final-readback.json')
            anchor = read(role/'anchor.json')
            for pair in anchor['objects'].values():
                pair = tuple(pair)
                assert pair not in object_ids
                object_ids.add(pair)
            if index:
                ancestry = read(role/'clone.json')
                assert ancestry['sourceRole'] == prior_role.name and ancestry['destinationRole'] == name
                assert ancestry['sourceFiles'] == prior_snapshot['backingFiles']
                assert ancestry['copiedBlockSha256'] == prior_snapshot['backingFiles']['chunk-00']
                assert ancestry['bytesCopied'] == 16*1024**2 and ancestry['sourceUnchanged'] and ancestry['fullyAllocated']
                assert ancestry['sourceObjects'] == read(prior_role/'anchor.json')['objects']
                assert ancestry['destinationObjects'] == anchor['objects']
            observed = inspector.snapshot(role, final=final)
            for key in ['logical', 'unlinked', 'unreferencedChunks', 'extraDirectories', 'stagingPresent',
                        'namespaceSha256', 'uniqueReachableBlocks', 'backingFiles']:
                assert observed[key] == retained[key], (case['id'], name, key)
            assert observed['imageUnchanged'] and not observed['recoveryInvoked']
            assert all(observed['readOnlyCallbacks'][k] == 0 for k in ['programCalls', 'programBytes', 'erases', 'syncs'])
            image_rows.append({'caseId': case['id'], 'role': name, 'final': final,
                               'backingFiles': observed['backingFiles'], 'namespaceSha256': observed['namespaceSha256'],
                               'uniqueReachableBlocks': observed['uniqueReachableBlocks'], 'unchanged': True})
            if final:
                assert observed['logical'] == result['logical'] and observed['logical'] in case['expected']
                assert not observed['unlinked'] and not observed['unreferencedChunks'] and not observed['extraDirectories'] and not observed['stagingPresent']
                final_rows.append({'caseId': case['id'], 'logical': observed['logical'],
                                   'intentSha256': intent_sha, 'matchedExpectedIndex': case['expected'].index(observed['logical'])})
            prior_role, prior_snapshot = role, observed
    assert len(stop_rows) == 24 and len(image_rows) == 46 and len(final_rows) == 22
    assert len(object_ids) == 184
    assert all(not Path('/proc', str(pid)).exists() for pid in all_pids)
    assert len(all_pids) == 68
    assert len(list(ATTEMPT.glob('*/**/image/chunk-00'))) == 46
    baseline = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert sha(baseline) == 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    rows = read(baseline)['files']
    assert len(rows) == 244 and all(sha(ROOT/r['path']) == r['sha256'] for r in rows)
    for row in inputs['files']:
        assert sha(ROOT/row['path']) == sha(FROZEN/row['frozen']) == row['sha256']
    output = {'schema': 'hms.chunk-interruption-evidence-audit/1', 'status': 'verified',
              'reviewer': 'primary agent only', 'casesVerified': 22, 'originalStopsVerified': 24,
              'imagesReinspectedReadOnly': 46, 'objectLocksPerImage': 4,
              'distinctObjectAnchors': 184, 'originalPidsAbsent': all_pids,
              'frozenInputsExact': 15, 'runtimeFilesExact': 244,
              'images': image_rows, 'stops': stop_rows, 'outcomes': final_rows,
              'noRecoveryInvokedByAudit': True, 'allImageBytesUnchanged': True,
              'physicalPowerLossTested': False, 'sqliteTested': False,
              'serviceStorageQualified': False, 'allMutationInterruptionsTested': False}
    with (HERE/'EVIDENCE-AUDIT.json').open('x') as f:
        json.dump(output, f, indent=2, sort_keys=True)
        f.write('\n')
    print(json.dumps({k: v for k, v in output.items() if k not in {'images', 'stops', 'outcomes', 'originalPidsAbsent'}}, sort_keys=True))


if __name__ == '__main__':
    main()
