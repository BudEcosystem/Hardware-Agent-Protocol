"""Join sealed evidence and documentation; execute no candidate or prior test."""
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
PRIOR = ROOT/'artifacts/verification/continuation-103/receipt.json'
PRIOR_SHA = '9b2bdbdbad03292d36365c9e1c47539f09b8c6320fff25d90054417f06f8dcf9'
HELPER = ROOT/'artifacts/verification/continuation-99/verify.py'
HELPER_SHA = 'c8eeecf02031c1203f030719e409c84863838ae79acd8c2164e7940d56513c2a'
PUBLIC = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
PUBLIC_SHA = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
EM = ROOT/'artifacts/implementation/standing-endpoint-shared-kernel'
HOST = ROOT/'artifacts/implementation/standing-host-boundaries'
EM_AUDIT_SHA = '93b918d4eadb150c0998b933c97e76c6bfeed5fd77f00b242d3f8b4334274e1d'
HOST_AUDIT_SHA = '9256654248b0751839b52aa2573ec0eee5fe251889b7f508d60b559c08e10177'
HOST_INPUT_SHA = 'd2c1e0432dc5da5e1d63cc022e01b212b7c33b1d41b17cd3cdcc375a161568a3'
DOCS = ('README.md','PROGRESS.md','docs/control-storage.md','docs/io-driver-hub-control.md',
    'docs/prompt-to-pat.md','docs/embedded-evidence.md','spec/12-io-driver-boundary.md')

def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def entry(path, row):
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256']

def links(path):
    checked = 0
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text()):
        split = urlsplit(target.strip().strip('<>'))
        if split.scheme or split.netloc or not split.path: continue
        candidate = Path(unquote(split.path))
        if not candidate.is_absolute(): candidate = path.parent/candidate
        assert candidate.exists(), (path,target)
        checked += 1
    return checked

