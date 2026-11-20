"""Independent retained-data audit. Imports no provider, control or worker code."""
import difflib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

HERE = Path(sys.argv[1]).resolve()
ROOT = HERE.parents[2]
COUNTS = dict(structural=23, live=102, faults=92, recovery=531, limits=50)
EXPECTED_ROWS = dict(structural=1, live=13, faults=13, recovery=33, limits=19)
PHASES = ('before_file_fsync', 'after_file_fsync', 'before_replace', 'after_replace',
          'before_directory_fsync', 'after_directory_fsync', 'before_publish', 'after_publish')
INTERRUPTS = ('none', 'before_reap', 'reaped', 'reaped_sigint')
PARENT_SHA = 'a0b6be34cab423581e8f9a80efd42791e17946cc96ff7e7e5226112e1273b229'
PUBLIC_SHA = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def read(path):
    assert path.stat().st_size <= 2*1024**2
    def pairs(items):
        result = {}
        for key, value in items:
            assert key not in result
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(AssertionError('nonfinite')))


def snapshot():
    result = {}
    for group in COUNTS:
        folder = HERE/(group+'-attempt-1')
        for path in sorted(folder.rglob('*')):
            assert not path.is_symlink()
            if path.is_file():
                result[str(path.relative_to(HERE))] = dict(bytes=path.stat().st_size, sha256=digest(path))
    assert len(result) <= 1500
    return result


def baselines():
    parent = HERE.parent/'owned-hub-jobs'
    assert digest(parent/'index.json') == digest(HERE/'baseline/index-parent.json') == PARENT_SHA
    index = read(parent/'index.json'); expected = {entry['path'] for entry in index['files']}
    assert len(expected) == 218
    actual = {str(path.relative_to(parent)) for path in parent.rglob('*') if path.is_file()}
    assert actual == expected | {'index.json'}
    for entry in index['files']:
        path = parent/entry['path']
        assert path.stat().st_size == entry['bytes'] and digest(path) == entry['sha256']
    original = read(HERE/'parent-pins.json')
    assert original['indexSha256'] == PARENT_SHA and len(original['files']) == 9
    indexed = {entry['path']: entry for entry in index['files']}
    for entry in original['files']:
        assert indexed[entry['path']]['sha256'] == entry['sha256']
        assert digest(HERE/'baseline'/entry['path']) == entry['sha256']
    changes = read(HERE/'change-pins.json'); patch = []
    assert changes['parentIndexSha256'] == PARENT_SHA and len(changes['files']) == 13
    for entry in changes['files']:
        name = entry['path']; after = (HERE/name).read_bytes()
        assert len(after) == entry['bytes'] and hashlib.sha256(after).hexdigest() == entry['candidateSha256']
        before = b'' if entry['parentSha256'] is None else (HERE/'baseline'/name).read_bytes()
        if entry['parentSha256'] is not None:
            assert hashlib.sha256(before).hexdigest() == entry['parentSha256']
        assert entry['changed'] is (entry['parentSha256'] is None or before != after)
        if entry['changed']:
            patch.extend(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                fromfile='/dev/null' if entry['parentSha256'] is None else 'baseline/'+name,
                tofile='candidate/'+name))
    assert ''.join(patch).encode() == (HERE/'source-diff.patch').read_bytes()
    assert digest(HERE/'source-diff.patch') == changes['sourceDiffSha256']
    public = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(public) == PUBLIC_SHA
    receipt = read(public); assert len(receipt['files']) == 244 and receipt['tests'] == 866
    assert all(digest(ROOT/item['path']) == item['sha256'] for item in receipt['files'])


def integer(value, low, high):
    assert type(value) is int and low <= value <= high


