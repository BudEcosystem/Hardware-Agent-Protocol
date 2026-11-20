"""Join retained evidence and current documents; execute no candidate or test."""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import sys
from urllib.parse import unquote, urlsplit

assert not sys.flags.optimize
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRIOR = ROOT/'artifacts/verification/continuation-102/receipt.json'
PRIOR_SHA = '61c0a5176e7e14be5cf472afbeea2d1245adc1eee6f0dcc91c7f925b06a65eff'
HELPER = ROOT/'artifacts/verification/continuation-99/verify.py'
HELPER_SHA = 'c8eeecf02031c1203f030719e409c84863838ae79acd8c2164e7940d56513c2a'
PUBLIC = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
PUBLIC_SHA = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
HOST = ROOT/'artifacts/implementation/standing-host-owner-death'
SIZE = ROOT/'artifacts/design/standing-endpoint-size-reduction'
HOST_INDEX_SHA = 'cbc0bd02a38aec40dc2826a8c38c2d7fd4cfe271ece672ce6316801c07b223d7'
SIZE_INDEX_SHA = '570f0d5e84d268d88f4a3ad50df21e6fe1f293d64adc41a0d0fc66eed35191d2'
AUDIT_SHA = '030ee016eed19a7ecc699d8ab6071245d3344840bfe63bd0ea1b3f3c3b661fbf'
AUDIT_SOURCE_SHA = '0280e7dd3f291c42d342aa19b1f6d707826052078a7fd44b30179a682f376377'
REVIEW_SHA = '4dca9bff924a726520952e9beae2a4b7d18bd73f46a4735e2fd1c227f2aba9fe'
DOCS = ('README.md', 'PROGRESS.md', 'docs/control-storage.md', 'docs/io-driver-hub-control.md',
        'docs/prompt-to-pat.md', 'docs/embedded-evidence.md', 'spec/12-io-driver-boundary.md')
ROOT_RESULTS = {
    'owner-death-preflight.json': ('c73b377738e950f5e693f4616cb604727b7b2f57ee28fff1c7a2c7dd2f781fe4',
        'preflight_owner_death.py', '7ad8590374e9e8b2ccd9a1ccb4c7ce29666c4383c832332fb1e039bf0f76da4c'),
    'size-proposal-verification.json': ('3f008cc2402cb65ff46ef896ae3344d9319a20660c67ae5edc3889242f66b28f',
        'verify_size_proposal.py', 'f99cea7d3f7be594235c8ab7032ce0e88e6d7924d50201a90e1cecdd963c207f'),
}
CASES = ('open-prepared', 'open-possible', 'open-reply', 'start-prepared', 'start-possible',
         'start-reply', 'collection-before-ack', 'ack-prepared', 'ack-possible', 'ack-reply',
         'retire-prepared', 'retire-possible', 'retire-reply')


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def entry(path, row):
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256']


