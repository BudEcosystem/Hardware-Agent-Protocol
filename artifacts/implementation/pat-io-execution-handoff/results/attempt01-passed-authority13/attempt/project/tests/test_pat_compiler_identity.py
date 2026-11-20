"""Bounded seven-package setup identity; no runtime, SQL or device execution."""
from contextlib import contextmanager
import copy
import hashlib
import importlib.metadata
import io
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hms import pat_compiler as compiler
from hms.contracts import canonical
from hms.pat_contracts import PatError
from hms.pat_simulation_worker import simulation_identities
from test_pat_compiler import artifact, compile_fixture, descriptor


@contextmanager
def distribution_override(package, *, files=None, version=None, resource=None, target=None):
    actual = importlib.metadata.distribution
    original = actual(package)
    class Distribution:
        def locate_file(self, item):
            return resource if target is not None and str(item) == target else original.locate_file(item)
    replacement = Distribution()
    replacement.files = original.files if files is None else files
    replacement.version = original.version if version is None else version
    with patch.object(compiler.importlib.metadata, 'distribution',
                      side_effect=lambda name: replacement if name == package else actual(name)):
        yield


def packages(manifest):
    return {row['package']: row for row in manifest['packages']}


class CompilerIdentityTests(unittest.TestCase):
    def refuses(self, callback, code='PAT_COMPILER_IDENTITY_UNAVAILABLE'):
        with self.assertRaises(PatError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_profile_and_digest_domain_version_are_explicit(self):
        manifest = compiler.compiler_manifest()
        self.assertEqual(manifest['profile'], 'hms.pat-compiler-identity/0.2')
        self.assertEqual(set(packages(manifest)), {'jsonschema', 'referencing',
            'jsonschema-specifications', 'attrs', 'rpds-py', 'typing_extensions', 'idna'})
        expected = 'sha256:' + hashlib.sha256(
            b'HMS-PAT-COMPILER-SHA256-v0.2\0' + canonical(manifest)).hexdigest()
        self.assertEqual(compiler.compiler_digest(), expected)
        old_domain = 'sha256:' + hashlib.sha256(
            b'HMS-PAT-COMPILER-SHA256-v0.1\0' + canonical(manifest)).hexdigest()
        self.assertNotEqual(expected, old_domain)

    def test_both_previously_omitted_code_closures_change_identity(self):
        for package, target in [('typing_extensions', 'typing_extensions.py'),
                                ('idna', 'idna/core.py')]:
            with self.subTest(package=package), tempfile.TemporaryDirectory() as directory:
                original = importlib.metadata.distribution(package)
                resource = Path(directory) / 'retained.py'
                resource.write_bytes(original.locate_file(target).read_bytes())
                with distribution_override(package, resource=resource, target=target):
                    before = compiler._identity()
                    self.assertEqual(before, compiler.compiler_manifest())
                    resource.write_bytes(resource.read_bytes() + b'\n# changed fixture bytes\n')
                    after = compiler._identity()
                    left, right = packages(before), packages(after)
                    self.assertNotEqual(left.pop(package)['codeDigest'], right.pop(package)['codeDigest'])
                    self.assertEqual(left, right)
                    self.refuses(compiler.verify_compiler_identity, 'PAT_COMPILER_IMPLEMENTATION_CHANGED')
                self.assertEqual(compiler.verify_compiler_identity(), before)

    def test_optional_distribution_version_changes_identity(self):
        for package in ('typing_extensions', 'idna'):
            with self.subTest(package=package), distribution_override(package, version='fixture:changed'):
                self.refuses(compiler.verify_compiler_identity, 'PAT_COMPILER_IMPLEMENTATION_CHANGED')

    def test_missing_either_selected_distribution_is_a_structured_refusal(self):
        actual = importlib.metadata.distribution
        for package in ('typing_extensions', 'idna'):
            def lookup(name):
                if name == package:
                    raise importlib.metadata.PackageNotFoundError(name)
                return actual(name)
            with self.subTest(package=package), patch.object(
                    compiler.importlib.metadata, 'distribution', side_effect=lookup):
                self.refuses(compiler._identity)

    def test_missing_selected_optional_file_is_a_structured_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            for package, target in [('typing_extensions', 'typing_extensions.py'), ('idna', 'idna/core.py')]:
                with self.subTest(package=package), distribution_override(package,
                        target=target, resource=Path(directory)/'missing'):
                    self.refuses(compiler._identity)

    def test_missing_source_is_a_structured_refusal(self):
        actual = Path.lstat
        def lstat(path):
            if path.name == 'pat_contracts.py':
                raise FileNotFoundError('fixture source unavailable')
            return actual(path)
        with patch.object(Path, 'lstat', lstat):
            self.refuses(compiler._identity)

    def test_reordered_distribution_inventory_preserves_identity(self):
        original = importlib.metadata.distribution('idna')
        with distribution_override('idna', files=list(reversed(original.files))):
            self.assertEqual(compiler.verify_compiler_identity(), compiler.compiler_manifest())

    def test_duplicate_code_record_refuses(self):
        original = importlib.metadata.distribution('idna')
        item = next(item for item in original.files if str(item) == 'idna/core.py')
        with distribution_override('idna', files=[*original.files, item]):
            self.refuses(compiler._identity)

    def test_absolute_parent_and_cache_code_paths_refuse_before_read(self):
        for path in ('/fixture.py', '../fixture.py', 'idna/__pycache__/fixture.py'):
            with self.subTest(path=path), distribution_override('idna',
                    files=[importlib.metadata.PackagePath(path)]):
                self.refuses(compiler._identity)

    def test_empty_and_oversized_distribution_inventory_refuse(self):
        for files in ([], [importlib.metadata.PackagePath('idna/core.py')] * 8193):
            with self.subTest(size=len(files)), distribution_override('idna', files=files):
                self.refuses(compiler._identity)

    def test_selected_file_symlink_and_directory_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root/'data'; target.write_bytes(b'retained data')
            link = root/'link'; link.symlink_to(target)
            for resource in (link, root):
                with self.subTest(resource=resource), distribution_override('typing_extensions',
                        target='typing_extensions.py', resource=resource):
                    self.refuses(compiler._identity)

    def test_file_count_and_byte_limits_refuse_without_widening(self):
        for limit, value in [('_IDENTITY_MAX_FILES', 1), ('_IDENTITY_MAX_FILE_BYTES', 1),
                             ('_IDENTITY_MAX_BYTES', 1)]:
            with self.subTest(limit=limit), patch.object(compiler, limit, value):
                self.refuses(compiler._identity, 'PAT_COMPILER_IDENTITY_LIMIT')
        self.assertEqual((compiler._IDENTITY_MAX_FILES, compiler._IDENTITY_MAX_FILE_BYTES,
            compiler._IDENTITY_MAX_BYTES), (8192, 16*1024*1024, 256*1024*1024))

    def test_acquisition_checks_exact_size_and_bounds_the_actual_read(self):
        reads = []
        class Stream(io.BytesIO):
            def read(self, size):
                reads.append(size)
                return super().read(size)
        class FixturePath:
            def lstat(self):
                return SimpleNamespace(st_mode=stat.S_IFREG, st_size=1)
            def open(self, mode):
                assert mode == 'rb'
                return Stream(b'grew')
        with patch.object(compiler, '_IDENTITY_MAX_FILE_BYTES', 2):
            self.refuses(lambda: compiler._identity_file(FixturePath(), [0, 0]))
        self.assertEqual(reads, [3])

    def test_valid_setup_recheck_is_detached_and_preserves_imported_identity(self):
        expected = compiler.compiler_manifest()
        actual = compiler.verify_compiler_identity()
        self.assertEqual(actual, expected)
        actual['sources'].clear(); actual['packages'].clear()
        self.assertEqual(compiler.compiler_manifest(), expected)

    def test_setup_recheck_refuses_changed_source_without_refreshing_cached_identity(self):
        before = compiler.compiler_manifest(); changed = copy.deepcopy(before)
        changed['sources'][0]['sha256'] = '0' * 64
        digest = compiler.compiler_digest()
        with patch.object(compiler, '_identity', return_value=changed):
            self.refuses(compiler.verify_compiler_identity, 'PAT_COMPILER_IMPLEMENTATION_CHANGED')
        self.assertEqual(compiler.compiler_manifest(), before)
        self.assertEqual(compiler.compiler_digest(), digest)

    def test_worker_setup_rechecks_dependency_bytes_before_returning_identity(self):
        before = simulation_identities()
        original = importlib.metadata.distribution('idna')
        with tempfile.TemporaryDirectory() as directory:
            resource = Path(directory)/'fixture-data'
            resource.write_bytes(original.locate_file('idna/core.py').read_bytes() + b'\n# changed\n')
            with distribution_override('idna', target='idna/core.py', resource=resource):
                self.refuses(simulation_identities, 'PAT_COMPILER_IMPLEMENTATION_CHANGED')
        self.assertEqual(simulation_identities(), before)

    def test_lowered_policy_limits_still_have_distinct_identity(self):
        from hms.pat_simulation_contracts import CEILINGS
        before = simulation_identities()
        limits = dict(CEILINGS); limits['maxCases'] -= 1
        after = simulation_identities(limits)
        self.assertNotEqual(before['policyDigest'], after['policyDigest'])
        self.assertEqual({k: v for k, v in before.items() if k != 'policyDigest'},
                         {k: v for k, v in after.items() if k != 'policyDigest'})

    def test_lowering_does_not_invoke_setup_acquisition(self):
        value, binding = artifact(), descriptor()
        with patch.object(compiler, '_identity', side_effect=AssertionError('identity I/O during lowering')), \
             patch.object(Path, 'open', side_effect=AssertionError('file I/O during lowering')), \
             patch('time.time', side_effect=AssertionError('clock during lowering')):
            result = compile_fixture(value, bindings={'fan': binding})
        self.assertEqual(result['compilerDigest'], compiler.compiler_digest())
        self.assertEqual(result['report']['stepCount'], 2)
