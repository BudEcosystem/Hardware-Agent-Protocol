"""Independent state-path boundary probes using owned temporary fixtures.

No second UID is accessed. Foreign ownership cases inject stat metadata only;
same-UID/root rename after validation remains outside the isolation boundary.
"""
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from hms.journal import Context, JournalError
from hms.runtime import Runtime
from hms.state_path import private_state_directory


STORAGE_NAMES = [base + suffix for base in ("authority.db", "simulated-plant.db")
                 for suffix in ("", ".owner", "-journal", "-wal", "-shm")]


class StatePathReview(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hms-state-review-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.owner = Context("state-review-owner", "simulation:local")

    def directory(self, name, mode=0o700):
        path = self.base / name
        path.mkdir(mode=mode, parents=True)
        path.chmod(mode)
        return path

    def runtime(self, path, *, create=True):
        runtime = Runtime(path, create=create, owner=self.owner if create else None,
                          wall_clock_ms=lambda: 1000, monotonic_ms=lambda: 1000)
        self.addCleanup(runtime.close)
        return runtime

    def reject(self, path, code, *, create=True):
        with self.assertRaises(JournalError) as raised:
            self.runtime(path, create=create)
        self.assertEqual(raised.exception.code, code)

    def test_writable_ancestor_rejects_before_missing_leaf_is_created(self):
        for index, mode in enumerate((0o777, 0o770, 0o707)):
            with self.subTest(mode=oct(mode)):
                parent = self.directory(f"writable-{index}", mode)
                state = parent / "state"
                self.reject(state, "UNSAFE_STATE_ANCESTOR")
                self.assertFalse(state.exists())
                self.assertEqual(list(parent.iterdir()), [])

    def test_private_leaf_does_not_hide_a_writable_grandparent(self):
        shared = self.directory("shared", 0o777)
        private = shared / "private"
        private.mkdir(mode=0o700)
        state = private / "state"
        state.mkdir(mode=0o700)
        self.reject(state, "UNSAFE_STATE_ANCESTOR")
        self.assertEqual(list(state.iterdir()), [])

    def test_symlinked_ancestor_cannot_redirect_private_state(self):
        target = self.directory("target")
        state = target / "state"
        state.mkdir(mode=0o700)
        link = self.base / "alias"
        link.symlink_to(target, target_is_directory=True)
        self.reject(link / "state", "UNSAFE_OR_MISSING_STATE_DIRECTORY")
        self.assertEqual(list(state.iterdir()), [])

    def test_symlink_leaf_cannot_redirect_initialization(self):
        target = self.directory("target")
        link = self.base / "state"
        link.symlink_to(target, target_is_directory=True)
        self.reject(link, "UNSAFE_OR_MISSING_STATE_DIRECTORY")
        self.assertEqual(list(target.iterdir()), [])

    def test_unsafe_directory_replacement_before_open_is_rejected(self):
        original = self.directory("state")
        original.rename(self.base / "old-state")
        replacement = self.directory("replacement", 0o777)
        replacement.rename(original)
        self.reject(original, "UNSAFE_STATE_DIRECTORY")
        self.assertEqual(list(original.iterdir()), [])

    def test_private_state_under_trusted_sticky_parent_creates_and_reopens(self):
        # The fixture also traverses the real /tmp chain used by TemporaryDirectory.
        parent = self.directory("sticky", 0o1777)
        state = parent / "state"
        runtime = self.runtime(state)
        authority = runtime.journal.authority_id
        self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o700)
        self.assertEqual(len(runtime.request(self.owner, "discover", {})["items"]), 3)
        runtime.close()
        reopened = self.runtime(state, create=False)
        self.assertEqual(reopened.journal.authority_id, authority)

    def test_every_known_storage_leaf_rejects_symlinks_without_touching_target(self):
        target = self.base / "sentinel"
        target.write_bytes(b"unchanged review sentinel")
        target.chmod(0o600)
        for index, name in enumerate(STORAGE_NAMES):
            with self.subTest(name=name):
                state = self.directory(f"link-{index}")
                (state / name).symlink_to(target)
                self.reject(state, "UNSAFE_STATE_FILE")
                self.assertEqual(target.read_bytes(), b"unchanged review sentinel")
                self.assertEqual(sorted(p.name for p in state.iterdir()), [name])

    def test_every_known_storage_leaf_rejects_nonprivate_permissions(self):
        for index, name in enumerate(STORAGE_NAMES):
            with self.subTest(name=name):
                state = self.directory(f"permissions-{index}")
                path = state / name
                path.write_bytes(b"invalid private storage")
                path.chmod(0o660)
                self.reject(state, "UNSAFE_STATE_FILE")
                self.assertEqual(sorted(p.name for p in state.iterdir()), [name])

    def test_storage_hardlinks_are_rejected_without_changing_the_other_name(self):
        for index, name in enumerate(STORAGE_NAMES):
            with self.subTest(name=name):
                state = self.directory(f"hardlink-{index}")
                target = self.base / f"sentinel-{index}"
                target.write_bytes(b"unchanged hardlink sentinel")
                target.chmod(0o600)
                os.link(target, state / name)
                self.reject(state, "UNSAFE_STATE_FILE")
                self.assertEqual(target.read_bytes(), b"unchanged hardlink sentinel")
                self.assertEqual(target.stat().st_nlink, 2)

    def test_nonregular_storage_entries_are_rejected_before_database_open(self):
        for index, name in enumerate(STORAGE_NAMES):
            with self.subTest(name=name):
                state = self.directory(f"nonregular-{index}")
                (state / name).mkdir(mode=0o700)
                self.reject(state, "UNSAFE_STATE_FILE")
                self.assertEqual(sorted(p.name for p in state.iterdir()), [name])

    def test_foreign_owned_ancestor_is_rejected_even_with_safe_modes_or_sticky_bit(self):
        for index, mode in enumerate((0o755, 0o1777)):
            with self.subTest(mode=oct(mode)):
                parent = self.directory(f"foreign-{index}", mode)
                parent_identity = (parent.stat().st_dev, parent.stat().st_ino)
                original_fstat = os.fstat

                def foreign_fstat(descriptor):
                    info = original_fstat(descriptor)
                    if (info.st_dev, info.st_ino) == parent_identity:
                        values = list(info)
                        values[4] = os.getuid() + 100000
                        return os.stat_result(values)
                    return info

                with patch("hms.state_path.os.fstat", side_effect=foreign_fstat):
                    self.reject(parent / "state", "UNSAFE_STATE_ANCESTOR")
                self.assertFalse((parent / "state").exists())

    def test_foreign_owned_storage_file_is_rejected_with_private_mode(self):
        state = self.directory("foreign-file")
        leaf = state / "authority.db.owner"
        leaf.write_bytes(b"")
        leaf.chmod(0o600)
        identity = (leaf.stat().st_dev, leaf.stat().st_ino)
        original_stat = os.stat

        def foreign_stat(*args, **kwargs):
            info = original_stat(*args, **kwargs)
            if (info.st_dev, info.st_ino) == identity:
                values = list(info)
                values[4] = os.getuid() + 100000
                return os.stat_result(values)
            return info

        with patch("hms.state_path.os.stat", side_effect=foreign_stat):
            self.reject(state, "UNSAFE_STATE_FILE")
        self.assertEqual(list(state.iterdir()), [leaf])

    def test_reopen_does_not_create_a_missing_state_directory(self):
        path = self.base / "missing-state"
        self.reject(path, "UNSAFE_OR_MISSING_STATE_DIRECTORY", create=False)
        self.assertFalse(path.exists())

    def test_root_cannot_be_selected_as_private_state(self):
        with self.assertRaisesRegex(JournalError, "UNSAFE_STATE_DIRECTORY"):
            private_state_directory("/")


if __name__ == "__main__":
    unittest.main()
