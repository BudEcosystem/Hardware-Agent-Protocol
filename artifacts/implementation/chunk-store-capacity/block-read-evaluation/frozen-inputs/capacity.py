"""Original full-geometry preparation and host-capacity observations."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys

from chunk_store import ChunkStore, Native, NativeError, StorageError, _block_module
from readonly_image import ReadOnlyImage

HERE = Path(__file__).resolve().parent
WORK = Path.cwd()
CAP = Path(os.environ['HMS_CAPACITY_ROOT'])
LIBRARY = Path(os.environ['HMS_CHUNK_LIBRARY'])
LIBRARY_HASH = os.environ['HMS_CHUNK_LIBRARY_SHA256']
KW = {'block_source': HERE/'fixed_block.py', 'library': LIBRARY, 'library_hash': LIBRARY_HASH}
BULK_ID = '86'*16
CONTROL_ID = 'c6'*16
BYTES = 16*1024**2
CONTROL_BEFORE = b'before-bulk\n'
CONTROL_AFTER = CONTROL_BEFORE+b'after-bulk-full\nafter-bulk-missing\n'


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Ram:
    block_count = 4096

    def __init__(self, data, writable=False):
        assert len(data) == BYTES
        self.data = bytearray(data)
        self.writable = writable

    def bounds(self, block, offset, size):
        assert 0 <= block < 4096 and 0 <= offset <= 4096 and 0 <= size <= 4096-offset
        assert offset % 16 == size % 16 == 0
        return block*4096+offset

    def read(self, block, offset, size):
        start = self.bounds(block, offset, size)
        return bytes(self.data[start:start+size])

    def write(self, block, offset, data):
        assert self.writable
        start = self.bounds(block, offset, len(data))
        assert all((a & b) == b for a, b in zip(self.data[start:start+len(data)], data))
        self.data[start:start+len(data)] = data

    def erase(self, block):
        assert self.writable and 0 <= block < 4096
        self.data[block*4096:(block+1)*4096] = b'\xff'*4096

    def sync(self):
        assert self.writable


def finalize():
    preparation = read(CAP/'seed-build/stdout.txt')
    assert preparation['blockCount'] == 4096 and preparation['failureCode'] == -28
    count = preparation['safeChunks']
    assert 0 < count < preparation['successfulChunks'] < 4096
    ram = Ram((CAP/'seed-build/safe-before-namespace.bin').read_bytes(), writable=True)
    native = Native(ram, LIBRARY, LIBRARY_HASH)
    try:
        native.call('hm_mount')
        assert native.read('state') == b'seed-placeholder'
        entries = native.entries('i0000000000000001', 4096)
        assert len(entries) == count
        assert set(entries) == {(f'c{n:08x}', 1, 4096) for n in range(count)}
        bitmap = bytearray(512)
        for n in range(count):
            bitmap[n//8] |= 1 << (n%8)
        body = {'profile': 'hms.chunk-store/0.1', 'identity': BULK_ID, 'next': 2,
                'inodes': [{'id': 1, 'name': 'bulk', 'size': count*4096,
                            'chunks': base64.b64encode(bitmap).decode()}]}
        document = canonical({'body': body, 'sha256': hashlib.sha256(canonical(body)).hexdigest()})
        native.write('state.tmp', document)
        native.call('hm_rename', b'state.tmp', b'state')
        assert native.read('state') == document
        used = native.call('hm_used')
        assert count <= used <= 4096-16
        with (WORK/'seed.bin').open('xb') as f:
            os.posix_fallocate(f.fileno(), 0, BYTES)
            f.write(ram.data)
            f.flush()
            os.fsync(f.fileno())
        return {'status': 'finalized', 'baseChunks': count, 'logicalBytes': count*4096,
                'uniqueReachableBlocks': used, 'remainingBlockSlots': 4096-used,
                'seedSha256': sha(WORK/'seed.bin'), 'namespaceSha256': hashlib.sha256(document).hexdigest(),
                'ramOnly': True, 'callbacks': dict(native.counts)}
    finally:
        native.dispose()


def raw_to_image(raw, role, identity):
    role.mkdir(mode=0o700)
    module = _block_module(HERE/'fixed_block.py', ChunkStore.BLOCK_HASH)
    anchor = module.create_image(role/'image', identity, 1)
    save(role/'anchor.json', anchor)
    target = module.FixedBlockImage(role/'image', identity, 1, expected_objects=anchor['objects'])
    try:
        with raw.open('rb') as source:
            for block in range(4096):
                data = source.read(4096)
                assert len(data) == 4096
                target.write(block, 0, data)
            assert source.read(1) == b''
        target.sync()
        assert sha(role/'image/chunk-00') == sha(raw)
    finally:
        target.close()
    return anchor


def install():
    finalized = read(CAP/'seed-finalize/observation.json')
    verified = read(CAP/'seed-verify/stdout.txt')
    assert verified['status'] == 'verified' and verified['chunks'] == finalized['baseChunks']
    raw = CAP/'seed-finalize/seed.bin'
    assert sha(raw) == finalized['seedSha256']
    anchor = raw_to_image(raw, CAP/'bulk', BULK_ID)
    (CAP/'control').mkdir(mode=0o700)
    control = ChunkStore.create(CAP/'control/image', CONTROL_ID, **KW)
    save(CAP/'control/anchor.json', control.anchor)
    handle = control.open('continuation', create=True)
    control.pwrite(handle, CONTROL_BEFORE, 0)
    control.close_handle(handle)
    control.close()
    return {'status': 'installed', 'bulkAnchor': anchor, 'seedSha256': finalized['seedSha256'],
            'independentControlIdentity': CONTROL_ID, 'backingBytesPerDomain': BYTES}


def open_role(name):
    role = CAP/name
    return ChunkStore.reopen(role/'image', read(role/'anchor.json'), **KW)


def fill():
    base = read(CAP/'seed-finalize/observation.json')['baseChunks']
    store = open_role('bulk')
    handle = store.open('bulk')
    assert store.info(handle)['size'] == base*4096
    completed = 0
    failed = None
    original_call = store.native.call
    native_failure = []

    def traced(name, *args, **kwargs):
        try:
            return original_call(name, *args, **kwargs)
        except NativeError as exc:
            native_failure.append({'name': name, 'path': args[0].decode() if args and isinstance(args[0], bytes) else None,
                                   'code': exc.code})
            raise
    store.native.call = traced
    try:
        for number in range(64):
            offset = (base+completed)*4096
            intent = {'key': f'append-{number:02d}', 'identity': BULK_ID, 'offset': offset,
                      'bytes': 4096, 'payloadSha256': hashlib.sha256(b'B'*4096).hexdigest()}
            path = WORK/f'append-{number:02d}.intent.json'
            save(path, intent)
            try:
                amount = store.pwrite(handle, b'B'*4096, offset)
                assert amount == 4096
                completed += 1
                save(WORK/f'append-{number:02d}.result.json', {'intentSha256': sha(path), 'status': 'returned', 'bytes': amount})
            except NativeError as exc:
                assert exc.code == -28 and store.native.fault is None
                assert store.poisoned
                failed = {'intentSha256': sha(path), 'key': intent['key'], 'code': exc.code,
                          'nativeFailure': list(native_failure), 'inMemorySizeNotAuthoritative': store.body['inodes'][0]['size']}
                save(WORK/f'append-{number:02d}.result.json', {'status': 'error', **failed})
                break
        assert failed is not None, 'allocation exhaustion was not reached within the declared bound'
        counts = dict(store.native.counts)
        refusals = []
        for label, action in [('read', lambda: store.pread(handle, 1, 0)), ('write', lambda: store.pwrite(handle, b'X', 0))]:
            try:
                action()
            except StorageError as exc:
                assert str(exc) == 'POISONED'
                refusals.append(label)
            else:
                raise AssertionError('poisoned owner admitted work')
        assert store.native.counts == counts
        return {'status': 'observed', 'allocatorEnospc': True, 'baseChunks': base, 'completedAppends': completed,
                'failedAppend': failed, 'poisonRefusals': refusals, 'callbacks': counts,
                'hostEnospcInjected': False, 'geometryBlocks': 4096}
    finally:
        store.dispose()


def observe(role_name):
    role = CAP/role_name
    image = ReadOnlyImage(role)
    native = None
    try:
        raw = os.pread(image.fds['chunk-00'], BYTES, 0)
        assert len(raw) == BYTES
        native = Native(Ram(raw), LIBRARY, LIBRARY_HASH)
        native.call('hm_mount')
        document = native.read('state')
        envelope = json.loads(document)
        body = envelope['body']
        assert canonical(envelope) == document and envelope['sha256'] == hashlib.sha256(canonical(body)).hexdigest()
        assert body['profile'] == 'hms.chunk-store/0.1' and body['identity'] == image.anchor['identity']
        bulk = next(r for r in body['inodes'] if r['name'] == 'bulk')
        assert bulk['id'] == 1 and bulk['size'] % 4096 == 0
        count = bulk['size']//4096
        bitmap = base64.b64decode(bulk['chunks'], validate=True)
        assert len(bitmap) == 512
        assert {n for n in range(4096) if bitmap[n//8] & (1 << (n%8))} == set(range(count))
        entries = native.entries('i0000000000000001', 4096)
        names = {name: (kind, size) for name, kind, size in entries}
        for number in range(count):
            assert names[f'c{number:08x}'] == (1, 4096)
        fill_result = read(CAP/'bulk-fill/observation.json')
        confirmed = fill_result['baseChunks']+fill_result['completedAppends']
        assert count in {confirmed, confirmed+1}
        if role_name == 'bulk':
            assert body['next'] == 2 and len(body['inodes']) == 1
        else:
            assert body['next'] in {2, 3} and len(body['inodes']) in {1, 2}
            for inode in body['inodes']:
                if inode is not bulk:
                    assert inode['id'] == 2 and inode['name'] == 'metadata_new' and inode['size'] == 0
                    assert base64.b64decode(inode['chunks'], validate=True) == b'\0'*512
        used = native.call('hm_used')
        assert native.fault is None
        assert all(native.counts[k] == 0 for k in ['programCalls', 'programBytes', 'erases', 'syncs'])
        image.stable()
        return {'status': 'inspected', 'role': role_name, 'committedChunks': count,
                'confirmedBeforeError': confirmed, 'pendingAppendVisible': count == confirmed+1,
                'namespaceSha256': hashlib.sha256(document).hexdigest(), 'namespace': body,
                'unreferencedBulkChunks': sorted(set(names)-{f'c{n:08x}' for n in range(count)}),
                'rootEntries': native.entries('/', 18), 'uniqueReachableBlocks': used,
                'backingFiles': image.before, 'imageUnchanged': True, 'noRecoveryInvoked': True,
                'readOnlyCallbacks': dict(native.counts)}
    finally:
        if native is not None:
            native.dispose()
        image.close()


def control_after():
    full = read(CAP/'bulk-fill/observation.json')
    assert full['allocatorEnospc'] and full['failedAppend']['code'] == -28
    original = read(CAP/'bulk-observe/observation.json')['backingFiles']
    control = open_role('control')
    handle = control.open('continuation')
    assert control.pread(handle, 1024, 0) == CONTROL_BEFORE
    control.pwrite(handle, b'after-bulk-full\n', len(CONTROL_BEFORE))
    missing = CAP/'missing-bulk/image'
    assert not missing.exists()
    try:
        ChunkStore.reopen(missing, read(CAP/'bulk/anchor.json'), **KW)
    except FileNotFoundError as exc:
        missing_errno = exc.errno
        assert missing_errno == 2
    else:
        raise AssertionError('missing bulk path unexpectedly opened')
    control.pwrite(handle, b'after-bulk-missing\n', len(CONTROL_BEFORE)+len(b'after-bulk-full\n'))
    control.close_handle(handle)
    control.close()
    control = open_role('control')
    handle = control.open('continuation', writable=False)
    data = control.pread(handle, 1024, 0)
    assert data == CONTROL_AFTER
    control.close_handle(handle)
    control.close()
    for name, digest in original.items():
        assert sha(CAP/'bulk/image'/name) == digest
    return {'status': 'verified', 'controlBytes': len(data), 'controlSha256': hashlib.sha256(data).hexdigest(),
            'bulkFullWriteCompleted': True, 'missingBulkErrno': missing_errno, 'coldReadExact': True,
            'originalBulkUnchanged': True, 'reservedContinuationBytes': 0}


def clone_bulk():
    original = ReadOnlyImage(CAP/'bulk')
    try:
        source = CAP/'bulk/image/chunk-00'
        anchor = raw_to_image(source, CAP/'bulk-recovery', BULK_ID)
        original.stable()
        assert anchor['objects']['chunk-00'] != original.anchor['objects']['chunk-00']
        return {'status': 'copied', 'sourceFiles': original.before, 'sourceObjects': original.anchor['objects'],
                'destinationObjects': anchor['objects'], 'copySha256': sha(CAP/'bulk-recovery/image/chunk-00'),
                'bytesCopied': BYTES, 'originalUnchanged': True}
    finally:
        original.close()


def recover():
    original = read(CAP/'bulk-observe/observation.json')['backingFiles']
    store = None
    result = {'recoveryCompleted': False, 'metadataCreationCompleted': False, 'metadataEnospc': False}
    try:
        try:
            store = open_role('bulk-recovery')
            result['recoveryCompleted'] = True
        except NativeError as exc:
            assert exc.code == -28
            result['recoveryError'] = exc.code
        if store is not None:
            try:
                handle = store.open('metadata_new', create=True, exclusive=True)
                store.close_handle(handle)
                store.close()
                result['metadataCreationCompleted'] = True
            except NativeError as exc:
                assert exc.code == -28 and store.poisoned and store.native.fault is None
                result['metadataEnospc'] = True
                result['metadataError'] = exc.code
    finally:
        if store is not None:
            store.dispose()
    for name, digest in original.items():
        assert sha(CAP/'bulk/image'/name) == digest
    result.update(status='observed', originalBulkUnchanged=True, serviceRecoveryQualified=False)
    return result


if __name__ == '__main__':
    assert len(sys.argv) == 2
    modes = {'finalize': finalize, 'install': install, 'fill': fill,
             'observe-bulk': lambda: observe('bulk'), 'control-after': control_after,
             'clone-bulk': clone_bulk, 'recover': recover,
             'observe-recovery': lambda: observe('bulk-recovery')}
    assert sys.argv[1] in modes
    result = modes[sys.argv[1]]()
    save(WORK/'observation.json', result)
    print(json.dumps(result, sort_keys=True), flush=True)
