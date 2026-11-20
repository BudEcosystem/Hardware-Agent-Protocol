"""Reconcile exact retained attempts without changing their original evidence."""
import hashlib
import json
from pathlib import Path

ROOT = Path.cwd(); B = ROOT / 'artifacts/implementation/pat-io-service-config'; R = B / 'results'
def read(path): return json.loads(path.read_bytes())
def write(path, value):
    with path.open('x') as stream: stream.write(json.dumps(value, indent=2) + '\n')
entries = []; tested = set(); passed = set(); full = []
for folder in sorted(R.iterdir()):
    if not (folder / 'proof.json').exists(): continue
    proof = read(folder / 'proof.json'); result = read(folder / 'attempt/result.json')
    targets = read(folder / 'attempt/actual-tests.json')['executed']
    assert proof['status'] == result['status'] and result['childState'] == 'exited'
    assert result['errors'] == result['childErrors'] == []
    assert proof['sourceFilesVerified'] == 242 and proof['frozenFilesVerified'] == 245 and proof['externalPinsVerified'] == 159
    assert not tested.intersection(targets); tested.update(targets)
    if proof['status'] == 'passed': passed.update(targets)
    else: assert (folder / 'failure-audit.json').is_file()
    storage = read(folder / 'storage-audit.json'); assert storage['databaseBytesUnchanged']
    item = dict(destination=folder.name, attempt=proof['attempt'], harness=proof['harness'], status=proof['status'], counts=proof['counts'], testSeconds=proof['testSeconds'], elapsedSeconds=proof['elapsedSeconds'], rawScratch=proof['rawScratch'], rawScratchFiles=proof['rawScratchFiles'], rawScratchBytes=proof['rawScratchBytes'], attemptFiles=proof['attemptFilesAcquired'], actualOrigins=proof['actualOrigins']['recordCount'], parentSqliteConnections=proof['sqliteConnections'], databases=len(storage['databases']), databaseBytes=storage['totalBytes'], logicalDatabaseInspectionsSkipped=storage['logicalInspectionSkipped'])
    entries.append(item)
    if (folder / 'process-audit.json').exists():
        process = read(folder / 'process-audit.json')
        if process['groupStatus'] == 'captured':
            full.append(dict(destination=folder.name, cases=process['completedCases'], states=process['states'], effects=process['effects'], claims=process['claims'], owners=process['owners'], history=process['history'], archiveTransportComplete=process['archive']['transportComplete'], archiveExitCode=process['archive']['exitCode'], outputClosure=process['outputClosure']))
    audits = sorted(folder.glob('*audit.json'))
    (folder / 'README.md').write_text(f"# {proof['status'].title()} retained attempt\n\n[Proof](proof.json), [complete log](attempt/output.log), [terminal result](attempt/result.json).\n\n{proof['counts']['testsRun']} tests; {proof['counts']['failures']} failures; {proof['counts']['errors']} errors; {proof['testSeconds']:.3f} test seconds. All 242 project, 245 frozen, six active harness and 159 external inputs remain unchanged. Raw originals and copies retain {proof['rawScratchFiles']} files/{proof['rawScratchBytes']} bytes. Parent SQL opens: {proof['sqliteConnections']}; worker and fixed crash-driver SQL are separate.\n\n" + ' '.join(f'[{path.stem}]({path.name})' for path in audits) + '\n\nSee [stage results](../README.md). No physical qualification, aggregate quota or resolution of unknown effects is inferred.\n')
