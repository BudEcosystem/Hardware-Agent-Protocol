"""Join retained evidence and current documents; do not execute candidate code."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote,urlsplit

if sys.flags.optimize != 0:
    raise RuntimeError('Verification requires assertions enabled')

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PUBLIC = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
PUBLIC_SHA = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
DOCS = ('README.md','PROGRESS.md','docs/control-storage.md','docs/io-driver-hub-control.md',
        'docs/prompt-to-pat.md','docs/embedded-evidence.md','spec/12-io-driver-boundary.md')
NEW = (
    ('artifacts/implementation/owned-hub-writer-deferral','ad3c08a856113d2d41bb6f49f23fd3b78da2330d170d8cac43447502cdc7a9cd'),
    ('research/embedded/avr-io-boundaries','d939bfb0e1bf6415cc485c4185bb4c3a213f4ebd6c6a17a6e7dee40f4549908e'),
    ('artifacts/implementation/standing-endpoint-controller','10d3b5da8b4366511f64331af31ead9cd33b77e679eab106e5732d17d2a505a0'),
)


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def packet(name,pin):
    folder = ROOT/name; assert digest(folder/'index.json') == pin
    index = read(folder/'index.json'); paths = set()
    for row in index['files']:
        path = folder/row['path']; assert row['path'] not in paths
        assert not path.is_symlink() and path.is_file()
        assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256']
        paths.add(row['path'])
    for row in index.get('symlinks',[]):
        path = folder/row['path']; assert row['path'] not in paths
        assert path.is_symlink() and os.readlink(path) == row['target']
        paths.add(row['path'])
    assert {str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file() or p.is_symlink()} == paths|{'index.json'}
    return dict(path=name,indexSha256=pin,files=len(index['files']),symlinks=len(index.get('symlinks',[])))


def main():
    assert digest(PUBLIC) == PUBLIC_SHA
    baseline = read(PUBLIC)
    assert baseline['passed'] and baseline['tests'] == 866 and len(baseline['files']) == 244
    assert all(digest(ROOT/row['path']) == row['sha256'] for row in baseline['files'])
    previous_path = ROOT/'artifacts/verification/continuation-98/receipt.json'
    previous = read(previous_path); assert previous['status'] == 'verified' and len(previous['sealedPackets']) == 8
    packets = [packet(row['path'],row['indexSha256']) for row in previous['sealedPackets']]
    packets += [packet(name,pin) for name,pin in NEW]
    hub = ROOT/'artifacts/implementation/owned-hub-writer-deferral'
    result = read(hub/'writer-deferral-attempt01/RESULTS.json'); audit = read(hub/'AUDIT.json')
    assert result['passed'] and result['actualOwnerDeaths'] == result['deterministicHeldWriterDeferrals'] == 3
    assert audit['passed'] and audit['auditSourceSha256'] == digest(hub/'audit_evidence.py')
    assert audit['canonicalAdjacentSlots'] == 6 and audit['retainedHeldLeaseObservations'] == 9
    assert audit['familyReaps'] == 9 and audit['outerReaps'] == 1 and audit['observedIdentitiesAbsent'] == 10
    source = ROOT/'research/embedded/avr-io-boundaries'; reading = read(source/'reading.json')
    assert len(reading['files']) == 6 and reading['totalLfLines'] == 1443 and not reading['sourceExecuted']
    assert sum((source/row['path']).read_bytes().count(b'\n') for row in reading['files']) == 1443
    assert all(row['fullFileRead'] and row['firstLine'] == 1 and digest(source/row['path']) == row['sha256'] for row in reading['files'])
    standing = ROOT/'artifacts/implementation/standing-endpoint-controller'
    audit = read(standing/'AUDIT.json'); current = read(standing/'project-source-review.json')
    assert audit['passed'] and audit['auditSourceSha256'] == digest(standing/'audit_retained.py')
    assert audit['totalCommands'] == audit['observedOwnedIdentitiesAbsent'] == 65 and len(audit['attempts']) == 5
    assert audit['currentSourcesNativeCompleted'] and not audit['currentSourcesAvrCompleted'] and not audit['targetFitEstablished']
    native = read(standing/'checks-native-attempt-3.json'); avr = read(standing/'checks-avr-attempt-2.json')
    assert native['requested_checks_completed'] and not avr['requested_checks_completed']
    for report in (native,avr):
        assert {name.removeprefix('project/'):pin for name,pin in report['sources'].items() if name.startswith('project/')} == current['project_sha256']
    for mode in ('plain','asan'):
        assert native['native']['standing'][mode] == dict(assertions=638,cases=12,physical_qualification=False)
    assert avr['commands'][-1]['name'] == 'avr-link' and avr['commands'][-1]['exit_code'] == 1
    mapped = read(standing/'MAP-REVIEW.json'); folder = standing/'build/avr-attempt-2'
    assert mapped['mapSha256'] == digest(folder/'runtime.map') and mapped['linkErrorSha256'] == digest(folder/'avr-link.stderr')
    body = (folder/'runtime.map').read_text()
    sections = {name:int(re.search(r'^\.'+name+r'\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)',body,re.M).group(1),16) for name in ('text','data','bss','noinit')}
    assert sections == mapped['sections']
    assert sections['text']+sections['data'] == mapped['flashLoadBytes'] == 43646
    assert mapped['flashLoadBytes']-32768 == mapped['physicalFlashOverflowBytes'] == 10878
    assert sections['data']+sections['bss']+sections['noinit'] == mapped['staticSramBytes'] == 1511
    assert mapped['staticSramBytes']-1343 == mapped['newStaticDeltaBytes'] == 168
    assert mapped['staticDeltaExcessBytes'] == 8 and not mapped['validLinkedElf'] and not (folder/'runtime.elf').exists()
    documents = {}; links = 0; missing = []
    for name in DOCS:
        path = ROOT/name; documents[name] = digest(path)
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text()):
            split = urlsplit(target.strip().strip('<>'))
            if split.scheme or split.netloc or not split.path:continue
            candidate = Path(unquote(split.path))
            if not candidate.is_absolute():candidate = path.parent/candidate
            links += 1
            if not candidate.exists():missing.append(dict(document=name,target=target))
    assert not missing,missing
    result = dict(status='verified',goalStatus='active-incomplete',verificationSourceSha256=digest(Path(__file__)),
        previousReceiptSha256=digest(previous_path),rootDocuments=documents,sealedPackets=packets,
        publicReceiptSha256=PUBLIC_SHA,publicInputsExact=244,publicTestsRerun=False,
        deliberateHeldWriterDeferrals=3,writerDeferralObservedReaps=10,fullyReadNewArduinoFiles=6,fullyReadNewArduinoLfLines=1443,
        standingNativeCasesPerMode=12,standingNativeAssertionsPerMode=638,standingRetainedAttempts=5,standingOuterCommandReaps=65,
        standingAvrLinked=False,standingPhysicalFlashOverflowBytes=10878,standingStaticDeltaExcessBytes=8,
        standingTargetFitEstablished=False,storageReplacementModelExecuted=False,storageFullWriterPassed=False,
        physicalIOExecuted=False,localLinksChecked=links,missingLocalLinks=missing)
    with (HERE/'receipt.json').open('x') as target:
        json.dump(result,target,sort_keys=True,indent=2);target.write('\n');target.flush();os.fsync(target.fileno())
    print(json.dumps(result,sort_keys=True))


if __name__ == '__main__':
    main()
