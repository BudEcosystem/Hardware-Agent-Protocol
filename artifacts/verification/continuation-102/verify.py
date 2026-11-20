"""Join retained evidence and documents, without rerunning tests or candidate code."""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import sys
from urllib.parse import unquote,urlsplit

assert not sys.flags.optimize
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRIOR = ROOT/'artifacts/verification/continuation-101'
PRIOR_SHA = '216af8d7b87510a0304b19fdc342315d13f963c91434928d56f933d0a6be7a19'
HELPER = ROOT/'artifacts/verification/continuation-99/verify.py'
HELPER_SHA = 'c8eeecf02031c1203f030719e409c84863838ae79acd8c2164e7940d56513c2a'
PUBLIC = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
PUBLIC_SHA = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
DOCS = ('README.md','PROGRESS.md','docs/control-storage.md','docs/io-driver-hub-control.md',
        'docs/prompt-to-pat.md','docs/embedded-evidence.md','spec/12-io-driver-boundary.md')
NEW = (
    ('artifacts/verification/standing-lto-attribution','85cd88298d252d1a5d51b4d4c286e46e91c5aaef1541f356ebd33cf39ae92a39'),
    ('artifacts/design/standing-host-owner-death','27a2e096ed8ec465d76a4c19136103aeb440c97e014d6d1a98698aee46087cba'),
    ('artifacts/implementation/standing-host-deployment','72371ef7752f2e90f6e8b185c125b00b165b8b64ce50d8121680c5a24951249b'),
    ('artifacts/implementation/standing-endpoint-copy-boundary','49ae3507a68d994d0fc9454146850358b793511fa585f8e96e3f607b54e90a6c'),
)
AUDIT_SOURCES = (
    '5995c63954d50a3d2dad988101833831a5b2ee2c71ab809e2270128643edcf3b',
    '36be134b8b566a8abacce340f4322ccee845a36f0b3c527346583d32adcbe0dd',
    '9aec9c373cd8f33f8f78dd134c0d5bd33d4569c0cf4b2f70962bd0b576194c33',
    '0b060383cdb83926d375353ed2c810ea6ff695d4d7f34ed89e6091b074ef641e',
)
ROOT_RESULTS = {
    'attribution-verification.json':('1f90fa85c4c92c3ab2e3f1eca2a985aaa6eee7803c0a62ddc1dc9c95e762b753',
        'verify_attribution.py','0234a113ba2e7331cbe88859d65a7a2f640edebd45d0121125539765171f31f2'),
    'copy-boundary-verification.json':('e7dc9747cca9de94f36571b1be379d93f0ab682a4fc974365b8c693db4458384',
        'verify_copy_boundary.py','11f2498f31b1e425b3d6d0e59ff79f03107a1db3d466ee5fe1244a2227411ebf'),
}