assert len(entries) == 11 and len(tested) == 216
configured = next(item for item in entries if item['harness'] == 'harness11')
configured_pass = configured['status'] == 'passed'
service_audit = read(R / configured['destination'] / 'service-audit.json') if configured_pass else None
analysis = dict(scope='Closed trusted I/O service configuration, fresh configured run preparation and anchored historical parsing.', distinctTestedMethods=len(tested), distinctPassingMethods=len(passed), failedMethods=sorted(tested - passed), attempts=entries, completedGroups=full, configuredGroupPass=configured_pass, configuredGroupAudit=service_audit, changedInheritedFiles=['supervisor/supervisor_contracts.py'], newProductionFiles=['supervisor/io_services.py'], originalWorkerUnchanged=True, productionAuthorityConfigurationInstalled=False, serializedEvidenceImportInstalled=False, publicQualificationMounted=False, actualAggregateStorageEnforced=False, qualificationPassed=False, physicalMeasurementChecked=False, historicalFailedAttemptsUnchanged=True, repeatedReliabilityMeasured=False, originalsAndCopiesRetained=True, goalStatus='active')
write(B / 'RESULTS.json', analysis)
table = '\n'.join(f"| [{item['destination']}]({item['destination']}/README.md) | {item['counts']['testsRun'] - item['counts']['failures'] - item['counts']['errors']} pass / {item['counts']['failures']} fail | {item['testSeconds']:.3f} | {item['rawScratchFiles']} / {item['rawScratchBytes']} |" for item in entries)
conclusion = 'The configured original worker completes all 30 GPIO cases, with independent outcome inspection and exact replay before and after reopen.' if configured_pass else 'The configured process test remains failed; inspect its preserved failure audit before extending that path.'
(R / 'README.md').write_text(f'''# Trusted I/O configuration: {len(passed)} of {len(tested)} methods pass

{conclusion} The new service preparation API joins explicit configuration, current installed source identity, configured artifact-to-device mapping and fresh trusted descriptor snapshots to the original supervised request. Historical parsing requires a separately retained service pin, logical run ID and request digest. It performs no source reads or replanning.

The 21 new control tests cover exact fields and integer bounds, rejected execution/result fields, configuration/source/type/metadata drift, complete descriptor inventory, fresh session snapshots, mutation isolation and anchored replay. A changed same-key request cannot satisfy the original request digest. The configured process test durably retains its configuration, pin and request digest in a private fixture before supervisor construction, then executes the original worker and independent reader. That fixture retention is not a production authority configuration store.

| Attempt | Result | Test seconds | Raw files / bytes |
|---|---|---:|---:|
{table}

All 185 inherited control methods and the nine prior process selections remain unchanged. The control scope is 206 methods and the total is 216. Independent control audits preserve eleven corrupt records, three unknown-lease fixtures and three malformed replies. Negative cutoff and owner-loss results remain negative or unknown where required; a passed failure-handling test is not a qualified PAT.

The only existing production edit adds `io_services.py` to the supervisor source closure. Its source bytes are included in supervisor identity and the retained 257-file code image, including 157 pinned dependency files. All other inherited production bytes, including the worker and pure installation memo, remain unchanged. No time, effect, stream, file, input or retention ceiling is widened.

Every attempt verifies 242 project inputs, 245 frozen inputs, six active harness files and 159 external pins. Raw originals and complete copies are retained. Parent SQL receipts cover only the declared control/owner ledgers; the new configuration module performs no SQL or launch. Process collection retains the original owner/writer lease checks. Read-only database auditing never recovers transaction sidecars. Prior nominal failures remain preserved, and these fresh runs do not establish repeated reliability.

The API still requires trusted setup and externally retained pins. It does not authorize a caller, persist active configuration in the authority database, serialize evidence import, promote a PAT or mount public tools. Enforced aggregate storage, trusted Runtime reconstruction, learning and persistent applications, actual device/driver/hub providers and physical commissioning remain required. See the [design](../DESIGN.md) and [next work](../NEXT.md). The full goal remains active.
''')
(B / 'README.md').write_text('# Trusted I/O service configuration\n\n[Design](DESIGN.md), [results](results/README.md), [source](implementation01/README.md).\n\n' + conclusion + '\n\nDurable authority configuration, evidence import and public qualification remain unfinished.\n')
(B / 'NEXT.md').write_text('''# Next: durable authority-owned service configuration

Use the [frozen configured source](implementation01/index.json) and [exact results](RESULTS.json). The service preparation API now closes the configuration-to-supervisor path, but its external expected pin is still supplied by trusted host setup. Do not mistake test-fixture pin retention for an installed authority configuration.

Implement the authority-owned configuration record and reconstruction boundary next. It must retain canonical configuration and source-derived service pin under the same Journal/Registry authority; require explicit administration; enforce revision and expected-prior-state conflicts; retain historical versions and unknown/corrupt state without repair; and preserve exact mutation replay. Reopen must compare supplied installed configuration and current code against the retained active pin. A change must refuse fresh qualification/reuse without preventing historical status, cancellation or reconciliation.

Obtain each run's complete descriptor snapshot from the installed I/O resolver under the same authority transaction and configured explicit role map. The service's descriptor input is a trusted seam, not proof of live permissions or presence. Never substitute fixture descriptors, manufacture sessions or cache current authority. Ensure a retained run ID cannot be rebound to changed configuration, descriptors, limits or code.

Then join serialized supervised results to the independent full semantic reader and existing evidence store/memo. Preserve missing, corrupt, cold or incomplete evidence as unavailable. Qualification and promotion must depend on exact retained outcomes and current eligibility, not supervisor transportComplete. Catalog environment/evaluator checks must include configuration identity so configuration changes cannot leave old promotion silently eligible.

Keep public service mounting gated on actual aggregate storage enforcement and protected control capacity. Current file scans are accounting, not enforcement. Do not claim an OS sandbox, real-time guarantee or physical measurement from these host simulations. The remaining prompt-to-PAT learning loop, persistent Arduino applications, actual I/O/driver/hub compute and lifecycle providers, streams, wider research/conformance work and microscope commissioning remain part of the full goal.
''')
block = f'''
The [trusted I/O service configuration stage]({{prefix}}artifacts/implementation/pat-io-service-config/results/README.md)
passes **{len(passed)} of 216 distinct methods**. It adds a closed configuration-to-run
path: explicit policy, installation, artifact assignments, challenge bindings and
limits are joined to source-derived pins and fresh trusted descriptor snapshots.
Historical parsing requires external pin, run ID and request digest without
replanning. {conclusion}

The service module is now pinned in the supervisor identity and code image; the
worker and all other inherited production behavior remain unchanged. No bound was
widened. The configuration API itself opens no SQL and starts no worker. Durable
authority-owned configuration, resolver-based descriptor acquisition, serialized
evidence import, aggregate storage enforcement and public mounting remain pending.
PAT learning, persistent applications and actual device/driver/hub providers remain
required; the full goal stays active.
'''
for name, prefix in [('docs/prompt-to-pat.md', '../'), ('docs/io-driver-hub-control.md', '../')]:
    path = ROOT / name; text = path.read_text(); assert 'trusted I/O service configuration stage' not in text
    path.write_text(text + '\n' + block.format(prefix=prefix))
