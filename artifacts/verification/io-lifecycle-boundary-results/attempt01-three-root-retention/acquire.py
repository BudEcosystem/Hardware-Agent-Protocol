"""Acquire the already-terminal source12 attempt; never rerun project code."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import stat

ROOT = Path('/home/bud/Desktop/bud/hms')
BASE = Path(__file__).resolve().parent
SOURCE = ROOT / 'artifacts/implementation/io-lifecycle-settlement/review-inputs/12'
ATTEMPT = SOURCE / 'attempts/attempt01-boundary-three'
EXPECTED_RECEIPT = '855020fc64af4d779279824f6d0ffe09acf318293686ea0359849121338672c5'


def sha(path):
    assert not path.is_symlink() and path.is_file(), path
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(path):
    result = []
    for item in sorted(path.rglob('*')):
        assert not item.is_symlink(), item
        if item.is_file():
            result.append({'path': str(item.relative_to(path)), 'bytes': item.stat().st_size,
                           'sha256': sha(item)})
    return result


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


assert sha(ATTEMPT / 'result.json') == EXPECTED_RECEIPT
result = read(ATTEMPT / 'result.json')
assert result['currentPass'] is True and result['childState'] == 'exited' and result['exitCode'] == 0
assert result['counts'] == dict(testsRun=3, failures=0, errors=0, skips=0,
                                expectedFailures=0, unexpectedSuccesses=0)
for flag in ('inputsUnchanged', 'externalInputsUnchanged', 'runnerUnchanged',
             'rawScratchRetained', 'rawScratchIdentityUnchanged', 'rawScratchInventoryTerminal'):
    assert result[flag] is True, flag
assert result['errors'] == []
assert not Path('/proc', str(result['pid'])).exists(), 'Recorded child PID currently exists; inspect before proceeding'
assert read(ATTEMPT / 'inputs-before.json') == read(ATTEMPT / 'inputs-after.json')
assert read(ATTEMPT / 'external-before.json') == read(ATTEMPT / 'external-after.json')
for row in read(ATTEMPT / 'inputs-after.json'):
    path = ATTEMPT / 'project' / row['path']
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], path
for row in read(ATTEMPT / 'external-after.json'):
    path = Path(row['resolvedPath'])
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], path
for row in read(SOURCE / 'manifest.json')['files']:
    path = ROOT / row['copy']
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], path
selection = read(SOURCE / 'commands-12.json')['boundaryThree'][4:-1]
actual = re.findall(r'^(test_\w+) \(([^)]+)\) \.\.\. ok$',
                    (ATTEMPT / 'output.log').read_text(), re.M)
assert all(owner.endswith('.' + method) for method, owner in actual)
assert [owner for method, owner in actual] == selection == result['targets']
assert sha(ATTEMPT / 'run_attempt.py') == result['runnerSha256'] == sha(SOURCE / 'run_attempt.py')
assert sha(ATTEMPT / 'attempt_child.py') == result['childScriptSha256'] == sha(SOURCE / 'attempt_child.py')
origins = result['importReceipt']
assert origins['complete'] is True and origins['allProjectOriginsMatched'] is True
assert origins['violations'] == []

before = inventory(ATTEMPT)
shutil.copytree(ATTEMPT, BASE / 'attempt')
assert inventory(BASE / 'attempt') == before == inventory(ATTEMPT)
write(BASE / 'original-attempt-pins.json', before)
raw_record = read(ATTEMPT / 'raw-scratch-after.json')
raw = Path(result['rawScratchPath'])
info = raw.lstat()
identity = dict(path=str(raw), device=info.st_dev, inode=info.st_ino, uid=info.st_uid,
                gid=info.st_gid, mode=stat.S_IMODE(info.st_mode))
assert stat.S_ISDIR(info.st_mode) and not raw.is_symlink()
assert identity == raw_record['identity'] == raw_record['before']
assert inventory(raw) == []
shutil.copytree(raw, BASE / 'raw-scratch-copy')
assert inventory(raw) == inventory(BASE / 'raw-scratch-copy') == []
write(BASE / 'raw-acquisition.json', dict(identity=identity, originalRetained=True,
      copiedFiles=0, terminalChildPidAbsent=True, scope='External /tmp cleanup is not controlled.'))
references = BASE / 'references'
references.mkdir()
for name in ('manifest.json', 'targets-12.json', 'commands-12.json', 'REVISION-12.md'):
    shutil.copy2(SOURCE / name, references / name)
    assert sha(SOURCE / name) == sha(references / name)
captures = list((BASE / 'attempt/evidence').rglob('capture.json'))
assert len(captures) == 9 and len(inventory(BASE / 'attempt/evidence')) == 36
for path in captures:
    value = read(path)
    assert value['status'] == 'captured' and value['logicalSnapshot'] is True
    assert len(value['files']) == 2
    for row in value['files']:
        file = path.parent / row['path']
        assert file.stat().st_size == row['bytes'] and sha(file) == row['sha256']
write(BASE / 'acquisition.json', dict(profile='hms.root-terminal-result-acquisition/1',
      resultSha256=EXPECTED_RECEIPT, counts=result['counts'], exactMethodOrder=selection,
      originalAttemptFiles=len(before), sourceManifestFiles=210, projectInputs=156,
      selectedExternalInputs=159, actualOriginRecords=len(origins['records']),
      logicalSnapshots=9, evidenceFiles=36, unittestSeconds=33.295,
      outerSeconds=result['elapsedSeconds'], noRerun=True, originalRawRootRetained=True,
      scope='Root takeover after helper usage limit; independent result review was not sealed.'))
print(json.dumps(dict(acquiredFiles=len(before), snapshots=9, currentPass=True)))
