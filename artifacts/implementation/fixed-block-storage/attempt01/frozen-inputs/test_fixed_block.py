"""Retained real-file controls; explicit syscall injections are named as such."""
import errno
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

import fixed_block as bd

WORK = Path(os.environ['HMS_BLOCK_TEST_ROOT'])
IDENTITY = '81c1eac92d04468e8ad8e28f9fc36477'
CONTROL_ID = 'b50f1ecc80b64c498af24889ea159c097'


def note(kind, **data):
    with (WORK / 'observations.jsonl').open('a') as stream:
        stream.write(json.dumps({'kind': kind, **data}, sort_keys=True) + '\n')


class BlockImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_path = WORK / 'main'
        cls.control_path = WORK / 'control'
        cls.main_receipt = bd.create_image(cls.main_path, IDENTITY, 2)
        cls.control_receipt = bd.create_image(cls.control_path, CONTROL_ID, 1)
        (WORK / 'creation.json').write_text(json.dumps({
            'main': cls.main_receipt, 'control': cls.control_receipt}, indent=2) + '\n')

    def main(self):
        return bd.FixedBlockImage(self.main_path, IDENTITY, 2,
                                  expected_objects=self.main_receipt['objects'])

    def control(self):
        return bd.FixedBlockImage(self.control_path, CONTROL_ID, 1,
                                  expected_objects=self.control_receipt['objects'])

    def error(self, code, call):
        with self.assertRaisesRegex(bd.ImageError, '^' + code + '$'):
            call()

    def test_01_complete_initialization_and_fixed_geometry(self):
        expected = hashlib.sha256(b'\xff' * bd.CHUNK_BYTES).hexdigest()
        for root, count in [(self.main_path, 2), (self.control_path, 1)]:
            for number in range(count):
                p = root / f'chunk-{number:02d}'
                with p.open('rb') as stream:
                    self.assertEqual(hashlib.file_digest(stream, 'sha256').hexdigest(), expected)
                self.assertEqual(p.stat().st_size, bd.CHUNK_BYTES)
                self.assertGreaterEqual(p.stat().st_blocks * 512, bd.CHUNK_BYTES)
        with self.main() as image:
            self.assertEqual(image.block_count, 8192)
            self.assertEqual(image.read(0, 0, 16), b'\xff' * 16)
            self.assertEqual(image.read(8191, 4080, 16), b'\xff' * 16)
        note('initialization', chunks=3, bytes=3 * bd.CHUNK_BYTES)

    def test_02_invalid_ranges_do_no_io(self):
        with self.main() as image, patch.object(bd.os, 'pread') as read, patch.object(bd.os, 'pwrite') as write:
            for args in [(-1, 0, 16), (8192, 0, 16), (True, 0, 16), (1, -16, 16),
                         (1, 4096, 16), (1, 0, 4097), (1, 1, 16), (1, 0, 17)]:
                self.error('INVALID_RANGE', lambda args=args: image.read(*args))
            for block, offset, data in [(8192, 0, b'x' * 16), (1, 4096, b'x' * 16),
                                         (-1, 0, b''), (1, 0, b'x' * 17)]:
                self.error('INVALID_RANGE', lambda: image.write(block, offset, data))
            self.error('INVALID_DATA', lambda: image.write(0, 0, bytearray(16)))
            read.assert_not_called()
            write.assert_not_called()
        with self.main() as image:
            self.assertEqual(image.read(0, 0, 16), b'\xff' * 16)

    def test_03_cross_chunk_edges_preserve_neighbors(self):
        with self.main() as image:
            image.write(4095, 4080, b'A' * 16)
            image.write(4096, 0, b'B' * 16)
            self.assertEqual(image.read(4095, 4064, 32), b'\xff' * 16 + b'A' * 16)
            self.assertEqual(image.read(4096, 0, 32), b'B' * 16 + b'\xff' * 16)
            image.write(8191, 4080, b'Z' * 16)
            image.sync()
        self.assertTrue(all((self.main_path / f'chunk-{i:02d}').stat().st_size == bd.CHUNK_BYTES for i in range(2)))

    def test_04_positional_io_ignores_descriptor_cursor(self):
        with self.main() as image:
            fd = image._fds['chunk-00']
            os.lseek(fd, bd.CHUNK_BYTES, os.SEEK_SET)
            image.write(7, 0, b'P' * 16)
            self.assertEqual(image.read(7, 0, 16), b'P' * 16)
            self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), bd.CHUNK_BYTES)
            image.sync()

    def test_05_injected_positive_short_reads_complete(self):
        real = os.pread
        calls = []
        def short(fd, size, offset):
            calls.append(size)
            return real(fd, min(size, 7), offset)
        with self.main() as image, patch.object(bd.os, 'pread', short):
            self.assertEqual(image.read(7, 0, 16), b'P' * 16)
        self.assertGreater(len(calls), 3)
        note('injected-short-read', calls=len(calls))

    def test_06_injected_positive_short_writes_complete(self):
        real = os.pwrite
        calls = []
        def short(fd, data, offset):
            calls.append(len(data))
            return real(fd, data[:7], offset)
        with self.main() as image:
            with patch.object(bd.os, 'pwrite', short):
                image.write(8, 0, b'S' * 64)
            self.assertEqual(image.read(8, 0, 64), b'S' * 64)
            image.sync()
        self.assertEqual(len(calls), 10)
        note('injected-short-write', calls=len(calls))

    def test_07_injected_zero_write_poisoned_without_loop(self):
        with self.main() as image:
            with patch.object(bd.os, 'pwrite', return_value=0) as writer:
                self.error('WRITE_NO_PROGRESS', lambda: image.write(9, 0, b'Q' * 16))
            self.assertEqual(writer.call_count, 1)
            self.error('POISONED', lambda: image.read(9, 0, 16))
        note('injected-zero-write', calls=1)

    def test_08_injected_partial_write_is_retained_not_rolled_back(self):
        real = os.pwrite
        calls = 0
        def partial(fd, data, offset):
            nonlocal calls
            calls += 1
            if calls == 1:
                return real(fd, data[:8], offset)
            raise OSError(errno.EIO, 'injected after partial write')
        with self.main() as image:
            before = image.read(10, 0, 16)
            with patch.object(bd.os, 'pwrite', partial), self.assertRaises(OSError):
                image.write(10, 0, b'C' * 16)
            self.error('POISONED', image.sync)
        with self.main() as image:
            actual = image.read(10, 0, 16)
            self.assertEqual(actual, b'C' * 8 + before[8:])
            # Explicitly settle this known test fixture after observing the partial state.
            image.sync()
        note('injected-partial-write', before=before.hex(), after=actual.hex(), rollback=False)

    def test_09_injected_sync_error_poisoned(self):
        with self.main() as image:
            image.write(11, 0, b'F' * 16)
            with patch.object(bd.os, 'fsync', side_effect=OSError(errno.EIO, 'injected sync')):
                with self.assertRaises(OSError):
                    image.sync()
            self.error('POISONED', lambda: image.write(12, 0, b'X' * 16))
        with self.main() as image:
            self.assertEqual(image.read(11, 0, 16), b'F' * 16)
            image.sync()
        note('injected-sync-error', priorAcknowledgement=False, explicitLaterSync=True)

    def test_10_injected_interrupt_poisoned(self):
        with self.main() as image:
            with patch.object(bd.os, 'pwrite', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    image.write(13, 0, b'K' * 16)
            self.error('POISONED', image.sync)
        note('injected-interrupt')

    def test_11_sync_close_and_reopen(self):
        with self.main() as image:
            image.write(100, 32, b'R' * 32)
            image.sync()
        with self.main() as image:
            self.assertEqual(image.read(100, 16, 64), b'\xff' * 16 + b'R' * 32 + b'\xff' * 16)

    def test_12_cross_process_ownership(self):
        argv = [sys.executable, '-B', str(Path(__file__).resolve()), '--open-check', str(WORK)]
        with self.main():
            denied = subprocess.run(argv, capture_output=True, timeout=3, check=False)
            self.assertEqual(denied.returncode, 0, denied.stderr)
            self.assertEqual(denied.stdout, b'busy\n')
        permitted = subprocess.run(argv, capture_output=True, timeout=3, check=False)
        self.assertEqual(permitted.returncode, 0, permitted.stderr)
        self.assertEqual(permitted.stdout, b'opened\n')
        note('cross-process-owner', blockedWhileHeld=True, openedAfterClose=True)

    def test_13_fork_refused_before_inherited_mutex(self):
        acquired, release = threading.Event(), threading.Event()
        with self.main() as image:
            def holder():
                with image._mutex:
                    acquired.set()
                    release.wait(4)
            thread = threading.Thread(target=holder)
            thread.start()
            self.assertTrue(acquired.wait(2))
            read_fd, write_fd = os.pipe()
            pid = os.fork()
            if pid == 0:
                os.close(read_fd)
                signal.alarm(2)
                try:
                    image.read(0, 0, 16)
                except bd.ImageError as error:
                    os.write(write_fd, str(error).encode())
                    os._exit(0)
                os._exit(1)
            os.close(write_fd)
            try:
                ready, _, _ = select.select([read_fd], [], [], 3)
                observed = os.read(read_fd, 64) if ready else b'timeout'
                _, status = os.waitpid(pid, 0)
                self.assertEqual(status, 0)
                self.assertEqual(observed, b'FORKED_HANDLE')
            finally:
                os.close(read_fd)
                release.set()
                thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(image.read(0, 0, 16), b'\xff' * 16)
        note('actual-fork-refusal', heldByOtherThread=True)

    def test_14_missing_chunk_not_created(self):
        original = self.main_path / 'chunk-01'
        saved = WORK / 'chunk-01.saved'
        original.rename(saved)
        with self.assertRaises(FileNotFoundError):
            self.main()
        self.assertFalse(original.exists())
        saved.rename(original)
        with self.main() as image:
            self.assertEqual(image.read(8191, 4080, 16), b'Z' * 16)

    def test_15_replaced_owner_rejected_even_with_same_bytes(self):
        original = self.main_path / 'owner'
        saved = WORK / 'owner.saved'
        body = original.read_bytes()
        original.rename(saved)
        original.write_bytes(body)
        original.chmod(0o600)
        self.error('OBJECT_REPLACED', self.main)
        original.rename(WORK / 'rejected-owner')
        saved.rename(original)
        with self.main():
            pass

    def test_16_changed_manifest_poisoned(self):
        path = self.main_path / 'manifest'
        body = path.read_bytes()
        with self.main() as image:
            changed = body.replace(b'"programBytes":16', b'"programBytes":32')
            self.assertEqual(len(changed), len(body))
            path.write_bytes(changed)
            self.error('METADATA_CHANGED', lambda: image.read(0, 0, 16))
            self.error('POISONED', image.sync)
        self.error('MANIFEST_MISMATCH', self.main)
        path.write_bytes(body)
        with self.main() as image:
            image.sync()

    def test_17_symlink_chunk_is_not_followed(self):
        original = self.main_path / 'chunk-01'
        saved = WORK / 'symlink-target'
        original.rename(saved)
        original.symlink_to(saved)
        self.error('UNSUPPORTED_OWNERSHIP', self.main)
        original.unlink()
        saved.rename(original)

    def test_18_hardlink_and_mode_refused(self):
        original = self.main_path / 'chunk-00'
        link = WORK / 'extra-hardlink'
        os.link(original, link)
        self.error('UNSUPPORTED_OWNERSHIP', self.main)
        link.unlink()
        original.chmod(0o640)
        self.error('UNSUPPORTED_OWNERSHIP', self.main)
        original.chmod(0o600)

    def test_19_same_inode_sparse_backing_refused(self):
        path = self.main_path / 'chunk-01'
        body = path.read_bytes()
        before = path.stat()
        fd = os.open(path, os.O_RDWR)
        try:
            os.ftruncate(fd, 0)
            os.ftruncate(fd, bd.CHUNK_BYTES)
            self.assertEqual(os.fstat(fd).st_ino, before.st_ino)
            self.assertLess(os.fstat(fd).st_blocks * 512, bd.CHUNK_BYTES)
            self.error('INVALID_FILE_ALLOCATION', self.main)
            # Restore the exact known fixture only after the refusal passes.
            os.posix_fallocate(fd, 0, bd.CHUNK_BYTES)
            bd._write_all(fd, body, 0)
            os.fsync(fd)
        finally:
            os.close(fd)
        self.assertEqual(path.read_bytes(), body)
        note('sparse-backing-refusal', sameInode=True, bytesRestored=bd.CHUNK_BYTES)

    def test_20_extra_inventory_and_fifo_refused(self):
        extra = self.main_path / 'extra'
        extra.write_bytes(b'x')
        self.error('INVENTORY_CHANGED', self.main)
        extra.unlink()
        original = self.main_path / 'manifest'
        saved = WORK / 'manifest.saved'
        original.rename(saved)
        os.mkfifo(original, 0o600)
        self.error('UNSUPPORTED_OWNERSHIP', self.main)
        original.unlink()
        saved.rename(original)

    def test_21_creation_failure_retained_without_ready_manifest(self):
        path = WORK / 'partial-create'
        with patch.object(bd.os, 'posix_fallocate', side_effect=OSError(errno.ENOSPC, 'injected allocation failure')):
            with self.assertRaises(OSError):
                bd.create_image(path, 'a' * 32, 1)
        self.assertTrue(path.is_dir())
        self.assertEqual(sorted(p.name for p in path.iterdir()), ['chunk-00', 'owner'])
        self.assertEqual((path / 'chunk-00').stat().st_size, 0)
        with self.assertRaises(FileExistsError):
            bd.create_image(path, 'a' * 32, 1)
        note('injected-create-allocation-failure', retained=True, readyManifest=False)

    def test_22_independent_control_image_still_operates(self):
        path = self.main_path / 'manifest'
        saved = WORK / 'bulk-manifest.saved'
        path.rename(saved)
        with self.assertRaises(FileNotFoundError):
            self.main()
        with self.control() as image:
            image.write(20, 0, b'T' * 16)
            image.sync()
        with self.control() as image:
            self.assertEqual(image.read(20, 0, 16), b'T' * 16)
        saved.rename(path)
        note('independent-image', bulkManifestMissing=True, controlSyncAndReopen=True,
             serviceRecoveryQualified=False)

    def test_23_close_is_not_sync_and_releases_descriptors(self):
        before = len(os.listdir('/proc/self/fd'))
        image = self.main()
        with patch.object(bd.os, 'fsync') as sync:
            image.close()
            image.close()
            sync.assert_not_called()
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)
        self.error('CLOSED', lambda: image.read(0, 0, 16))

    def test_24_invalid_geometry_identity_and_anchor_before_open(self):
        with patch.object(bd.os, 'open') as opener:
            for count in [0, 9, True, 1.5]:
                self.error('INVALID_GEOMETRY', lambda: bd.FixedBlockImage(self.main_path, IDENTITY, count, expected_objects={}))
            self.error('INVALID_IDENTITY', lambda: bd.FixedBlockImage(self.main_path, 'bad', 2, expected_objects={}))
            self.error('INVALID_OBJECT_ANCHOR', lambda: bd.FixedBlockImage(self.main_path, IDENTITY, 2, expected_objects={}))
            opener.assert_not_called()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--open-check':
        root = Path(sys.argv[2])
        receipt = json.loads((root / 'creation.json').read_text())['main']
        try:
            with bd.FixedBlockImage(root / 'main', IDENTITY, 2, expected_objects=receipt['objects']):
                print('opened')
        except BlockingIOError:
            print('busy')
        sys.exit(0)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BlockImageTests)
    result = unittest.TextTestRunner(verbosity=2, failfast=True).run(suite)
    print(json.dumps({'tests': result.testsRun, 'failures': len(result.failures),
                      'errors': len(result.errors), 'passed': result.wasSuccessful()}, sort_keys=True))
    sys.exit(0 if result.wasSuccessful() and result.testsRun == 24 else 1)
