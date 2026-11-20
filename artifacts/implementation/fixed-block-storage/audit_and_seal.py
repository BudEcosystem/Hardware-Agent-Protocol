"""Read-only evidence audit followed by new, exclusive audit/index publication.

Does not import the block implementation, open databases, rerun controls or mount.
"""
from pathlib import Path
import ast
import datetime
import fcntl
import hashlib
import json
import os
import re
import stat
from urllib.parse import unquote

STAGE = Path(__file__).resolve().parent
ROOT = STAGE.parents[2]
RESEARCH = ROOT / 'research/host-contract/fixed-block-storage'
CHUNK = 16 * 1024 * 1024
LIMIT = 256 * 1024 * 1024


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def entries(base):
    result = []
    for path in sorted(base.rglob('*')):
        info = path.lstat()
        assert not stat.S_ISLNK(info.st_mode), path
        if stat.S_ISREG(info.st_mode) and path.name != 'index.json':
            result.append({'path': str(path.relative_to(base)), 'bytes': info.st_size,
                           'sha256': digest(path)})
        else:
            assert stat.S_ISDIR(info.st_mode) or path.name == 'index.json', path
    return result


for path in [STAGE / 'AUDIT.json', STAGE / 'index.json', RESEARCH / 'index.json']:
    assert not path.exists(), path

preceding = []
for relative, expected in [
    ('artifacts/verification/pat-fuse-mount-probe',
     '3de8e5f9e1bcf668c6d43ac36de32e97c6e051d42e450d43953a30c1db698eb7'),
    ('research/host-contract/fuse-storage-boundary',
     '1d367d4b566595d8ee047eacd2b28534b9ade9eb17c1bbac314df17eb9158593'),
]:
    base = ROOT / relative
    assert digest(base / 'index.json') == expected
    previous = read(base / 'index.json')['files']
    assert entries(base) == previous
    preceding.append({'path': relative, 'indexSha256': expected, 'files': len(previous)})

baseline_path = ROOT / 'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
assert digest(baseline_path) == 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
baseline = read(baseline_path)
assert baseline['passed'] and baseline['tests'] == 866
assert len(baseline['files_after']) == 244
for item in baseline['files_after']:
    assert digest(ROOT / item['path']) == item['sha256'], item['path']

sources = read(RESEARCH / 'sources.json')['files']
coverage = read(RESEARCH / 'reading-coverage.json')
assert len(sources) == coverage['fullFiles'] == 11
assert sum(row['lines'] for row in sources) == coverage['lfLines'] == 7802
assert [r['path'] for r in coverage['files']] == [r['path'] for r in sources]
for source, record in zip(sources, coverage['files']):
    path = RESEARCH / source['path']
    assert path.stat().st_size == source['bytes']
    assert digest(path) == source['sha256'] == record['sha256']
    assert path.read_bytes().count(b'\n') == source['lines'] == record['lfLines']
    assert record['fullyRead'] is True
    next_line = 1
    for start, end in record['readRanges']:
        assert start == next_line and end >= start
        next_line = end + 1
    assert next_line == source['lines'] + 1
for item in read(RESEARCH / 'web-supplement.json')['files']:
    path = RESEARCH / item['path']
    assert path.stat().st_size == item['bytes'] and digest(path) == item['sha256']

