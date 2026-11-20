"""Reconcile exact retained attempts without changing their original evidence."""
import hashlib
import json
from pathlib import Path

ROOT = Path.cwd(); B = ROOT / 'artifacts/implementation/pat-io-installation-reuse'; R = B / 'results'
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
    assert proof['sourceFilesVerified'] == 240 and proof['frozenFilesVerified'] == 243 and proof['externalPinsVerified'] == 159
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
    (folder / 'README.md').write_text(f"# {proof['status'].title()} retained attempt\n\n[Proof](proof.json), [complete log](attempt/output.log), [terminal result](attempt/result.json).\n\n{proof['counts']['testsRun']} tests; {proof['counts']['failures']} failures; {proof['counts']['errors']} errors; {proof['testSeconds']:.3f} test seconds. All 240 project, 243 frozen, six active harness and 159 external inputs remain unchanged. Raw originals and copies retain {proof['rawScratchFiles']} files/{proof['rawScratchBytes']} bytes. Parent SQL opens: {proof['sqliteConnections']}; worker and fixed crash-driver SQL are separate.\n\n" + ' '.join(f'[{path.stem}]({path.name})' for path in audits) + '\n\nSee [stage results](../README.md). No physical qualification, aggregate quota or resolution of unknown effects is inferred.\n')
assert len(entries) == 10 and len(tested) == 194
nominal = all(item['status'] == 'passed' for item in entries if item['harness'] in {'harness02', 'harness07'})
analysis = dict(scope='Bounded pure static installation normalization reuse; unchanged worker/supervisor and recovery selections.', distinctTestedMethods=len(tested), distinctPassingMethods=len(passed), failedMethods=sorted(tested - passed), attempts=entries, completedGroups=full, currentNominalPwmAndArchiveCommitPass=nominal, historicalFailedAttemptsUnchanged=True, repeatedReliabilityMeasured=False, controlledPerformanceComparison=False, productionChangedFiles=['hms/synthetic_io_installation.py'], immutableKeyByteLimit=8 * 65536, entryLimit=8, currentSourceCheckedEachCall=True, liveAuthorityCached=False, supervisorAndWorkerUnchanged=True, originalsAndCopiesRetained=True, actualAggregateStorageEnforced=False, publicQualificationMounted=False, qualificationPassed=False, physicalMeasurementChecked=False, goalStatus='active')
write(B / 'RESULTS.json', analysis)
table = '\n'.join(f"| [{item['destination']}]({item['destination']}/README.md) | {item['counts']['testsRun'] - item['counts']['failures'] - item['counts']['errors']} pass / {item['counts']['failures']} fail | {item['testSeconds']:.3f} | {item['rawScratchFiles']} / {item['rawScratchBytes']} |" for item in entries)
conclusion = 'The fresh uninstrumented PWM and archive-commit nominal tests both pass.' if nominal else 'At least one fresh nominal PWM/archive-commit test remains failed; inspect the preserved failure audits.'
(R / 'README.md').write_text(f'''# Installation normalization reuse: {len(passed)} of {len(tested)} methods pass

{conclusion} Historical failed attempts, incomplete states and transaction sidecars remain unchanged. No old logical key was retried. Each current scope ran once on a fresh fixture. These are regression results, not repeated reliability measurements or a controlled benchmark.

Only the pure installation normalizer changes in production. The original semantic body remains AST-identical. Every call still bounds the original input, rejects unsupported types and floats, detaches it, checks its closed profile and recomputes current driver source identity. Eight exact canonical byte keys retain at most 512 KiB plus bounded immutable normalized trees; results are detached. Selected helper/validator/configuration changes disable reuse. The 14 new tests establish these specific boundaries, including concurrent callers and changes during validation. No authority, current permissions, binding/generation/session, clock, effect or receipt is cached. See the [design](../DESIGN.md) for trusted-process and private-validator limits.

| Attempt | Result | Test seconds | Raw files / bytes |
|---|---|---:|---:|
{table}

The unchanged 171 control selection plus 14 new pure tests passes 185 checks. Independent read-only inspection confirms eleven corrupt control records and three malformed replies remain intact, and three unknown lease fixtures remain unresolved. SQL allowances remain restricted to 28 original control ledger opens; new normalization tests open no SQL or worker.

The same nine process selections exercise PWM, archive commit, lowered record cutoff, pidfd failure, lowered deadline and hard owner loss at admission, launch intent, producer settlement and spawn. Original deadlines and effect/storage bounds remain unchanged. Complete group outputs are checked by the independent reader. Transport of a failed group does not qualify a PAT; recovery without trustworthy original exit information retains unknown status. See each process/state audit for its exact observed counts.

All 240 project / 243 frozen inputs, six active harness inputs and 159 external pins remain stable in each attempt. Original owner and writer leases are held during collection. Database audits do not recover sidecars. Cooperative audit hooks and byte accounting do not provide OS isolation or enforced aggregate storage. The public runtime and adjacent Harness checkout remain unchanged. No physical device, MCU/emulator, live inference or service was executed.

The full HMS goal remains active. [Next work](../NEXT.md) includes trusted service configuration, enforced storage, public qualification and lifecycle mounting, PAT synthesis/learning, persistent Arduino applications and actual device/driver/hub providers.
''')
(B / 'README.md').write_text('# Pure installation normalization reuse\n\n[Design](DESIGN.md), [results](results/README.md), [source](implementation01/README.md).\n\n' + conclusion + ' Historical failures remain preserved; no physical qualification is claimed.\n')
(B / 'NEXT.md').write_text('''# Next work after pure normalization reuse

Use the exact [frozen source](implementation01/index.json) and [retained results](RESULTS.json). Do not copy diagnostic profiling signal handlers or alter old failed ledgers. The new pure memo preserves per-call source checks and original live authority checks. Current attempts do not establish repeated reliability or physical outcomes.

If any current nominal test failed, investigate its retained failure before extending that path. Otherwise continue the fixed trusted service configuration and serialized evidence-import boundary described in the existing PAT service design. Bind the installation, evaluator, worker/source and simulation profile explicitly; never accept caller-selected execution code or treat transport completion as qualification. Preserve cold/missing/corrupt evidence as unavailable.

Public qualification still requires actual aggregate storage enforcement and protected control capacity, not scan-based accounting, plus evidence import, memo capacity, authorization and lifecycle handling. Design and implement the remaining pure boundaries independently while the deployment enforcement choice is unresolved. Do not expose an unqualified service or claim quotas from filesystem scans.

The full user-facing path remains natural-language intent → contextual planning → admitted device/driver/hub operations → observed evidence → validated PAT promotion → deterministic reuse with current guards. Persistent event-driven Arduino applications, genuine target providers, hub compute/lifecycle control, streams, physical commissioning and the wider research/conformance work remain required.
''')
block = f'''\nThe [bounded installation normalization reuse stage]({{prefix}}artifacts/implementation/pat-io-installation-reuse/results/README.md)
passes **{len(passed)} of 194 distinct methods**: unchanged 171 control checks, 14 new
pure memo tests and the same nine separate process cases. {conclusion}
The only production delta reuses immutable static installation results for exact
bounded inputs. Current source checks still run on every call; no live authority,
binding, generation, clock, effect or receipt is cached. The original semantic
validation body and all supervisor/worker bytes remain unchanged.\n\nHistorical failures remain preserved. Current cases ran once, so these results do
not establish repeated reliability or a controlled speedup. No deadline/effect/storage
ceiling changed. Public qualification, actual aggregate quotas, trusted service
mounting, PAT learning, persistent applications and physical device/driver/hub
providers remain incomplete; the full goal stays active.\n'''
for name, prefix in [('docs/prompt-to-pat.md', '../'), ('docs/io-driver-hub-control.md', '../')]:
    path = ROOT / name; text = path.read_text(); assert 'bounded installation normalization reuse stage' not in text
    path.write_text(text + '\n' + block.format(prefix=prefix))
