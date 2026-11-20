"""Compare existing observations only; launch no worker and infer no cause."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
rows = []
for number in (63, 83):
    attempt = BASE / ('harness%d/attempts/attempt01-actual' % number)
    result = json.loads((attempt / 'result.json').read_bytes())
    assert result['status'] == 'failed' and result['childState'] == 'exited'
    raw = Path(result['scratchPath'])
    work = raw / 'test_actual_original_matrix_catalog_execution_and_historical_replay'
    path = work / 'worker-archive.json'
    saved = next(row for row in json.loads((attempt / 'scratch-index.json').read_bytes())
                 if row['path'] == path.relative_to(raw).as_posix())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == saved['sha256']
    archive = json.loads(path.read_bytes())
    output = work / 'supervisor' / archive['record']['attemptId'] / 'output'
    cases = sorted(path for path in output.glob('case-*') if path.is_dir())
    phases = {row['phase']: row['elapsedMs'] for row in archive['phases']}
    rows.append(dict(harness=number, originalScopePassed=False,
        archiveSha256=saved['sha256'], originalAttemptId=archive['record']['attemptId'],
        phases=archive['phases'], spawnToProducerSettledMs=phases['producer_settled']-phases['spawned'],
        caseDirectories=len(cases), caseManifests=sum((path/'manifest.json').is_file() for path in cases),
        lastCaseDirectory=cases[-1].name, resultDocumentPresent=(output/'result.json').is_file(),
        supervisorReason=archive['record']['archive']['supervisorReason'],
        transportComplete=archive['record']['archive']['transportComplete']))
report = dict(observations=rows, productionUnchangedBetweenSources03And04=True,
    actualTestOnlyCorrection='per-instance effect counter assertion, after worker completion',
    originalWorkerMaxWallMs=60000, noWorkerLaunched=True, performanceRootCauseEstablished=False,
    limits='Elapsed phase observations and file presence do not identify CPU, I/O, scheduling, or lock-wait causes. A case manifest is not independent proof of semantic success.',
    deadlineFailureRetained=True, failedScopeReclassified=False)
with (BASE / 'retained-worker-progress.json').open('x') as stream:
    stream.write(json.dumps(report, indent=2) + '\n')
print(json.dumps(dict(observations=rows, performanceRootCauseEstablished=False)))
