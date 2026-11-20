"""Read the failed third host attempt; never import or execute candidate code."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LANE = ROOT/'artifacts/implementation/standing-host-deployment'
ATTEMPT = LANE/'host-attempt03'
REVIEW_SHA = '999e10a470bf6a404f5e9259289cf442504217887e9da3c95c3d6c95b31ccc7e'
RUNNER_SHA = 'cee5d4530e6e4100be741e8b52820b865bc48bd7ceb4fee91e000c02cf96d9cc'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def main():
    final = read(ATTEMPT/'RESULTS.json')
    intent = read(ATTEMPT/'intent.json')
    assert not final['passed'] and final['sourceStable'] and final['ownerEmpty'] and final['ownerClosed']
    assert not final['cleanupErrors'] and not final['interruptsPending'] and not final['terminalPendingSignals']
    assert not any(final[key] for key in ('physicalEligible','protectedCapacity','publicMountEligible','universalContainment'))
    frozen = ATTEMPT/'frozen'
    assert digest(frozen/'SOURCE-REVIEW.json') == REVIEW_SHA and digest(frozen/'run_checks.py') == RUNNER_SHA
    assert len(intent['sourcePins']) == 278
    for name,pin in intent['sourcePins'].items():
        assert digest(frozen/name) == pin, name
    for name,pin in intent['installedToolPins'].items():
        assert digest(Path(name)) == pin, name
    assert digest(Path(intent['interpreter'])) == intent['interpreterSha256']
    assert all(str(Path(name).resolve(strict=True)) == target for name,target in intent['toolAliases'].items())
    labels = ('compile-qualification','original-qualification','compile-pipe','host-controls')
    expected_exit = (0,0,0,1)
    assert len(final['commands']) == len(final['outerChildrenReaped']) == 4
    for command,label,code,reap in zip(final['commands'],labels,expected_exit,final['outerChildrenReaped']):
        assert command == read(ATTEMPT/(label+'.receipt.json')) and command['label'] == label
        assert command['exit'] == reap and command['childrenReaped'] == [reap]
        assert reap['reaped'] and reap['exitCode'] == code and command['failure'] is None
        assert command['cleanupComplete'] and not command['cleanupErrors'] and not command['adoptedAfterLeaderExit']
        assert not command['interruptsPending'] and command['heldImageBefore'] == command['heldImageAfter']
        assert command['heldImageBefore']['sha256'] == command['executableSha256'] == digest(Path(command['argv'][0]))
        began = read(ATTEMPT/(label+'.started.json'))
        assert all(began[key] == reap[key] for key in ('pid','parent','group','session','startTicks'))
        assert 0 <= int(command['finishedMonotonicNs'])-int(command['startedMonotonicNs']) < 30_000_000_000
        out = ATTEMPT/('qualification/stdout' if label == 'original-qualification' else label+'.stdout')
        err = ATTEMPT/('qualification/stderr' if label == 'original-qualification' else label+'.stderr')
        assert digest(out) == command['stdoutSha256'] and digest(err) == command['stderrSha256']
        proc = Path('/proc')/str(reap['pid'])/'stat'
        try:
            body = proc.read_bytes()
        except FileNotFoundError:
            pass
        else:
            assert len(body) <= 4096 and int(body.rsplit(b')',1)[1].split()[19]) != reap['startTicks']
    qualification = ATTEMPT/'qualification'
    reserve = read(qualification/'reservation.json')
    receipt = read(qualification/'receipt.json')
    manifest = read(qualification/'manifest.json')
    actual = final['commands'][1]
    for field in ('runId','evaluatorId','runnerDigest','domainDigest','sourcePins','binaryDigest','binaryPath','argv'):
        assert reserve[field] == receipt[field] == manifest[field]
    assert reserve['attemptId'] == receipt['attemptId'] == 'native-standing-attempt:3'
    assert receipt['runnerDigest'] == 'sha256:'+RUNNER_SHA
    assert receipt['binaryDigest'] == 'sha256:'+actual['executableSha256'] and receipt['argv'] == actual['argv']
    assert receipt['ownership']['pid'] == receipt['ownership']['waitedPid'] == actual['exit']['pid']
    assert receipt['ownership']['reaped'] and receipt['ownership']['cleanupComplete'] and receipt['ownership']['spawnCount'] == 1
    assert receipt['ownership']['openChildHandles'] == 0 and receipt['exitCode'] == receipt['terminationSignal'] == 0
    assert receipt['startedMonotonicNs'] == actual['startedMonotonicNs'] and receipt['finishedMonotonicNs'] == actual['finishedMonotonicNs']
    assert receipt['reservationDigest'] == 'sha256:'+digest(qualification/'reservation.json')
    for prefix in ('receipt','reservation','stdout','stderr'):
        assert manifest[prefix+'Digest'] == 'sha256:'+digest(qualification/manifest[prefix+'Path'])
    assert (qualification/'stdout').read_bytes() == b'{"cases":12,"assertions":638,"physical_qualification":false}\n'
    assert not (qualification/'stderr').read_bytes()
    for name,pin in receipt['sourcePins'].items():
        assert 'sha256:'+digest(frozen/'project'/name) == pin
    controls = read(ATTEMPT/'host-controls.stdout')
    assert controls['failure'] == 'JournalError: INVALID_TRANSITION'
    assert not controls['passed'] and controls['checks'] == 81 and len(controls['nativeChildrenReaped']) == 10
    assert [row['case'] for row in controls['cases']] == ['vertical','shared_authority','open_reply_loss','ack_reply_loss','collection_rollback','expiry_after_commit','boot_between_pages','renewal_withdrawal','loss_episode_resume']
    assert all(row['passed'] for row in controls['cases']) and sum(row['checks'] for row in controls['cases']) == 81
    assert controls['nativeExpectedCleanExits']
    assert len({(row['pid'],row['startTicks']) for row in controls['nativeChildrenReaped']}) == 10
    for child in controls['nativeChildrenReaped']:
        assert child['reaped'] and child['exitCode'] == 0 and child['parent'] == final['commands'][3]['exit']['pid']
        proc = Path('/proc')/str(child['pid'])/'stat'
        try:
            body = proc.read_bytes()
        except FileNotFoundError:
            pass
        else:
            assert len(body) <= 4096 and int(body.rsplit(b')',1)[1].split()[19]) != child['startTicks']
    assert controls['ownerEmpty'] and controls['ownerClosed'] and not controls['cleanupErrors'] and not controls['interruptsPending']
    public = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(public) == intent['publicReceiptSha256'] == 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    baseline = read(public); assert baseline['passed'] and baseline['tests'] == 866 and len(baseline['files']) == 244
    assert all(digest(ROOT/row['path']) == row['sha256'] for row in baseline['files'])
    inventory = [dict(path=str(path.relative_to(ATTEMPT)),bytes=path.stat().st_size,sha256=digest(path))
                 for path in sorted(ATTEMPT.rglob('*')) if path.is_file()]
    result = dict(status='verified-failed-attempt',auditSourceSha256=digest(Path(__file__)),
        resultsSha256=digest(ATTEMPT/'RESULTS.json'),sourceReviewSha256=REVIEW_SHA,
        runnerSha256=RUNNER_SHA,commands=4,outerReaps=4,ownedIdentitiesObservedAbsent=14,nativeReaps=10,
        qualificationCases=12,qualificationAssertions=638,hostCasesCompleted=9,hostChecks=81,nativeFixturesLaunched=10,
        failure=controls['failure'],publicInputsExact=244,publicTestsRerun=False,
        physicalEligible=False,hostQualified=False,files=inventory)
    with (HERE/'host-attempt03-audit.json').open('x') as out:
        json.dump(result,out,indent=2,sort_keys=True);out.write('\n');out.flush();os.fsync(out.fileno())
    print(json.dumps({k:v for k,v in result.items() if k != 'files'},sort_keys=True))


if __name__ == '__main__':
    main()