path = ROOT / 'PROGRESS.md'; text = path.read_text(); anchor = 'The separate [qualification supervisor rebase]'; assert text.count(anchor) == 1
path.write_text(text.replace(anchor, block.format(prefix='') + '\n' + anchor).replace('# Goal progress — 2026-11-07', '# Goal progress — 2026-11-08', 1))
path = ROOT / 'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md'; text = path.read_text()
old = 'No production fix exists yet. Address the nominal failures before treating those paths as complete.'
assert old in text
text = text.replace(old, f'The subsequent [bounded pure normalization candidate](../pat-io-installation-reuse/results/README.md) now passes {len(passed)} of 194 distinct methods. {conclusion} Current source checks and live authority checks remain; original failures are preserved. These single fresh runs are not a reliability measurement. Continue the [remaining service boundary work](../pat-io-installation-reuse/NEXT.md).')
path.write_text(text)
path = ROOT / 'scripts/check_project_links.py'; text = path.read_text(); anchor = "        *ROOT.glob('artifacts/implementation/pat-io-supervision-profile/*.md'),"
assert text.count(anchor) == 1
extra = "\n".join("        " + row for row in ["*ROOT.glob('artifacts/implementation/pat-io-installation-reuse/*.md'),", "ROOT/'artifacts/implementation/pat-io-installation-reuse/implementation01/README.md',", "*ROOT.glob('artifacts/implementation/pat-io-installation-reuse/harness*/README.md'),", "*ROOT.glob('artifacts/implementation/pat-io-installation-reuse/harness*/SCOPE.md'),", "ROOT/'artifacts/implementation/pat-io-installation-reuse/results/README.md',", "*ROOT.glob('artifacts/implementation/pat-io-installation-reuse/results/*/README.md'),"])
path.write_text(text.replace(anchor, extra + '\n' + anchor))
print(json.dumps(dict(distinctTestedMethods=len(tested), distinctPassingMethods=len(passed), nominalPass=nominal, completedGroups=len(full))))
