"""Original finite process-interruption matrix; candidate sources stay exact."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys
import time

from chunk_store import ChunkStore, Native, _block_module
from readonly_image import ReadOnlyImage

HERE = Path(__file__).resolve().parent
WORK = Path.cwd()
CASES = {c['id']: c for c in json.loads((HERE/'cases.json').read_text())['cases']}
LIBRARY = Path(os.environ['HMS_CHUNK_LIBRARY'])
LIBRARY_HASH = os.environ['HMS_CHUNK_LIBRARY_SHA256']
KW = {'block_source': HERE/'fixed_block.py', 'library': LIBRARY, 'library_hash': LIBRARY_HASH}
STATE = {'armed': False, 'point': None, 'count': 0}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def process_identity(pid):
    body = Path('/proc', str(pid), 'stat').read_text()
    fields = body[body.rindex(')')+2:].split()
    return {'pid': pid, 'state': fields[0], 'startTicks': int(fields[19])}


def reopen(role):
    return ChunkStore.reopen(role/'image', read(role/'anchor.json'), **KW)


def create(role, identity):
    store = ChunkStore.create(role/'image', identity, **KW)
    save(role/'anchor.json', store.anchor)
    return store


def seed(case, role):
    identity = hashlib.sha256(('stage85:'+case['id']).encode()).hexdigest()[:32]
    store = create(role, identity)
    fixture = case['fixture']
    if fixture in {'one', 'two', 'tail'}:
        handle = store.open('data', create=True)
        store.pwrite(handle, b'A'*(4096 if fixture == 'one' else 8192), 0)
        if fixture == 'tail':
            store.truncate(handle, 2048)
        store.close_handle(handle)
    elif fixture == 'rename':
        for name, byte in [('source', b'S'), ('target', b'T')]:
            handle = store.open(name, create=True)
            store.pwrite(handle, byte*4096, 0)
            store.close_handle(handle)
    else:
        assert fixture == 'empty'
    store.close()


def snapshot(role, *, final=False):
    image = ReadOnlyImage(role)
    native = None
    try:
        native = Native(image, LIBRARY, LIBRARY_HASH)
        native.call('hm_mount')
        raw = native.read('state')
        envelope = json.loads(raw)
        assert set(envelope) == {'body', 'sha256'} and canonical(envelope) == raw
        body = envelope['body']
        assert envelope['sha256'] == hashlib.sha256(canonical(body)).hexdigest()
        assert body['profile'] == 'hms.chunk-store/0.1' and body['identity'] == image.anchor['identity']
        assert type(body['next']) is int and 1 <= body['next'] < 2**64
        assert type(body['inodes']) is list and len(body['inodes']) <= 16
        roots = set(native.list('/', 18))
        assert 'state' in roots
        directories = {}
        for root in roots-{'state', 'state.tmp'}:
            assert re.fullmatch('i[0-9a-f]{16}', root) and native.stat(root) == (2, 0)
            chunks = set(native.list(root, 4096))
            for chunk in chunks:
                assert re.fullmatch('c[0-9a-f]{8}', chunk)
                number = int(chunk[1:], 16)
                kind, size = native.stat(f'{root}/{chunk}')
                assert number < 4096 and kind == 1 and 0 <= size <= 4096
            directories[root] = chunks
        logical = {'next': body['next'], 'files': {}}
        unlinked = []
        unreferenced = []
        expected_dirs = set()
        ids = set()
        for inode in body['inodes']:
            assert set(inode) == {'id', 'name', 'size', 'chunks'}
            identity, size = inode['id'], inode['size']
            assert type(identity) is int and 1 <= identity < body['next'] and identity not in ids
            ids.add(identity)
            assert type(size) is int and 0 <= size <= 8192
            directory = f'i{identity:016x}'
            expected_dirs.add(directory)
            assert directory in directories
            bitmap = base64.b64decode(inode['chunks'], validate=True)
            assert len(bitmap) == 512 and base64.b64encode(bitmap).decode() == inode['chunks']
            numbers = [n for n in range(4096) if bitmap[n//8] & (1 << (n%8))]
            required = {f'c{n:08x}' for n in numbers}
            assert required <= directories[directory]
            data = bytearray(size)
            for number in numbers:
                assert number*4096 < size
                chunk = native.read(f'{directory}/c{number:08x}')
                assert len(chunk) == 4096
                amount = min(4096, size-number*4096)
                data[number*4096:number*4096+amount] = chunk[:amount]
            entry = {'id': identity, 'bytes': size, 'sha256': hashlib.sha256(data).hexdigest()}
            if inode['name'] is None:
                unlinked.append(entry)
            else:
                assert type(inode['name']) is str and inode['name'] not in logical['files']
                logical['files'][inode['name']] = entry
            unreferenced += [f'{directory}/{name}' for name in sorted(directories[directory]-required)]
        extras = sorted(set(directories)-expected_dirs)
        if final:
            assert not unlinked and not unreferenced and not extras and 'state.tmp' not in roots
        used = native.call('hm_used')
        assert native.fault is None
        assert all(native.counts[k] == 0 for k in ['programCalls', 'programBytes', 'erases', 'syncs'])
        image.stable()
        return {'logical': logical, 'unlinked': unlinked, 'unreferencedChunks': unreferenced,
                'extraDirectories': extras, 'stagingPresent': 'state.tmp' in roots,
                'namespaceSha256': hashlib.sha256(raw).hexdigest(), 'uniqueReachableBlocks': used,
                'backingFiles': image.before, 'readOnlyCallbacks': dict(native.counts),
                'imageUnchanged': True, 'recoveryInvoked': False}
    finally:
        if native is not None:
            native.dispose()
        image.close()


def clone(source, destination):
    source_image = ReadOnlyImage(source)
    target = None
    try:
        module = _block_module(HERE/'fixed_block.py', ChunkStore.BLOCK_HASH)
        anchor = module.create_image(destination/'image', source_image.anchor['identity'], 1)
        save(destination/'anchor.json', anchor)
        target = module.FixedBlockImage(destination/'image', anchor['identity'], 1, expected_objects=anchor['objects'])
        for block in range(4096):
            data = os.pread(source_image.fds['chunk-00'], 4096, block*4096)
            assert len(data) == 4096
            target.write(block, 0, data)
        target.sync()
        digest = sha(destination/'image/chunk-00')
        assert digest == source_image.before['chunk-00']
        assert source_image.anchor['objects']['chunk-00'] != anchor['objects']['chunk-00']
        source_image.stable()
        record = {'sourceRole': source.name, 'destinationRole': destination.name,
                  'logicalIdentity': anchor['identity'], 'bytesCopied': 16*1024**2,
                  'sourceFiles': source_image.before, 'copiedBlockSha256': digest,
                  'sourceObjects': source_image.anchor['objects'], 'destinationObjects': anchor['objects'],
                  'sourceUnchanged': True, 'fullyAllocated': True}
        save(destination/'clone.json', record)
    finally:
        if target is not None:
            target.close()
        source_image.close()


def event(phase, frame, native):
    if not STATE['armed'] or phase != STATE['point']['phase']:
        return
    STATE['count'] += 1
    if STATE['count'] != STATE['point']['ordinal']:
        return
    checkpoint = {'caseId': STATE['case']['id'], 'intentSha256': STATE['intentSha256'],
                  'point': STATE['point'], 'observedPhase': phase, 'observedOrdinal': STATE['count'],
                  'process': process_identity(os.getpid()), 'call': dict(frame),
                  'callbackCounts': dict(native.counts), 'beforeStopUnix': time.time()}
    save(WORK/'checkpoint.pending', checkpoint)
    os.rename(WORK/'checkpoint.pending', WORK/'checkpoint.json')
    fd = os.open(WORK, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    os.kill(os.getpid(), signal.SIGSTOP)
    raise AssertionError('stopped owner unexpectedly resumed instead of being killed')


def instrument():
    old_init, old_call = Native.__init__, Native.call

    def initialize(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        self.observation_frames = []

        def callback(kind):
            if not STATE['armed'] or not self.observation_frames:
                return
            frame = self.observation_frames[-1]
            if kind == 'program':
                frame['programCallbacksSeen'] += 1
            if kind == 'sync':
                frame['syncCallbacksSeen'] += 1
            if frame['name'] == 'hm_write' and kind == 'program' and frame['programCallbacksSeen'] == 2:
                event('stage-before-program-2' if frame['path'] == 'state.tmp' else 'chunk-before-program-2', frame, self)
            if frame['name'] == 'hm_rename' and kind == 'sync' and frame['syncCallbacksSeen'] == 1:
                event('rename-before-sync', frame, self)
        self.inject = callback

    def call(self, name, *args, **kwargs):
        path = args[0].decode() if args and isinstance(args[0], bytes) else None
        frame = {'name': name, 'path': path, 'programCallbacksSeen': 0, 'syncCallbacksSeen': 0}
        self.observation_frames.append(frame)
        try:
            result = old_call(self, name, *args, **kwargs)
            if name == 'hm_mkdir':
                event('directory-created', frame, self)
            elif name == 'hm_write':
                event('namespace-staged' if path == 'state.tmp' else 'chunk-written', frame, self)
            elif name == 'hm_rename' and path == 'state.tmp':
                event('namespace-published', frame, self)
            elif name == 'hm_remove' and path != 'state.tmp':
                event('chunk-removed' if '/' in path else 'directory-removed', frame, self)
            return result
        finally:
            self.observation_frames.pop()
    Native.__init__, Native.call = initialize, call


def owner(case, mode, cut_index):
    intent = WORK.parent/'operation-intent.json'
    assert read(intent)['case'] == case
    STATE.update(case=case, intentSha256=sha(intent), point=None if mode == 'final' else case['cuts'][cut_index])
    if mode != 'final':
        instrument()
    if mode == 'recover-cut':
        STATE['armed'] = True
        reopen(WORK)
        raise AssertionError('recovery checkpoint was not reached')
    store = reopen(WORK)
    if mode == 'final':
        logical = {'next': store.body['next'], 'files': {}}
        for inode in store.body['inodes']:
            assert inode['name'] is not None
            handle = store.open(inode['name'], writable=False)
            info = store.info(handle)
            data = store.pread(handle, 8192, 0)
            logical['files'][info['name']] = {'id': info['id'], 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            assert len(data) == info['size']
            store.close_handle(handle)
        assert logical in case['expected']
        counts = dict(store.native.counts)
        store.close()
        save(WORK/'recovered.json', {'caseId': case['id'], 'intentSha256': sha(intent),
                                    'logical': logical, 'callbacksBeforeClose': counts,
                                    'process': process_identity(os.getpid()), 'closed': True})
        return
    assert mode == 'operate'
    operation = case['operation']
    handle = None
    if operation == 'rename':
        store.open('source')
        store.open('target')
    elif operation != 'create':
        handle = store.open('data')
        if operation == 'close':
            store.unlink('data')
    save(WORK/'armed.json', {'caseId': case['id'], 'intentSha256': sha(intent),
                            'process': process_identity(os.getpid()), 'operation': operation,
                            'namespace': store.body, 'callbacks': dict(store.native.counts)})
    STATE['armed'] = True
    if operation == 'create':
        store.open('data', create=True, exclusive=True)
    elif operation == 'extend':
        store.pwrite(handle, b'B'*4096, 4096)
    elif operation == 'overwrite':
        store.pwrite(handle, b'B'*8192, 0)
    elif operation == 'shrink':
        store.truncate(handle, 2048)
    elif operation == 'grow':
        store.truncate(handle, 8192)
    elif operation == 'rename':
        store.rename('source', 'target')
    elif operation == 'unlink':
        store.unlink('data')
    elif operation == 'close':
        store.close_handle(handle)
    else:
        raise AssertionError('unknown operation')
    raise AssertionError('operation checkpoint was not reached')


def run_owner(case, role, mode, cut_index=0):
    argv = [sys.executable, '-B', str(Path(__file__).resolve()), 'owner', case['id'], mode, str(cut_index)]
    save(role/'owner-intent.json', {'argv': argv, 'cwd': str(role), 'mode': mode, 'cutIndex': cut_index,
                                  'wallSeconds': 15, 'cpuSeconds': 10, 'intentSha256': sha(WORK/'operation-intent.json')})
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    started_at = time.monotonic()
    failure = None
    code = None
    stopped = None
    pidfd = None
    with (role/'stdout.txt').open('xb') as out, (role/'stderr.txt').open('xb') as err:
        proc = subprocess.Popen(argv, cwd=role, stdout=out, stderr=err, preexec_fn=limits)
        try:
            pidfd = os.pidfd_open(proc.pid, 0)
            identity = process_identity(proc.pid)
            save(role/'owner-started.json', {**identity, 'unix': time.time(), 'pidfdOpened': True})
            deadline = started_at+15
            if mode == 'final':
                code = proc.wait(timeout=max(0.001, deadline-time.monotonic()))
                assert code == 0, f'final owner exited {code}'
            else:
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        raise AssertionError(f'owner exited before selected stop: {proc.returncode}')
                    if (role/'checkpoint.json').exists():
                        current = process_identity(proc.pid)
                        assert current['startTicks'] == identity['startTicks']
                        if current['state'] in {'T', 't'}:
                            stopped = current
                            break
                    time.sleep(0.01)
                if stopped is None:
                    raise TimeoutError('selected stopped checkpoint not observed')
                point = read(role/'checkpoint.json')
                assert point['process']['pid'] == proc.pid and point['process']['startTicks'] == identity['startTicks']
                assert point['caseId'] == case['id'] and point['point'] == case['cuts'][cut_index]
                assert point['intentSha256'] == sha(WORK/'operation-intent.json')
                assert point['observedPhase'] == point['point']['phase'] and point['observedOrdinal'] == point['point']['ordinal']
                save(role/'stopped.json', {**stopped, 'checkpointSha256': sha(role/'checkpoint.json'),
                                         'intentSha256': sha(WORK/'operation-intent.json')})
                signal.pidfd_send_signal(pidfd, signal.SIGKILL, None, 0)
                code = proc.wait(timeout=max(0.001, deadline-time.monotonic()))
                assert code == -signal.SIGKILL
        except BaseException as exc:
            failure = f'{type(exc).__name__}: {exc}'
            if proc.poll() is None:
                if pidfd is not None:
                    signal.pidfd_send_signal(pidfd, signal.SIGKILL, None, 0)
                else:
                    proc.kill()
                code = proc.wait(timeout=5)
            else:
                code = proc.returncode
        finally:
            if pidfd is not None:
                os.close(pidfd)
            out.flush()
            err.flush()
            os.fsync(out.fileno())
            os.fsync(err.fileno())
    result = {'mode': mode, 'returnCode': code, 'reaped': True,
              'selectedStopObserved': stopped is not None, 'error': failure,
              'elapsedSeconds': time.monotonic()-started_at}
    save(role/'owner-result.json', result)
    if failure:
        raise RuntimeError(failure)
    assert (role/'stderr.txt').stat().st_size == 0
    return result


def execute(case):
    assert hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal')
    started = time.monotonic()
    intent = {'schema': 'hms.chunk-interruption-intent/1', 'case': case,
              'librarySha256': LIBRARY_HASH, 'casesSha256': sha(HERE/'cases.json'),
              'originalAdapterSha256': sha(HERE/'chunk_store.py'),
              'backingBytesPerImage': 16*1024**2, 'retries': 0}
    save(WORK/'operation-intent.json', intent)
    original = WORK/'original'
    original.mkdir(mode=0o700)
    seed(case, original)
    save(original/'baseline.json', snapshot(original, final=True))
    run_owner(case, original, 'operate')
    original_snapshot = snapshot(original)
    save(original/'interrupted.json', original_snapshot)
    preserved = [(original, original_snapshot['backingFiles'])]
    current = original
    for index in range(1, len(case['cuts'])+1):
        next_role = WORK/f'recovery-{index}'
        next_role.mkdir(mode=0o700)
        clone(current, next_role)
        if index < len(case['cuts']):
            run_owner(case, next_role, 'recover-cut', index)
            cut_snapshot = snapshot(next_role)
            save(next_role/'interrupted.json', cut_snapshot)
            preserved.append((next_role, cut_snapshot['backingFiles']))
        else:
            run_owner(case, next_role, 'final')
            final_snapshot = snapshot(next_role, final=True)
            save(next_role/'final-readback.json', final_snapshot)
            recovered = read(next_role/'recovered.json')
            assert recovered['logical'] == final_snapshot['logical']
            assert final_snapshot['logical'] in case['expected']
        current = next_role
    for role, expected in preserved:
        for name, value in expected.items():
            assert sha(role/'image'/name) == value
    result = {'schema': 'hms.chunk-interruption-result/1', 'caseId': case['id'], 'status': 'passed',
              'intentSha256': sha(WORK/'operation-intent.json'), 'selectedInterruptions': len(case['cuts']),
              'retainedImages': len(case['cuts'])+1, 'finalRole': current.name,
              'logical': final_snapshot['logical'], 'interruptedSourcesUnchanged': True,
              'elapsedSeconds': time.monotonic()-started, 'physicalPowerLossTested': False,
              'sqliteTested': False, 'allMutationInterruptionsTested': False}
    save(WORK/'case-result.json', result)
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'case' and sys.argv[2] in CASES:
        execute(CASES[sys.argv[2]])
    elif len(sys.argv) == 5 and sys.argv[1] == 'owner' and sys.argv[2] in CASES and sys.argv[3] in {'operate', 'recover-cut', 'final'}:
        owner(CASES[sys.argv[2]], sys.argv[3], int(sys.argv[4]))
    else:
        raise SystemExit('explicit declared case or owner required')