def digest(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def read(path):return json.loads(path.read_bytes())


def entry(path,row):
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256']


def main():
    assert digest(HELPER) == HELPER_SHA
    packet = runpy.run_path(str(HELPER))['packet']
    assert digest(PRIOR/'receipt.json') == PRIOR_SHA
    previous = read(PRIOR/'receipt.json')
    assert previous['status'] == 'verified' and len(previous['sealedPackets']) == 17
    preflight = read(HERE/'revalidation.json')
    assert preflight['previousReceiptSha256'] == PRIOR_SHA and preflight['previousTurnClassification'] == 'progress'
    packets = [packet(row['path'],row['indexSha256']) for row in previous['sealedPackets']]
    packets += [packet(name,pin) for name,pin in NEW]
    assert len(packets) == 21
    assert digest(PUBLIC) == PUBLIC_SHA
    public = read(PUBLIC);assert public['passed'] and public['tests'] == 866 and len(public['files']) == 244
    assert all(digest(ROOT/row['path']) == row['sha256'] for row in public['files'])
    host = ROOT/'artifacts/implementation/standing-host-deployment'
    assert digest(host/'AUDIT.json') == 'd2dad5b3451f90aa102dce752cf6649b25c0db9813b461b440a19abc23690f36'
    aggregate = read(host/'AUDIT.json');attempts = []
    assert len(aggregate['rootIndependentAudits']) == 4
    for i,row in enumerate(aggregate['rootIndependentAudits'],1):
        name = f'host-attempt{i:02d}';assert row['attempt'] == name
        source = HERE/f'audit_host_attempt{i:02d}.py';audit_path = HERE/f'{name}-audit.json'
        assert digest(source) == AUDIT_SOURCES[i-1]
        entry(ROOT/row['rootAuditSource']['path'],row['rootAuditSource'])
        entry(ROOT/row['rootAuditResult']['path'],row['rootAuditResult'])
        assert digest(source) == digest(host/row['copiedAuditSource'])
        assert digest(audit_path) == digest(host/row['copiedAuditResult'])
        audit = read(audit_path)
        assert audit['auditSourceSha256'] == AUDIT_SOURCES[i-1]
        assert audit['resultsSha256'] == row['resultsSha256'] == digest(host/name/'RESULTS.json')
        assert audit['qualificationCases'] == 12 and audit['qualificationAssertions'] == 638
        assert audit['outerReaps'] == audit['commands'] == 4
        assert audit['publicInputsExact'] == 244 and not audit['publicTestsRerun']
        assert not audit['hostQualified'] and not audit['physicalEligible']
        if i <= 2:
            assert audit['nativeFixturesLaunched'] == audit['hostCasesCompleted'] == 0
            assert row['hostChecks'] == row['nativeReaps'] == 0
        observed_paths = set()
        for item in audit['files']:
            assert item['path'] not in observed_paths;observed_paths.add(item['path'])
            entry(host/name/item['path'],item)
        assert observed_paths == {str(path.relative_to(host/name)) for path in (host/name).rglob('*') if path.is_file() or path.is_symlink()}
        assert len(observed_paths) == row['retainedInventoryFiles']
        result = read(host/name/'RESULTS.json')
        assert result['ownerClosed'] and result['ownerEmpty'] and not result['cleanupErrors'] and not result['interruptsPending']
        assert result['passed'] == (i == 4)
        attempts.append(audit)
    assert [row['hostCasesCompleted'] for row in attempts] == [0,0,9,20]
    assert [row['hostChecks'] for row in attempts[2:]] == [81,173]
    assert [row['nativeReaps'] for row in attempts[2:]] == [10,20]
    assert sum(len(row['files']) for row in attempts) == aggregate['retainedAttemptFiles'] == 1264
    assert sum(row['outerReaps'] for row in attempts) == aggregate['outerReaps'] == 16
    assert sum(row['nativeReaps'] for row in attempts[2:]) == aggregate['nativeReaps'] == 30
    assert sum(row['ownedIdentitiesObservedAbsent'] for row in attempts) == 46
    assert not any(aggregate[key] for key in ('actualOwnerDeathTested','physicalEligible','protectedCapacity','publicMountEligible','universalContainment','wholeHostQualified'))
    lane = ROOT/'artifacts/implementation/standing-endpoint-copy-boundary'
    assert digest(lane/'AUDIT.json') == '0dd8b6b07fe67b6b5328c2be4dce52e5069158f9d6deee7b7e5d48a095a185b7'
    embedded = read(lane/'AUDIT.json')
    assert embedded['passed'] and embedded['auditSourceSha256'] == digest(lane/'audit_retained.py') == 'd4f96f6cbea251dfb56a564759d9d0734be5dd358fe8f8e5018731e5c59feda1'
    assert embedded['totalCommands'] == embedded['observedOwnedIdentitiesAbsent'] == 37
    assert embedded['currentSourcesNativeCompleted'] and not embedded['currentSourcesAvrCompleted']
    assert embedded['currentProjectFiles'] == embedded['originalCopies'] == 36
    assert embedded['oldStandingCaseBodiesExact'] == 13 and embedded['sourceProposalHistoryFilesExact'] == 93
    assert not embedded['targetFitEstablished'] and not embedded['targetExecuted'] and not embedded['physicalIOQualified']
    for name,row in embedded['retainedFiles'].items():entry(lane/name,row)
    native = read(lane/'checks-native.json');avr = read(lane/'checks-avr.json')
    assert digest(lane/'checks-native.json') == '13a655a2aeb9edf4d605f405b24999a8e1eafdbad2ce7cc01831df8856702f04'
    assert digest(lane/'checks-avr.json') == 'c48444ae4c8eae3c3bd71ddee851b6c95e030869dc7a8de782e78391cff7f36a'
    assert native['requested_checks_completed'] and not avr['requested_checks_completed']
    assert len(native['commands']) == 14 and len(avr['commands']) == 23
    assert all(row['passed'] for row in native['commands']+avr['commands'][:-1])
    assert avr['commands'][-1]['name'] == 'avr-link' and avr['commands'][-1]['exit_code'] == 1
    assert sum(row['name'].startswith('avr-compile-') for row in avr['commands']) == 12
    for mode in ('plain','asan'):
        assert native['native']['standing'][mode] == dict(assertions=766,cases=14,physical_qualification=False)
    for report in (native,avr):
        assert report['owner_closed'] and report['owner_empty'] and not report['owner_cleanup_errors'] and not report['interrupts_pending_after_cleanup']
        assert report['sources_unchanged'] and report['copied_sources_unchanged'] and report['runtime_unchanged']
        assert report['installed_files_unchanged'] and report['tool_aliases_unchanged'] and report['plugin_lookup_unchanged']
        for name,pin in report['sources'].items():assert digest(lane/name) == pin
    for name,(pin,source,source_pin) in ROOT_RESULTS.items():
        assert digest(HERE/name) == pin and digest(HERE/source) == source_pin
        record = read(HERE/name);assert record['verificationSourceSha256'] == source_pin
        assert not record['candidateExecuted'] and not record['compilerExecuted'] and not record['targetExecuted']
    boundary = read(HERE/'copy-boundary-verification.json')
    assert boundary['flashLoadBytes'] == 41810 and boundary['physicalFlashOverflowBytes'] == 9042
    assert boundary['standingCallCallerOwnedReductionBytes'] == 95 and not boundary['fullStackProof']
    assert boundary['coverageRangesVerified'] == 10 and boundary['savedArtifacts'] == 54
    assert all(digest(lane/name) == pin for name,pin in boundary['reportPins'].items())
    attribution = read(HERE/'attribution-verification.json')
    assert attribution['coverageRangesVerified'] == 38 and attribution['packetFiles'] == 25
    design = ROOT/'artifacts/design/standing-host-owner-death';coverage = read(design/'SOURCE-COVERAGE.json')
    assert len(coverage['files']) == 18 and coverage['status'] == 'source-only-design'
    lines_read = 0;full_files = 0
    for row in coverage['files']:
        path = ROOT/row['path'];entry(path,row)
        lines = path.read_bytes().splitlines(keepends=True);assert len(lines) == row['lf_lines']
        full_files += row['full_file_read']
        for part in row['read_ranges_inclusive']:
            first,last = part['first'],part['last'];assert 1 <= first <= last <= len(lines)
            assert hashlib.sha256(b''.join(lines[first-1:last])).hexdigest() == part['sha256']
            lines_read += last-first+1
    assert lines_read == coverage['total_read_lines'] == 3691 and full_files == 14
    assert not any(coverage[key] for key in ('candidate_imported','candidate_or_compiler_executed_by_this_design','children_spawned_by_this_design','physical_io','signals_sent','tests_run_by_this_design'))
    documents = {};links = 0;missing = []
    for name in DOCS:
        path = ROOT/name;documents[name] = digest(path)
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text()):
            split = urlsplit(target.strip().strip('<>'))
            if split.scheme or split.netloc or not split.path:continue
            candidate = Path(unquote(split.path))
            if not candidate.is_absolute():candidate = path.parent/candidate
            links += 1
            if not candidate.exists():missing.append(dict(document=name,target=target))
    assert not missing,missing
    supporting = {path.name:digest(path) for path in HERE.iterdir() if path.is_file() and path.name not in ('receipt.json','verify.py')}
    result = dict(status='verified',goalStatus='active-incomplete',verificationSourceSha256=digest(Path(__file__)),
        reusedVerifierSha256=HELPER_SHA,previousReceiptSha256=PRIOR_SHA,previousTurnClassification='progress',
        rootDocuments=documents,rootSupportingFiles=supporting,sealedPackets=packets,
        publicReceiptSha256=PUBLIC_SHA,publicInputsExact=244,publicTestsRerun=False,
        hostAttempts=4,hostCasesPassed=20,hostChecksPassed=173,hostRetainedAttemptFiles=1264,
        hostOuterReaps=16,hostNativeReaps=30,hostHistoricallyObservedIdentitiesAbsent=46,
        wholeHostQualified=False,actualStandingHostOwnerDeathTested=False,protectedHostCapacity=False,
        standingOwnerDeathPlannedCuts=13,ownerDeathDesignReadLines=3691,ownerDeathDesignFullyReadFiles=14,
        embeddedOuterReaps=37,embeddedStandingCasesPerMode=14,embeddedStandingAssertionsPerMode=766,
        standingFlashLoadBytes=41810,standingPhysicalFlashOverflowBytes=9042,combinedFlashReductionBytes=82,
        standingStaticBytes=1503,standingStaticDeltaBytes=160,standingCallCallerOwnedReductionBytes=95,
        finalStackProof=False,targetFitEstablished=False,targetExecuted=False,
        savedLtoArtifacts=54,possibleBackendStackRecords=106,attributionCoverageRanges=38,boundaryCoverageRanges=10,
        storageFullWriterPassed=False,storageReplacementModelExecuted=False,physicalIOExecuted=False,
        localLinksChecked=links,missingLocalLinks=missing)
    with (HERE/'receipt.json').open('x') as output:
        json.dump(result,output,sort_keys=True,indent=2);output.write('\n');output.flush();os.fsync(output.fileno())
    print(json.dumps({key:value for key,value in result.items() if key not in ('sealedPackets','rootSupportingFiles')},sort_keys=True))


if __name__ == '__main__':main()
