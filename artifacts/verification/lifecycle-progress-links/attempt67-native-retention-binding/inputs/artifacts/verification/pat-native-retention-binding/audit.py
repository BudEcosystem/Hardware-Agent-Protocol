"""Read-only evidence audit, including a narrow actual-syscall allowlist."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

BASE = Path(__file__).resolve().parent
def read(path):
    return json.loads(path.read_bytes())
def sha(path):
    assert stat.S_ISREG(path.lstat().st_mode)
    return hashlib.sha256(path.read_bytes()).hexdigest()
inputs = read(BASE / 'inputs.json')
assert sha(BASE / 'inputs.json') == '8a329a70e3f03e105ceffade69cccb81f505e9b4595bcac7cce310eec52348df'
for row in inputs['files']:
    assert (BASE / row['path']).lstat().st_size == row['bytes'] and sha(BASE / row['path']) == row['sha256']
assert (BASE / 'reference.py').read_bytes() == (BASE.parent / 'pat-native-retention-prototype/reference.py').read_bytes()
parent = read(BASE / 'attempt01/result.json')
assert parent['status'] == 'passed' and parent['inputsUnchanged']
assert len(parent['processes']) == 2 and all(row['exitCode'] == 0 for row in parent['processes'])
counts = {}
for kind, expected in [('production', 43), ('instrumented', 20)]:
    result = read(BASE / 'attempt01' / kind / 'result.json')
    assert result['status'] == 'passed' and result['error'] is None and result['kind'] == kind
    assert len(result['checks']) == expected == len({row['name'] for row in result['checks']})
    assert not result['productionIntegration'] and not result['actualWorkerRun'] and not result['physicalEffects']
    counts[kind] = expected
collection = read(BASE / 'trace01/collection.json')
assert collection['metadataBefore'] == collection['metadataAfter']
assert collection['probeSha256'] == sha(BASE / 'trace_probe.py')
assert collection['scriptSha256'] == sha(BASE / 'trace.py')
build = read(BASE / 'build01/production/build.json')
assert collection['binarySha256'] == build['binarySha256'] == sha(BASE / build['binary'])
traces = []
for mode, reason in [('ordinary', 'OK'), ('fifo', 'QUALIFICATION_UNSAFE_FILE'), ('veto', 'AUDIT_VETO')]:
    path = BASE / 'trace01' / (mode + '.trace')
    assert path.stat().st_size <= 1048576
    lines = path.read_text().splitlines()
    assert 0 < len(lines) <= 1000 and lines[-1] == '+++ exited with 0 +++'
    names = [line.split('(', 1)[0] for line in lines[:-1]]
    assert names.count('execve') == 1
    assert not set(names).intersection({'fork', 'vfork', 'clone', 'clone3', 'socket', 'connect', 'unlink',
        'unlinkat', 'rename', 'renameat', 'mkdir', 'mkdirat', 'chmod', 'fchmod', 'chown', 'fchown',
        'truncate', 'ftruncate', 'pwrite64', 'writev'})
    begin = [i for i, line in enumerate(lines) if line.startswith('write(1, "HMS_SCAN_BEGIN\\n", 15)')]
    end = [i for i, line in enumerate(lines) if line.startswith('write(1, "HMS_SCAN_END\\n", 13)')]
    assert len(begin) == len(end) == 1 and begin[0] < end[0]
    phase = lines[begin[0] + 1:end[0]]
    stdout = (BASE / 'trace01' / (mode + '.stdout')).read_text().splitlines()
    assert stdout[:2] == ['HMS_SCAN_BEGIN', 'HMS_SCAN_END'] and len(stdout) == 3
    record = json.loads(stdout[2])
    assert record['result']['reason'] == reason and record['events'] == ['hms.retention.scan.v1']
    expected_root = str(BASE / 'attempt01' / 'production' / mode)
    live = set()
    opened = closed = entry_stats = 0
    for line in phase:
        name = line.split('(', 1)[0]
        if name == 'openat':
            match = re.fullmatch(r'openat\((AT_FDCWD|[0-9]+), "([^"\\]+)", ([A-Z_|]+)\)\s+= ([0-9]+)', line)
            assert match, line
            parent_fd, filename, flags, descriptor = match.groups()
            assert set(flags.split('|')) == {'O_RDONLY', 'O_NOFOLLOW', 'O_CLOEXEC', 'O_DIRECTORY'}
            if parent_fd == 'AT_FDCWD':
                assert filename == expected_root and opened == 0
            else:
                assert int(parent_fd) in live and filename == 'nested'
            fd = int(descriptor)
            assert fd not in live
            live.add(fd)
            opened += 1
        elif name == 'fstat':
            assert int(line.split('(', 1)[1].split(',', 1)[0]) in live
            assert 'st_mode=S_IFDIR|0700' in line and line.endswith('= 0')
        elif name == 'newfstatat':
            assert int(line.split('(', 1)[1].split(',', 1)[0]) in live
            assert 'AT_SYMLINK_NOFOLLOW)' in line and line.endswith('= 0')
            entry_stats += 1
        elif name == 'fcntl':
            match = re.fullmatch(r'fcntl\(([0-9]+), (F_GETFL|F_SETFD)(?:, (FD_CLOEXEC))?\)\s+= (.*)', line)
            assert match, line
            fd, operation, argument, result = match.groups()
            assert int(fd) in live
            if operation == 'F_GETFL':
                assert argument is None and 'O_DIRECTORY' in result
            else:
                assert argument == 'FD_CLOEXEC' and result == '0'
        elif name == 'getdents64':
            assert int(line.split('(', 1)[1].split(',', 1)[0]) in live
        elif name == 'getuid':
            assert re.fullmatch(r'getuid\(\)\s+= ' + str(os.getuid()), line)
        elif name == 'close':
            match = re.fullmatch(r'close\(([0-9]+)\)\s+= 0', line)
            assert match and int(match[1]) in live, line
            live.remove(int(match[1]))
            closed += 1
        elif name == 'brk':
            assert re.fullmatch(r'brk\(0x[0-9a-f]+\)\s+= 0x[0-9a-f]+', line)
        else:
            raise AssertionError(('unexpected native-phase syscall', line))
    assert not live and opened == closed
    assert (opened, entry_stats) == {'ordinary': (2, 4), 'fifo': (1, 1), 'veto': (0, 0)}[mode]
    if mode == 'veto':
        assert phase == []
    traces.append(dict(mode=mode, sha256=sha(path), wholeTraceLines=len(lines),
                       nativePhaseFirstLfLine=begin[0] + 2, nativePhaseLastLfLine=end[0],
                       nativeSyscalls=len(phase), openedDirectories=opened, closedDirectories=closed,
                       entryMetadataCalls=entry_stats, fileContentReadsInNativePhase=0))
receipt = dict(status='verified-isolated-native-binding', controls=counts, tracedScopes=traces,
               inputIndexSha256=sha(BASE / 'inputs.json'), binarySha256=build['binarySha256'],
               nativeSourceSha256=sha(BASE / 'scanmodule.c'),
               sourceInputsUnchanged=True, fixtureTraceMetadataUnchanged=True,
               originalWorkerStateTouched=False, qualificationWorkersLaunched=0,
               productionIntegrated=False, wholeWorkerTimingQualified=False,
               physicalProvidersAdded=False, separateInstrumentedBuild=True,
               syscallAuditScope='Three production marked scan phases; loader reads precede the phase',
               independentReviewer=False)
with (BASE / 'RESULTS.json').open('x') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
print(json.dumps(dict(status=receipt['status'], controls=counts, traces=len(traces))))
