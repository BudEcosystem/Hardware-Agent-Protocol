"""Original finite behavioral controls against real allocated host block images."""
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

from chunk_store import ChunkStore, Reject, StorageError, CHUNK, MAX_FILE

HERE = Path(__file__).resolve().parent
LIBRARY = Path(os.environ['HMS_CHUNK_LIBRARY'])
KW = {'block_source': HERE/'fixed_block.py', 'library': LIBRARY,
      'library_hash': os.environ['HMS_CHUNK_LIBRARY_SHA256']}
WORK = Path.cwd()
CHECKS = []
DETAILS = {}


def save(name, value):
    with (WORK/name).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def refused(label, error, action, match):
    try:
        action()
    except error as exc:
        check(label, match in str(exc))
    else:
        raise AssertionError(f'{label}: not refused')


def create():
    store = ChunkStore.create(WORK/'image', '849ab52db0914ce8b9da01636c350001', **KW)
    save('anchor.json', store.anchor)
    return store


def reopen():
    return ChunkStore.reopen(WORK/'image', json.loads((WORK/'anchor.json').read_text()), **KW)


def read_all(store, handle):
    size = store.info(handle)['size']
    return b''.join(store.pread(handle, min(65536, size-pos), pos) for pos in range(0, size, 65536))


def finish(store):
    DETAILS['finalAccounting'] = store.accounting()
    for handle in list(store.handles):
        store.close_handle(handle)
    store.close()


def semantics():
    store = create()
    a = store.open('data', create=True, exclusive=True)
    b = store.open('data')
    original = bytes(range(256))*32
    check('write full two chunks', store.pwrite(a, original, 0) == len(original))
    check('existing descriptor sees data and size', read_all(store, b) == original)
    expected = bytearray(original)
    expected[4090:4106] = b'X'*16
    store.pwrite(b, b'X'*16, 4090)
    check('cross-chunk overwrite coherent in first descriptor', read_all(store, a) == expected)
    store.truncate(a, 4100)
    expected = expected[:4100]
    check('shrink visible through existing reader', read_all(store, b) == expected)
    store.truncate(b, 9000)
    expected += b'\0'*(9000-len(expected))
    check('regrowth never exposes truncated bytes', read_all(store, a) == expected)
    store.pwrite(a, b'Z', 12000)
    expected += b'\0'*(12000-len(expected)) + b'Z'
    check('sparse gap is zero and terminal byte exact', read_all(store, b) == expected)
    ro = store.open('data', writable=False)
    refused('read-only descriptor refuses mutation', Reject, lambda: store.pwrite(ro, b'Q', 0), 'READ_ONLY')
    store.close_handle(ro)
    refused('closed descriptor is stale', Reject, lambda: store.pread(ro, 1, 0), 'BAD_HANDLE')
    before = dict(store.native.counts)
    check('zero write beyond eof does not grow file', store.pwrite(a, b'', MAX_FILE) == 0 and store.info(a)['size'] == len(expected))
    check('zero write performs no storage callbacks', store.native.counts == before)
    check('pread beyond eof is empty', store.pread(b, 1, 20000) == b'')
    DETAILS['expectedDataSha256'] = hashlib.sha256(expected).hexdigest()
    finish(store)
    store = reopen()
    fresh = store.open('data')
    check('cold data matches full reference', read_all(store, fresh) == expected)
    refused('previous owner handle is stale after reopen', Reject, lambda: store.pread(a, 1, 0), 'BAD_HANDLE')
    finish(store)