path = ROOT / 'PROGRESS.md'; text = path.read_text(); anchor = 'The separate [qualification supervisor rebase]'; assert text.count(anchor) == 1
path.write_text(text.replace(anchor, block.format(prefix='') + '\n' + anchor))
path = ROOT / 'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md'; text = path.read_text()
old = 'Continue the [remaining service boundary work](../pat-io-installation-reuse/NEXT.md).'; assert old in text
text = text.replace(old, f'The [trusted I/O service configuration](../pat-io-service-config/results/README.md) now passes {len(passed)} of 216 methods and binds configured preparation to source identity and external replay anchors. {conclusion} Continue with the [authority-owned configuration boundary](../pat-io-service-config/NEXT.md); fixture retention is not production configuration persistence.')
path.write_text(text)
path = ROOT / 'scripts/check_project_links.py'; text = path.read_text(); anchor = "        *ROOT.glob('artifacts/implementation/pat-io-installation-reuse/*.md'),"; assert text.count(anchor) == 1
extra = '\n'.join('        ' + row for row in ["*ROOT.glob('artifacts/implementation/pat-io-service-config/*.md'),", "ROOT/'artifacts/implementation/pat-io-service-config/implementation01/README.md',", "*ROOT.glob('artifacts/implementation/pat-io-service-config/harness*/README.md'),", "*ROOT.glob('artifacts/implementation/pat-io-service-config/harness*/SCOPE.md'),", "ROOT/'artifacts/implementation/pat-io-service-config/results/README.md',", "*ROOT.glob('artifacts/implementation/pat-io-service-config/results/*/README.md'),"])
path.write_text(text.replace(anchor, extra + '\n' + anchor))
print(json.dumps(dict(distinctTestedMethods=len(tested), distinctPassingMethods=len(passed), configuredGroupPass=configured_pass, completedGroups=len(full))))
