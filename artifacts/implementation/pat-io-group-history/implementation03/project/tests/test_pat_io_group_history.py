"""Pre-run trusted setup, complete real groups and altered archive refusals."""
import ast
import builtins
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.pat_contracts import PatError
from hms import pat_io_group_history as reader
from hms.pat_io_group_setup import prepare_io_group
from hms.synthetic_io_installation import normalize_installation
from test_io_synthetic_provider import installation
from test_pat_io_combined_matrix import bindings
from test_pat_io_contracts import program
from test_pat_io_group_worker import IoGroupWorkerTests


def authority(document):
    owner = dict(principal='pat-io-trial-worker', deployment=document['topology']['deployment'])
    return owner | dict(profile='hms.pat.io-trusted-authority/0.1', initialRegistryRevision=13,
        initialGrants=[owner | dict(target='*', verb='admin')], grantChanges=[])


class IoGroupSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        document = normalize_installation(installation()); chosen = bindings(document)
        cls.options = dict(candidate=program(literal=True), installation=document,
            descriptor=chosen['gpio']['descriptor'], challenge_bindings=chosen)
        cls.authority = authority(document)
        cls.prepared = prepare_io_group(**cls.options, authority=cls.authority)

    def test_all_required_cases_have_individual_bounded_pre_run_setup(self):
        value = self.prepared; cases = value['expected_cases']; matrix = value['expected_inputs']['matrix']
        self.assertEqual([e['expected_case'] for e in cases], matrix['cases'])
        self.assertEqual(len(cases), 30)
        self.assertTrue(all(len(canonical(e)) <= 65536 for e in cases))
        names = {e['expected_case']['definition']['scenario'] for e in cases if e['expected_case']['kind'] != 'candidate'}
        self.assertEqual(names, reader.TIMING | reader.CLOCK | reader.LIFECYCLE | reader.AUTHORITY | {'shared_resources'})
        self.assertEqual(len(cases[-1]['expected_actors']), 4)

    def test_setup_does_not_create_runtime_or_consult_authority_database(self):
        with patch('hms.pat_io_trials.IoRuntime', side_effect=AssertionError('runtime')), \
             patch.object(sqlite3, 'connect', side_effect=AssertionError('database')):
            result = prepare_io_group(**self.options, authority=self.authority)
        self.assertEqual(result, self.prepared)

    def test_setup_requires_separate_exact_initial_authority(self):
        for key, value in [('principal', 'another-owner'), ('initialRegistryRevision', True),
                ('initialRegistryRevision', 13.0), ('initialGrants', []), ('grantChanges', [{}])]:
            changed = copy.deepcopy(self.authority); changed[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(PatError):
                prepare_io_group(**self.options, authority=changed)

    def test_setup_snapshots_do_not_share_caller_or_case_mutations(self):
        options = copy.deepcopy(self.options)
        value = prepare_io_group(**options, authority=self.authority)
        options['candidate']['name'] = 'caller:changed'
        value['expected_cases'][0]['expected_setup']['artifact']['name'] = 'case:changed'
        self.assertEqual(value['expected_inputs']['candidate'], self.options['candidate'])
        self.assertEqual(value['expected_cases'][1]['expected_setup']['artifact'], self.options['candidate'])
        self.assertEqual(self.prepared['expected_cases'][0]['expected_setup']['artifact'], self.options['candidate'])

    def test_fault_and_permission_plans_are_selected_before_capture(self):
        cases = {e['expected_case']['definition']['scenario']: e for e in self.prepared['expected_cases']
            if e['expected_case']['kind'] == 'fixed_challenge'}
        self.assertEqual(cases['permission_after_completion']['expected_authority']['grantChanges'][0]['phase'], 6)
        self.assertEqual(cases['permission_after_completion']['expected_faults'][0]['point'], 'journal.record_execution.before_commit')
        self.assertEqual(cases['pending_reply_lost']['expected_faults'][0]['phase'], 4)
        self.assertEqual(cases['cancel_pending']['expected_faults'], [])
        self.assertEqual(cases['binding_pending']['expected_authority_change']['action'], 'invalidate_binding')
        self.assertEqual(cases['full_authority_withdrawal']['expected_authority_change']['action'], 'withdraw_all')

    def test_reader_rejects_archive_shapes_and_capacity_before_inspection(self):
        bad = [[], {}, {'../escape': b'{}'}, {'absolute//path': b'{}'}, {'/absolute': b'{}'}, {'x': 'text'},
            {'x': b'x' * (16*1024*1024 + 1)}, {str(i): b'{}' for i in range(8193)}]
        with patch.object(reader, 'inspect_conflict_history', side_effect=AssertionError('inspected invalid archive')):
            for files in bad:
                with self.subTest(kind=type(files).__name__), self.assertRaises(reader.IoGroupHistoryError):
                    reader.inspect_io_group(files, **self.prepared)

    def test_reader_refuses_incomplete_and_duplicate_expected_case_inventory(self):
        for change in ('missing', 'duplicate'):
            value = copy.deepcopy(self.prepared)
            if change == 'missing': value['expected_cases'].pop()
            else: value['expected_cases'][1] = value['expected_cases'][0]
            with self.subTest(change=change), self.assertRaisesRegex(reader.IoGroupHistoryError, 'CASE_INVENTORY'):
                reader.inspect_io_group({'result.json': b'{}'}, **value)

    def test_reader_rejects_scalar_coercion_and_noncanonical_result(self):
        value = copy.deepcopy(self.prepared); value['expected_inputs']['matrix']['limits']['maxCases'] = 32.0
        with self.assertRaisesRegex(reader.IoGroupHistoryError, 'SCALAR'):
            reader.inspect_io_group({'result.json': b'{}'}, **value)
        for raw in (b'{ "x":1}', b'{"x":1,"x":2}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                reader.inspect_io_group({'result.json': raw}, **self.prepared)

    def test_reader_has_no_direct_producer_or_effect_imports(self):
        source = Path(reader.__file__).read_text(); tree = ast.parse(source)
        forbidden = ('pat_io_group_worker', 'pat_io_group_setup', 'pat_io_combined_matrix', 'pat_io_contracts',
            'pat_compiler', 'pat_io_trials', 'synthetic_io_runtime', 'synthetic_io_installation', 'sqlite3', 'pathlib', 'time')
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        self.assertFalse(set(imports) & set(forbidden))

    def test_absent_current_environment_requires_exact_authority_reopen_context(self):
        compiler = 'sha256:' + '1' * 64
        valid = dict(originalEnvironment=dict(compilerDigest=compiler), workerEnvironment=None, create=False,
            bindingResolution=dict(status='unavailable', exception='PatError', code='PAT_BINDING_NOT_APPLICABLE'))
        for name in ('full_authority_withdrawal', 'binding_pending'):
            case = dict(kind='fixed_challenge', definition=dict(scenario=name))
            reader._opening(valid, compiler, case)
            for key, value in (('create', True), ('originalEnvironment', None),
                    ('originalEnvironment', dict(compilerDigest='sha256:' + '0' * 64)),
                    ('bindingResolution', dict(status='unavailable', exception='PatError', code='arbitrary'))):
                with self.subTest(name=name, key=key), self.assertRaises(reader.IoGroupHistoryError):
                    reader._opening(valid | {key: value}, compiler, case)
        for name in ('cancel_pending', 'binding_before_dispatch', 'wall_clock_regression'):
            with self.subTest(name=name), self.assertRaises(reader.IoGroupHistoryError):
                reader._opening(valid, compiler, dict(kind='fixed_challenge', definition=dict(scenario=name)))
        with self.assertRaises(reader.IoGroupHistoryError):
            reader._opening(valid, compiler, dict(kind='candidate'))
        reader._opening(valid | dict(workerEnvironment=dict(compilerDigest=compiler)), compiler, dict(kind='candidate'))
        with self.assertRaises(reader.IoGroupHistoryError):
            reader._opening(valid | dict(workerEnvironment=dict(compilerDigest='sha256:' + '0' * 64)), compiler, dict(kind='candidate'))


class IoGroupHistoryTests(IoGroupWorkerTests):
    def full_history(self, pwm):
        prepared = prepare_io_group(**self.options(pwm), authority=authority(self.document))
        requested = self.workspace / 'requested'; requested.mkdir(mode=0o700)
        for key, value in prepared['expected_inputs'].items():
            (requested / (key + '.json')).write_bytes(canonical(value))
        for i, value in enumerate(prepared['expected_cases']):
            (requested / ('case-%02d.json' % i)).write_bytes(canonical(value))
        pins = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in requested.iterdir()}
        # Preserve the complete original group test, including effects/accounting
        # and actual 1024-byte database header assertions.
        self.full(pwm)
        self.assertEqual(pins, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in requested.iterdir()})
        files = {p.relative_to(self.directory).as_posix(): p.read_bytes() for p in self.directory.rglob('*') if p.is_file()}
        families = ('inspect_timing_challenge', 'inspect_clock_challenge', 'inspect_lifecycle_challenge',
            'inspect_authority_challenge', 'inspect_resource_challenge')
        counts = {}
        patches = []
        for name in families:
            p = patch.object(reader, name, wraps=getattr(reader, name)); counts[name] = p.start(); patches.append(p)
        try:
            with patch.object(builtins, 'open', side_effect=AssertionError('reader file I/O')), \
                 patch.object(Path, 'read_bytes', side_effect=AssertionError('reader file read')), \
                 patch.object(sqlite3, 'connect', side_effect=AssertionError('reader SQL')), \
                 patch.object(time, 'monotonic', side_effect=AssertionError('reader clock')):
                checked = reader.inspect_io_group(files, **prepared)
        finally:
            for p in reversed(patches): p.stop()
        self.assertEqual([counts[name].call_count for name in families], [8, 3, 10, 3, 1])
        summary = checked['summary']; self.assertTrue(summary['requiredMatrixCoverageChecked'])
        self.assertTrue(summary['independentOutcomeChecked']); self.assertTrue(summary['archiveAccountingChecked'])
        self.assertEqual(len(checked['inspections']), 30)
        for flag in ('configurationAttested', 'implementationIdentityAttested', 'runAssociationAttested',
                'wallDeadlineAttested', 'actualAggregateStorageEnforced', 'physicalMeasurementChecked', 'qualificationPassed'):
            self.assertFalse(summary[flag])
        self.assertTrue(checked['inspections'][0]['outcome']['nominalCompletionSatisfied'])
        self.assertEqual(summary['accounting']['actualChildOperations'], 28)
        self.assertEqual(summary['accounting']['schedulerTicks'], 99)
        out = self.workspace / 'inspection'; out.mkdir(mode=0o700)
        (out / 'summary.json').write_bytes(canonical(summary))
        for i, inspection in enumerate(checked['inspections']):
            (out / ('case-%02d.json' % i)).write_bytes(canonical(inspection))
        # Early refusals must not call any semantic checker or accept worker flags.
        original = json.loads(files['result.json'])
        for label in ('case_order', 'success_claim', 'compiler_identity'):
            changed = copy.deepcopy(original)
            if label == 'case_order': changed['cases'][0], changed['cases'][1] = changed['cases'][1], changed['cases'][0]
            elif label == 'success_claim': changed['qualificationPassed'] = True
            else: changed['identities']['compilerDigest'] = 'sha256:' + '0' * 64
            attacked = dict(files); attacked['result.json'] = canonical(changed)
            with self.subTest(attack=label), patch.object(reader, 'inspect_conflict_history', side_effect=AssertionError('late refusal')):
                with self.assertRaises(reader.IoGroupHistoryError): reader.inspect_io_group(attacked, **prepared)
        (out / 'checks.json').write_bytes(canonical(dict(fullOriginalGroupAssertions=True, requestedSetupPreserved=True,
            independentReaderPure=True, checkerCalls={k: counts[k].call_count for k in families}, earlyArchiveRefusals=3,
            qualificationPassed=False)))

    def test_complete_gpio_history(self):
        self.full_history(False)

    def test_complete_pwm_history(self):
        self.full_history(True)