def namespace():
    store = create()
    source = store.open('source', create=True)
    target = store.open('target', create=True)
    store.pwrite(source, b'S'*4096, 0)
    store.pwrite(target, b'T'*4096, 0)
    old_id = store.info(target)['id']
    store.rename('source', 'target')
    fresh = store.open('target')
    check('rename target resolves source inode', store.info(source)['id'] == store.info(fresh)['id'])
    check('open replaced target retains its own bytes', read_all(store, target) == b'T'*4096)
    check('replaced target remains tracked and unlinked', store.info(target)['name'] is None)
    store.unlink('target')
    new = store.open('target', create=True, exclusive=True)
    store.pwrite(new, b'N'*4096, 0)
    check('unlink recreate allocates a distinct inode', store.info(new)['id'] not in {old_id, store.info(source)['id']})
    check('old unlinked descriptors retain source data', read_all(store, fresh) == read_all(store, source) == b'S'*4096)
    store.pwrite(source, b'O', 0)
    check('unlinked descriptors stay mutually coherent', store.pread(fresh, 1, 0) == b'O')
    check('old writes do not affect recreated name', read_all(store, new) == b'N'*4096)
    before = store.accounting()['uniqueReachableBlocks']
    store.close_handle(target)
    check('last reference reclaims replaced target', all(r['id'] != old_id for r in store.body['inodes']))
    store.close_handle(source)
    check('remaining unlinked reference retains storage', store.info(fresh)['name'] is None)
    store.close_handle(fresh)
    check('both unlinked inodes reclaimed', len(store.body['inodes']) == 1)
    check('reclamation reduces reachable allocation', store.accounting()['uniqueReachableBlocks'] < before)
    finish(store)
    store = reopen()
    new = store.open('target')
    check('namespace survives cold reopen', read_all(store, new) == b'N'*4096 and len(store.body['inodes']) == 1)
    finish(store)


def owner_child():
    store = reopen()
    live = store.open('live', create=True)
    gone = store.open('gone', create=True)
    store.pwrite(live, b'L'*4096, 0)
    store.pwrite(gone, b'G'*4096, 0)
    store.unlink('gone')
    store.sync()
    save('owner-before-exit.json', {'pid': os.getpid(), 'live': store.info(live)['id'],
                                   'unlinked': store.info(gone)['id'], 'accounting': store.accounting()})
    # Deliberate exit with live descriptors and owner locks; no Python cleanup.
    os._exit(0)


def recovery():
    store = create()
    store.close()
    argv = [sys.executable, '-B', str(Path(__file__).resolve()), 'owner-child']
    save('owner-intent.json', {'argv': argv, 'wallSeconds': 20, 'cpuSeconds': 15,
                             'phase': 'exit after completed sync with linked and unlinked open handles'})
    def child_limits():
        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    with (WORK/'owner-stdout.txt').open('xb') as out, (WORK/'owner-stderr.txt').open('xb') as err:
        proc = subprocess.Popen(argv, stdout=out, stderr=err, preexec_fn=child_limits)
        save('owner-started.json', {'pid': proc.pid, 'unix': time.time()})
        code = proc.wait(timeout=20)
        save('owner-result.json', {'returnCode': code, 'reaped': True})
    check('actual owner exited and was reaped', code == 0 and proc.poll() == 0)
    check('owner emitted no errors', (WORK/'owner-stderr.txt').stat().st_size == 0)
    prior = json.loads((WORK/'owner-before-exit.json').read_text())
    store = reopen()
    live = store.open('live')
    check('linked data survives owner exit', read_all(store, live) == b'L'*4096)
    refused('unlinked name stays absent', Reject, lambda: store.open('gone'), 'NOT_FOUND')
    check('ownerless unlinked inode reclaimed', all(r['id'] != prior['unlinked'] for r in store.body['inodes']))
    check('orphan directory no longer reachable', store.native.stat(store._directory(prior['unlinked'])) is None)
    check('recovery allocation below retained pre-exit allocation', store.accounting()['uniqueReachableBlocks'] < prior['accounting']['uniqueReachableBlocks'])
    finish(store)


def accounting():
    store = create()
    handle = store.open('large', create=True)
    for off in range(0, 256*1024, 65536):
        store.pwrite(handle, b'A'*65536, off)
    before = store.accounting()
    check('logical size and distinct chunks accounted', before['logicalBytes'] == 256*1024 and len(store._present(store._fd(handle))) == 64)
    counts = dict(store.native.counts)
    store.pwrite(handle, b'B'*4096, 0)
    prefix = {key: store.native.counts[key]-counts[key] for key in counts}
    counts = dict(store.native.counts)
    store.pwrite(handle, b'C'*4096, 252*1024)
    tail = {key: store.native.counts[key]-counts[key] for key in counts}
    expected = b'B'*4096+b'A'*(248*1024)+b'C'*4096
    check('entire 256 KiB file matches intended changes', read_all(store, handle) == expected)
    check('prefix and tail each program less than whole logical file', 0 < prefix['programBytes'] < 256*1024 and 0 < tail['programBytes'] < 256*1024)
    check('real allocation exceeds logical payload and stays within image', before['logicalBytes'] < before['uniqueReachableBlocks']*4096 < before['backingBytes'])
    check('no continuation reservation claimed', before['reservedContinuationBytes'] == 0)
    DETAILS.update(prefix=prefix, tail=tail, before=before, expectedDataSha256=hashlib.sha256(expected).hexdigest())
    finish(store)


