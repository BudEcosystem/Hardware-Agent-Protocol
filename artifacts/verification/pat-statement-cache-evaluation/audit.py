"""Verify frozen fixtures, original failures and successful bounded results."""
import ast
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
CURRENT = BASE / 'evaluation02'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def index(path, prefix, expected):
    assert sha(path) == expected
    rows = read(path)['files']
    for row in rows:
        member = prefix / row['path']
        assert member.is_file() and not member.is_symlink()
        assert member.stat().st_size == row['bytes'] and sha(member) == row['sha256'], str(member)
    return rows


old_rows = index(BASE / 'inputs.json', BASE,
    '4701ceda4a10ac8443822753944e0935ddbb6c7688da1c97dcac5a28fb6764e5')
new_rows = index(CURRENT / 'inputs.json', CURRENT,
    'd6238ac531a8d8b26ebda66a361d937d348abef7511b0e85ed6e7f2019d7f807')
assert len(old_rows) == 85 and len(new_rows) == 91
index(BASE / 'preparation01/index.json', BASE / 'preparation01',
      '6e0f37f952ba64d996c929f5e8a1bdcc5f07afc2dc23a0d8f2eef4150024528c')
research = ROOT / 'research/host-contract/sqlite-cache-binding'
index(research / 'index.json', ROOT,
      'c1a9eca2686e7d0d3ee0a27321e859845732cc400ac3f3427e38d3b9c77ad2d9')
assert read(research / 'reading.json')['coveredLfLines'] == 4025
observation_root = ROOT / 'research/host-contract/sqlite-statement-cache'
index(observation_root / 'index.json', ROOT,
      'e48140f30f37d555b6db3bdf0db4d217566ef96279b0416b7d40396f65cc9f9b')
observations = read(observation_root / 'OBSERVATION.json')
static_sql = {store: [row['sql'] for row in observations['queries'] if row['store'] == store]
              for store in ('authority', 'board')}

for folder, rows in ((BASE, old_rows), (CURRENT, new_rows)):
    attempt = folder / 'attempt01'
    assert read(attempt / 'inputs-before.json') == read(attempt / 'inputs-after.json') == rows
    result = read(attempt / 'result.json')
    assert result['childState'] == 'exited' and result['inputsUnchanged'] and result['inputIndexUnchanged']
    command = read(attempt / 'command.json')
    assert command['inputIndexSha256'] == sha(folder / 'inputs.json')
    assert command['argv'][1:4] == ['-I', '-S', '-B']
    assert command['wallLimitSeconds'] == 60 and command['cpuLimitSeconds'] == 30
    assert command['retainedOutputLimitBytes'] == 4194304
old_result = read(BASE / 'attempt01/result.json')
assert not old_result['currentPass'] and old_result['exitCode'] == 1
assert 'assert capture(observers, writer) == expected' in (BASE / 'attempt01/stderr.log').read_text()
assert (BASE / 'attempt01/stdout.json').stat().st_size == 0
old_text, new_text = (BASE / 'child.py').read_text(), (CURRENT / 'child.py').read_text()
assert new_text.replace("LEGACY = json.loads(verify('fixture-profile.json'))['legacyProfile']",
                        "LEGACY = specifications['RECORD_PROFILE']") == old_text
assert read(BASE / 'FAILED_ATTEMPT_REVIEW.json')['timingSamplesStarted'] is False
assert read(BASE / 'CORRECTION_PREPARATION_FAILURE.json')['correctionCopiesWritten'] == 0

specs = read(CURRENT / 'table-specifications.json')
for filename, names in [('pat_io_trials.py', ('RECORD_PROFILE', '_AUTHORITY', '_BOARD')),
                        ('pat_io_configuration_capture.py', ('PROFILE', 'PUBLIC_META', 'TABLES'))]:
    tree = ast.parse((CURRENT / 'references' / filename).read_bytes())
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in names:
                assert specs[name] == json.loads(json.dumps(ast.literal_eval(node.value)))
profile = read(CURRENT / 'fixture-profile.json')
assert specs['RECORD_PROFILE'] == 'hms.pat.io-trial-record/0.1'
assert profile['legacyProfile'] == 'hms.pat.io-trial-record/0.2'
for path in (CURRENT / 'documents/records').glob('*.json'):
    assert read(path)['profile'] == profile['legacyProfile']

borrowed = read(CURRENT / 'borrowed-inputs.json')
assert len(borrowed) == 69
for row in borrowed:
    assert sha(ROOT / row['source']) == sha(CURRENT / row['copy']) == row['sha256']