def main():
    assert digest(PRIOR) == PRIOR_SHA and digest(HELPER) == HELPER_SHA
    previous = read(PRIOR)
    assert previous['status'] == 'verified' and len(previous['sealedPackets']) == 21
    prevalidation = read(HERE/'revalidation.json')
    assert prevalidation['previousReceiptSha256'] == PRIOR_SHA
    assert prevalidation['previousTurnClassification'] == 'progress'
    packet = runpy.run_path(str(HELPER))['packet']
    packets = [packet(row['path'], row['indexSha256']) for row in previous['sealedPackets']]
    packets += [packet(str(SIZE.relative_to(ROOT)), SIZE_INDEX_SHA), packet(str(HOST.relative_to(ROOT)), HOST_INDEX_SHA)]
    assert len(packets) == 23 and len({row['path'] for row in packets}) == 23
    assert digest(PUBLIC) == PUBLIC_SHA
    public = read(PUBLIC)
    assert public['passed'] and public['tests'] == 866 and len(public['files']) == 244
    assert all(digest(ROOT/row['path']) == row['sha256'] for row in public['files'])
    for name, (pin, source, source_pin) in ROOT_RESULTS.items():
        assert digest(HERE/name) == pin and digest(HERE/source) == source_pin
        assert read(HERE/name)['verificationSourceSha256'] == source_pin

    assert digest(HOST/'AUDIT.json') == AUDIT_SHA and digest(HOST/'audit_retained.py') == AUDIT_SOURCE_SHA
    audit = read(HOST/'AUDIT.json')
    assert audit['auditSourceSha256'] == AUDIT_SOURCE_SHA and audit['sourceReviewSha256'] == REVIEW_SHA
    assert audit['status'] == 'verified-thirteen-fixed-owner-death-cuts' and audit['checks'] == 12739
    assert tuple(row['case'] for row in audit['cases']) == CASES
    assert audit['innerReaps'] == 39 and audit['outerReaps'] == 1
    assert audit['actualOwnerDeath'] and audit['nativePeerSurvivedOwner']
    assert not any(audit[key] for key in ('candidateImports', 'candidateRerun', 'qualificationRerun',
        'historicalPossibleEffectsResent', 'physicalEligible', 'protectedCapacity',
        'publicMountEligible', 'universalContainment', 'wholeHostQualified'))
    assert audit['copiedSourceHelperFilesExact'] == 261 and audit['originalProvenanceFilesExact'] == 19
    assert audit['sealedParentFilesExact'] == 3755 and audit['publicInputsExact'] == 244
    attempt = HOST/'owner-death-attempt01'
    inventory = set()
    for row in audit['files']:
        assert row['path'] not in inventory
        inventory.add(row['path']); entry(attempt/row['path'], row)
    assert len(inventory) == 476
    assert inventory == {str(path.relative_to(attempt)) for path in attempt.rglob('*') if path.is_file() or path.is_symlink()}
    result = read(attempt/'RESULTS.json'); control = read(attempt/'state/CONTROL-RESULTS.json')
    assert digest(attempt/'RESULTS.json') == audit['resultsSha256'] == 'c7dc7de7f0bf5f8b70ab1037f7894c9e5b8518c289e0d24b3be1e33ae26a4f77'
    for record in (result, control):
        assert record['passed'] and record['ownerEmpty'] and record['ownerClosed']
        assert record['actualOwnerDeath'] and record['nativePeerSurvivedOwner']
        assert not record['cleanupErrors'] and not record['interruptsPending'] and not record['historicalPossibleEffectsResent']
    elapsed = int(result['controlTerminalObservedMonotonicNs']) - int(result['controlStartedMonotonicNs'])
    assert elapsed == int(result['controlObservedElapsedMonotonicNs']) == int(audit['controlObservedElapsedMonotonicNs']) == 22150156088
    assert elapsed <= 30_000_000_000 and int(result['elapsedMonotonicNs']) == 22943975796
    assert result['innerCases'] == 13 and result['innerReaps'] == 39 and not result['unexpectedChildrenObserved']
    assert result['heldInterpreterBefore'] == result['heldInterpreterAfter'] and result['parentPacketStable']
    outer = result['controlExit']; assert result['outerChildrenReaped'] == [outer] and outer['exitCode'] == 0 and outer['reaped']
    reaps = []
    assert tuple(case['case'] for case in control['cases']) == CASES
    for case, classification in zip(control['cases'], audit['cases']):
        directory = attempt/'state'/case['case']
        assert read(directory/'CASE-RESULT.json') == case and case['passed']
        for name, pin in case['evidence'].items():
            assert digest(directory/name) == pin
        recovery = read(directory/'recovery.json')
        assert recovery['passed'] and not recovery['historicalPossibleEffectsResent']
        assert classification['claims'] == len(recovery['final']['claims'])
        if case['cut'] == 'possible':
            assert classification['claims'] == 3 and classification['explicitEffects'] == []
            assert classification['classification'] == 'possible-unresolved-retained'
        for kind, expected_exit in (('owner', -9), ('recovery', 0), ('native', 0)):
            record = case['reaps'][kind]; identity = case['identities'][kind]
            assert all(record[key] == value for key, value in identity.items())
            assert record['reaped'] and record['exitCode'] == expected_exit and record['parent'] == outer['pid']
            reaps.append(record)
    key = lambda row: (row['pid'], row['startTicks'])
    assert len({key(row) for row in reaps}) == 39
    assert sorted(reaps, key=key) == sorted(control['childrenReaped'], key=key)
    observations = audit['ownedIdentityObservations']
    assert len(observations) == 40 and all(row['observation'] == 'absent' for row in observations)
    assert {key(row) for row in observations} == {key(row) for row in [outer]+reaps}
    intent = read(attempt/'intent.json'); review = read(HOST/'SOURCE-REVIEW.json')
    assert digest(HOST/'SOURCE-REVIEW.json') == digest(attempt/'frozen/SOURCE-REVIEW.json') == REVIEW_SHA
    assert len(review['files']) == 287 and set(intent['sourcePins']) == {row['path'] for row in review['files']}|{'SOURCE-REVIEW.json'}
    for row in review['files']:
        assert intent['sourcePins'][row['path']] == row['sha256']
        entry(HOST/row['path'], row); entry(attempt/'frozen'/row['path'], row)

    size = read(HERE/'size-proposal-verification.json')
    assert size['status'] == 'verified-retained-text-proposal' and size['packetFiles'] == 31 and size['packetBytes'] == 726614
    assert size['evidenceSha256'] == digest(SIZE/'evidence.json') == 'c9f8c76907d59c29f3b55544c264b8adae029fa13c87495331f0093840f57b5e'
    assert digest(SIZE/'measure.py') == 'cd0511fda604c3851a980ca396f5e1247ed4e280998c3e3dc93277165382f0df'
    assert digest(SIZE/'measurements.json') == '2c42b48947042d7cd17fb9d76c0ef4f5eebb35c7b1eb0561ff8ca741c7031f48'
    assert digest(SIZE/'coverage.json') == '269b8e771e5281f8eab1f7c67e1d5a1741b686ef04dd0f803526155a337e004d'
    assert size['flashLoadBytes'] == 41810 and size['physicalFlashExcessBytes'] == 9042 and size['applicationFlashExcessBytes'] == 9554
    assert size['mechanicallyEnumeratedInstructions'] == 8604 and size['selectedBodyBytes'] == 17982
    assert size['functionRootsIncludingMain'] == 30 and size['exactStorageRoots'] == 9 and size['staticStorageRootBytes'] == 1477
    assert size['readRangesVerified'] == 23 and size['repeatedTokenRunsVerified'] == 22
    assert not any(size[key] for key in ('candidateExecuted', 'compilerExecuted', 'targetExecuted', 'fitEstablished', 'combinedStackProof', 'machineByteIdentityEstablished'))
    join = read(HERE/'host-latest-join.json')
    assert digest(HERE/'host-latest-join.patch') == join['sourceDiffSha256']
    assert len(join['readCoverage']) == 8 and len(join['sourceChanges']) == 4
    for row in join['readCoverage']:
        path = ROOT/row['path']; assert digest(path) == row['sha256']
        lines = path.read_bytes().splitlines(keepends=True); first, last = row['readRange']
        assert len(lines) == row['lineCount'] and 1 <= first <= last <= len(lines)
        assert hashlib.sha256(b''.join(lines[first-1:last])).hexdigest() == row['rangeSha256']
        if row['fullFileRead']: assert first == 1 and last == len(lines)

    documents = {}; links = 0; missing = []
    for name in DOCS:
        path = ROOT/name; documents[name] = digest(path)
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text()):
            split = urlsplit(target.strip().strip('<>'))
            if split.scheme or split.netloc or not split.path: continue
            candidate = Path(unquote(split.path))
            if not candidate.is_absolute(): candidate = path.parent/candidate
            links += 1
            if not candidate.exists(): missing.append(dict(document=name, target=target))
    assert not missing, missing
    supporting = {}
    for path in sorted(HERE.rglob('*')):
        assert not path.is_symlink()
        if path.is_file() and path not in (HERE/'receipt.json', HERE/'verify.py'):
            supporting[str(path.relative_to(HERE))] = dict(bytes=path.stat().st_size, sha256=digest(path))
    receipt = dict(status='verified', goalStatus='active-incomplete', previousTurnClassification='progress',
        verificationSourceSha256=digest(Path(__file__)), reusedVerifierSha256=HELPER_SHA, previousReceiptSha256=PRIOR_SHA,
        sealedPackets=packets, rootDocuments=documents, rootSupportingFiles=supporting,
        publicReceiptSha256=PUBLIC_SHA, publicInputsExact=244, publicTestsRerun=False,
        actualStandingHostOwnerDeathTested=True, fixedOwnerDeathCutsPassed=13, hostInnerReaps=39, hostOuterReaps=1,
        hostHistoricallyObservedIdentitiesAbsent=40, hostRetainedAttemptFiles=476, retainedAuditAssertions=12739,
        hostAuditSha256=AUDIT_SHA, hostAuditSourceSha256=AUDIT_SOURCE_SHA, hostSourceReviewSha256=REVIEW_SHA,
        historicalPossibleEffectsResent=False, nativePeerSurvivedOwner=True, hostObservedElapsedMonotonicNs=str(elapsed),
        wholeHostQualified=False, protectedHostCapacity=False, publicStandingMountEligible=False,
        sizeProposalImplemented=False, sizeProposalSavingsMeasured=False, sizeProposalInstructions=8604,
        sizeProposalSelectedBodyBytes=17982, sizeProposalReadRanges=23, sizeProposalRetainedFunctionRoots=30,
        sizeProposalRetainedStorageObjects=9, standingFlashLoadBytes=41810, standingPhysicalFlashOverflowBytes=9042,
        standingApplicationFlashOverflowBytes=9554, targetFitEstablished=False, finalStackProof=False,
        targetExecuted=False, compilerExecutedThisTurn=False, physicalIOExecuted=False,
        storageFullWriterPassed=False, storageReplacementModelExecuted=False,
        localLinksChecked=links, missingLocalLinks=missing)
    with (HERE/'receipt.json').open('x') as output:
        json.dump(receipt, output, indent=2, sort_keys=True); output.write('\n'); output.flush(); os.fsync(output.fileno())
    print(json.dumps({key: value for key, value in receipt.items() if key not in ('sealedPackets', 'rootDocuments', 'rootSupportingFiles')}, sort_keys=True))


if __name__ == '__main__':
    main()
