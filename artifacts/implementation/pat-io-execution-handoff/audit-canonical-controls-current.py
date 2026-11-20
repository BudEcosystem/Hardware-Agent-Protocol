"""Read-only association of pure controls and bounded work observation."""
import hashlib
import json
import sys
from pathlib import Path

B = Path.cwd()/'artifacts/implementation/pat-io-execution-handoff'
F = B/'results'/sys.argv[1]
A = F/'attempt'
def read(path):
    return json.loads(path.read_bytes())
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

proof = read(F/'proof.json')
assert proof['status'] == 'passed' and proof['counts']['testsRun'] == 19
assert proof['sqliteConnections'] == 0 and read(A/'sqlite-connections.json') == []
assert read(F/'storage-audit.json')['databases'] == []
targets = read(A/'harness/targets.json')['targets']
actual = read(A/'actual-tests.json')
assert actual['loaded'] == actual['executed'] == targets and len(set(targets)) == 19
path = A/'scratch/test_repeated_document_work_observation_has_no_latency_acceptance_threshold/work-observation.json'
observation = read(path)
assert observation['repeats'] == observation['originalFullValidations'] == 1000
assert observation['reuseFullValidations'] == 1 and observation['documentBytes'] == 2455
assert observation['latencyAcceptanceThreshold'] is False
for kind in ('original','reuse'):
    assert set(observation[kind]) == {'cpuNs','wallNs'}
    assert all(type(value) is int and value > 0 for value in observation[kind].values())
failed = A/'scratch/test_validated_bytes_do_not_hide_failed_durable_publication/engine/configuration/000000.json'
value = read(failed)
assert value['profile'] == 'hms.pat.io-configuration-record/0.1' and value['kind'] == 'table_page'
assert value['value']['rows'] == [[dict(type='blob-utf8',value='{"a":1}')]]
assert failed.read_bytes() == json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
report = dict(scope='Exact pure19 method selection, zero SQLite opens, retained failed-write bytes and bounded repeated-document observation; no timing or physical acceptance.',
    tests=19,sqliteConnections=0,sourceIndexSha256=proof['sourceIndexSha256'],
    observation=observation,observationSha256=sha(path),retainedFailedWriteSha256=sha(failed),
    noFailedWriteRepair=True,deploymentLatencyQualified=False,physicalValidation=False)
with (F/'canonical-control-audit.json').open('x') as stream:
    stream.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(tests=19,sqliteConnections=0,fullValidationsBefore=1000,fullValidationsAfter=1,
                     originalCpuNs=observation['original']['cpuNs'],reuseCpuNs=observation['reuse']['cpuNs'])))
