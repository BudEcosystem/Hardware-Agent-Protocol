"""Small original fixtures for the historical compiler archive verifier."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('retained_audit', ROOT / 'scripts/audit_endpoint_evidence.py')
auditor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auditor)


class ArchiveChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='hms-archive-audit-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        auditor.ROOT = self.root
        auditor.toolchain_members.clear()
        auditor.historical_toolchain_checks.clear()
        self.body = b'original non-executable compiler-byte fixture'
        self.sha = hashlib.sha256(self.body).hexdigest()
        self.installed = self.root / 'absent-compiler'
        self.files = {str(self.installed): dict(archive_member='avr/bin/cc', sha256=self.sha),
            str(self.root / 'absent-alias'): dict(archive_member='avr/avr/bin/cc', sha256=self.sha)}
        self.archive = self.make_archive([
            ('avr/bin/cc', self.body), ('avr/avr/bin/cc', 'avr/bin/cc')])

    def make_archive(self, entries):
        path = self.root / ('fixture-' + str(len(list(self.root.glob('*.tar.bz2')))) + '.tar.bz2')
        with tarfile.open(path, 'w:bz2') as target:
            for name, value in entries:
                info = tarfile.TarInfo(name)
                if type(value) is bytes:
                    info.size = len(value); target.addfile(info, io.BytesIO(value))
                else:
                    info.type = tarfile.LNKTYPE; info.linkname = value; target.addfile(info)
        return dict(path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    def test_missing_installed_paths_verify_archive_bytes_without_extraction(self):
        before = set(self.root.iterdir())
        auditor.historical_toolchain(self.archive, self.files)
        self.assertEqual(set(self.root.iterdir()), before)
        self.assertEqual([row['verification'] for row in auditor.historical_toolchain_checks],
                         ['archive_only', 'archive_only'])

    def test_present_installed_bytes_must_match_even_after_cache_hit(self):
        auditor.historical_toolchain(self.archive, self.files)
        self.installed.write_bytes(self.body)
        auditor.historical_toolchain(self.archive, self.files)
        self.assertEqual(auditor.historical_toolchain_checks[-2]['verification'], 'archive_and_installed_path')
        self.installed.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            auditor.historical_toolchain(self.archive, self.files)

    def test_changed_archive_hash_refuses(self):
        with self.assertRaises(ValueError):
            auditor.historical_toolchain(self.archive | {'sha256': '0' * 64}, self.files)

    def test_wrong_member_hash_refuses(self):
        self.files[str(self.installed)]['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            auditor.historical_toolchain(self.archive, self.files)

    def test_missing_archive_member_refuses(self):
        self.files[str(self.installed)]['archive_member'] = 'avr/missing'
        with self.assertRaises(ValueError):
            auditor.historical_toolchain(self.archive, self.files)

    def test_unselected_link_target_refuses(self):
        with self.assertRaises(ValueError):
            auditor.historical_toolchain(self.archive, {str(self.root / 'alias'): self.files[str(self.root / 'absent-alias')]})

    def test_escaping_and_cyclic_link_targets_refuse(self):
        for entries in ([('avr/bin/cc', '../outside'), ('avr/avr/bin/cc', 'avr/bin/cc')],
                        [('avr/bin/cc', 'avr/avr/bin/cc'), ('avr/avr/bin/cc', 'avr/bin/cc')]):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                auditor.historical_toolchain(self.make_archive(entries), self.files)

    def test_duplicate_members_refuse(self):
        archive = self.make_archive([('avr/bin/cc', self.body), ('avr/bin/cc', self.body),
                                     ('avr/avr/bin/cc', 'avr/bin/cc')])
        with self.assertRaises(ValueError):
            auditor.historical_toolchain(archive, self.files)


if __name__ == '__main__':
    unittest.main(verbosity=2)