def caps():
    store = create()
    handle = store.open('data', create=True)
    store.pwrite(handle, b'D'*4096, 0)
    for number in range(15):
        h = store.open(f'n{number}', create=True)
        store.close_handle(h)
    before = dict(store.native.counts)
    refused('inode cap refuses before storage I/O', Reject, lambda: store.open('overflow', create=True), 'INODE_LIMIT')
    refused('maximum file offset enforced', Reject, lambda: store.pwrite(handle, b'X', MAX_FILE), 'FILE_LIMIT')
    refused('negative offset refused', Reject, lambda: store.pread(handle, 1, -1), 'INVALID_RANGE')
    refused('boolean offset refused', Reject, lambda: store.pread(handle, 1, True), 'INVALID_RANGE')
    refused('path traversal refused', Reject, lambda: store.open('../state'), 'INVALID_NAME')
    refused('oversized transfer refused', Reject, lambda: store.pwrite(handle, b'X'*65537, 0), 'INVALID_DATA')
    check('invalid requests perform no storage callbacks', store.native.counts == before)
    extra = [store.open('data') for unused in range(63)]
    refused('handle cap enforced', Reject, lambda: store.open('data'), 'HANDLE_LIMIT')
    for h in extra:
        store.close_handle(h)
    check('rejected requests leave valid handle usable', store.pread(handle, 1, 0) == b'D')
    # Explicit injected namespace corruption, not a naturally interrupted write.
    store.native.remove(store._path(store._fd(handle), 0))
    store.dispose()
    files_before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (WORK/'image').iterdir() if p.is_file()}
    refused('missing referenced chunk refuses recovery', StorageError, reopen, 'MISSING_REFERENCED_CHUNK')
    files_after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (WORK/'image').iterdir() if p.is_file()}
    check('failed validation makes no backing changes or format', files_before == files_after)
    DETAILS['injectedCorruption'] = 'removed an explicitly referenced chunk; image retained unavailable'


def fault():
    store = create()
    handle = store.open('data', create=True)
    store.pwrite(handle, b'A'*4096, 0)
    def fail(kind):
        if kind == 'sync':
            raise OSError('injected sync failure')
    store.native.inject = fail
    refused('sync failure reaches caller', StorageError, lambda: store.pwrite(handle, b'B'*4096, 0), 'LITTLEFS_')
    check('store poisoned after uncertain write', store.poisoned and store.native.fault is not None)
    before = dict(store.native.counts)
    refused('poisoned owner refuses reads', StorageError, lambda: store.pread(handle, 1, 0), 'POISONED')
    refused('poisoned owner refuses writes', StorageError, lambda: store.pwrite(handle, b'C', 0), 'POISONED')
    check('poison refusal performs no additional callbacks', store.native.counts == before)
    DETAILS['injectedFault'] = store.native.fault
    store.dispose()
    store = reopen()
    handle = store.open('data')
    data = read_all(store, handle)
    check('cold recovery has complete old or new single-chunk version', data in {b'A'*4096, b'B'*4096})
    DETAILS['recoveredByte'] = data[0]
    finish(store)


SCOPES = {'semantics': semantics, 'namespace': namespace, 'recovery': recovery,
          'accounting': accounting, 'caps': caps, 'fault': fault, 'owner-child': owner_child}
if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in SCOPES:
        raise SystemExit('explicit scope required')
    SCOPES[sys.argv[1]]()
    report = {'scope': sys.argv[1], 'status': 'passed', 'checks': CHECKS, 'details': DETAILS,
              'physicalPowerLossTested': False, 'sqliteTested': False, 'serviceStorageQualified': False}
    save('checks.json', report)
    print(json.dumps(report, sort_keys=True))
