"""Read-only evidence joins for the size increment and host integration frontier."""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import sys
from urllib.parse import unquote,urlsplit

if sys.flags.optimize:
    raise RuntimeError('Assertions required')
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRIOR = ROOT/'artifacts/verification/continuation-99'
PRIOR_SOURCE_SHA = 'c8eeecf02031c1203f030719e409c84863838ae79acd8c2164e7940d56513c2a'
PUBLIC = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
PUBLIC_SHA = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
DOCS = ('README.md','PROGRESS.md','docs/control-storage.md','docs/io-driver-hub-control.md',
        'docs/prompt-to-pat.md','docs/embedded-evidence.md','spec/12-io-driver-boundary.md')
NEW = (
    ('artifacts/implementation/standing-endpoint-fit','ede57dc170628262e80e865c6326e1a5813e04a90e962317b9f698d76726afc0'),
    ('artifacts/verification/standing-size-analysis','8cf51878b7cfa9d1889e32e0eaf2f1e84f99d83608e1747bc2e334c65b210fed'),
    ('research/constrained/avr/compiler-options-review','aa5b1846621d0ec07f2d5fbbeb6b127c9ba239df4771eadd6b52cb3d957bed3e'),
    ('artifacts/design/standing-host-deployment','9aba3626646c5ba6a2db70f48c797f32cf7ef5958453647d5232224d6a60e270'),
)


