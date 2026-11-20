"""Offline proof seal. Read retained bytes only; execute no worker or HMS code."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def record(path):
    return {'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def main():
    latest = sys.argv[1]
    assert not (BASE / 'index.json').exists(), 'A seal is immutable; use a new proof directory.'
    attempts = []
    directories = sorted((BASE / 'attempts').iterdir(), key=lambda p: read(p / 'result.json')['createdAt'])
    for directory in directories:
        result = read(directory / 'result.json')
        before, after = [read(directory / ('inputs-' + phase + '.json')) for phase in ('before', 'after')]
        assert before == after and result['inputsStable']
        for row in before:
            path = directory / 'inputs' / row['path']
            assert sha(path) == row['sha256'] and path.stat().st_size == row['bytes']
        compilers = [read(directory / ('compiler-' + phase + '.json')) for phase in ('before', 'after')]
        assert compilers[0] == compilers[1] and compilers[0]['import_matches_current']
        assert result['compilerIdentityStable']
        workers = []
        report = read(directory / 'worker-report.json')
        for worker in report['workers']:
            case, actual = worker['case'], worker['result']
            output = directory / 'worker-output' / case
            assert read(output / 'test-return.json') == actual
            trust_path = output.parent / (case + '-trust.json')
            assert sha(trust_path) == worker['trustSha256']
            trust = read(trust_path)
            assert trust['input']['attemptId'] == actual['attemptId']
            assert trust['input']['identities'] == actual['identities']
            assert actual['identities']['compilerDigest'] == compilers[0]['compilerDigest']
            seen = set()
            def verify_reference(ref):
                name = ref['path']; path = output / name
                assert name.startswith('evidence/') and path.resolve().is_relative_to(output.resolve())
                assert sha(path) == ref['sha256'] and path.stat().st_size == ref['bytes']
                assert name not in seen
                seen.add(name)
                return read(path)
            for page in actual['evidencePages']:
                content = verify_reference(page)
                for ref in content['value']['records']:
                    verify_reference(ref)
            evidence = list((output / 'evidence').glob('*.json')) if (output / 'evidence').exists() else []
            assert seen == {str(path.relative_to(output)) for path in evidence}
            assert len(evidence) == actual['evidenceRecordCount']
            assert sum(path.stat().st_size for path in evidence) == actual['outputBytes']
            workers.append({key: actual[key] for key in ('outcome', 'completedCases', 'childOperations',
                'unresolvedEffects', 'evidenceRecordCount', 'outputBytes', 'scratchBytes', 'totalDiskQuotaEnforced')} |
                {'case': case, 'trust': record(trust_path), 'result': record(output / 'test-return.json'),
                 'evidenceReferenceHashesVerified': True})
        current = None
        if directory.name == latest:
            assert result['passed'] and not result['skipped']
            assert [(w['case'], w['outcome'], w['completedCases'], w['childOperations']) for w in workers] == [
                ('case-04', 'passed', 27, 25), ('case-01', 'passed', 10, 9),
                ('case-00', 'inconclusive', 0, 0), ('case-02', 'passed', 27, 25)]
            assert report['catalog'] == {'coldPromotion': 'PAT_EVIDENCE_UNAVAILABLE',
                'warmAmbiguity': 'PAT_AMBIGUOUS', 'coldSelection': 'PAT_EVIDENCE_UNAVAILABLE',
                'historicalReplayPreserved': True, 'refusalsAllocateNothing': True}
            for row in before:
                assert sha(ROOT / row['path']) == row['sha256'], row['path']
            current = True
        attempts.append({key: result[key] for key in ('tests', 'failures', 'errors', 'skipped', 'seconds', 'passed')} |
            {'attempt': directory.name, 'inputCount': len(before), 'inputSnapshotsEqual': True,
             'inputHashesVerified': True, 'compilerPairsEqual': True,
             'compilerDigest': compilers[0]['compilerDigest'], 'currentSourceEqualityVerifiedAtSeal': current,
             'result': record(directory / 'result.json'), 'workers': workers, 'catalog': report.get('catalog')})
    assert latest in {a['attempt'] for a in attempts}
    files = [record(path) for path in sorted(BASE.rglob('*')) if path.is_file() and '__pycache__' not in path.parts]
    result = {'schema': 'hms-current-pat-memo-integration-proof/1',
        'createdAt': datetime.now(timezone.utc).isoformat(), 'latestAttempt': latest,
        'scope': 'Copied live libraries, real current worker output and catalog guard; no public service, hardware or model execution.',
        'limitations': ['No routine admission latency or RSS bound is established.',
            'Explicit memo warming/capacity and durable supervisor service mounting remain separate.',
            'Failed dependency reproductions remain failed; earlier worker and compiler identities are historical.'],
        'attempts': attempts, 'files': files}
    (BASE / 'index.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'files': len(files), 'sha256': sha(BASE / 'index.json'), 'attempts': [
        {k: a[k] for k in ('attempt', 'tests', 'failures', 'errors', 'passed')} for a in attempts]}))


if __name__ == '__main__':
    main()
