"""Join actual executions, sealed evidence and current docs; run no candidate."""
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
PRIOR = ROOT/'artifacts/verification/continuation-104/receipt.json'
PRIOR_SHA = '176f0dd7e71c17ee89f0bddc0ec36fdf1de7203e93219c357532d867f9138e03'
HELPER = ROOT/'artifacts/verification/continuation-99/verify.py'
HELPER_SHA = 'c8eeecf02031c1203f030719e409c84863838ae79acd8c2164e7940d56513c2a'
HOST = ROOT/'artifacts/implementation/standing-host-history-cost'
PROPOSAL = ROOT/'artifacts/design/standing-endpoint-phase-size'
HOST_INDEX = '559679c886bac679ebac028e3c9d041f3b56f1026e24408a31fe24f45d3b94bd'
PROPOSAL_INDEX = '358207f52b904bcb6bb717e83b06846904ac56b9d4b295b85a68cd8f03559a27'
DOCS = ('README.md','PROGRESS.md','docs/control-storage.md','docs/io-driver-hub-control.md',
    'docs/prompt-to-pat.md','docs/embedded-evidence.md','spec/12-io-driver-boundary.md')

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def read(path):return json.loads(path.read_bytes())

def entry(path,row):
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256']

def links(path):
    count=0
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text()):
        split=urlsplit(target.strip().strip('<>'))
        if split.scheme or split.netloc or not split.path:continue
        destination=Path(unquote(split.path))
        if not destination.is_absolute():destination=path.parent/destination
        assert destination.exists(),(path,target)
        count+=1
    return count

