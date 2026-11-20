"""Seal the passing public I/O milestone without executing devices or tests."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from scripts.check_runtime import compiler_identity


def read(path):
    return json.loads((ROOT / path).read_text())


def pin(path):
    data = path.read_bytes()
    return {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def verify(path, expected):
    assert pin(path)['sha256'] == expected, str(path)


def observers(value):
    if isinstance(value, dict):
        yield from value.get('observerReads', [])
        for key, child in value.items():
            if key != 'observerReads':
                yield from observers(child)
    elif isinstance(value, list):
        for child in value:
            yield from observers(child)


def main():
    current = read('artifacts/verification/local-runtime-current.json')
    assert current['status'] == 'passed' and current['current_pass'] is True
    receipt_path = ROOT / current['receipt']['path']
    verify(receipt_path, current['receipt']['sha256'])
    verify(ROOT / 'artifacts/verification/local-runtime.json', current['receipt']['sha256'])
    runtime = read(current['receipt']['path'])
    assert runtime['tests'] == 748 and runtime['passed']
    assert not any(runtime[key] for key in ('failures', 'errors', 'skipped', 'expected_failures',
                                          'unexpected_successes', 'runner_errors', 'input_capture_errors'))
    assert runtime['inputs_stable'] and runtime['compiler_identity_stable']
    assert len(runtime['files_before']) == len(runtime['files_after']) == 151
    for row in runtime['files_before']:
        verify(ROOT / row['path'], row['sha256'])
        assert (ROOT / row['path']).stat().st_size == row['bytes']
    for row in runtime['files_before'] + runtime['files_after']:
        verify(ROOT / row['snapshot_path'], row['sha256'])
    for row in runtime['outputs']:
        verify(ROOT / row['path'], row['sha256'])
    output = receipt_path.parent / 'outputs'
    compiler = compiler_identity()
    assert compiler == json.loads((output / 'pat-compiler-identity-after.json').read_text())
    assert compiler['import_matches_current']
    (HERE / 'compiler-at-seal.json').write_text(json.dumps(compiler, indent=2) + '\n')
    audit = read('artifacts/verification/endpoint-evidence-audit.json')
    assert audit['passed'] and audit['summary']['python_tests'] == 748
    verify(ROOT / 'scripts/audit_endpoint_evidence.py', audit['auditor_sha256'])
    links = read('artifacts/verification/project-links.json')
    assert not links['missing']
    verify(ROOT / 'scripts/check_project_links.py', links['checker_sha256'])
    for row in links['files']:
        verify(ROOT / row['path'], row['sha256'])
    # These two new archives are separate from the completed main audit and
    # the historical consolidated research corpus. Check their stated roots.
    extra = []
    for name, base in (('modbus-serial-full-read', ROOT),
                       ('runtime-748-audit-source-review', ROOT / 'artifacts/verification/runtime-748-audit-source-review')):
        path = ROOT / 'artifacts/verification' / name / 'index.json'
        index = json.loads(path.read_text())
        for row in index['files']:
            verify(base / row['path'], row['sha256'])
            assert (base / row['path']).stat().st_size == row['bytes']
        extra.append({'index': pin(path), 'fileRecordsVerified': len(index['files']),
                      'base': str(base.relative_to(ROOT)) or '.'})
    docs = ['README.md', 'PROGRESS.md', 'docs/io-simulation.md', 'docs/io-driver-hub-control.md',
            'docs/prompt-to-pat.md', 'docs/pat-simulation-qualification.md', 'docs/instrumentation-bindings.md',
            'research/PLAN.md', 'research/instrumentation/README.md', 'spec/00-scope.md', 'schemas/README.md',
            'scripts/audit_endpoint_evidence.py', 'scripts/check_project_links.py',
            'artifacts/verification/local-runtime-current.json', 'artifacts/verification/local-runtime.json',
            'artifacts/verification/endpoint-evidence-audit.json', 'artifacts/verification/project-links.json']
    files = []
    for name in docs:
        source = ROOT / name
        target = HERE / 'snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as handle:
            handle.write(source.read_bytes())
        files.append({'originalPath': name, **pin(target)})
    files += [pin(HERE / 'compiler-at-seal.json'), pin(Path(__file__).resolve())]
    references = [current['receipt']['path'],
        'artifacts/verification/runtime-attempts/20261107T011441.670375Z-c1003207c4ba/receipt.json',
        'artifacts/verification/runtime-696-checkpoint/index.json',
        'artifacts/verification/io-provider-runtime-integration-before/index.json',
        'artifacts/verification/io-provider-live-integration/index.json',
        'artifacts/verification/io-provider-runtime-integration/index.json',
        'artifacts/verification/io-runtime-entry-review/index.json',
        'artifacts/verification/io-response-contract-diagnosis/index.json',
        'artifacts/verification/io-response-contract-resolution-review/index.json',
        'artifacts/verification/io-transport-session-resolution/index.json',
        'artifacts/verification/io-status-read-timeout-diagnosis/index.json',
        'artifacts/verification/io-status-read-timeout-resolution/index.json',
        'artifacts/verification/io-status-read-timeout-resolution-review/index.json',
        'artifacts/verification/runtime-748-audit/20261107T015809.359107Z-65acc626a51a/index.json',
        'artifacts/verification/runtime-748-links/index.json',
        'artifacts/verification/runtime-748-audit-source-review/index.json',
        'artifacts/verification/pat-supervisor-current-integration/index.json',
        'artifacts/verification/io-pat-qualification-design/index.json',
        'artifacts/verification/io-lifecycle-source-preparation-review/index.json',
        'artifacts/verification/io-lifecycle-harness-remediation-review/04/index.json',
        'artifacts/verification/io-lifecycle-harness-remediation-review/05/index.json',
        'artifacts/implementation/io-lifecycle-settlement/review-inputs/05/manifest.json',
        'artifacts/verification/modbus-serial-full-read/index.json']
    io = json.loads((output / 'io-transport-trace.json').read_text())
    assert len(io['cases']) == 5 and all(case['passed'] for case in io['cases'].values())
    reports = [json.loads((output / name).read_text()) for name in
               ('io-transport-trace.json', 'procedure-transport-trace.json', 'runtime-ipc-trace.json',
                'multi-cli-trace.json', 'endpoint-cli-trace.json')]
    observed = [row for report in reports for row in observers(report)]
    io_observed = list(observers(io))
    assert all(row['succeeded'] for row in observed)
    test_seconds = float(re.search(r'Ran 748 tests in ([0-9.]+)s', (output / 'local-runtime-tests.txt').read_text())[1])
    result = {'schema': 'hms-runtime-checkpoint/1', 'createdAt': datetime.now(timezone.utc).isoformat(),
        'status': 'passing_public_io_runtime_with_separate_unexecuted_lifecycle_preparation',
        'runtime': {'tests': 748, 'failures': 0, 'errors': 0, 'skipped': 0, 'inputs': 151,
                    'testSeconds': test_seconds, 'compilerIdentityStable': True,
                    'compilerAtSealMatches': True, 'currentSourcesMatchReceipt': True},
        'io': {'publicRuntimeMounted': True, 'transportTests': 5, 'mcpToolsPerProtocol': 14,
               'validatedMcpReplies': sum(case.get('validatedToolReplies', 0) for case in io['cases'].values()),
               'observerReads': len(io_observed), 'observerBusyRetries': sum(row['busyRetries'] for row in io_observed),
               'statusReadRecoveryMethods': ['operation', 'procedure_status'], 'mutationRetriesAdded': False,
               'productionIpcTimeoutChanged': False, 'operationBoundsChanged': False},
        'transport': {'observerReads': len(observed), 'observerBusyRetries': sum(row['busyRetries'] for row in observed),
                      'allObserverReadsSucceeded': True, 'boundedAvailabilityQualified': False},
        'audit': {'hashAssertions': audit['hash_assertions_verified'], 'uniqueFiles': audit['unique_files_verified'],
                  'symlinksCheckedWithoutFollowing': 5},
        'links': {'files': links['project_markdown_files'], 'localPaths': links['local_links_checked'], 'missing': 0},
        'additionalArchivesVerifiedSeparately': extra,
        'separateScopes': {'supervisorRebaseBaseline': 'full696', 'supervisorRebaseTests': 19,
            'supervisorMountedLive': False, 'hardAggregateStorageQuota': False,
            'lifecycleLatestSourceSnapshot': '05', 'lifecycleExecution': False, 'lifecyclePublicResultSupported': False,
            'ioPatQualification': 'design only', 'promptSynthesisAndLearningImplemented': False,
            'physicalQualification': False, 'modbusSerialTextLinesRead': 2459, 'modbusSerialPagesViewed': 44,
            'newSerialReadingIncludedInConsolidatedCorpusCounts': False, 'tenPartGoalComplete': False},
        'files': files, 'references': [pin(ROOT / name) for name in references],
        'scope': 'Passing public shared-board SQLite GPIO/PWM runtime and retained failure/correction history. No physical I/O, MCU/model/OS lifecycle execution or learned PAT claim. Sequential source hashes are not whole-host or power-loss attestation.'}
    with (HERE / 'index.json').open('x') as handle:
        handle.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'checkpoint': pin(HERE / 'index.json'), 'runtime': result['runtime'],
                      'files': len(files), 'references': len(references), 'links': result['links']}))


if __name__ == '__main__':
    main()
