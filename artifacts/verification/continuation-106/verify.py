"""Verify this continuation's actual local results and retained evidence only."""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import sys
from urllib.parse import unquote,urlsplit

assert not sys.flags.optimize
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PRIOR=ROOT/'artifacts/verification/continuation-105/receipt.json'
PRIOR_SHA='c34488f0a4bf7ea2ef2d1902b5f93a38dac0a91f864342f76f75b2510f04f673'
HELPER=ROOT/'artifacts/verification/continuation-99/verify.py'
HELPER_SHA='c8eeecf02031c1203f030719e409c84863838ae79acd8c2164e7940d56513c2a'
FW=ROOT/'artifacts/implementation/standing-endpoint-phase-kernels'
HOST=ROOT/'artifacts/implementation/standing-host-selection-reuse'
DOCS=('README.md','PROGRESS.md','docs/control-storage.md','docs/io-driver-hub-control.md',
      'docs/prompt-to-pat.md','docs/embedded-evidence.md','spec/12-io-driver-boundary.md')
def sha(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()
def read(path):return json.loads(path.read_bytes())
def entry(path,row):
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
def links(path):
    count=0
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text()):
        parsed=urlsplit(target.strip().strip('<>'))
        if parsed.scheme or parsed.netloc or not parsed.path:continue
        destination=Path(unquote(parsed.path))
        if not destination.is_absolute():destination=path.parent/destination
        assert destination.exists(),(path,target)
        count+=1
    return count
def absent(pid,tick):
    try:fields=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
    except FileNotFoundError:return
    assert int(fields[19])!=tick,'Original owned identity remains'

