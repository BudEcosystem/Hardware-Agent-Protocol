"""Read-only retained image inspection; never invokes adapter recovery."""
import base64
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import stat

HERE = Path(__file__).resolve().parent
ATTEMPT = HERE/'attempt02'
SCOPES = ['semantics', 'namespace', 'recovery', 'accounting', 'caps', 'fault']


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


class ReadOnlyImage:
    block_count = 4096

    def __init__(self, work):
        self.root = work/'image'
        self.anchor = read(work/'anchor.json')
        self.fds = {}
        self.before = {}
        try:
            assert self.root.resolve(strict=True) == self.root
            assert {p.name for p in self.root.iterdir()} == {'owner', 'manifest', 'chunk-00'}
            for name in ['.', 'owner', 'manifest', 'chunk-00']:
                path = self.root/name
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
                if name == '.':
                    flags |= os.O_DIRECTORY
                fd = os.open(path, flags)
                self.fds[name] = fd
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                info = os.fstat(fd)
                named = path.stat(follow_symlinks=False)
                assert (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino) == tuple(self.anchor['objects'][name])
                assert info.st_uid == os.getuid()
                assert stat.S_IMODE(info.st_mode) == (0o700 if name == '.' else 0o600)
                if name != '.':
                    assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_blocks*512 >= info.st_size
                    self.before[name] = digest(path)
            assert os.fstat(self.fds['chunk-00']).st_size == 16*1024**2
            assert os.pread(self.fds['owner'], 34, 0) == (self.anchor['identity']+'\n').encode()
            raw = os.pread(self.fds['manifest'], 4096, 0)
            assert hashlib.sha256(raw).hexdigest() == self.anchor['manifestSha256']
        except BaseException:
            self.close()
            raise

    def read(self, block, offset, size):
        assert 0 <= block < self.block_count and 0 <= offset <= 4096 and 0 <= size <= 4096-offset
        assert offset % 16 == size % 16 == 0
        data = os.pread(self.fds['chunk-00'], size, block*4096+offset)
        assert len(data) == size
        return data

    def write(self, *unused):
        raise AssertionError('AUDIT_WRITE_FORBIDDEN')

    def erase(self, *unused):
        raise AssertionError('AUDIT_ERASE_FORBIDDEN')

    def sync(self):
        raise AssertionError('AUDIT_SYNC_FORBIDDEN')

    def stable(self):
        for name, expected in self.before.items():
            info = os.fstat(self.fds[name])
            named = (self.root/name).stat(follow_symlinks=False)
            assert (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino)
            assert digest(self.root/name) == expected

    def close(self):
        for fd in self.fds.values():
            os.close(fd)
        self.fds.clear()


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (512*1024**2, 512*1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16*1024**2, 16*1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    assert not (HERE/'image-readback.json').exists()
    report = read(ATTEMPT/'RESULTS.json')
    assert report['status'] == 'passed'
    assert sum(r['checks'] for r in report['scopes'].values()) == 54
    for name in ['compiler-version', 'build', *SCOPES]:
        result = read(ATTEMPT/name/'result.json')
        started = read(ATTEMPT/name/'started.json')
        assert result['returnCode'] == 0 and result['reaped'] and not result['timedOut']
        assert not Path('/proc', str(started['pid'])).exists()
    owner = read(ATTEMPT/'recovery/owner-started.json')
    assert read(ATTEMPT/'recovery/owner-result.json') == {'reaped': True, 'returnCode': 0}
    assert not Path('/proc', str(owner['pid'])).exists()
    original = read(HERE/'attempt01-preservation.json')
    for row in original['files']:
        path = HERE/'attempt01'/row['path']
        assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256']
    assert (HERE/'chunk_store.py').read_bytes() == (HERE/'attempt01/frozen-inputs/chunk_store.py').read_bytes() == (ATTEMPT/'frozen-inputs/chunk_store.py').read_bytes()
    assert (HERE/'controls.py').read_bytes() == (HERE/'attempt01/frozen-inputs/controls.py').read_bytes() == (ATTEMPT/'frozen-inputs/controls.py').read_bytes()
    frozen = ATTEMPT/'frozen-inputs/chunk_store.py'
    spec = importlib.util.spec_from_file_location('hms_readonly_chunk_bridge', frozen)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    library = ATTEMPT/'chunk-store.so'
    assert digest(library) == report['librarySha256']
    expected = bytearray(bytes(range(256))*32)
    expected[4090:4106] = b'X'*16
    expected = expected[:4100] + b'\0'*(12000-4100) + b'Z'
    references = {
        'semantics': {'data': bytes(expected)}, 'namespace': {'target': b'N'*4096},
        'recovery': {'live': b'L'*4096},
        'accounting': {'large': b'B'*4096+b'A'*(248*1024)+b'C'*4096},
        'caps': {'data': None, **{f'n{i}': b'' for i in range(15)}},
        'fault': {'data': bytes([read(ATTEMPT/'fault/checks.json')['details']['recoveredByte']])*4096}}
    assert references['fault']['data'] in {b'A'*4096, b'B'*4096}
    images = {}
    try:
        # Lock every image before inspection, including raw-only failed backing.
        for name in SCOPES:
            images[name] = ReadOnlyImage(ATTEMPT/name)
        images['failed-attempt01'] = ReadOnlyImage(HERE/'attempt01/semantics')
        inspected = []
        for name in SCOPES:
            image = images[name]
            native = module.Native(image, library, report['librarySha256'])
            try:
                native.call('hm_mount')
                raw = native.read('state')
                envelope = json.loads(raw)
                body = envelope['body']
                assert raw == canonical(envelope)
                assert envelope['sha256'] == hashlib.sha256(canonical(body)).hexdigest()
                assert body['profile'] == 'hms.chunk-store/0.1' and body['identity'] == image.anchor['identity']
                assert {r['name'] for r in body['inodes']} == set(references[name])
                roots = {'state'} | {f"i{r['id']:016x}" for r in body['inodes']}
                assert set(native.list('/', 18)) == roots
                payloads = []
                missing = []
                for inode in body['inodes']:
                    directory = f"i{inode['id']:016x}"
                    bitmap = base64.b64decode(inode['chunks'], validate=True)
                    assert len(bitmap) == 512
                    numbers = [n for n in range(4096) if bitmap[n//8] & (1 << (n%8))]
                    expected_names = {f'c{n:08x}' for n in numbers}
                    actual_names = set(native.list(directory, 4096))
                    assert actual_names <= expected_names
                    absent = sorted(expected_names-actual_names)
                    if absent:
                        assert name == 'caps' and inode['name'] == 'data' and absent == ['c00000000']
                        missing.append({'inode': inode['id'], 'name': inode['name'], 'chunks': absent})
                        continue
                    payload = bytearray(inode['size'])
                    assert len(payload) <= 256*1024
                    for number in numbers:
                        assert number*4096 < len(payload)
                        chunk = native.read(f'{directory}/c{number:08x}')
                        assert len(chunk) == 4096
                        amount = min(4096, len(payload)-number*4096)
                        payload[number*4096:number*4096+amount] = chunk[:amount]
                    assert bytes(payload) == references[name][inode['name']]
                    payloads.append({'inode': inode['id'], 'name': inode['name'], 'bytes': len(payload),
                                     'sha256': hashlib.sha256(payload).hexdigest(), 'chunks': len(numbers)})
                assert len(missing) == (1 if name == 'caps' else 0)
                used = native.call('hm_used')
                final = read(ATTEMPT/name/'checks.json')['details'].get('finalAccounting')
                if final:
                    assert used == final['uniqueReachableBlocks']
                assert native.fault is None
                assert all(native.counts[k] == 0 for k in ['programCalls', 'programBytes', 'erases', 'syncs'])
                inspected.append({'scope': name, 'payloads': payloads, 'knownMissingChunks': missing,
                                  'namespaceSha256': hashlib.sha256(raw).hexdigest(),
                                  'uniqueReachableBlocks': used, 'callbacks': native.counts,
                                  'backingFiles': image.before})
            finally:
                native.dispose()
        for image in images.values():
            image.stable()
        result = {'schema': 'hms.chunk-store-readonly-audit/1', 'status': 'verified',
                  'reviewer': 'primary agent only', 'readOnlyObjectLocksHeld': 28,
                  'passedImagesInspected': 6, 'failedImageHashOnly': True,
                  'originalAttemptFilesExact': len(original['files']), 'noImageBytesChanged': True,
                  'noRecoveryOrFormatInvoked': True, 'images': inspected,
                  'physicalPowerLossTested': False, 'sqliteTested': False}
        with (HERE/'image-readback.json').open('x') as f:
            json.dump(result, f, indent=2, sort_keys=True)
            f.write('\n')
        print(json.dumps({key: val for key, val in result.items() if key != 'images'}, sort_keys=True))
    finally:
        for image in images.values():
            image.close()


if __name__ == '__main__':
    main()
