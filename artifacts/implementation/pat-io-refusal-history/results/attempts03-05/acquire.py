"""Retain the failed setup and both complete follow-up invocations, without project imports."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import stat

ROOT = Path.cwd().resolve()
BASE = ROOT / 'artifacts/implementation/pat-io-refusal-history'
OUT = BASE / 'results/attempts03-05'
def read(path): return json.loads(path.read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(path, row):
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], str(path)
def inventory(folder):
    rows = []
    for path in sorted(folder.rglob('*')):
        assert not path.is_symlink()
        if path.is_dir(): continue
        assert stat.S_ISREG(path.stat().st_mode)
        rows.append(dict(path=path.relative_to(folder).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    return rows
def identity(path):
    value = path.lstat(); assert stat.S_ISDIR(value.st_mode)
    return dict(path=str(path), device=value.st_dev, inode=value.st_ino, uid=value.st_uid, gid=value.st_gid, mode=stat.S_IMODE(value.st_mode))
def frozen(folder, digest, rooted=False):
    assert sha(folder / 'index.json') == digest
    rows = read(folder / 'index.json')['files']
    for row in rows: verify((ROOT if rooted else folder) / row['path'], row)
    return dict(path=(folder / 'index.json').relative_to(ROOT).as_posix(), sha256=digest, filesVerified=len(rows))

plan_path = BASE / 'followup-selection-plan.json'
assert sha(plan_path) == 'd6ab281941ab39f30d1306e8e3e0f5ae59fe4d79e7b37f226e0cc683629179e0'
plan = read(plan_path)
prior = BASE / 'results/attempts01-02'
seals = [frozen(prior, plan['retainedOriginalResultIndexSha256']),
         frozen(BASE / 'implementation01', plan['sourceIndexSha256'], True)]
seals += [frozen(BASE / g['harness'], g['indexSha256']) for g in plan['groups']]
earlier = read(prior / 'proof.json')
assert not earlier['allSelectionsPassed'] and [p['status'] for p in earlier['attempts']] == ['passed', 'timed_out']
reused = plan['reusedPassingGroup']
reused_dir = prior / reused['attempt']
assert read(reused_dir / 'result.json')['status'] == 'passed'
reused_actual = read(reused_dir / 'actual-tests.json')
assert reused_actual['loaded'] == reused_actual['executed'] and len(reused_actual['executed']) == 72
assert sha(reused_dir / 'harness/targets.json') == reused['targetsSha256']
assert reused_actual['executed'] == read(reused_dir / 'harness/targets.json')['targets']

proofs = []; union = list(reused_actual['executed'])
for group, attempt, passes in [
    (plan['groups'][0], 'attempt03-observation27', False),
    (plan['groups'][0], 'attempt04-observation27', True),
    (plan['groups'][1], 'attempt05-refusal29', True),
]:
    source = BASE / group['harness'] / 'attempts' / attempt
    result = read(source / 'result.json')
    assert result['timeoutSeconds'] == 180
    for prefix, root, count in [('inputs', source / 'project', 7060), ('frozen', ROOT, 7065), ('harness', source / 'harness', 6)]:
        rows = read(source / (prefix + '-before.json'))
        assert rows == read(source / (prefix + '-after.json')) and len(rows) == count
        for row in rows: verify(root / row['path'], row)
    details = dict(attempt=attempt, status=result['status'], counts=result['counts'], currentPass=result['currentPass'],
        elapsedSeconds=result['elapsedSeconds'], timeoutSeconds=180, projectFilesVerified=7060, frozenFilesVerified=7065, activeHarnessFilesVerified=6)
    if not passes:
        assert result['status'] == 'failed' and not result['currentPass'] and result['childState'] == 'not_started'
        assert result['counts'] is None and result['exitCode'] is None and 'pid' not in result and 'scratchPath' not in result
        assert [(e['phase'], e['type']) for e in result['errors']] == [('execution', 'PackageNotFoundError'), ('child-receipts', 'ValueError')]
        assert result['errors'][0]['message'] == 'No package metadata was found for jsonschema'
        assert not (source / 'command.json').exists() and not (source / 'output.log').exists()
        details.update(childState='not_started', errors=result['errors'], testsStarted=False, rawScratchCreated=False,
            externalInventoryAvailable=False, originReceiptsAvailable=False)
    else:
        count = group['testCount']
        assert result['status'] == 'passed' and result['currentPass'] and result['childState'] == 'exited' and result['exitCode'] == 0
        assert not Path('/proc/' + str(result['pid'])).exists()
        assert result['errors'] == result['childErrors'] == []
        assert result['counts'] == dict(testsRun=count, failures=0, errors=0, skips=0, expectedFailures=0, unexpectedSuccesses=0)
        assert sha(source / 'harness/targets.json') == group['targetsSha256']
        targets = read(source / 'harness/targets.json')['targets']; actual = read(source / 'actual-tests.json')
        log = (source / 'output.log').read_text()
        ok = [line.split('(')[1].split(')')[0] for line in log.splitlines() if line.endswith(' ... ok')]
        assert actual['loaded'] == actual['executed'] == targets == ok and len(ok) == count
        match = re.search(r'Ran ' + str(count) + r' tests in ([0-9.]+)s\n\nOK\n$', log); assert match
        origins = read(source / 'imports.json')
        assert origins['violations'] == origins['prohibitedAttempts'] == [] and origins['summary']['allOriginsMatched']
        for row in origins['records']:
            if 'sha256' in row: assert sha(Path(row['origin'])) == row['sha256']
        for name in ['compiler', 'driver']: assert read(source / (name + '-before.json')) == read(source / (name + '-after.json'))
        external = read(source / 'external-before.json')
        assert external == read(source / 'external-after.json') and len(external['files']) == 159
        for row in external['files']: verify(Path(row['resolvedPath']), row)
        raw_before = read(source / 'raw-scratch-before.json'); raw = Path(result['scratchPath'])
        assert identity(raw) == raw_before['identity'] and identity(raw.parent) == raw_before['parent']
        assert inventory(raw) == inventory(source / 'scratch') == read(source / 'scratch-index.json') == []
        details.update(testSeconds=float(match.group(1)), methodOrderVerified=True, originSummary=origins['summary'],
            bytecodeReadsRefused=len(origins['deniedBytecodeReads']), actualOriginFileHashesRechecked=True,
            compilerAndDriverStable=True, externalFilesVerified=159, rawScratch=raw_before['identity'],
            rawScratchEmpty=True, rawScratchOriginalRetained=True)
        union += actual['executed']
    before = inventory(source); shutil.copytree(source, OUT / attempt)
    assert inventory(OUT / attempt) == before == inventory(source)
    details['attemptFilesAcquired'] = len(before); proofs.append(details)

assert union == plan['targetUnion'] and len(union) == len(set(union)) == 128
assert sum('.IoRefusalHistoryTests.' in name for name in union) == 29
for name in ['selection-plan.json', 'followup-selection-plan.json', 'followup-launch-record.json']:
    shutil.copyfile(BASE / name, OUT / name); assert sha(OUT / name) == sha(BASE / name)
proof = dict(scope='128 distinct methods passed across three separate successful invocations: retained72 and follow-up27+29. Original timeout and setup failure remain retained.',
    allSelectedMethodsHavePassingInvocation=True, single128MethodInvocation=False, totalDistinctPassingMethods=128,
    inheritedPassingMethods=99, newPassingMethods=29, selectedMethods=union, attempts=proofs,
    reusedPassingAttempt=earlier['attempts'][0], earlierTimedOutAttemptRetained=earlier['attempts'][1],
    preparationSeals=seals, followupSelectionPlanSha256=sha(plan_path), fixtureProvenance=earlier['fixtureProvenance'],
    inheritedInputsUnchanged=earlier['inheritedInputsUnchanged'], changedInheritedInputs=earlier['changedInheritedInputs'],
    independentReview=False, configurationAttested=False, compilerIdentityAttested=False, physicalMeasurementChecked=False,
    staticTimingPolicyChecked=False, allFaultScenariosChecked=False, independentOutcomeChecked=False, qualificationPassed=False,
    limitations=['Scope is the immutable synthetic GPIO/PWM history profile, including two supported pre-effect permission refusals.',
        'The old full136 suite was not rerun; all 99 selected inherited methods and29 new methods passed on the same new source pin.',
        'The 56-method timeout and27-method parent setup failure remain failed evidence.',
        'Final compiler/driver receipts agree within passing invocations; current-source attestation is a separate unmet requirement.',
        'No Runtime, SQL connection, physical device, MCU/emulator, inference, public service or live source change.'])
with (OUT / 'proof.json').open('x') as stream: stream.write(json.dumps(proof, indent=2) + '\n')
print(json.dumps(dict(distinctPassingMethods=128, attempts=[dict(attempt=p['attempt'], status=p['status'], files=p['attemptFilesAcquired']) for p in proofs], reusedPassing72=True)))