def row_shape(row):
    assert set(row) == {'id', 'request', 'digest', 'nonce', 'phase', 'history', 'lease',
                        'ownerSession', 'pid', 'releaseIntent', 'cancelRequested', 'reason', 'receipt'}
    assert len(canonical(row)) <= 3500
    request = row['request']
    assert set(request) == {'profile', 'key', 'artifact', 'input', 'limits'}
    assert request['profile'] == 'hms.host.cpu-series/0.1'
    assert set(request['key']) == {'deployment', 'caller', 'operation'}
    assert all(type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,47}', value)
               for value in request['key'].values())
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', request['artifact'])
    assert row['id'] == hashlib.sha256(b'HMS-OWNED-HOST-JOB-KEY-v1\0'+canonical(request['key'])).hexdigest()
    assert row['digest'] == 'sha256:'+hashlib.sha256(b'HMS-OWNED-HOST-JOB-REQUEST-v1\0'+canonical(request)).hexdigest()
    assert set(request['input']) == {'first', 'step', 'count'}
    for name, limits in dict(first=(-(2**31), 2**31-1), step=(-32768,32767), count=(0,50_000_000)).items():
        integer(request['input'][name], *limits)
    ceilings = dict(cpuSeconds=(1,5), addressBytes=(64*1024**2,256*1024**2), fileBytes=(1,4096),
        openFiles=(16,32), wallMs=(100,10000), stopGraceMs=(1,500), settleGraceMs=(1,2000), streamBytes=(128,4096))
    assert set(request['limits']) == set(ceilings)
    for name, limits in ceilings.items():
        integer(request['limits'][name], *limits)
    for name in ('nonce','ownerSession'):
        assert re.fullmatch(r'[0-9a-f]{32}', row[name])
    allowed = dict(admitted={'launching','settled'}, launching={'associated','stopping','settled'},
        associated={'released','stopping','settled'}, released={'stopping','settled'}, stopping={'settled'}, settled=set())
    history = row['history']
    assert 1 <= len(history) <= 6 and history[0] == 'admitted' and history[-1] == row['phase']
    assert all(right in allowed[left] for left,right in zip(history,history[1:]))
    assert type(row['cancelRequested']) is bool and row['releaseIntent'] is ('released' in history)
    assert (row['lease'] is not None) is ('launching' in history)
    assert (row['pid'] is not None) is ('associated' in history)
    assert (row['receipt'] is not None) is (row['phase'] == 'settled')
    if row['pid'] is not None:
        integer(row['pid'],1,2**31-1)


