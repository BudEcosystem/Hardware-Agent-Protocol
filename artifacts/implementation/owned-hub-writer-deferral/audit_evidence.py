"""Independent retained-data audit; imports no provider, worker or control code."""
import difflib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ATTEMPT = HERE/'writer-deferral-attempt01'
PUBLIC_SHA = 'dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
PARENTS = {'recovery': 'e97e4cf1ac3448f44b3ef2c1d3369da25f662dd72b337970c485b1dc245847fe',
           'guardian': 'fa94f2dac2c9f36fbe78a56e7c3a47fbb7ae5e76729827e3ab8028c3ccb3e91e'}


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def read(path):
    assert not path.is_symlink() and path.stat().st_size <= 2*1024**2
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
    for path in sorted(ATTEMPT.rglob('*')):
        assert not path.is_symlink()
        if path.is_file():
            result[str(path.relative_to(ATTEMPT))] = dict(bytes=path.stat().st_size, sha256=digest(path))
    assert len(result) < 200
    return result


def baselines():
    pins = read(HERE/'parent-pins.json'); indices = {}; counts = {}
    assert len(pins['parents']) == 2 and len(pins['files']) == 10
    for row in pins['parents']:
        folder = ROOT/row['path']; kind = row['kind']; index = read(folder/'index.json')
        assert digest(folder/'index.json') == digest(HERE/'baseline'/(kind+'-index.json')) == row['indexSha256'] == PARENTS[kind]
        entries = {item['path']: item for item in index['files']}
        assert len(entries) == len(index['files'])
        assert {str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file()} == set(entries)|{'index.json'}
        for name, item in entries.items():
            path = folder/name
            assert not path.is_symlink() and path.stat().st_size == item['bytes'] and digest(path) == item['sha256']
        indices[kind] = entries; counts[kind] = len(entries)
    assert counts == dict(recovery=510, guardian=143)
    for row in pins['files']:
        assert indices[row['parent']][row['source']]['sha256'] == digest(HERE/'baseline'/row['target']) == row['sha256']
    changes = read(HERE/'change-pins.json'); patch = []
    for row in changes['files']:
        name = row['path']; after = (HERE/name).read_bytes()
        assert len(after) == row['bytes'] and digest(HERE/name) == row['candidateSha256']
        before = b'' if row['parentSha256'] is None else (HERE/'baseline'/name).read_bytes()
        if row['parentSha256'] is not None:
            assert hashlib.sha256(before).hexdigest() == row['parentSha256']
        assert row['changed'] is (row['parentSha256'] is None or before != after)
        if row['changed']:
            patch.extend(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                         fromfile='/dev/null' if row['parentSha256'] is None else 'baseline/'+name,
                         tofile='candidate/'+name))
    assert ''.join(patch).encode() == (HERE/'source-diff.patch').read_bytes()
    assert digest(HERE/'source-diff.patch') == changes['sourceDiffSha256']
    public = ROOT/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
    assert digest(public) == PUBLIC_SHA
    baseline = read(public)
    assert baseline['passed'] is True and baseline['tests'] == 866 and len(baseline['files']) == 244
    assert all(digest(ROOT/row['path']) == row['sha256'] for row in baseline['files'])
    return counts


