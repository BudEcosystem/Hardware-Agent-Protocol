"""Read-only audit of the exact block-read profile's original regression matrix."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ORIGINAL = HERE/'attempt01'
FROZEN = ORIGINAL/'frozen-inputs'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    for key, amount in [(resource.RLIMIT_CPU, 40), (resource.RLIMIT_AS, 512*1024**2),
                        (resource.RLIMIT_FSIZE, 16*1024**2), (resource.RLIMIT_NOFILE, 128)]:
        resource.setrlimit(key, (amount, amount))
    assert not (HERE/'EVIDENCE-AUDIT.json').exists()
    original = read(ORIGINAL/'RESULTS.json')
    assert original['status'] == 'passed' and original['inputsStable']
    assert original['librarySha256'] == 'be8b43b7ad909ed65b9ee834fccee3a769f08091c6fc0d1ad48a8ad14bd9abc2'
    for row in read(ORIGINAL/'inputs.json')['files']:
        assert sha(ROOT/row['path']) == sha(FROZEN/row['frozen']) == row['sha256']
    os.environ['HMS_CHUNK_LIBRARY'] = str(FROZEN/'block-read.so')
    os.environ['HMS_CHUNK_LIBRARY_SHA256'] = original['librarySha256']
    sys.path.insert(0, str(FROZEN))
    matrix = load(FROZEN/'matrix.py', 'hms_block_read_regression_inspector')
    from chunk_store import Native
    from readonly_image import ReadOnlyImage
    assert Path(sys.modules['chunk_store'].__file__).resolve() == FROZEN/'chunk_store.py'
    cases = read(FROZEN/'cases.json')['cases']
    assert len(original['interruptionCases']) == len(cases) == 22
    regression_images = []
    stops = []
    for case in cases:
        work = ORIGINAL/'interruptions'/case['id']
        result = read(work/'case-result.json')
        assert result['status'] == 'passed' and result['logical'] in case['expected']
        assert result == read(work/'stdout.txt')
        for index in range(len(case['cuts'])+1):
            name = 'original' if index == 0 else f'recovery-{index}'
            role = work/name
            final = index == len(case['cuts'])
            retained = read(role/('final-readback.json' if final else 'interrupted.json'))
            observed = matrix.snapshot(role, final=final)
            for key in ['logical', 'unlinked', 'unreferencedChunks', 'extraDirectories', 'stagingPresent',
                        'namespaceSha256', 'uniqueReachableBlocks', 'backingFiles']:
                assert observed[key] == retained[key]
            assert observed['imageUnchanged'] and not observed['recoveryInvoked']
            regression_images.append({'kind': 'interruption', 'caseId': case['id'], 'role': name,
                                      'backingFiles': observed['backingFiles']})
            owner = read(role/'owner-result.json')
            started = read(role/'owner-started.json')
            assert owner['reaped'] and owner['error'] is None
            if final:
                assert owner['returnCode'] == 0 and read(role/'recovered.json')['logical'] == observed['logical']
                assert observed['logical'] in case['expected']
            else:
                checkpoint = read(role/'checkpoint.json')
                stopped = read(role/'stopped.json')
                assert owner['returnCode'] == -9 and owner['selectedStopObserved']
                assert checkpoint['point'] == case['cuts'][index]
                assert checkpoint['intentSha256'] == sha(work/'operation-intent.json')
                assert stopped['checkpointSha256'] == sha(role/'checkpoint.json')
                assert checkpoint['process']['pid'] == stopped['pid'] == started['pid']
                assert checkpoint['process']['startTicks'] == stopped['startTicks'] == started['startTicks']
                assert stopped['state'] in {'T', 't'}
                stops.append({'caseId': case['id'], 'role': name, 'point': checkpoint['point'], 'pid': started['pid']})
            if index:
                clone = read(role/'clone.json')
                parent = work/clone['sourceRole']
                assert clone['sourceFiles'] == read(parent/'interrupted.json')['backingFiles']
                assert clone['copiedBlockSha256'] == clone['sourceFiles']['chunk-00']
                assert clone['destinationObjects'] == read(role/'anchor.json')['objects']
    assert len(stops) == 24 and len(regression_images) == 46
    expected = bytearray(bytes(range(256))*32)
    expected[4090:4106] = b'X'*16
    expected = expected[:4100]+b'\0'*(12000-4100)+b'Z'
    references = {'semantics': {'data': bytes(expected)}, 'namespace': {'target': b'N'*4096},
                  'recovery': {'live': b'L'*4096},
                  'accounting': {'large': b'B'*4096+b'A'*(248*1024)+b'C'*4096},
                  'caps': {'data': None, **{f'n{i}': b'' for i in range(15)}},
                  'fault': {'data': bytes([read(ORIGINAL/'semantics/fault/checks.json')['details']['recoveredByte']])*4096}}
    assert references['fault']['data'] in {b'A'*4096, b'B'*4096}
    check_count = 0
    for row in original['semanticScopes']:
        name = row['scope']
        work = ORIGINAL/'semantics'/name
        checks = read(work/'checks.json')
        assert checks['status'] == 'passed' and checks == read(work/'stdout.txt')
        assert len(checks['checks']) == row['checks'] and sha(work/'checks.json') == row['resultSha256']
        check_count += len(checks['checks'])
        image = ReadOnlyImage(work)
        native = None
        try:
            native = Native(image, FROZEN/'block-read.so', original['librarySha256'])
            native.call('hm_mount')
            raw = native.read('state')
            envelope = json.loads(raw)
            body = envelope['body']
            assert raw == canonical(envelope) and envelope['sha256'] == hashlib.sha256(canonical(body)).hexdigest()
            assert {r['name'] for r in body['inodes']} == set(references[name])
            for inode in body['inodes']:
                bits = base64.b64decode(inode['chunks'], validate=True)
                numbers = [n for n in range(4096) if bits[n//8] & (1 << (n%8))]
                directory = f"i{inode['id']:016x}"
                if references[name][inode['name']] is None:
                    assert name == 'caps' and numbers == [0] and native.stat(directory+'/c00000000') is None
                    continue
                data = bytearray(inode['size'])
                assert len(data) <= 256*1024
                for number in numbers:
                    chunk = native.read(f'{directory}/c{number:08x}')
                    assert len(chunk) == 4096
                    amount = min(4096, len(data)-number*4096)
                    data[number*4096:number*4096+amount] = chunk[:amount]
                assert bytes(data) == references[name][inode['name']]
            assert native.fault is None and all(native.counts[k] == 0 for k in ['programCalls', 'erases', 'syncs'])
            image.stable()
            regression_images.append({'kind': 'semantic', 'scope': name, 'backingFiles': image.before})
        finally:
            if native is not None:
                native.dispose()
            image.close()
    assert check_count == 54 and len(regression_images) == 52
    anchors = []
    for row in regression_images:
        role = ORIGINAL/'semantics'/row['scope'] if row['kind'] == 'semantic' else ORIGINAL/'interruptions'/row['caseId']/row['role']
        anchor = read(role/'anchor.json')
        for entry in anchor['objects'].values():
            assert len(entry) == 2 and all(isinstance(n, int) for n in entry)
            anchors.append(tuple(entry))
        for name, digest in row['backingFiles'].items():
            assert sha(role/'image'/name) == digest
    assert len(anchors) == len(set(anchors)) == 208
    processes = []
    for path in ORIGINAL.rglob('*started.json'):
        started = read(path)
        terminal = read(path.with_name(path.name.replace('started', 'result')))
        assert terminal['reaped'] and not Path('/proc', str(started['pid'])).exists()
        assert terminal['returnCode'] in ({0, -9} if path.name == 'owner-started.json' else {0})
        assert not terminal.get('timedOut', False)
        processes.append({'path': str(path.relative_to(HERE)), 'pid': started['pid'], 'returnCode': terminal['returnCode']})
    expected_processes = {f'attempt01/semantics/{r["scope"]}/process-started.json' for r in original['semanticScopes']}
    expected_processes.add('attempt01/semantics/recovery/owner-started.json')
    for case in cases:
        expected_processes.add(f'attempt01/interruptions/{case["id"]}/process-started.json')
        for index in range(len(case['cuts'])+1):
            role = 'original' if index == 0 else f'recovery-{index}'
            expected_processes.add(f'attempt01/interruptions/{case["id"]}/{role}/owner-started.json')
    assert {r['path'] for r in processes} == expected_processes
    assert len(processes) == len(expected_processes) == 75
    runtime = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert sha(runtime) == 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    rows = read(runtime)['files']
    assert len(rows) == 244 and all(sha(ROOT/r['path']) == r['sha256'] for r in rows)
    for row in read(ORIGINAL/'inputs.json')['files']:
        assert sha(ROOT/row['path']) == sha(FROZEN/row['frozen']) == row['sha256']
    files = [p for p in HERE.rglob('*') if p.is_file()]
    assert sum(p.stat().st_blocks*512 for p in files) < 1024**3
    assert sum(p.stat().st_size == 16*1024**2 for p in files) == 52
    output = {'schema': 'hms.chunk-block-read-evidence-audit/1', 'status': 'verified',
              'reviewer': 'primary agent only', 'semanticChecks': 54, 'interruptionCases': 22,
              'selectedStopsVerified': 24, 'regressionImagesReadOnly': regression_images,
              'stops': stops, 'processes': processes, 'distinctObjectAnchors': 208,
              'runtimeFilesExact': 244, 'retained16MiBImages': 52, 'allAuditedImageBytesUnchanged': True,
              'allMutationInterruptionsTested': False, 'serviceStorageQualified': False,
              'physicalPowerLossTested': False, 'backedControlCapacity': False,
              'sqliteTested': False, 'publicRuntimeInstalled': False}
    with (HERE/'EVIDENCE-AUDIT.json').open('x') as f:
        json.dump(output, f, indent=2, sort_keys=True); f.write('\n')
    print(json.dumps({k:v for k,v in output.items() if k not in {'regressionImagesReadOnly','stops','processes'}}, sort_keys=True))


if __name__ == '__main__':
    main()