for row in read(CURRENT / 'runtime-inputs.json')['files']:
    path = Path(row['path'])
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
attempt = CURRENT / 'attempt01'
assert (attempt / 'stderr.log').stat().st_size == 0
result, report = read(attempt / 'result.json'), read(attempt / 'stdout.json')
assert result['currentPass'] and result['exitCode'] == 0 and report['status'] == 'passed'
assert report['inputsUnchanged'] and not report['prohibitedAttempts']
assert report['differentialCases'] == len(report['cases']) == 62
assert len({r['id'] for r in report['cases']}) == 62 and all(r['matched'] for r in report['cases'])
assert report['baselinePagesExact'] == 46 and report['legacyTables'] == 29 and report['configurationTables'] == 15
assert not report['captureMethodsChanged'] and not report['guardMethodsChanged']
assert report['ddlConstraintsAndIndexesRetained'] and report['memoryFixtureSubstitutionsDeclared']
diagnostics = report['diagnostics']
assert [d['authorityCacheCapacity'] for d in diagnostics] == [0, 128, 256]
for diagnostic in diagnostics:
    assert [c['cycle'] for c in diagnostic['cycles']] == [0, 1, 2, 3]
    for cycle in diagnostic['cycles']:
        for store in ('authority', 'board'):
            data = cycle['connections'][store]
            statements = data['statements']
            assert [r['sql'] for r in statements] == static_sql[store]
            assert data['executeCalls'] == len(statements) == (164 if store == 'authority' else 28)
            assert data['statementsWithAuthorizerEvents'] == sum(bool(r['events']) for r in statements)
            assert data['authorizerEvents'] == sum(sum(r['events'].values()) for r in statements)
            if cycle['cycle'] and (store == 'board' or diagnostic['authorityCacheCapacity'] == 256):
                observed = [r for r in statements if r['events']]
                assert len(observed) == (37 if store == 'authority' else 7)
                assert all(r['sql'].startswith('PRAGMA table_info(') and r['events'] == {'19': 1} for r in observed)
warm = {str(d['authorityCacheCapacity']): sum(c['connections']['authority']['statementsWithAuthorizerEvents']
    for c in d['cycles'][1:]) for d in diagnostics}
assert warm == report['warmAuthorityStatementsWithAuthorizerEvents'] == {'0': 492, '128': 492, '256': 111}
pairs = report['timingPairs']
assert len(pairs) == 9 and report['fullCapturesPerSample'] == 16
for i, pair in enumerate(pairs):
    assert pair['order'] == (['reference', 'candidate'] if i % 2 == 0 else ['candidate', 'reference'])
    assert pair['cpuRatio'] == pair['candidate']['cpuNs'] / pair['reference']['cpuNs'] < 1
left, right = sorted(p['reference']['cpuNs'] for p in pairs)[4], sorted(p['candidate']['cpuNs'] for p in pairs)[4]
assert report['referenceMedianCpuNs'] == left and report['candidateMedianCpuNs'] == right
assert report['candidateToReferenceMedianCpuRatio'] == right / left <= 0.95
assert report['fasterPairs'] == 9 and report['integrationScreenPassed']
assert report['inMemoryConnectionsOpened'] == 154 and report['peakLiveConnections'] == 4
assert report['liveConnectionsAtEnd'] == report['persistentDatabasesOpened'] == 0
assert not report['qualifiedWorkerLaunched'] and not report['productionAdopted']
summary = {key: value for key, value in report.items() if key not in ('diagnostics', 'cases')}
summary.update(retentionAuditPassed=True, inputIndexSha256=sha(CURRENT / 'inputs.json'),
    rawReportSha256=sha(attempt / 'stdout.json'), attemptResultSha256=sha(attempt / 'result.json'),
    frozenCurrentInputsVerified=91, frozenFailedInputsVerified=85, borrowedInputsVerified=69,
    exactStaticQueryInventoryVerified=True, sourceReviewSha256=sha(CURRENT / 'SOURCE_REVIEW.json'),
    originalFailedAttemptPreserved=True, timingRunsPerformed=1,
    failedPreparationRetained=True, correctionPinFailureRetained=True,
    researchFullyReadLfLines=4025, auditDatabaseConnectionsOpened=0,
    broaderGoalComplete=False)
with (BASE / 'RESULTS.json').open('x') as out:
    json.dump(summary, out, indent=2); out.write('\n')
with (BASE / 'DECISION.json').open('x') as out:
    json.dump({'productionAdopted': False, 'advanceToIsolatedWorkerIntegration': True,
        'semanticComparisonPassed': True, 'localPerformanceScreenPassed': True,
        'authorityCacheCandidate': 256, 'boardCacheChanged': False,
        'candidateToReferenceMedianCpuRatio': right / left, 'fasterPairs': 9,
        'wholeWorkerQualificationPerformed': False, 'repeatBenchmarkPlanned': False,
        'nativeStatementByteReservationProven': False,
        'reason': 'Exact local outcomes and lower observed preparation work justify a separate full-worker candidate.'},
        out, indent=2); out.write('\n')
print(json.dumps({'retentionAuditPassed': True, 'differentialCases': 62,
    'candidateToReferenceMedianCpuRatio': right / left, 'fasterPairs': 9,
    'advanceToIsolatedWorkerIntegration': True, 'productionAdopted': False}))