def main():
    assert len(sys.argv)==1 and sha(PRIOR)==PRIOR_SHA and sha(HELPER)==HELPER_SHA
    previous=read(PRIOR);assert previous['status']=='verified' and len(previous['sealedPackets'])==27
    assert sha(PRIOR.parent/'verify.py')==previous['verificationSourceSha256']
    for name,row in previous['rootSupportingFiles'].items():entry(PRIOR.parent/name,row)
    revalidation=read(HERE/'revalidation.json')
    assert revalidation['previousReceiptSha256']==PRIOR_SHA and revalidation['previousTurnClassification']=='progress'
    final=read(HERE/'final-review.json');assert final['rootReviewComplete']
    for folder,key in ((FW,'firmwareFinalFiles'),(HOST,'hostFinalFiles')):
        for name,pin in final[key].items():assert sha(folder/name)==pin
    execution=read(HERE/'executions.json')
    assert execution['actualRootToolExecutions'] and not execution['candidateReruns']
    assert not execution['qualificationRerun'] and not execution['physicalIOExecuted']
    expected=[('revalidation',0),('host-proposal-seal',0),('firmware-preflight',0),('firmware-native',0),
        ('firmware-avr',1),('firmware-retained-audit',0),('host-preflight',0),('host-pure',0),('host-live',0),
        ('codegen-reader-draft',1),('codegen-reader-corrected',0),('host-retained-audit',0),('firmware-seal',0),('host-seal',0)]
    assert [(row['name'],row['terminalExitCode']) for row in execution['executions']]==expected
    for row in execution['executions']:
        assert sha(ROOT/row['source'])==row['sourceSha256']
        assert sha(ROOT/row['receipt'])==row['receiptSha256']
    packet=runpy.run_path(str(HELPER))['packet']
    packets=[packet(row['path'],row['indexSha256']) for row in previous['sealedPackets']]
    for row in execution['newSealedPackets']:packets.append(packet(row['path'],row['indexSha256']))
    assert len(packets)==len({row['path'] for row in packets})==30
    for folder in (FW,HOST):
        index=read(folder/'index.json')
        assert index['sealSourceSha256']==sha(HERE/'seal_candidates.py')
        assert index['rootReviewSha256']==sha(HERE/'final-review.json')
    public=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert sha(public)==previous['publicReceiptSha256']=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    baseline=read(public);assert baseline['passed'] and baseline['tests']==866 and len(baseline['files'])==244
    for row in baseline['files']:assert sha(ROOT/row['path'])==row['sha256']
    audit=read(FW/'AUDIT.json')
    assert audit['passed'] and audit['totalCommands']==audit['totalReaps']==audit['observedOwnedIdentitiesAbsent']==58
    assert audit['frozenInputsExact']==139 and audit['currentSourcesNativeCompleted'] and not audit['currentSourcesAvrCompleted']
    identities=[]
    for stage,count in (('native',34),('avr',24)):
        report=read(FW/('checks-'+stage+'.json'));assert len(report['commands'])==len(report['owned_children_reaped'])==count
        assert report['owner_empty'] and report['owner_closed'] and not report['owner_cleanup_errors']
        for row in report['owned_children_reaped']:identities.append((row['pid'],row['startTicks']))
    native=read(FW/'checks-native.json')['native']
    for mode in ('plain','asan'):
        assert native['equivalence'][mode]['summary']['assertions']==1617
        assert native['equivalence'][mode]['summary']['trace_records']==1177
        for backend in ('byte','fallback'):assert native['kernel'][mode][backend]['assertions']==86889
    m=read(FW/'codegen-measurements.json')
    assert m['current']['flashBytes']==39186 and m['current']['staticBytes']==1503
    assert m['flashReductionBytes']==716 and m['applicationOverflowBytes']==6930 and m['physicalOverflowBytes']==6418
    assert m['current']['emittedFunctionCount']==146 and len(m['current']['allocatedTextSections'])==166
    assert m['current']['emittedBodyBytes']==38606 and m['current']['otherTextBytes']==554
    assert not m['validElf'] and not m['completeStackProof'] and not (FW/'build/avr/runtime.elf').exists()
    failure=read(HERE/'codegen-reader-attempt01.json')
    assert failure['exitCode']==1 and not failure['outputJsonCreated'] and not failure['candidateOrCompilerRerun']
    assert sha(FW/'reader-history/draft01/attempt01.json')==sha(HERE/'codegen-reader-attempt01.json')
    host_audit=read(HOST/'AUDIT.json')
    assert host_audit['passed'] and host_audit['checks']==51874 and host_audit['attemptFiles']==608
    assert host_audit['completedCases']==10 and host_audit['ownedIdentitiesCurrentlyAbsent']==11
    assert host_audit['newControlChecks']==351 and host_audit['legacyChecks']==76
    for profile,cases,checks,legacy,native_children in (('pure',1,84,0,0),('live',9,267,76,9)):
        folder=HOST/('selection-reuse-'+profile+'-attempt01')
        result=read(folder/'RESULTS.json');inner=read(folder/'state/CONTROL-RESULTS.json')
        assert result['passed'] and inner['passed'] and len(inner['cases'])==cases
        assert inner['checks']==checks and inner['legacyChecks']==legacy
        assert result['innerReaps']==len(inner['nativeChildrenReaped'])==native_children
        assert len(result['outerChildrenReaped'])==1
        for report,key in ((result,'outerChildrenReaped'),(inner,'nativeChildrenReaped')):
            assert report['ownerEmpty'] and report['ownerClosed'] and not report['cleanupErrors'] and not report['interruptsPending']
            for row in report[key]:
                assert row['reaped'] and row['exitCode']==0
                identities.append((row['pid'],row['startTicks']))
        assert not result['full128RecordQualification'] and not result['qualificationRerun']
        assert int(result['controlObservedElapsedMonotonicNs'])<=30_000_000_000
    pure=read(HOST/'selection-reuse-pure-attempt01/state/compiler_equivalence/evidence.json')
    assert len(pure['vectors'])==34 and pure['publicParseCalls']==5 and pure['privateParseCalls']==1
    management=read(HOST/'selection-reuse-live-attempt01/state/management_replays/evidence.json')
    assert management['selectionParseCalls']==3
    assert len(identities)==len(set(identities))==69
    for pid,tick in identities:absent(pid,tick)
    old=read(ROOT/'artifacts/implementation/standing-host-boundaries/boundary-mutation-attempt01/RESULTS.json')
    assert not old['passed'] and old['reason']=='RuntimeError: CONTROL_WALL_LIMIT'
    documents={name:sha(ROOT/name) for name in DOCS};dr=read(HERE/'documentation-review.json')
    assert documents==dr['rootDocuments'] and dr['independentLeadingStatusReviewComplete'] and dr['rootLeadingStatusReviewComplete']
    local_links=sum(links(ROOT/name) for name in DOCS)
    packet_links=sum(links(ROOT/name) for name in final['newProseFullyRead'])
    support={}
    for path in sorted(HERE.rglob('*')):
        assert not path.is_symlink()
        if path.is_file() and path not in (HERE/'receipt.json',Path(__file__)):
            support[str(path.relative_to(HERE))]=dict(bytes=path.stat().st_size,sha256=sha(path))
    receipt=dict(status='verified',goalStatus='active-incomplete',previousTurnClassification='progress',
        previousReceiptSha256=PRIOR_SHA,verificationSourceSha256=sha(Path(__file__)),reusedVerifierSha256=HELPER_SHA,
        sealedPackets=packets,rootDocuments=documents,rootSupportingFiles=support,
        publicReceiptSha256=sha(public),publicInputsExact=244,publicTestsPreviouslyPassed=866,publicTestsRerun=False,
        hostCompilerVectors=34,hostNativeCases=9,hostNewControlChecks=351,hostLegacyChecks=76,hostOwnedReaps=11,
        privateCompilationValidations=1,completeSelectionValidations=3,hostProductionChanged=True,
        full128RecordCapacityQualified=False,oldCapacityFailurePreserved=True,performanceImprovementEstablished=False,
        firmwareNativeCommands=34,firmwareAvrCommands=24,firmwareFrozenInputs=139,
        firmwareDifferentialGroups=20,firmwareDifferentialAssertions=1617,firmwareTraceRecords=1177,equalCompleteTraces=6,
        kernelAssertionsPerBackendMode=86889,standingFlashLoadBytes=39186,standingFlashReductionBytes=716,
        standingApplicationFlashOverflowBytes=6930,standingPhysicalFlashOverflowBytes=6418,standingStaticBytes=1503,
        newCompilerExecution=True,combinedStackProof=False,targetFitEstablished=False,ownedIdentitiesObservedAbsent=69,
        physicalIOExecuted=False,promptLearningImplemented=False,publicStandingMountEligible=False,
        localLinksChecked=local_links,newPacketLinksChecked=packet_links,missingLocalLinks=[],
        dataOnlyReaderFailureRetained=True,candidateReruns=False)
    with (HERE/'receipt.json').open('x') as out:
        json.dump(receipt,out,indent=2,sort_keys=True);out.write('\n');out.flush();os.fsync(out.fileno())
    print(json.dumps(dict(status='verified',sealedPackets=len(packets),publicInputsExact=244,ownedReaps=69,
        localLinksChecked=local_links,newPacketLinksChecked=packet_links,supportingFiles=len(support),
        receiptSha256=sha(HERE/'receipt.json'),goalStatus='active-incomplete'),sort_keys=True))

if __name__=='__main__':main()