def main(embedded_index_sha, host_index_sha):
    assert digest(PRIOR) == PRIOR_SHA and digest(HELPER) == HELPER_SHA
    previous = read(PRIOR); assert previous['status'] == 'verified' and len(previous['sealedPackets']) == 23
    revalidation = read(HERE/'revalidation.json')
    assert revalidation['previousReceiptSha256'] == PRIOR_SHA and revalidation['previousTurnClassification'] == 'progress'
    packet = runpy.run_path(str(HELPER))['packet']
    packets = [packet(row['path'],row['indexSha256']) for row in previous['sealedPackets']]
    packets += [packet(str(EM.relative_to(ROOT)),embedded_index_sha),packet(str(HOST.relative_to(ROOT)),host_index_sha)]
    assert len(packets) == len({row['path'] for row in packets}) == 25
    assert all(read(folder/'index.json')['sealSourceSha256'] == digest(HERE/'seal.py') for folder in (EM,HOST))
    assert digest(PUBLIC) == PUBLIC_SHA
    public = read(PUBLIC)
    assert public['passed'] and public['tests'] == 866 and len(public['files']) == 244
    assert all(digest(ROOT/row['path']) == row['sha256'] for row in public['files'])
    execution = read(HERE/'executions.json')
    assert [(row['name'],row['terminalExitCode']) for row in execution['executions']] == [
        ('preflight',0),('embedded-native',0),('embedded-avr',1),('host-negative',0),('host-storage',0),
        ('host-mutation',1),('embedded-retained-audit',0),('generated-text-verification',0),('host-retained-audit',0)]
    for row in execution['executions']:
        assert digest(ROOT/row['source']) == row['sourceSha256'] and digest(ROOT/row['receipt']) == row['receiptSha256']
    assert not any(execution[key] for key in ('candidateRerunsAfterFailure','laterHostProfilesExecuted',
        'physicalIOExecuted','publicBaselineRerun','hostQualificationRerun'))
    preflight = read(HERE/'preflight.json')
    assert preflight['verificationSourceSha256'] == digest(HERE/'preflight.py')
    assert preflight['status'] == 'verified-frozen-reviewed-inputs-before-execution'
    assert preflight['embeddedReviewSha256'] == digest(EM/'project-source-review.json')
    assert preflight['hostReviewSha256'] == digest(HOST/'SOURCE-REVIEW.json')
    review = read(HERE/'final-review.json')
    assert review['rootReviewComplete'] and review['bothAuditorsFullyReadBeforeExecution']
    assert review['embeddedRetainedAuditorSha256'] == digest(EM/'audit_retained.py') == '892c961d48d24e097c34fb11d3b18555574712740421c07374d0b4a9822262ff'
    assert review['hostRetainedAuditorSha256'] == digest(HOST/'audit_retained.py') == 'da98d091cc59a3fb7c49a53f08635a76e1644f03e240c7f9669d6a0b67244f0d'
    assert digest(EM/'AUDIT.json') == EM_AUDIT_SHA and digest(HOST/'AUDIT.json') == HOST_AUDIT_SHA
    embedded = read(EM/'AUDIT.json'); host = read(HOST/'AUDIT.json')
    assert embedded['passed'] and embedded['totalCommands'] == embedded['totalReaps'] == embedded['observedOwnedIdentitiesAbsent'] == 50
    assert embedded['currentSourcesNativeCompleted'] and not embedded['currentSourcesAvrCompleted']
    assert embedded['frozenInputsExact'] == 119 and embedded['currentProjectFiles'] == 40 and embedded['originalCopies'] == 36
    assert not any(embedded[key] for key in ('targetFitEstablished','combinedStackProof','candidateCodeImported','checksRerun','targetExecuted','physicalIOQualified'))
    for name,row in embedded['retainedFiles'].items(): entry(EM/name,row)
    identities = set()
    native = read(EM/'checks-native.json'); avr = read(EM/'checks-avr.json')
    assert native['requested_checks_completed'] and not avr['requested_checks_completed']
    for report, count in ((native,26),(avr,24)):
        assert len(report['commands']) == len(report['owned_children_reaped']) == count
        assert report['owner_empty'] and report['owner_closed'] and not report['owner_cleanup_errors'] and not report['interrupts_pending_after_cleanup']
        for reap in report['owned_children_reaped']:
            assert reap['reaped']; identities.add((reap['pid'],reap['startTicks']))
    for mode in ('plain','asan'):
        assert native['native']['standing'][mode] == dict(cases=14,assertions=766,physical_qualification=False)
        assert native['native']['kernel'][mode] == dict(cases=3,assertions=13014,physical_qualification=False)
        eq = native['native']['equivalence'][mode]
        assert eq['summary'] == dict(equivalence_cases=16,old_cases=14,assertions=1241,added_assertions=475,
            trace_records=829,physical_qualification=False)
        for domain in ('baseline','candidate'):
            assert digest(EM/('build/native/equivalence-probe-'+domain+'-'+mode+'.stdout')) == eq['complete_trace_sha256'] == '086bc3496901dc560e4aef0f51abb426e5d90698d27920ca57a27dd1a3e85541'
    assert avr['commands'][-1]['name'] == 'avr-link' and avr['commands'][-1]['exit_code'] == 1
    assert len([c for c in avr['commands'] if c['name'].startswith('avr-compile-')]) == 13
    assert not (EM/'build/avr/runtime.elf').exists()
    generated = read(HERE/'codegen-verification.json')
    assert generated['verificationSourceSha256'] == digest(HERE/'verify_codegen.py') == 'ca17c4958f60ff964469e1446715a7adeceed92cd37575818226481dfa74e43a'
    assert generated['codegenReviewSha256'] == digest(EM/'codegen-review.json') == 'e703da177edb24a1beeaa9e828fecb975967fdaf331e612276ecd017c4ddfde0'
    assert generated['status'] == 'verified-generated-text-joins' and generated['retainedFunctionRoots'] == 30 and generated['chargedStorageObjects'] == 9
    assert generated['kernelBodies'] == 19 and generated['kernelBodyBytes'] == 2348
    assert not generated['completeStackProof'] and not generated['targetFitEstablished']
    mapped = (EM/'build/avr/runtime.map').read_text()
    sections = {name:int(re.search(r'^\.'+name+r'\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)',mapped,re.M)[1],16) for name in ('text','data','bss','noinit')}
    assert sections == dict(text=39876,data=26,bss=1477,noinit=0)
    assert sections['text']+sections['data'] == generated['memory']['flashBytes'] == 39902
    assert generated['memory']['physicalOverflowBytes'] == 7134 and generated['memory']['applicationOverflowBytes'] == 7646
    assert 'overflowed by 7134 bytes' in (EM/'build/avr/avr-link.stderr').read_text()
    assert host['passed'] and host['checks'] == 42895 and host['completedCases'] == 18
    assert host['completedProfiles'] == 2 and host['failedProfiles'] == 1 and host['completedProfileControlChecks'] == 258
    assert host['completedCaseChecks'] == 252 and host['failedProfilePartialChecks'] == 209
    assert host['nativeChildrenReaped'] == 19 and host['outerChildrenReaped'] == 3 and host['ownedIdentitiesCurrentlyAbsent'] == 22
    assert not any(host[key] for key in ('allEightProfilesPassed','full24CaseMatrixPassed','simultaneousMaximumHistoriesEstablished',
        'physicalEligible','protectedCapacity','publicMountEligible','qualificationRerun','actualOwnerDeathTestedHere'))
    assert host['unexecutedProfiles'] == ['episodes','activations','keys','fixed','accounting']
    assert digest(HOST/'AUDIT-INPUT-PINS.json') == host['auditInputPinsSha256'] == HOST_INPUT_SHA
    pins = read(HOST/'AUDIT-INPUT-PINS.json'); total = 0
    assert [r['profile'] for r in pins['attempts']] == ['negative','storage','mutation']
    for row in pins['attempts']:
        directory = HOST/row['path']; names = set()
        for item in row['files']:
            assert item['path'] not in names; names.add(item['path']);entry(directory/item['path'],item)
        assert names == {str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
        total += len(names)
        result = read(directory/'RESULTS.json'); control = read(directory/'state/CONTROL-RESULTS.json')
        assert digest(directory/'RESULTS.json') == row['resultSha256']
        assert result['ownerEmpty'] and result['ownerClosed'] and not result['cleanupErrors']
        assert control['ownerEmpty'] and control['ownerClosed'] and not control['cleanupErrors']
        outer = result['controlExit']; assert result['outerChildrenReaped'] == [outer]
        assert outer['reaped'] and outer['exitCode'] == (1 if row['profile']=='mutation' else 0)
        identities.add((outer['pid'],outer['startTicks']))
        for reap in control['nativeChildrenReaped']:
            assert reap['reaped'] and reap['exitCode'] == 0 and reap['parent'] == outer['pid']
            identities.add((reap['pid'],reap['startTicks']))
        if row['profile']=='mutation':
            assert not result['passed'] and not control['passed'] and result['reason'] == 'RuntimeError: CONTROL_WALL_LIMIT'
            assert len(control['nativeChildrenReaped']) == 1 and not control['cases']
            assert result['innerReaps'] == 0 and result['controlObservedElapsedMonotonicNs'] is None
        else:
            assert result['passed'] and control['passed']
            assert int(result['controlObservedElapsedMonotonicNs']) == int(result['controlTerminalObservedMonotonicNs'])-int(result['controlStartedMonotonicNs']) <= 30_000_000_000
    assert total == host['attemptFiles'] == 995
    progress = host['failedMutationProgress']
    assert progress['mutations'] == 68 and progress['retainedClaims'] == 3 and progress['mutationSequence'] == 0
    assert not progress['hasFullCaseSnapshot'] and progress['activations'] == progress['episodes'] == progress['versions'] == 0
    assert digest(HOST/'boundary-mutation-attempt01/state/mutation_capacity/authority.db') == progress['databaseSha256'] == 'f698be974640031c6df87f65bec8cbbc4bb100cf46e9768c86afb52fc46dcdcd'
    assert len(identities) == 72
    for pid,tick in identities:
        try: fields = (Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
        except FileNotFoundError: continue
        assert int(fields[19]) != tick, 'Original owned identity remains, including zombie'
    documents = {name:digest(ROOT/name) for name in DOCS}
    assert documents == read(HERE/'documentation-review.json')['rootDocuments']
    local_links = sum(links(ROOT/name) for name in DOCS)
    new_documents = [EM/'RESULTS.md',EM/'NEXT.md',EM/'CODEGEN-REVIEW.md',HOST/'RESULTS.md',HOST/'NEXT.md']
    packet_links = sum(links(path) for path in new_documents)
    supporting = {}
    for path in sorted(HERE.rglob('*')):
        assert not path.is_symlink()
        if path.is_file() and path not in (HERE/'receipt.json',HERE/'verify.py'):
            supporting[str(path.relative_to(HERE))] = dict(bytes=path.stat().st_size,sha256=digest(path))
    receipt = dict(status='verified',goalStatus='active-incomplete',previousTurnClassification='progress',
        previousReceiptSha256=PRIOR_SHA,verificationSourceSha256=digest(Path(__file__)),reusedVerifierSha256=HELPER_SHA,
        sealedPackets=packets,rootDocuments=documents,rootSupportingFiles=supporting,publicReceiptSha256=PUBLIC_SHA,
        publicInputsExact=244,publicTestsPreviouslyPassed=866,publicTestsRerun=False,
        embeddedNativeCommandsPassed=26,embeddedAvrCommands=24,embeddedOwnedReaps=50,embeddedAuditSha256=EM_AUDIT_SHA,
        embeddedKernelAssertionsPerMode=13014,embeddedEquivalenceGroups=16,embeddedEquivalenceAssertions=1241,
        embeddedNewAssertions=475,embeddedTraceRecords=829,embeddedFrozenInputs=119,
        sizeProposalImplemented=True,sizeProposalSavingsMeasured=True,combinedFlashReductionBytes=1908,
        standingFlashLoadBytes=39902,standingPhysicalFlashOverflowBytes=7134,standingApplicationFlashOverflowBytes=7646,
        standingStaticSramBytes=1503,retainedFunctionRootsIncludingMain=30,retainedStorageObjects=9,
        hostCompletedBoundaryCases=18,hostCompletedProfileControlChecks=258,hostFailedCapacityProfiles=1,
        hostFailedMutationRecords=68,hostFailedPartialChecks=209,hostInnerReaps=19,hostOuterReaps=3,
        hostAuditAssertions=42895,hostAuditSha256=HOST_AUDIT_SHA,hostRetainedAttemptFiles=995,
        hostFull24CaseMatrixPassed=False,hostSimultaneousMaximumHistoriesEstablished=False,
        hostUnexecutedProfiles=host['unexecutedProfiles'],allOriginalOwnedIdentitiesObservedAbsent=72,
        wholeHostQualified=False,protectedHostCapacity=False,publicStandingMountEligible=False,
        targetFitEstablished=False,finalStackProof=False,targetExecuted=False,compilerExecutedThisTurn=True,
        physicalIOExecuted=False,hostQualificationRerun=False,storageFullWriterPassed=False,storageReplacementModelExecuted=False,
        localLinksChecked=local_links,newPacketLocalLinksChecked=packet_links,missingLocalLinks=[])
    with (HERE/'receipt.json').open('x') as output:
        json.dump(receipt,output,indent=2,sort_keys=True);output.write('\n');output.flush();os.fsync(output.fileno())
    print(json.dumps({key:value for key,value in receipt.items() if key not in ('sealedPackets','rootDocuments','rootSupportingFiles')},sort_keys=True))

if __name__ == '__main__':
    assert len(sys.argv) == 3 and all(re.fullmatch(r'[0-9a-f]{64}',arg) for arg in sys.argv[1:])
    main(sys.argv[1],sys.argv[2])