def digest(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def read(path):return json.loads(path.read_bytes())


def main():
    assert digest(PRIOR/'verify.py') == PRIOR_SOURCE_SHA
    # The exact previously reviewed verifier defines the inert packet-byte join.
    # run_path uses a non-main name, so its receipt-writing main is not invoked.
    packet = runpy.run_path(str(PRIOR/'verify.py'))['packet']
    previous = read(PRIOR/'receipt.json');assert previous['status'] == 'verified' and len(previous['sealedPackets']) == 11
    revalidation = read(HERE/'revalidation.json')
    assert revalidation['previousReceiptSha256'] == digest(PRIOR/'receipt.json')
    assert revalidation['previousTurnClassification'] == 'progress'
    packets = [packet(row['path'],row['indexSha256']) for row in previous['sealedPackets']]
    packets += [packet(name,pin) for name,pin in NEW]
    assert digest(PUBLIC) == PUBLIC_SHA
    public = read(PUBLIC);assert public['passed'] and public['tests'] == 866 and len(public['files']) == 244
    assert all(digest(ROOT/row['path']) == row['sha256'] for row in public['files'])
    fit = ROOT/'artifacts/implementation/standing-endpoint-fit';audit = read(fit/'AUDIT.json')
    assert audit['passed'] and audit['auditSourceSha256'] == digest(fit/'audit_retained.py')
    assert audit['totalCommands'] == audit['observedOwnedIdentitiesAbsent'] == 33 and len(audit['attempts']) == 2
    assert audit['currentSourcesNativeCompleted'] and not audit['currentSourcesAvrCompleted']
    native = read(fit/'checks-native.json');avr = read(fit/'checks-avr.json');current = read(fit/'project-source-review.json')
    assert native['requested_checks_completed'] and not avr['requested_checks_completed']
    for report in (native,avr):
        assert {name.removeprefix('project/'):pin for name,pin in report['sources'].items() if name.startswith('project/')} == current['project_sha256']
    for mode in ('plain','asan'):
        assert native['native']['standing'][mode] == dict(assertions=673,cases=13,physical_qualification=False)
    assert avr['commands'][-1]['name'] == 'avr-link' and avr['commands'][-1]['exit_code'] == 1
    mapped = read(fit/'MAP-REVIEW.json');folder = fit/'build/avr'
    assert digest(folder/'runtime.map') == mapped['mapSha256'] and digest(folder/'avr-link.stderr') == mapped['linkErrorSha256']
    body = (folder/'runtime.map').read_text()
    sections = {name:int(re.search(r'^\.'+name+r'\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)',body,re.M).group(1),16) for name in ('text','data','bss','noinit')}
    assert sections == mapped['sections'] == dict(text=43038,data=26,bss=1477,noinit=0)
    assert sections['text']+sections['data'] == mapped['flashLoadBytes'] == 43064
    assert mapped['physicalFlashOverflowBytes'] == mapped['flashLoadBytes']-32768 == 10296
    assert mapped['newStaticDeltaBytes'] == 160 and mapped['staticDeltaExcessBytes'] == 0
    assert mapped['combinedFlashReductionBytes'] == 582 and mapped['combinedStaticReductionBytes'] == 8
    assert mapped['staticPlusReservedStackBytes'] == 2015 and not mapped['targetFits'] and not (folder/'runtime.elf').exists()
    inspect = ROOT/'artifacts/verification/standing-size-analysis';ia = read(inspect/'AUDIT.json')
    assert ia['passed'] and ia['auditSourceSha256'] == digest(inspect/'audit.py')
    assert ia['outerCommands'] == ia['observedOwnedIdentitiesAbsent'] == 9
    assert ia['descriptorConstantConfirmed'] and ia['descriptorConstantBytes'] == 'e803000003200100' and not ia['objectsExecuted']
    research = ROOT/'research/constrained/avr/compiler-options-review';ledger = read(research/'reading-ledger.json');lines_read = 0
    for source in ledger['sources']:
        path = research/source['text'];lines = path.read_bytes().splitlines(keepends=True);next_line = 1
        assert digest(path) == source['textSha256'] and source['completeExtractedBodyRead']
        for part in source['ranges']:
            assert part['firstLine'] == next_line and part['readInFull'] and not part['outputTruncated']
            content = b''.join(lines[next_line-1:part['lastLine']]);assert hashlib.sha256(content).hexdigest() == part['sha256']
            next_line = part['lastLine']+1
        assert next_line == len(lines)+1 and len(lines) == source['coveredLines'];lines_read += len(lines)
    assert lines_read == 3438
    plan = ROOT/'artifacts/design/standing-host-deployment';evidence = read(plan/'SOURCE-EVIDENCE.json')
    assert len(evidence['sources']) == 30 and digest(plan/'HOST-DEPLOYMENT-PLAN.md') == evidence['plan']['sha256']
    for row in evidence['sources']:
        path = plan/'sources'/row['path'];assert digest(path) == row['sha256']
        lines = path.read_bytes().splitlines(keepends=True);assert len(row['readRanges']) == len(row['readRangeSha256'])
        for pair,pin in zip(row['readRanges'],row['readRangeSha256']):
            assert hashlib.sha256(b''.join(lines[pair[0]-1:pair[1]])).hexdigest() == pin
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
    result = dict(status='verified',goalStatus='active-incomplete',verificationSourceSha256=digest(Path(__file__)),
        reusedVerifierSha256=PRIOR_SOURCE_SHA,previousReceiptSha256=digest(PRIOR/'receipt.json'),rootDocuments=documents,sealedPackets=packets,
        publicReceiptSha256=PUBLIC_SHA,publicInputsExact=244,publicTestsRerun=False,previousTurnClassification='progress',
        standingCasesPerMode=13,standingAssertionsPerMode=673,standingOuterCommandReaps=33,inspectionCommandReaps=9,
        combinedFlashReductionBytes=582,standingFlashLoadBytes=43064,standingPhysicalFlashOverflowBytes=10296,
        standingStaticDeltaBytes=160,standingStaticDeltaExcessBytes=0,standingTargetFitEstablished=False,
        compilerManualChaptersFullyRead=2,compilerManualBodyLinesFullyRead=3438,ltoExecutionClaimed=False,
        hostDesignSourceCopies=30,hostImplementationStatus='source-in-progress-unexecuted-unqualified',
        storageFullWriterPassed=False,storageReplacementModelExecuted=False,physicalIOExecuted=False,
        localLinksChecked=links,missingLocalLinks=missing)
    with (HERE/'receipt.json').open('x') as target:
        json.dump(result,target,sort_keys=True,indent=2);target.write('\n');target.flush();os.fsync(target.fileno())
    print(json.dumps(result,sort_keys=True))


if __name__ == '__main__':main()