def main():
    before = snapshot(); parents = baselines(); intent = read(ATTEMPT/'intent.json')
    for name, pin in intent['sourcePins'].items():
        assert digest(HERE/name) == digest(ATTEMPT/'frozen'/name) == pin
    assert digest(Path(intent['executable'])) == intent['executableSha256']
    result = read(ATTEMPT/'RESULTS.json'); checks = read(ATTEMPT/'state/checks.json')
    assert result['passed'] is True and result['reason'] is None
    assert result['actualOwnerDeaths'] == result['deterministicHeldWriterDeferrals'] == 3
    assert result['sourceStable'] and result['sealedParentsStable'] and result['publicInputsExact'] == 244
    assert not result['adoptedAfterControlExit'] and not result['interruptsPendingAfterCleanup']
    assert not result['universalContainment'] and result['guardianAliveRequired']
    assert read(ATTEMPT/'stdout.txt') == result['control']
    assert result['control'] == dict(passed=True, cases=3, ownersKilled=3, normalLeaderExits=3,
                                   heldLeaseDeferrals=3, childrenReaped=9, subreaperRestored=True)
    assert not (ATTEMPT/'stderr.txt').read_bytes()
    outer = result['controlExit']; start = read(ATTEMPT/'started.json')
    assert outer['reaped'] is True and outer['exitCode'] == 0
    assert result['outerChildrenReaped'] == [outer]
    assert all(start[key] == outer[key] for key in ('pid','startTicks','parent','group','session'))
    reaped = []; cases = []; identities = {(outer['pid'], outer['startTicks'])}
    for name, exit_code in [('release',0),('eof',79),('guardian_stop',-9)]:
        folder = ATTEMPT/'state'/name
        checkpoint = read(folder/'checkpoint.json'); ready = read(folder/'writer-ready.json'); recovery = read(folder/'recovery.json')
        row = checkpoint['record']; request = row['request']; key = row['id']
        assert key == hashlib.sha256(b'HMS-OWNED-HOST-JOB-KEY-v1\0'+canonical(request['key'])).hexdigest()
        assert row['digest'] == 'sha256:'+hashlib.sha256(b'HMS-OWNED-HOST-JOB-REQUEST-v1\0'+canonical(request)).hexdigest()
        assert request['key'] == dict(caller='fixed-guardian', deployment='writer-deferral', operation=name)
        assert row['phase'] == 'released' and row['receipt'] is None and row['releaseIntent'] is True
        assert checkpoint['leaderNormalExitObserved'] and checkpoint['leaderRetainedUnreaped']
        assert recovery['before']['record'] == recovery['deferred']['record'] == row
        assert not recovery['heldReconcileChangedSlots'] and not recovery['historicalReplaySpawned']
        manifest = checkpoint['manifest']
        assert request['artifact'] == 'sha256:'+hashlib.sha256(b'HMS-INSTALLED-HOST-ARTIFACT-v1\0'+canonical(manifest)).hexdigest()
        assert manifest['installedTestMode'] == 'writer_barrier'
        fixture = manifest['installedFixture']; roles = fixture['roles']
        assert fixture['profile'] == 'hms.writer-barrier-installation/1'
        assert [(r['role'],r['access']) for r in roles] == [('writerHoldReader',0),('readyNoticeWriter',1)]
        assert len({(r['device'],r['inode']) for r in roles}) == 2
        assert all(digest(HERE/'provider-inputs'/path) == pin for path,pin in manifest['sources'].items())
        assert manifest['interpreter']['sha256'] == intent['executableSha256']
        assert manifest['helperBinary'] == digest(HERE/'provider-inputs/helper-check01/libowner-preconditions.so')
        assert manifest['helperSource'] == digest(HERE/'provider-inputs/owner_preconditions.c')
        assert ready['requestDigest'] == row['digest'] and ready['nonce'] == row['nonce']
        assert ready['artifact'] == request['artifact'] and ready['lease'] == row['lease']
        assert ready['originalLeader'] == row['pid'] == checkpoint['leader']['pid']
        writer = recovery['kernelSelectedWriter']
        assert all(ready['child'][k] == writer[k] for k in ready['child'])
        data = request['input']; assert data == dict(count=1000, first=-7, step=3)
        arithmetic = dict(count=data['count'],sumSquaresMod64=str(sum((data['first']+i*data['step'])**2 for i in range(data['count']))%(2**64)))
        assert ready['result'] == recovery['sourceKnownComputation'] == arithmetic
        for field in ('heldBeforeOwnerDeath','heldAfterOwnerDeath','heldAfterDeferredReconcile','freeAfterWriterReaped'):
            probe = recovery[field]
            assert {k:probe[k] for k in ('device','inode')} == row['lease']
            assert probe['independentlyOpened'] is True and probe['held'] is (field!='freeAfterWriterReaped')
        family = recovery['childrenReaped']; assert len(family) == 3
        assert [r['exitCode'] for r in family] == [-9,0,exit_code]
        assert all(r['reaped'] is True and r['parent'] == outer['pid'] for r in family)
        assert family[0]['pid'] == checkpoint['ownerPid'] and family[1] == recovery['normalLeaderExit']
        assert all(family[1][k] == checkpoint['leader'][k] for k in ('pid','startTicks','group','session'))
        assert all(family[2][k] == writer[k] for k in ('pid','startTicks','group','session','parent'))
        reaped += family; identities.update((r['pid'],r['startTicks']) for r in family)
        final = recovery['final']['record']; receipt = final['receipt']
        assert {k:v for k,v in final.items() if k not in ('phase','reason','receipt','history')} == {k:v for k,v in row.items() if k not in ('phase','reason','receipt','history')}
        assert final['phase'] == 'settled' and final['history'] == row['history']+['settled'] and final['reason'] == 'OWNER_LOST'
        assert receipt['execution'] == 'unknown' and receipt['mayHaveActed'] and receipt['recovered']
        assert receipt['writerLeaseQuiescent'] and receipt['resourceReleased'] and not receipt['outputValidated']
        assert receipt['result'] is None and receipt['processExitCode'] is None
        slots = []
        for number in (0,1):
            path = folder/'ledger'/('state.'+str(number)); envelope = read(path); state = envelope['state']
            assert canonical(envelope) == path.read_bytes() and envelope['sha256'] == hashlib.sha256(canonical(state)).hexdigest()
            assert state['generation'] == 4+number and state['generation']%2 == number
            assert state['profile'] == 'hms.host.cpu-ledger/0.1' and set(state['rows']) == {key}
            slots.append(state['rows'][key])
        assert slots == [row,final]
        fd = os.open(folder/'ledger'/('lease-'+key),os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600
            assert info.st_uid==os.getuid() and info.st_nlink==1 and info.st_size==0
            assert dict(device=info.st_dev,inode=info.st_ino)==row['lease']
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB); fcntl.flock(fd,fcntl.LOCK_UN)
        finally:
            os.close(fd)
        cases.append(dict(case=name, childrenReaped=3, finalExecution='unknown', heldLeaseObserved=True,
                          leaderExit=0, reconcileDeferred=True, replayedWithoutLaunch=True, writerExit=exit_code))
    assert checks['cases'] == cases and checks['reaped'] == reaped and len(identities) == 10
    for pid,tick in identities:
        path = Path('/proc')/str(pid)/'stat'
        try:
            tail = path.read_text().rsplit(')',1)[1].split()
        except FileNotFoundError:
            continue
        assert int(tail[19]) != tick, 'observed identity remains present, including zombies'
    assert snapshot() == before and baselines() == parents
    report = dict(passed=True, auditSourceSha256=digest(Path(__file__)), sourcePins=len(intent['sourcePins']),
                  sealedParentFiles=parents, publicInputsExact=244, cases=cases, canonicalAdjacentSlots=6,
                  independentArithmeticResults=3, retainedHeldLeaseObservations=9, retainedFreeLeaseObservations=3,
                  independentlyFreeMatchingLeases=3, familyReaps=9, outerReaps=1, observedIdentitiesAbsent=10,
                  retainedAttemptUnchanged=True, candidateCodeImported=False, providerJobsRerun=False,
                  scope='Retained-data joins and current free-lease probes; historical held probes come from the single original run.',
                  limitations=['Guardian must remain alive','No universal containment','No physical or GPU settlement',
                               'No aggregate storage qualification','No power-loss durability'], retainedFiles=before)
    with (HERE/'AUDIT.json').open('x') as target:
        json.dump(report,target,indent=2,sort_keys=True);target.write('\n');target.flush();os.fsync(target.fileno())
    print(json.dumps({k:v for k,v in report.items() if k!='retainedFiles'},sort_keys=True))


if __name__ == '__main__':
    main()