def main():
    assert len(sys.argv)==1 and digest(PRIOR)==PRIOR_SHA and digest(HELPER)==HELPER_SHA
    previous=read(PRIOR);assert previous['status']=='verified' and len(previous['sealedPackets'])==25
    assert digest(PRIOR.parent/'verify.py')==previous['verificationSourceSha256']
    for name,row in previous['rootSupportingFiles'].items():entry(PRIOR.parent/name,row)
    revalidation=read(HERE/'revalidation.json')
    assert revalidation['previousReceiptSha256']==PRIOR_SHA and revalidation['previousTurnClassification']=='progress'
    packet=runpy.run_path(str(HELPER))['packet']
    packets=[packet(row['path'],row['indexSha256']) for row in previous['sealedPackets']]
    packets += [packet(str(HOST.relative_to(ROOT)),HOST_INDEX),packet(str(PROPOSAL.relative_to(ROOT)),PROPOSAL_INDEX)]
    assert len(packets)==len({row['path'] for row in packets})==27
    assert read(HOST/'index.json')['sealSourceSha256']==digest(HERE/'seal_diagnostic.py')
    assert read(PROPOSAL/'index.json')['sealSourceSha256']==digest(HERE/'seal_proposal.py')
    public_path=ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(public_path)==previous['publicReceiptSha256']=='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    public=read(public_path);assert public['passed'] and public['tests']==866 and len(public['files'])==244
    assert all(digest(ROOT/row['path'])==row['sha256'] for row in public['files'])
    execution=read(HERE/'executions.json')
    assert [(r['name'],r['terminalExitCode']) for r in execution['executions']]==[
        ('revalidation',0),('history-cost-preflight',0),('phase-text-measurement',0),('history-cost',0),
        ('history-cost-retained-audit',0),('phase-proposal-seal',0),('diagnostic-seal-draft',1),('diagnostic-seal',0)]
    for row in execution['executions']:
        assert digest(ROOT/row['source'])==row['sourceSha256'] and digest(ROOT/row['receipt'])==row['receiptSha256']
    assert execution['actualRootToolExecutions'] and execution['dataOnlySealReaderCorrectionPreserved']
    assert not any(execution[k] for k in ('candidateReruns','qualifierRerun','publicBaselineRerun','compilerExecuted','physicalIOExecuted'))
    failure=read(HERE/'reader-history/seal-diagnostic01/failure.json')
    assert failure['terminalExitCode']==1 and not failure['indexWritten'] and not failure['candidateRerun']
    review=read(HERE/'final-review.json')
    assert review['rootReviewComplete'] and review['auditorFullyReadBeforeExecution'] and review['proposalSixProseFilesFullyRead']
    assert digest(HOST/'audit_retained.py')==review['auditorSha256']=='16bb0303d87e72ab815f85199159f5a441961503d6187abae23845785c9f2579'
    assert digest(HOST/'SOURCE-REVIEW.json')==review['diagnosticSourceReviewSha256']=='75bb8a047304aa6b2cd4348837e68843b01983a947640c356b8a2764ea75f082'
    for name,key in [('history_cost_controls.py','controlFinalSha256'),('run_checks.py','runnerSha256')]:
        assert digest(HOST/name)==review[key]
    assert digest(PROPOSAL/'measure.py')==review['proposalReaderSha256']=='641f50f80605ef7f481d90c278b224767bdf922ea059ebe0010dbc6ac00d44f8'
    audit=read(HOST/'AUDIT.json');assert digest(HOST/'AUDIT.json')=='ad43b0a46898e13a0c8d59bb92ed48a31beeb16c07f816d44ad7e1a6fe64ef0e'
    assert audit['passed'] and audit['checks']==61794 and audit['attemptFiles']==309 and audit['sourceFilesReverified']==299
    assert audit['loopCount']==audit['database']['retainedMutations']==32 and audit['mutationValidations']==2176
    assert audit['database']['retainedClaims']==3 and audit['database']['mutationSequence']==audit['database']['activations']==0
    assert audit['database']['wireRequests']==audit['database']['wireResponses']==70 and audit['database']['selectors']==28
    assert audit['database']['databaseBytes']==249856 and audit['database']['chargedLogicalBytes']==81471
    assert audit['timing']['metricRows']==981 and audit['timing']['nonHeldExclusiveNs']=='5284797397'
    assert audit['timing']['loopElapsedNs']=='8186641095' and audit['timing']['outsideMeasuredSpansNs']=='2901843698'
    assert not any(audit[k] for k in ('productionChanged','qualificationRerun','full128RecordQualification','physicalEligible','protectedCapacity','publicMountEligible'))
    result=read(HOST/'history-cost-attempt01/RESULTS.json');inner=read(HOST/'history-cost-attempt01/state/CONTROL-RESULTS.json')
    assert result['passed'] and inner['passed'] and inner['checks']==143 and inner['cases'][0]['checks']==142
    assert result['controlObservedElapsedMonotonicNs']==audit['controlObservedElapsedNs']=='9642591362'
    assert result['elapsedMonotonicNs']==audit['finalElapsedNs']=='10730299100'
    identities=[]
    for report,reaps in ((result,result['outerChildrenReaped']),(inner,inner['nativeChildrenReaped'])):
        assert report['ownerEmpty'] and report['ownerClosed'] and not report['cleanupErrors'] and not report['interruptsPending']
        assert len(reaps)==1
        for reap in reaps:
            assert reap['reaped'] and reap['exitCode']==0
            identities.append((reap['pid'],reap['startTicks']))
    assert len(set(identities))==2 and inner['nativeChildrenReaped'][0]['parent']==result['controlExit']['pid']
    for pid,tick in identities:
        try:fields=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
        except FileNotFoundError:continue
        assert int(fields[19])!=tick,'Original owned identity remains'
    old=read(ROOT/'artifacts/implementation/standing-host-boundaries/boundary-mutation-attempt01/RESULTS.json')
    assert not old['passed'] and old['reason']=='RuntimeError: CONTROL_WALL_LIMIT'
    m=read(PROPOSAL/'measurements.json')
    assert m['flashBytes']==39902 and m['applicationGapBytes']==7646 and m['physicalGapBytes']==7134
    assert m['allocatedTextSectionCount']==151 and len(m['emittedFunctions'])==131 and m['directCallSites']==676
    assert m['emittedBodyBytes']==39322 and m['otherTextBytes']==554
    assert not any(m[k] for k in ('candidateImplemented','compilerExecuted','expectedSavingsKnown','supportedFit','completeStackProof'))
    documents={name:digest(ROOT/name) for name in DOCS};dr=read(HERE/'documentation-review.json')
    assert documents==dr['rootDocuments'] and dr['independentReviewComplete'] and dr['rootAppliedBothCorrections']
    local_links=sum(links(ROOT/name) for name in DOCS)
    new_docs=[HOST/name for name in ('README.md','RESULTS.md','NEXT.md','AUDIT-PLAN.md')]
    new_docs += [PROPOSAL/name for name in ('README.md','ANALYSIS.md','PROPOSAL.md','SEMANTICS.md','CONTROLS.md','SOURCE-COVERAGE.md')]
    packet_links=sum(links(path) for path in new_docs)
    supporting={}
    for path in sorted(HERE.rglob('*')):
        assert not path.is_symlink()
        if path.is_file() and path not in (HERE/'receipt.json',Path(__file__)):
            supporting[str(path.relative_to(HERE))]=dict(bytes=path.stat().st_size,sha256=digest(path))
    receipt=dict(status='verified',goalStatus='active-incomplete',previousTurnClassification='progress',
        previousReceiptSha256=PRIOR_SHA,verificationSourceSha256=digest(Path(__file__)),reusedVerifierSha256=HELPER_SHA,
        sealedPackets=packets,rootDocuments=documents,rootSupportingFiles=supporting,
        publicReceiptSha256=digest(public_path),publicInputsExact=244,publicTestsPreviouslyPassed=866,publicTestsRerun=False,
        hostDiagnosticCases=1,hostDiagnosticChecks=143,hostDiagnosticLoops=32,hostMutationValidations=2176,
        hostDiagnosticAuditChecks=61794,hostAuditTerminalChecks=61795,hostAttemptFiles=309,hostFrozenFiles=299,
        hostRawPackets=140,hostNativeSelectors=28,hostRetainedClaims=3,hostOwnedReaps=2,hostProductionChanged=False,
        hostFullCapacityPassed=False,oldCapacityFailurePreserved=True,historyCountModelConfirmed=True,
        narrowerOptimizationPriorityIdentified=True,performanceImprovementEstablished=False,
        phaseProposalInputFiles=20,phaseProposalTextSections=151,phaseProposalGeneratedBodies=131,
        standingFlashLoadBytes=39902,standingApplicationFlashOverflowBytes=7646,standingPhysicalFlashOverflowBytes=7134,
        newCompilerExecution=False,newFlashSavingsMeasured=False,combinedStackProof=False,targetFitEstablished=False,
        physicalIOExecuted=False,promptLearningImplemented=False,publicStandingMountEligible=False,
        localLinksChecked=local_links,newPacketLinksChecked=packet_links,missingLocalLinks=[],
        dataOnlySealReaderFailureRetained=True,candidateReruns=False)
    with (HERE/'receipt.json').open('x') as stream:
        json.dump(receipt,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    print(json.dumps(dict(status='verified',sealedPackets=len(packets),publicInputsExact=244,
        diagnosticLoops=32,mutationValidations=2176,localLinksChecked=local_links,newPacketLinksChecked=packet_links,
        supportingFiles=len(supporting),receiptSha256=digest(HERE/'receipt.json'),goalStatus='active-incomplete'),sort_keys=True))

if __name__=='__main__':main()
