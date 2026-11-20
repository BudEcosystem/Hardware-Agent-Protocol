"""Primary-agent data-only cross-check of the acquired timing evidence."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
def read(path): return json.loads(path.read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value):
    with path.open('x') as stream: stream.write(json.dumps(value, indent=2)+'\n')

# Independent summary expectations; no project code is imported or executed.
specs = {
    'not_before_boundary': (1,1,0,'satisfied',True,6),
    'latest_start_before': (1,1,0,'satisfied',False,4),
    'latest_start_equal': (0,0,0,'failed',None,3),
    'run_completion_equal': (1,0,1,'failed',None,4),
    'wall_completion_equal': (1,0,1,'failed',None,4),
    'lease_wait_before': (1,1,0,'satisfied',True,6),
    'lease_wait_equal': (0,0,0,'failed',None,3),
    'late_parent_reporting': (1,1,0,'satisfied',False,4),
}
tests = []; cases = []; case_ids = set()
for number, count in [('03',9),('04',8),('05',77)]:
    attempt = BASE/('attempt'+number)
    actual = read(attempt/'actual-tests.json')
    assert actual['loaded'] == actual['executed'] and len(actual['executed']) == count
    tests.extend(actual['executed'])
    for path in sorted((attempt/'scratch').glob('*/engine-0.json')):
        manifest = read(path); checked = manifest['independentTimingInspection']
        scenario = checked['scenario']; expected = specs[scenario]
        outcome = checked['trial']['outcome']; history = checked['trial']['history']
        assert tuple(outcome[k] for k in ('activations','completedCycles','canceledActivations')) == expected[:3]
        assert outcome['contractStatus'] == expected[3] and outcome['nominalTimingSatisfied'] is expected[4]
        assert manifest['report']['schedulerTicks'] == expected[5]
        assert outcome['settledAndQuiescent'] and outcome['unresolvedOperationIds'] == []
        assert checked['exactControlScheduleChecked'] and checked['expectedResponseVerified'] and checked['independentOutcomeChecked']
        for flag in ('qualificationPassed','configurationAttested','compilerIdentityAttested',
                     'actualAggregateStorageEnforced','physicalMeasurementChecked','requiredMatrixCoverageChecked'):
            assert checked[flag] is False
        docs = {}
        for ref in manifest['records']:
            raw = path.parent/'trial-0/records'/ref['path']
            assert raw.stat().st_size == ref['bytes'] and sha(raw) == ref['sha256']
            docs[ref['path']] = read(raw)
        checkpoint = [doc['value'] for doc in docs.values() if doc['kind']=='checkpoint'][-1]
        assert checkpoint['label'] == 'test_final'
        tables = {}
        for table in checkpoint['tables']:
            rows = []
            for ref in table['pages']:
                page = docs[ref['path']]['value']
                rows.extend(dict(zip(page['columns'], [field['value'] for field in row])) for row in page['rows'])
            assert len(rows) == table['rowCount']; tables[table['table']] = rows
        assert len(tables['operations']) == 1 and tables['claims'] == []
        assert tuple(sum(row[k] for row in tables['io_effects']) for k in ('activations','completed','canceled')) == expected[:3]
        operation = tables['operations'][0]; admission = json.loads(operation['admission'])
        assert sorted((r['resource'],r['fence']) for r in tables['resource_floors']) == [(resource,1) for resource in sorted(admission['resources'])]
        if scenario in ('latest_start_equal','lease_wait_equal'):
            assert operation['state']=='rejected_before_dispatch' and operation['attempt_id'] is None and operation['may_have_acted']==0
            assert tables['io_dispatch_links']==tables['io_receipts']==tables['io_fences']==[]
            events = [e for e in tables['events'] if e['kind']=='rejected_before_dispatch']
            assert len(events)==1 and json.loads(events[0]['payload'])=={'reason':'start_or_lease_expired'}
            assert len(history['refusalsChecked'])==1 and history['refusalsChecked'][0]['code']=='start_or_lease_expired'
        if scenario in ('run_completion_equal','wall_completion_equal'):
            assert len(tables['io_receipts'])==1
            receipt=json.loads(tables['io_receipts'][0]['document'])
            assert receipt['state']=='canceled' and receipt['result']['reason']=='execution_deadline'
        if scenario=='late_parent_reporting':
            assert outcome['parentCompletedAtMs']==1001000 and outcome['parentCompletionBeforeDeadline'] is False
            assert outcome['zeroLagChildScheduleMatched'] and outcome['nominalCompletionSatisfied'] is False
        assert checked['caseId'] not in case_ids; case_ids.add(checked['caseId'])
        cases.append(dict(attempt='attempt'+number,scenario=scenario,caseId=checked['caseId'],
            artifact=path.relative_to(BASE).as_posix(),artifactSha256=sha(path),
            activations=expected[0],completedCycles=expected[1],canceledActivations=expected[2],
            contractStatus=expected[3],nominalTimingSatisfied=expected[4],schedulerTicks=expected[5]))
    assert sum(c['attempt']=='attempt'+number for c in cases)==(0 if number=='05' else 8)
assert len(tests)==len(set(tests))==94 and len(cases)==16
totals={key:sum(c[key] for c in cases) for key in ('activations','completedCycles','canceledActivations','schedulerTicks')}
assert totals==dict(activations=12,completedCycles=8,canceledActivations=4,schedulerTicks=68)
write(BASE/'data-audit.json', dict(scope='Data-only cross-check of acquired evidence; primary-agent review, not a second independent reviewer.',
    distinctPassingMethods=94, runtimeCases=16, exactCases=cases, totals=totals,
    satisfiedContracts=8, failedContractsWithExpectedResponse=8, noHandoffExpiryCases=4,
    terminalCasesSettled=True, qualificationPassed=False, requiredMatrixCoverageChecked=False,
    independentAgentReview=False, projectExecution=False))
print(json.dumps(dict(distinctPassingMethods=94,runtimeCases=16,totals=totals,qualificationPassed=False)))