tree = ast.parse((STAGE / 'test_fixed_block.py').read_text())
test_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'BlockImageTests')
names = sorted(n.name for n in test_class.body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_'))
assert len(names) == 24
log = (STAGE / 'attempt02/stderr.log').read_text()
assert re.findall(r'^(test_\d\d_\w+) \(__main__\.BlockImageTests\.\1\) \.\.\.', log, re.M) == names
assert len(re.findall(r'(?:\.\.\. |^)ok$', log, re.M)) == 24
assert '\nRan 24 tests in ' in log and log.endswith('\nOK\n')
assert 'Ran 0 tests' in (STAGE / 'attempt01/stderr.log').read_text()
assert 'INVALID_IDENTITY' in (STAGE / 'attempt01/stderr.log').read_text()

locks = []
try:
    # Hold every retained backing object's advisory lock during inspection.
    for attempt in ['attempt01', 'attempt02']:
        work = STAGE / attempt / 'images'
        for path in sorted(work.rglob('*')):
            if path.name not in {'owner', 'manifest', 'rejected-owner'} and not path.name.startswith('chunk-'):
                continue
            fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
            locks.append(fd)
            info = os.fstat(fd)
            assert stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            assert stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    attempts = []
    for number in [1, 2]:
        base = STAGE / f'attempt{number:02d}'
        result = read(base / 'RESULTS.json')
        before = read(base / 'inputs-before.json')
        assert before == read(base / 'inputs-after.json') and len(before) == 5
        assert {p.name for p in (base / 'frozen-inputs').iterdir()} == {Path(i['path']).name for i in before}
        for item in before:
            assert digest(base / 'frozen-inputs' / Path(item['path']).name) == item['sha256']
            if number == 2:
                assert digest(ROOT / item['path']) == item['sha256']
        for item in result['files']:
            path = base / item['path']
            info = path.stat()
            assert info.st_size == item['bytes'] and info.st_blocks * 512 == item['allocatedBytes']
            assert digest(path) == item['sha256'], path
        started = read(base / 'started.json')
        assert not Path('/proc', str(started['pid'])).exists()
        assert started['wallLimitSeconds'] == 60 and started['cpuLimitSeconds'] == 20
        assert started['scratchLimitBytes'] == LIMIT and started['perFileLimitBytes'] == CHUNK
        assert result['inputsStable'] and result['publicInputsUnchanged'] and result['publicInputCount'] == 244
        assert result['error'] is None
        assert result['status'] == ('failed' if number == 1 else 'passed')
        assert result['returncode'] == (1 if number == 1 else 0)
        expected = {'tests': 0, 'errors': 1, 'failures': 0, 'passed': False} if number == 1 else {
            'tests': 24, 'errors': 0, 'failures': 0, 'passed': True}
        assert result['tests'] == read(base / 'stdout.log') == expected
        for key in ['physicalPowerLossTested', 'filesystemIntegrated', 'serviceStorageEnforced',
                    'backedControlCapacity', 'productionChanged', 'acquiredCodeExecuted']:
            assert result[key] is False
        attempts.append({'attempt': base.name, 'status': result['status'], 'tests': expected,
                         'receiptFilesVerified': len(result['files']), 'frozenInputs': len(before),
                         'originalPidAbsent': True, 'elapsedSeconds': result['elapsedSeconds']})

    assert (STAGE / 'attempt01/frozen-inputs/fixed_block.py').read_bytes() == (STAGE / 'fixed_block.py').read_bytes()
    old_test = (STAGE / 'attempt01/frozen-inputs/test_fixed_block.py').read_text()
    assert old_test.replace('b50f1ecc80b64c498af24889ea159c097', 'b50f1ecc80b64c498af24889ea159c09') == (STAGE / 'test_fixed_block.py').read_text()

    creation = read(STAGE / 'attempt02/images/creation.json')
    for name, row in creation.items():
        base = STAGE / 'attempt02/images' / name
        assert digest(base / 'manifest') == row['manifestSha256']
        assert (base / 'owner').read_text() == row['identity'] + '\n'
        assert {p.name for p in base.iterdir()} == set(row['objects']) - {'.'}
        for obj, anchor in row['objects'].items():
            info = (base / obj).stat()
            assert [info.st_dev, info.st_ino] == anchor
        assert row['capacityBytes'] == sum(f['bytes'] for f in row['files'])

    # Independently reconstruct every retained data byte, including the partial write.
    patches = {
        'attempt01/images/main/chunk-00': [],
        'attempt01/images/main/chunk-01': [],
        'attempt02/images/main/chunk-00': [(CHUNK - 16, b'A' * 16), (7 * 4096, b'P' * 16),
            (8 * 4096, b'S' * 64), (10 * 4096, b'C' * 8), (11 * 4096, b'F' * 16),
            (100 * 4096 + 32, b'R' * 32)],
        'attempt02/images/main/chunk-01': [(0, b'B' * 16), (CHUNK - 16, b'Z' * 16)],
        'attempt02/images/control/chunk-00': [(20 * 4096, b'T' * 16)],
    }
    for name, changes in patches.items():
        expected = bytearray(b'\xff') * CHUNK
        for offset, body in changes:
            expected[offset:offset + len(body)] = body
        path = STAGE / name
        assert path.stat().st_size == CHUNK and path.stat().st_blocks * 512 >= CHUNK
        assert digest(path) == hashlib.sha256(expected).hexdigest(), name
    partial = STAGE / 'attempt02/images/partial-create'
    assert {p.name for p in partial.iterdir()} == {'owner', 'chunk-00'}
    assert (partial / 'chunk-00').stat().st_size == 0
    assert (partial / 'owner').read_bytes() == b'a' * 32 + b'\n'

    observations = [json.loads(line) for line in (STAGE / 'attempt02/images/observations.jsonl').read_text().splitlines()]
    assert len(observations) == 12 and len({r['kind'] for r in observations}) == 12
    by_kind = {r['kind']: r for r in observations}
    assert by_kind['injected-partial-write']['rollback'] is False
    assert by_kind['independent-image']['serviceRecoveryQualified'] is False
    assert by_kind['injected-create-allocation-failure']['readyManifest'] is False

    docs = [ROOT / p for p in ['README.md', 'PROGRESS.md', 'docs/control-storage.md', 'docs/io-driver-hub-control.md']]
    docs += [STAGE / p for p in ['README.md', 'NEXT.md', 'PLAN.md', 'REVIEW.md', 'CORRECTION.md']]
    docs += [RESEARCH / p for p in ['README.md', 'NOTES.md']]
    targets = []
    for doc in docs:
        for raw in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)', doc.read_text()):
            target = unquote(raw.strip('<>').split('#', 1)[0])
            if not target or re.match(r'[a-zA-Z][a-zA-Z0-9+.-]*:', target):
                continue
            path = (doc.parent / target).resolve()
            assert path.exists() or path == STAGE / 'AUDIT.json', (doc, target)
            targets.append(path)

    retained = entries(STAGE)
    logical = sum(r['bytes'] for r in retained)
    allocated = sum((STAGE / r['path']).stat().st_blocks * 512 for r in retained)
    assert all(r['bytes'] <= CHUNK for r in retained)
    assert logical < LIMIT and allocated < LIMIT
    report = {
        'schema': 'hms.fixed-block-storage-audit/1', 'status': 'passed',
        'createdAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'review': 'primary agent only', 'attempts': attempts, 'testNames': names,
        'productionPrototypeUnchangedBetweenAttempts': True,
        'publicBaselineTests': 866, 'publicInputsUnchanged': 244,
        'priorSealedPacketsVerified': preceding, 'rawSourceFilesVerified': 11,
        'fullyReadSourceLfLines': 7802, 'supplementalManualRetainedAndRead': True,
        'retainedBackingBytes': 5 * CHUNK, 'backingObjectsLockedReadOnly': len(locks),
        'allRetainedChunkContentsVerified': True, 'creationAnchorsVerified': True,
        'injectedPartialWriteRetained': True, 'failedCreationRetained': True,
        'filesBeforeAuditAndIndices': len(retained), 'logicalBytesBeforeAuditAndIndices': logical,
        'allocatedBytesBeforeAuditAndIndices': allocated, 'scratchLimitBytes': LIMIT,
        'perFileLimitBytes': CHUNK, 'scratchEnforcement': 'finite original inventory and post-run verification',
        'documentsChecked': len(docs), 'localLinksChecked': len(targets), 'missingLinks': 0,
        'documentation': [{'path': str(p.relative_to(ROOT)), 'sha256': digest(p)} for p in docs],
        'productionChanged': False, 'filesystemIntegrated': False,
        'totalDiskQuotaEnforced': False, 'backedControlCapacity': False,
        'serviceRecoveryQualified': False, 'physicalPowerLossTested': False,
        'acquiredCodeExecuted': False, 'testsRepeatedDuringAudit': False,
    }
    save(STAGE / 'AUDIT.json', report)
    assert all(path.exists() for path in targets)
    for base in [RESEARCH, STAGE]:
        index = {'schema': 'hms.retained-files/1', 'files': entries(base)}
        save(base / 'index.json', index)
        assert entries(base) == index['files']
    final_files = [p for p in STAGE.rglob('*') if p.is_file()]
    final_logical = sum(p.stat().st_size for p in final_files)
    final_allocated = sum(p.stat().st_blocks * 512 for p in final_files)
    assert final_logical < LIMIT and final_allocated < LIMIT
    assert all(p.stat().st_size <= CHUNK for p in final_files)
    print(json.dumps({'status': 'passed', 'tests': 24, 'publicInputsUnchanged': 244,
        'lockedObjects': len(locks), 'finalFiles': len(final_files),
        'finalLogicalBytes': final_logical, 'finalAllocatedBytes': final_allocated,
        'researchIndexSha256': digest(RESEARCH / 'index.json'),
        'stageIndexSha256': digest(STAGE / 'index.json')}, sort_keys=True))
finally:
    for fd in reversed(locks):
        os.close(fd)