def main():
    baselines(); before = snapshot(); controls = []; records = []; identities = set()
    leases = sums = slots_count = 0; first_pins = None; latest = {}
    for group, count in COUNTS.items():
        folder = HERE/(group+'-attempt-1'); result = read(folder/'RESULTS.json')
        assert result['passed'] is True and result['reaped'] is True and result['returnCode'] == 0
        assert result['reason'] is None and result['remainingObservedLiveProcesses'] == []
        assert result['interruptsPendingAfterCleanup'] == [] and result['abnormalOwnerCrashQualified'] is False
        assert all(result[field] is True for field in ('sourceStable','publicBaselineStable','interpreterStable','sealedParentStable'))
        assert result['control'] == read(folder/'control.stdout') and result['control']['checks'] == count
        assert not (folder/'control.stderr').read_bytes()
        extras = {'sourceStable','publicBaselineStable','interpreterStable','sealedParentStable','interruptsPendingAfterCleanup'}
        assert read(folder/'process-result.json') == {k:v for k,v in result.items() if k not in extras}
        pins = read(folder/'source-pins.json')
        if first_pins is None:
            first_pins = pins
        assert pins == first_pins
        assert all(digest(HERE/path) == digest(folder/'frozen'/path) == sha for path,sha in pins.items())
        assert read(folder/'interpreter-before.json') == read(folder/'interpreter-after.json')
        for phase in ('before','after'):
            assert read(folder/('public-'+phase+'.json'))['passed'] is True
            parent = read(folder/('parent-'+phase+'.json'))
            assert parent['passed'] is True and parent['matching'] == parent['files'] == 218
        identities.update((p['pid'],p['startTicks']) for p in result['observedProcesses'])
        controls.append(dict(group=group, checks=count, elapsedSeconds=result['control']['elapsedSeconds'],
                             resultSha256=digest(folder/'RESULTS.json')))
        row_count = 0
        for directory in sorted((folder/'control-state').iterdir()):
            if not directory.is_dir():
                assert group in ('recovery','limits') and directory.name == 'observations.json'
                continue
            slots = []
            for path in sorted(directory.glob('state.[01]')):
                raw = path.read_bytes(); envelope = read(path); slots_count += 1
                assert len(raw) <= 65536 and canonical(envelope) == raw
                assert set(envelope) == {'state','sha256'}
                state = envelope['state']
                assert hashlib.sha256(canonical(state)).hexdigest() == envelope['sha256']
                assert set(state) == {'profile','generation','rows'} and state['profile'] == 'hms.host.cpu-ledger/0.1'
                integer(state['generation'],0,2**63-1)
                assert state['generation'] % 2 == int(path.name[-1]) and len(state['rows']) <= 16
                for name,row in state['rows'].items():
                    row_shape(row); assert name == row['id']
                slots.append(state)
            slots.sort(key=lambda state:state['generation'])
            assert len(slots) == 1 and slots[0]['generation'] == 0 or len(slots) == 2 and slots[1]['generation'] == slots[0]['generation']+1
            if directory.name == 'rollback':
                assert group == 'structural'
                old,new = [next(iter(state['rows'].values())) for state in slots]
                assert old['nonce'] == 'a'*32 and new['nonce'] == 'c'*32 and old['phase'] == new['phase'] == 'admitted'
                assert {k:v for k,v in old.items() if k!='nonce'} == {k:v for k,v in new.items() if k!='nonce'}
                continue
            if len(slots) == 2:
                old,new = slots[0]['rows'],slots[1]['rows']; assert set(old) <= set(new)
                for name,previous in old.items():
                    current = new[name]
                    for field in ('id','request','digest','nonce','ownerSession'):
                        assert canonical(previous[field]) == canonical(current[field])
                    assert current['history'][:len(previous['history'])] == previous['history']
                    assert not previous['releaseIntent'] or current['releaseIntent']
                    assert not previous['cancelRequested'] or current['cancelRequested']
                    if previous['phase'] == 'settled':
                        assert previous == current
            rows = list(slots[-1]['rows'].values()); latest[(group,directory.name)] = rows
            if not rows:
                assert group == 'faults' and directory.name == 'sigchld-refusal'
            for row in rows:
                row_count += 1; receipt = row['receipt']; assert row['phase'] == 'settled'
                assert receipt['resourceReleased'] is True and receipt['writerLeaseQuiescent'] is True
                assert receipt['mayHaveActed'] is row['releaseIntent'] and receipt['reason'] == row['reason']
                if receipt['execution'] == 'completed':
                    assert receipt['outputValidated'] is True and receipt['recovered'] is False
                    assert type(receipt['processExitCode']) is int and receipt['processExitCode'] == 0
                    inp = row['request']['input']; n=inp['count']; assert n<=1000
                    expected = sum((inp['first']+i*inp['step'])**2 for i in range(n)) % (1<<64)
                    assert type(receipt['result']['count']) is int and receipt['result']['count'] == n
                    assert receipt['result']['sumSquaresMod64'] == str(expected); sums += 1
                else:
                    assert receipt['result'] is None and receipt['outputValidated'] is False
                identities.update((p['pid'],p['startTicks']) for p in receipt['observedProcesses'])
                if row['lease'] is not None:
                    fd = os.open(directory/('lease-'+row['id']), os.O_RDONLY|os.O_NOFOLLOW)
                    try:
                        info=os.fstat(fd)
                        assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600
                        assert info.st_uid==os.getuid() and info.st_nlink==1 and info.st_size==0
                        assert row['lease']==dict(device=info.st_dev,inode=info.st_ino)
                        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB); leases += 1
                    finally:
                        os.close(fd)
                records.append(dict(group=group,fixture=directory.name,key=row['request']['key'],
                    execution=receipt['execution'],reason=row['reason'],recovered=receipt['recovered']))
        assert row_count == EXPECTED_ROWS[group]
    observations = read(HERE/'recovery-attempt-1/control-state/observations.json')
    assert observations[0] == dict(case='terminal-reconcile',retainedHandleReleased=True,terminalReceiptUnchanged=True)
    combinations = {(entry['boundary'],entry['interruption']):entry for entry in observations[1:]}
    assert len(observations)==33 and set(combinations)=={(p,i) for p in PHASES for i in INTERRUPTS}
    for (phase,interrupt),entry in combinations.items():
        committed = phase not in PHASES[:3]
        expected = 'completed' if committed else 'unknown'
        assert entry['reopenedExecution']==expected and entry['recovered'] is (not committed)
        assert entry['retainedHandlesSettled'] is True and entry['poisonedFreshLaunchRefused'] is True
        assert entry['caught']==('OSError' if interrupt=='none' else 'KeyboardInterrupt' if interrupt=='reaped_sigint' else 'JobError')
        row, = latest[('recovery',phase+'-'+interrupt)]; receipt=row['receipt']
        assert row['releaseIntent'] is True and receipt['execution']==expected and receipt['recovered'] is (not committed)
        if not committed:
            assert receipt['processExitCode'] is None and receipt['observedLiveGroupMembers'] is None
            assert receipt['streamEof'] is None and receipt['observedProcesses']==[] and row['reason']=='OWNER_LOST'
    limits = read(HERE/'limits-attempt-1/control-state/observations.json')
    assert [entry['case'] for entry in limits]==['bootstrap','wall-after-release','cpu-hard-limit','retention']
    boot, = latest[('limits','bootstrap')]
    assert boot['receipt']['execution']=='not_started' and boot['releaseIntent'] is False
    assert boot['receipt']['processExitCode']==74 and boot['reason']=='BOOTSTRAP_EXIT'
    wall, = latest[('limits','wall-after-release')]
    assert wall['receipt']['execution']=='failed' and wall['releaseIntent'] is True and wall['reason']=='WALL_LIMIT'
    cpu, = latest[('limits','cpu-hard-limit')]
    assert cpu['receipt']['execution']=='failed' and cpu['receipt']['processExitCode']==76 and cpu['reason']=='PROCESS_FAILED'
    diagnostic=limits[2]['diagnostic']
    assert diagnostic['childSignal']==9 and .8 <= diagnostic['childCpuSeconds'] <= 2
    assert limits[2]['childReapedByInstalledLeader'] is True
    retained=latest[('limits','retention')]
    assert len(retained)==16 and {row['request']['key']['operation'] for row in retained}=={'retained-'+str(i) for i in range(16)}
    assert all(row['receipt']['execution']=='completed' for row in retained)
    assert limits[3]==dict(case='retention',historicalReplays=16,retained=16,seventeenthRefused=True)
    for pid,start in identities:
        try:
            fields=Path('/proc',str(pid),'stat').read_bytes().rsplit(b')',1)[1].split()
        except FileNotFoundError:
            continue
        assert int(fields[19])!=start, 'An original observed process still exists, including zombie'
    baselines(); assert snapshot()==before
    report=dict(status='verified',controls=controls,observedChecks=sum(COUNTS.values()),
        slotsChecked=slots_count,terminalRecords=len(records),terminalByGroup=EXPECTED_ROWS,
        faultCombinationsVerified=32,preReplaceUnknown=12,postReplaceRetainedCompleted=20,
        matchingFreeLeases=leases,independentlySummedSuccessfulResults=sums,
        originalObservedProcessIdentitiesAbsent=len(identities),cpuDiagnostic=diagnostic,
        retainedAttemptBytesUnchanged=True,publicInputsExact=244,sealedParentFilesExact=218,
        originalCopiesExact=9,sourceDiffRecomputed=True,prior866TestsRerun=False,
        actualKilledOwnerQualified=False,completeDescendantEnumerationProven=False,
        records=records,retainedFiles=before)
    with (HERE/'AUDIT.json').open('x') as target:
        json.dump(report,target,indent=2,sort_keys=True);target.write('\n');target.flush();os.fsync(target.fileno())
    print(json.dumps({key:value for key,value in report.items() if key not in ('records','retainedFiles')},sort_keys=True))


if __name__=='__main__':
    main()
