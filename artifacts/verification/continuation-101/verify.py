"""Read retained LTO/research evidence; never import candidate or execute probes."""
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
PRIOR = ROOT/'artifacts/verification/continuation-100'
HELPER = ROOT/'artifacts/verification/continuation-99/verify.py'
HELPER_SHA = 'c8eeecf02031c1203f030719e409c84863838ae79acd8c2164e7940d56513c2a'
PUBLIC = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
PUBLIC_SHA = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
DOCS = ('README.md','PROGRESS.md','docs/control-storage.md','docs/io-driver-hub-control.md',
        'docs/prompt-to-pat.md','docs/embedded-evidence.md','spec/12-io-driver-boundary.md')
NEW = (
    ('artifacts/implementation/standing-endpoint-lto','52ab3bcf4f94135f26ec18a40ffe6fcf0d8f480a019518b86f22f7aabf7bb469'),
    ('research/constrained/avr/plugin-lookup-review','54942f2e1408bebb352632db66c666bf0398df3102fbc9d91c71f30732fdda71'),
)


def digest(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def read(path):return json.loads(path.read_bytes())


def main():
    assert digest(HELPER) == HELPER_SHA
    packet = runpy.run_path(str(HELPER))['packet']
    previous = read(PRIOR/'receipt.json');assert previous['status'] == 'verified' and len(previous['sealedPackets']) == 15
    preflight = read(HERE/'revalidation.json')
    assert preflight['previousReceiptSha256'] == digest(PRIOR/'receipt.json')
    assert preflight['previousTurnClassification'] == 'progress'
    packets = [packet(row['path'],row['indexSha256']) for row in previous['sealedPackets']]
    packets += [packet(name,pin) for name,pin in NEW]
    assert digest(PUBLIC) == PUBLIC_SHA
    public = read(PUBLIC);assert public['passed'] and public['tests'] == 866 and len(public['files']) == 244
    assert all(digest(ROOT/row['path']) == row['sha256'] for row in public['files'])
    lane = ROOT/'artifacts/implementation/standing-endpoint-lto';audit = read(lane/'AUDIT.json')
    assert audit['passed'] and audit['auditSourceSha256'] == digest(lane/'audit_retained.py')
    assert audit['totalCommands'] == audit['observedOwnedIdentitiesAbsent'] == 32
    assert len(audit['attempts']) == 2 and not audit['currentSourcesAvrCompleted'] and not audit['nativeTestsRerun']
    first = read(lane/'checks-avr.json');second = read(lane/'checks-avr-attempt-2.json')
    assert not first['requested_checks_completed'] and not second['requested_checks_completed']
    assert len(first['commands']) == 9 and len(second['commands']) == 23
    assert all(command['passed'] for command in first['commands'])
    assert all(command['passed'] for command in second['commands'][:-1])
    assert second['commands'][-1]['name'] == 'avr-link' and second['commands'][-1]['exit_code'] == 1
    assert second['plugin_lookup_unchanged'] and second['plugin_lookup_after'] == second['plugin_lookup_expected']
    assert sum(command['name'].startswith('avr-compile-') for command in second['commands']) == 12
    folder = lane/'build/avr-attempt-2';mapped = read(lane/'MAP-REVIEW.json')
    assert all(digest(lane/name) == pin for name,pin in mapped['inputs'].items())
    body = (folder/'runtime.map').read_text()
    for name,expected in (('.text',41866),('.data',26),('.bss',1477),('.noinit',0)):
        match = re.search(r'^'+re.escape(name)+r'\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)',body,re.M)
        assert match and int(match[2],16) == expected == mapped['sections'][name]['bytes']
        assert int(match[1],16) == mapped['sections'][name]['address']
    assert mapped['flash_bytes'] == 41892 and mapped['physical_overflow_bytes'] == 41892-32768 == 9124
    assert mapped['application_excess_bytes'] == 41892-32256 == 9636
    assert mapped['static_bytes'] == 1503 and mapped['standing_delta_bytes'] == 1503-1343 == 160
    assert mapped['static_plus_stack_reservation_bytes'] == 1503+512 == 2015
    assert mapped['comparison']['difference_bytes'] == 43064-41892 == 1172
    assert not (folder/'runtime.elf').exists() and not mapped['combined_stack_proof']
    retention = read(lane/'retention.json')
    assert len(mapped['function_roots']) == 29 and len(mapped['storage_roots']) == 9
    expected_sizes = {row['name']:row['bytes'] for row in retention['storage_roots']}
    for row in mapped['function_roots']+mapped['storage_roots']:
        match = re.search(r'^\s+(0x[0-9a-f]+)\s+'+re.escape(row['name'])+r'\s*$',body,re.M)
        assert match and int(match[1],16) == row['address']
        if row['name'] in expected_sizes:
            section = re.search(r'^\s+\.bss\.'+re.escape(row['name'])+r'\s*\n?\s*(0x[0-9a-f]+)\s+(0x[0-9a-f]+)',body,re.M)
            assert section and int(section[1],16) == row['address'] and int(section[2],16) == row['bytes'] == expected_sizes[row['name']]
    storage = sorted(mapped['storage_roots'],key=lambda row:row['address'])
    assert sum(row['bytes'] for row in storage) == 1477
    assert all(a['address']+a['bytes'] <= b['address'] for a,b in zip(storage,storage[1:]))
    assert all(0x800100 <= row['address'] and row['address']+row['bytes'] <= 0x800100+2048 for row in storage)
    inventory = read(folder/'lto-artifacts.json');assert len(inventory['files']) == 54
    assert sum(row['bytes'] for row in inventory['files']) == 8398929
    assert len(inventory['possible_backend_stack_files']) == 1 and not inventory['final_stack_evidence_complete']
    assert len((folder/inventory['possible_backend_stack_files'][0]).read_text().splitlines()) == 105
    assert len(read(folder/'pre-lto-stack-records.json')['records']) == 131
    research = ROOT/'research/constrained/avr/plugin-lookup-review';coverage = read(research/'SOURCE-COVERAGE.json')
    ranges = [];count = 0
    for source in coverage['files']:
        path = research/source['path'];assert digest(path) == source['sha256'] and path.stat().st_size == source['bytes']
        lines = path.read_bytes().splitlines(keepends=True);assert len(lines) == source['lf_lines']
        for first_line,last_line in source['read_ranges_inclusive']:
            assert 1 <= first_line <= last_line <= len(lines)
            ranges.append(dict(path=source['path'],firstLine=first_line,lastLine=last_line,
                sha256=hashlib.sha256(b''.join(lines[first_line-1:last_line])).hexdigest()))
            count += last_line-first_line+1
    assert count == 1781 and coverage['files'][0]['full_file_read'] is False and coverage['files'][1]['full_file_read'] is False
    host_freeze = ROOT/'artifacts/implementation/standing-host-deployment/history/source-freeze01'
    assert digest(host_freeze/'SOURCE-REVIEW.json') == 'f7f605c415cb348fff31ebae2335f39ed7b7a5dc479c11cdc73ed1f8347c412b'
    host = read(host_freeze/'SOURCE-REVIEW.json');assert host['notSealed'] and len(host['files']) == 269
    assert all((host_freeze/row['path']).stat().st_size == row['bytes'] and digest(host_freeze/row['path']) == row['sha256'] for row in host['files'])
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
        reusedVerifierSha256=HELPER_SHA,previousReceiptSha256=digest(PRIOR/'receipt.json'),rootDocuments=documents,sealedPackets=packets,
        publicReceiptSha256=PUBLIC_SHA,publicInputsExact=244,publicTestsRerun=False,previousTurnClassification='progress',
        ltoAttempts=2,ltoOuterCommandReaps=32,standingFlashLoadBytes=41892,standingPhysicalFlashOverflowBytes=9124,
        standingStaticBytes=1503,standingStaticDeltaBytes=160,combinedProfileFlashReductionBytes=1172,
        finalStackProof=False,targetFitEstablished=False,targetExecuted=False,savedLtoArtifacts=54,
        possibleBackendStackRecords=105,compilerSourceReadLines=1781,compilerSourceReadRanges=ranges,
        compilerSourceFilesFullyRead=False,hostImplementationStatus='source-review-and-revision-unexecuted-unqualified',
        hostCandidateExecuted=False,hostFirstSourceFreezeFiles=269,hostFirstFreezeVerified=True,
        storageFullWriterPassed=False,storageReplacementModelExecuted=False,physicalIOExecuted=False,
        rootReviewNotes={name:digest(HERE/name) for name in ('HOST-SOURCE-REVIEW.md','LTO-SOURCE-REVIEW.md')},
        localLinksChecked=links,missingLocalLinks=missing)
    with (HERE/'receipt.json').open('x') as target:
        json.dump(result,target,sort_keys=True,indent=2);target.write('\n');target.flush();os.fsync(target.fileno())
    print(json.dumps({key:value for key,value in result.items() if key not in ('compilerSourceReadRanges','sealedPackets')},sort_keys=True))


if __name__ == '__main__':main()
