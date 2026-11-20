"""Original read-only post-run audit; imports no candidate modules or workers."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ATTEMPTS = {'structural-attempt-1': 23, 'live-attempt-1': 94, 'faults-attempt-1': 92}


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def read(path):
    return json.loads(path.read_bytes())


def snapshot():
    return {str(p.relative_to(HERE)): digest(p)
            for name in ATTEMPTS for p in sorted((HERE/name).rglob('*')) if p.is_file()}


def main():
    before = snapshot(); identities = set(); records = []; controls = []
    checked_leases = 0; checked_results = 0; slot_count = 0; first_pins = None
    for name, count in ATTEMPTS.items():
        folder = HERE/name; result = read(folder/'RESULTS.json')
        assert result['passed'] and result['reaped'] and result['returnCode'] == 0
        assert result['reason'] is None and not result['remainingObservedLiveProcesses']
        assert not result['interruptsPendingAfterCleanup'] and not result['abnormalOwnerCrashQualified']
        assert result['sourceStable'] and result['publicBaselineStable'] and result['interpreterStable']
        assert result['control'] == read(folder/'control.stdout')
        assert result['control']['checks'] == count and not (folder/'control.stderr').read_bytes()
        assert read(folder/'process-result.json') == {k: v for k, v in result.items() if k not in (
            'sourceStable', 'publicBaselineStable', 'interpreterStable', 'interruptsPendingAfterCleanup')}
        pins = read(folder/'source-pins.json')
        if first_pins is None:
            first_pins = pins
        assert pins == first_pins
        assert all(digest(HERE/path) == digest(folder/'frozen'/path) == value for path, value in pins.items())
        assert read(folder/'interpreter-before.json') == read(folder/'interpreter-after.json')
        controls.append(dict(attempt=name, checks=count, elapsedSeconds=result['elapsedSeconds'],
                             resultSha256=digest(folder/'RESULTS.json')))
        identities.update((p['pid'], p['startTicks']) for p in result['observedProcesses'])
        rows_in_attempt = 0
        for directory in sorted((folder/'control-state').iterdir()):
            slots = []
            for path in sorted(directory.glob('state.[01]')):
                body = path.read_bytes(); envelope = json.loads(body)
                assert len(body) <= 65536 and canonical(envelope) == body
                assert set(envelope) == {'sha256', 'state'}
                state = envelope['state']; slot_count += 1
                assert hashlib.sha256(canonical(state)).hexdigest() == envelope['sha256']
                assert state['profile'] == 'hms.host.cpu-ledger/0.1'
                assert type(state['generation']) is int and state['generation'] % 2 == int(path.name[-1])
                assert len(state['rows']) <= 16
                slots.append(state)
            slots.sort(key=lambda state: state['generation'])
            assert len(slots) == 1 and slots[0]['generation'] == 0 or (
                len(slots) == 2 and slots[1]['generation'] == slots[0]['generation']+1)
            if directory.name == 'rollback':
                assert name == 'structural-attempt-1' and len(slots) == 2
                old, new = [next(iter(s['rows'].values())) for s in slots]
                assert old['phase'] == new['phase'] == 'admitted'
                assert old['nonce'] == 'a'*32 and new['nonce'] == 'c'*32
                assert {k: v for k, v in old.items() if k != 'nonce'} == {
                    k: v for k, v in new.items() if k != 'nonce'}
                continue  # Deliberately invalid successor; not an admitted execution ledger.
            if len(slots) == 2:
                old, new = slots[0]['rows'], slots[1]['rows']
                assert set(old) <= set(new)
                for key, prior in old.items():
                    current = new[key]
                    for field in ('id', 'request', 'digest', 'nonce', 'ownerSession'):
                        assert canonical(prior[field]) == canonical(current[field])
                    assert current['history'][:len(prior['history'])] == prior['history']
                    if prior['phase'] == 'settled':
                        assert canonical(prior) == canonical(current)
            for row in slots[-1]['rows'].values():
                rows_in_attempt += 1
                assert row['phase'] == 'settled' and row['history'][-1] == 'settled'
                assert len(canonical(row)) <= 3500
                request = row['request']; receipt = row['receipt']
                assert row['id'] == hashlib.sha256(b'HMS-OWNED-HOST-JOB-KEY-v1\0'+canonical(request['key'])).hexdigest()
                assert row['digest'] == 'sha256:'+hashlib.sha256(b'HMS-OWNED-HOST-JOB-REQUEST-v1\0'+canonical(request)).hexdigest()
                assert receipt['resourceReleased'] is True and receipt['writerLeaseQuiescent'] is True
                assert receipt['mayHaveActed'] is row['releaseIntent'] and receipt['reason'] == row['reason']
                if receipt['execution'] == 'completed':
                    assert receipt['outputValidated'] is True and not receipt['recovered']
                    assert type(receipt['processExitCode']) is int and receipt['processExitCode'] == 0
                    inp = request['input']; n = inp['count']; assert type(n) is int and n <= 1000
                    expected = sum((inp['first']+i*inp['step'])**2 for i in range(n)) % (1 << 64)
                    assert type(receipt['result']['count']) is int and receipt['result']['count'] == n
                    assert receipt['result']['sumSquaresMod64'] == str(expected)
                    checked_results += 1
                else:
                    assert receipt['result'] is None and receipt['outputValidated'] is False
                identities.update((p['pid'], p['startTicks']) for p in receipt['observedProcesses'])
                if row['lease'] is not None:
                    path = directory/('lease-'+row['id'])
                    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                    try:
                        info = os.fstat(fd)
                        assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                        assert info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == 0
                        assert row['lease'] == {'device': info.st_dev, 'inode': info.st_ino}
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        checked_leases += 1
                    finally:
                        os.close(fd)
                records.append(dict(attempt=name, fixture=directory.name, phase=row['phase'],
                    execution=receipt['execution'], releaseIntent=row['releaseIntent'], reason=row['reason'],
                    recovered=receipt['recovered'], observedProcesses=receipt['observedProcesses']))
        assert rows_in_attempt == (1 if name == 'structural-attempt-1' else 13)
    for pid, start in identities:
        try:
            fields = Path('/proc', str(pid), 'stat').read_bytes().rsplit(b')', 1)[1].split()
        except FileNotFoundError:
            continue
        assert int(fields[19]) != start, 'Original observed process still exists, including zombie'
    baseline = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(baseline) == 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
    public = read(baseline)['files']; assert len(public) == 244
    assert all(digest(ROOT/r['path']) == r['sha256'] for r in public)
    assert snapshot() == before
    result = dict(status='verified', controls=controls, checks=209, slotsChecked=slot_count,
        terminalRecords=len(records), liveAndFaultTerminalRecords=26, structuralTerminalFixtureRecords=1,
        intentionallyInvalidSuccessorFixtures=1, matchingFreeLeases=checked_leases,
        independentlySummedSuccessfulResults=checked_results,
        originalObservedProcessIdentitiesAbsent=len(identities), retainedAttemptBytesUnchanged=True,
        publicInputsExact=244, prior866TestsRerun=False, actualKilledOwnerQualified=False,
        completeDescendantEnumerationProven=False, aggregateCapacityQualified=False,
        records=records, retainedFiles=before)
    with (HERE/'ROOT-AUDIT.json').open('x') as target:
        json.dump(result, target, indent=2, sort_keys=True); target.write('\n')
        target.flush(); os.fsync(target.fileno())
    print(json.dumps({k: v for k, v in result.items() if k not in ('records', 'retainedFiles')}, sort_keys=True))


if __name__ == '__main__':
    main()
