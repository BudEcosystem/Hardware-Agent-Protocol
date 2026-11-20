"""Pre-release multi-document association, bounded parsing and fresh rebuilds."""
import builtins
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.pat_contracts import PatError
from hms import pat_io_run_bundle as bundle
from hms.synthetic_io_installation import normalize_installation
from test_io_synthetic_provider import installation
from test_pat_io_combined_matrix import bindings
from test_pat_io_contracts import program
from test_pat_io_group_history import authority


def hashed(domain, value):
    return 'sha256:' + hashlib.sha256(domain + b'\0' + canonical(value)).hexdigest()


class IoRunBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        document = normalize_installation(installation()); chosen = bindings(document)
        cls.options = dict(candidate=program(literal=True), installation=document,
            descriptor=chosen['gpio']['descriptor'], challenge_bindings=chosen, authority=authority(document))
        cls.context = dict(deployment=document['topology']['deployment'], evaluatorId='eval:io-finite',
            runId='run:bundle-gpio', configurationDigest='sha256:' + '7' * 64, configurationRevision=4)
        cls.original = bundle.prepare_io_run_bundle(context=cls.context, **cls.options)

    def parse(self, value=None, context=None, digest=None):
        value = self.original if value is None else value
        return bundle.parse_io_run_bundle(value['header'], value['documents'],
            expected_context=self.context if context is None else context,
            expected_bundle_digest=value['bundleDigest'] if digest is None else digest)

    def fresh(self, value=None):
        value = self.original if value is None else value
        return bundle.validate_fresh_io_run_bundle(value['header'], value['documents'],
            expected_context=self.context, expected_bundle_digest=value['bundleDigest'])

    def alter(self, mutator):
        """Attacker can rehash carriers; only tests explicitly replace the anchor."""
        value = copy.deepcopy(self.original)
        header = json.loads(value['header']); docs = {k: json.loads(v) for k, v in value['documents'].items()}
        mutator(header, docs)
        value['documents'] = {k: canonical(v) for k, v in docs.items()}
        header['manifest'] = [dict(path=p, bytes=len(value['documents'][p]),
            sha256=hashlib.sha256(value['documents'][p]).hexdigest()) for p in value['documents']]
        header['inputBytes'] = sum(map(len, value['documents'].values()))
        header['inputSetDigest'] = hashed(b'HMS-PAT-IO-INPUT-SET-v0.1', header['manifest'])
        header['matrixDigest'] = hashed(b'HMS-PAT-IO-COMBINED-MATRIX-v0.1', docs['inputs/matrix.json'])
        value['header'] = canonical(header); value['bundleDigest'] = bundle.bundle_digest(value['header'])
        return value

    def test_complete_pre_run_bundle_rebuilds_without_runtime_database_or_clock(self):
        with patch('hms.pat_io_trials.IoRuntime', side_effect=AssertionError('runtime')), \
             patch.object(sqlite3, 'connect', side_effect=AssertionError('SQL')), \
             patch.object(time, 'monotonic', side_effect=AssertionError('clock')):
            parsed = self.fresh()
        self.assertEqual(len(self.original['documents']), 37)
        self.assertEqual(len(parsed['expected_cases']), 30)
        self.assertEqual(parsed['authority'], self.options['authority'])
        header = json.loads(self.original['header'])
        self.assertGreater(header['inputBytes'], 65536)
        self.assertLessEqual(len(self.original['header']), 65536)
        self.assertEqual(header['inputBytes'], sum(map(len, self.original['documents'].values())))
        self.assertEqual(set(parsed['expected_inputs']), set(bundle.INPUTS) - {'authority'})

    def test_parsing_supplied_carriers_performs_no_io_planning_or_clock_calls(self):
        with patch.object(builtins, 'open', side_effect=AssertionError('open')), \
             patch.object(Path, 'read_bytes', side_effect=AssertionError('read')), \
             patch.object(sqlite3, 'connect', side_effect=AssertionError('SQL')), \
             patch.object(time, 'time', side_effect=AssertionError('clock')), \
             patch.object(time, 'monotonic', side_effect=AssertionError('clock')), \
             patch('hms.pat_io_group_setup.prepare_io_group', side_effect=AssertionError('plan')), \
             patch('hms.pat_io_group_worker._identities', side_effect=AssertionError('identity')):
            self.assertEqual(self.parse()['context'], self.context)

    def test_pwm_bundle_has_separate_candidate_matrix_and_run_associations(self):
        options = self.options | dict(candidate=program(pwm=True, literal=True),
            descriptor=self.options['challenge_bindings']['pwm']['descriptor'])
        context = self.context | dict(runId='run:bundle-pwm')
        value = bundle.prepare_io_run_bundle(context=context, **options)
        parsed = bundle.validate_fresh_io_run_bundle(value['header'], value['documents'],
            expected_context=context, expected_bundle_digest=value['bundleDigest'])
        self.assertEqual(len(parsed['expected_cases']), 30)
        self.assertEqual(parsed['expected_inputs']['candidate'], options['candidate'])
        self.assertNotEqual(value['bundleDigest'], self.original['bundleDigest'])
        self.assertNotEqual(json.loads(value['header'])['matrixDigest'], json.loads(self.original['header'])['matrixDigest'])
        with self.assertRaisesRegex(bundle.IoRunBundleError, 'CONTEXT_ASSOCIATION'): self.parse(value)

    def test_document_mapping_order_is_irrelevant_but_manifest_order_is_fixed(self):
        changed = copy.deepcopy(self.original)
        changed['documents'] = dict(reversed(list(changed['documents'].items())))
        self.assertEqual(self.parse(changed), self.parse())
        header = json.loads(changed['header']); header['manifest'].reverse()
        header['inputSetDigest'] = hashed(b'HMS-PAT-IO-INPUT-SET-v0.1', header['manifest'])
        changed['header'] = canonical(header); changed['bundleDigest'] = bundle.bundle_digest(changed['header'])
        with self.assertRaisesRegex(bundle.IoRunBundleError, 'REFERENCE'): self.parse(changed)

    def test_builder_and_parsed_trees_are_detached(self):
        context = copy.deepcopy(self.context); options = copy.deepcopy(self.options)
        built = bundle.prepare_io_run_bundle(context=context, **options)
        self.assertEqual(built, self.original)
        context['runId'] = 'changed'; options['authority']['initialGrants'].clear()
        first = self.parse(); first['expected_cases'][0]['expected_setup']['installation']['boardId'] = 'changed'
        first['authority']['initialGrants'].clear(); first['context']['runId'] = 'changed'
        self.assertEqual(built, self.original)
        self.assertEqual(self.parse()['authority'], self.options['authority'])
        self.assertNotEqual(first['expected_inputs']['installation']['boardId'], 'changed')
        self.assertNotEqual(first['expected_cases'][1]['expected_setup']['installation']['boardId'], 'changed')

    def test_missing_extra_renamed_and_nonbytes_documents_refuse(self):
        for mutation in ('missing', 'extra', 'traversal', 'absolute', 'empty', 'text', 'bytearray'):
            changed = copy.deepcopy(self.original); docs = changed['documents']; key = 'inputs/authority.json'
            if mutation == 'missing': del docs[key]
            elif mutation in ('extra', 'traversal', 'absolute'):
                docs[{'extra':'extra.json', 'traversal':'../authority.json', 'absolute':'/authority.json'}[mutation]] = docs.pop(key)
            elif mutation == 'empty': docs[key] = b''
            elif mutation == 'text': docs[key] = docs[key].decode()
            else: docs[key] = bytearray(docs[key])
            with self.subTest(mutation=mutation), self.assertRaises(bundle.IoRunBundleError): self.parse(changed)
        changed = copy.deepcopy(self.original); changed['documents']['extra.json'] = b'{}'
        with self.assertRaisesRegex(bundle.IoRunBundleError, 'CLOSURE'): self.parse(changed)

    def test_changed_content_cannot_reuse_retained_manifest_or_digest(self):
        changed = copy.deepcopy(self.original)
        changed['documents']['inputs/authority.json'] = changed['documents']['inputs/authority.json'].replace(b'13', b'14')
        with self.assertRaisesRegex(bundle.IoRunBundleError, 'REFERENCE'): self.parse(changed)
        changed = self.alter(lambda h, d: d['inputs/authority.json'].update(initialRegistryRevision=14))
        with self.assertRaisesRegex(bundle.IoRunBundleError, 'HEADER_ASSOCIATION'):
            self.parse(changed, digest=self.original['bundleDigest'])

    def test_rehashed_context_cannot_substitute_another_run_or_configuration(self):
        for key, value in [('runId', 'run:other'), ('evaluatorId', 'eval:other'), ('deployment', 'deployment:other'),
                ('configurationDigest', 'sha256:' + '8' * 64), ('configurationRevision', 5)]:
            changed = self.alter(lambda h, d: h['context'].update({key:value}))
            with self.subTest(key=key), self.assertRaisesRegex(bundle.IoRunBundleError, 'CONTEXT_ASSOCIATION'):
                self.parse(changed)

    def test_context_requires_closed_typed_bounded_values(self):
        for key, value in [('runId', ''), ('runId', 'x'*129), ('runId', 'space here'), ('evaluatorId', True),
                ('configurationRevision', True), ('configurationRevision', 4.0), ('configurationRevision', 0),
                ('configurationDigest', 'sha256:' + 'G'*64), ('extra', 'field')]:
            changed = self.context | {key:value}
            with self.subTest(key=key, value=value), self.assertRaises(bundle.IoRunBundleError):
                self.parse(context=changed)
        with self.assertRaises(bundle.IoRunBundleError): self.parse(context={})
        with self.assertRaises(bundle.IoRunBundleError): self.parse(digest=True)
        with self.assertRaises(bundle.IoRunBundleError): self.parse(digest='sha256:'+'0'*64)

    def test_duplicate_keys_noncanonical_carriers_and_float_aliases_refuse(self):
        for raw in (b'{ "x":1}', b'{"x":1,"x":2}', b'{"x":1.0}', b'{"x":NaN}'):
            changed = copy.deepcopy(self.original); key = 'inputs/authority.json'; changed['documents'][key] = raw
            header = json.loads(changed['header']); row = next(r for r in header['manifest'] if r['path']==key)
            row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            header['inputBytes'] = sum(map(len, changed['documents'].values()))
            header['inputSetDigest'] = hashed(b'HMS-PAT-IO-INPUT-SET-v0.1', header['manifest'])
            changed['header'] = canonical(header); changed['bundleDigest'] = bundle.bundle_digest(changed['header'])
            with self.subTest(raw=raw), self.assertRaises(bundle.IoRunBundleError): self.parse(changed)
        for raw in (b' '+self.original['header'], b'{"profile":1,"profile":2}'):
            changed = self.original | dict(header=raw, bundleDigest=bundle.bundle_digest(raw))
            with self.assertRaises(bundle.IoRunBundleError): self.parse(changed)

    def test_exact_per_document_and_header_limits_are_not_widened(self):
        raw = b'"' + b'x'*65534 + b'"'
        self.assertEqual(len(raw), 65536)
        self.assertEqual(len(bundle._document(raw)), 65534)
        self.assertTrue(bundle.bundle_digest(raw).startswith('sha256:'))
        with patch.object(bundle, 'parse_json', side_effect=AssertionError('oversized parse')):
            with self.assertRaisesRegex(bundle.IoRunBundleError, 'DOCUMENT'): bundle._document(raw+b' ')
            with self.assertRaisesRegex(bundle.IoRunBundleError, 'HEADER'): bundle.bundle_digest(raw+b' ')
        changed = copy.deepcopy(self.original); changed['documents']['cases/00.json'] = raw+b' '
        with self.assertRaisesRegex(bundle.IoRunBundleError, 'DOCUMENT'): self.parse(changed)
        self.assertEqual(bundle.MAX_DOCUMENTS, 39)
        self.assertEqual(bundle.MAX_INPUT_BYTES, 2555904)

    def test_input_total_reference_counts_and_hash_fields_are_checked(self):
        mutations = [lambda h: h.update(inputBytes=True), lambda h: h.update(inputBytes=2555905),
            lambda h: h.update(inputBytes=h['inputBytes']-1), lambda h: h['manifest'][0].update(bytes=True),
            lambda h: h['manifest'][0].update(sha256='0'*64), lambda h: h['manifest'].pop(),
            lambda h: h['manifest'].__setitem__(1, h['manifest'][0]),
            lambda h: h.update(inputSetDigest='sha256:'+'0'*64), lambda h: h.update(matrixDigest='sha256:'+'0'*64),
            lambda h: h.update(extra=True)]
        for mutate in mutations:
            changed = copy.deepcopy(self.original); header = json.loads(changed['header']); mutate(header)
            changed['header'] = canonical(header); changed['bundleDigest'] = bundle.bundle_digest(changed['header'])
            with self.subTest(mutate=mutate), self.assertRaises(bundle.IoRunBundleError): self.parse(changed)

    def test_case_inventory_and_matrix_associations_cannot_be_reordered_or_dropped(self):
        mutations = [lambda h,d: h['caseIds'].pop(), lambda h,d: h['caseIds'].reverse(),
            lambda h,d: h['caseIds'].__setitem__(1,h['caseIds'][0]),
            lambda h,d: h.update(caseIds=h['caseIds']+['sha256:'+('%064x'%i) for i in range(3)]),
            lambda h,d: d['cases/00.json'].update(expected_case=d['cases/01.json']['expected_case']),
            lambda h,d: d['cases/00.json']['expected_setup']['installation'].update(boardId='changed'),
            lambda h,d: d['inputs/matrix.json'].update(artifactDigest='sha256:'+'0'*64)]
        for mutate in mutations:
            changed = self.alter(mutate)
            with self.subTest(mutate=mutate), self.assertRaises(bundle.IoRunBundleError): self.parse(changed)

    def test_original_authority_and_deployment_are_explicit_closed_inputs(self):
        for key, value in [('principal', 'other'), ('initialRegistryRevision', True), ('initialGrants', []),
                ('grantChanges', [{}]), ('extra', True), ('deployment', 'other')]:
            changed = self.alter(lambda h,d: d['inputs/authority.json'].update({key:value}))
            with self.subTest(key=key), self.assertRaises(bundle.IoRunBundleError): self.parse(changed)
        with self.assertRaisesRegex(bundle.IoRunBundleError, 'AUTHORITY'):
            bundle.prepare_io_run_bundle(context=self.context | dict(deployment='other'), **self.options)
        changed = self.alter(lambda h,d: d['inputs/installation.json']['topology'].update(deployment='other'))
        with self.assertRaisesRegex(bundle.IoRunBundleError, 'DEPLOYMENT'): self.parse(changed)

    def test_rehashed_authority_change_is_not_fresh_expected_case_setup(self):
        changed = self.alter(lambda h,d: d['inputs/authority.json'].update(initialRegistryRevision=14))
        self.assertEqual(self.parse(changed)['authority']['initialRegistryRevision'], 14)
        with self.assertRaisesRegex(bundle.IoRunBundleError, 'FRESH_MISMATCH'): self.fresh(changed)

    def test_rehashed_false_setup_can_be_structural_but_cannot_pass_fresh_validation(self):
        changed = self.alter(lambda h,d: d['cases/00.json']['expected_setup']['static_contract'].update(forged=True))
        self.assertTrue(self.parse(changed)['expected_cases'][0]['expected_setup']['static_contract']['forged'])
        with self.assertRaisesRegex(bundle.IoRunBundleError, 'FRESH_MISMATCH'): self.fresh(changed)

    def test_fresh_validation_rechecks_current_source_and_implementation_identity(self):
        with patch('hms.pat_io_group_worker._source_identity', return_value={}):
            with self.assertRaisesRegex(PatError, 'PAT_IO_GROUP_IMPLEMENTATION_CHANGED'): self.fresh()
        parsed = self.parse(); identity = parsed['expected_inputs']['implementation'] | dict(workerDigest='sha256:'+'f'*64)
        with patch('hms.pat_io_group_worker._identities', return_value=identity):
            with self.assertRaisesRegex(bundle.IoRunBundleError, 'FRESH_MISMATCH'): self.fresh()

    def test_group_limits_keep_original_exact_types_and_maxima(self):
        from hms.pat_io_combined_matrix import CEILINGS
        self.assertEqual(bundle.CEILINGS, CEILINGS)
        for key, value in [('maxCases', True), ('maxCases', 33), ('maxWallMs', 60001), ('maxDerivedBytes', 20*1024*1024+1)]:
            changed = self.alter(lambda h,d: d['inputs/matrix.json']['limits'].update({key:value}))
            with self.subTest(key=key), self.assertRaisesRegex(bundle.IoRunBundleError, 'LIMITS'): self.parse(changed)
        limits = CEILINGS | dict(maxRecords=4095)
        smaller = bundle.prepare_io_run_bundle(context=self.context, **self.options, limits=limits)
        self.assertEqual(self.fresh(smaller)['expected_inputs']['matrix']['limits'], limits)
        with self.assertRaises(PatError):
            bundle.prepare_io_run_bundle(context=self.context, **self.options, limits=CEILINGS | dict(maxCases=29))

    def test_retained_example_has_exact_pre_run_documents_and_no_attestation_claim(self):
        # Retain an actual bounded builder result for downstream supervisor work.
        output = Path(os.environ['TMPDIR']) / 'io-run-bundle-example'; output.mkdir(mode=0o700)
        (output/'header.json').write_bytes(self.original['header'])
        (output/'trusted-context.json').write_bytes(canonical(self.context))
        for name, raw in self.original['documents'].items():
            p = output/name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(raw)
        parsed = self.fresh()
        (output/'association.json').write_bytes(canonical(dict(bundleDigest=self.original['bundleDigest'],
            expectedCases=len(parsed['expected_cases']), freshReconstructionMatched=True,
            configurationAttested=False, runAssociationAttested=False, implementationIdentityAttested=False,
            actualAggregateStorageEnforced=False, physicalMeasurementChecked=False, qualificationPassed=False)))
        self.assertEqual(len([p for p in output.rglob('*') if p.is_file()]), 40)


if __name__ == '__main__': unittest.main()
