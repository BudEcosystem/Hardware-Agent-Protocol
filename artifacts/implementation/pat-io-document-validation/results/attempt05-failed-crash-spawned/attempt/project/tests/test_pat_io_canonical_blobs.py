"""Exact validation reuse, original refusals and fresh storage observations."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from hms import contracts
from hms import pat_io_canonical_blobs as memo
from hms import pat_io_configuration_capture as configuration
from hms.pat_contracts import PatError
from test_pat_io_page_encoding import Database, PageEncodingTests


class CanonicalBlobTests(unittest.TestCase):
    def check(self, cache, value, canonical=None, parser=None):
        return cache.is_canonical(value, canonical=canonical or contracts.canonical,
                                  parser=parser or contracts.parse_json)

    def engine(self, name='engine'):
        return PageEncodingTests.engine(self, True, name)

    def test_identical_bytes_reuse_only_successful_validation(self):
        cache = memo.CanonicalBlobs()
        with patch.object(cache, '_validate', wraps=cache._validate) as validate:
            self.assertTrue(self.check(cache, b'{"a":1}'))
            self.assertTrue(self.check(cache, bytes(bytearray(b'{"a":1}'))))
            self.assertEqual(validate.call_count, 1)
            self.assertTrue(self.check(cache, b'{"a":2}'))
            self.assertEqual(validate.call_count, 2)
        self.assertEqual(cache.retained_bytes, 14)
        self.assertTrue(all(type(key) is bytes and value is True for key, value in cache._entries.items()))

    def test_original_nonbyte_types_never_enter_cache(self):
        class BytesSubclass(bytes):
            pass
        cache = memo.CanonicalBlobs()
        for value in ('{}', bytearray(b'{}'), memoryview(b'{}'), {}, None, BytesSubclass(b'{}')):
            with self.subTest(kind=type(value).__name__):
                self.assertFalse(self.check(cache, value))
        self.assertEqual((len(cache._entries), cache.retained_bytes), (0, 0))

    def test_canonical_scalars_unicode_and_numbers_keep_original_identity(self):
        cache = memo.CanonicalBlobs()
        for value in (None, True, False, 0, 1, 0.1, '\nµ😀', {'😀':1,'\ue000':2}, [1,'x',False]):
            wire = contracts.canonical(value)
            self.assertTrue(self.check(cache, wire))
            self.assertTrue(self.check(cache, wire))
        for wire in (b'1.0', b'1e0', b' {"a":1}', b'{"b":2,"a":1}', b'"\\u0061"'):
            self.assertFalse(self.check(cache, wire))
            self.assertNotIn(wire, cache._entries)

    def test_malformed_inputs_keep_original_exception_and_are_not_published(self):
        cache = memo.CanonicalBlobs()
        for wire in (b'', b'not-json', b'{"a":1,"a":2}', b'-0', b'-0.0', b'NaN', b'1e1000',
                     b'9007199254740992', b'0.10000000000000001', b'"\xff"', b'"\\ud800"', b' '*65537):
            with self.subTest(wire=wire[:40]):
                with self.assertRaises(contracts.ContractError) as expected:
                    contracts.canonical(contracts.parse_json(wire))
                for _ in range(2):
                    with self.assertRaises(contracts.ContractError) as actual:
                        self.check(cache, wire)
                    self.assertEqual(str(actual.exception), str(expected.exception))
                self.assertNotIn(wire, cache._entries)

    def test_lowered_document_tree_bounds_reject_warm_inputs(self):
        for name, limit in [('MAX_BYTES', 2), ('MAX_DEPTH', 0), ('MAX_NODES', 1)]:
            cache = memo.CanonicalBlobs(); wire = b'{"a":[1]}'
            self.assertTrue(self.check(cache, wire))
            with patch.object(contracts, name, limit):
                with self.assertRaises(contracts.ContractError) as expected:
                    contracts.canonical(contracts.parse_json(wire))
                with self.assertRaises(contracts.ContractError) as actual:
                    self.check(cache, wire)
                self.assertEqual(str(actual.exception), str(expected.exception))
                self.assertEqual((len(cache._entries), cache.retained_bytes), (0, 0))

    def test_entry_limit_and_lru_refresh_do_not_widen(self):
        cache = memo.CanonicalBlobs()
        wires = [contracts.canonical({'i':i}) for i in range(memo.MAX_ENTRIES+1)]
        for wire in wires[:-1]:
            self.assertTrue(self.check(cache, wire))
        self.assertTrue(self.check(cache, wires[0]))
        self.assertTrue(self.check(cache, wires[-1]))
        self.assertIn(wires[0], cache._entries)
        self.assertNotIn(wires[1], cache._entries)
        self.assertEqual(len(cache._entries), 64)
        self.assertEqual(cache.retained_bytes, sum(map(len, cache._entries)))

    def test_byte_limit_evicts_before_retaining_new_document(self):
        cache = memo.CanonicalBlobs()
        wires = [contracts.canonical(str(i)+'x'*50000) for i in range(4)]
        for wire in wires:
            self.assertTrue(self.check(cache, wire))
            self.assertLessEqual(cache.retained_bytes, 128*1024)
            self.assertEqual(cache.retained_bytes, sum(map(len, cache._entries)))
        self.assertNotIn(wires[0], cache._entries)
        self.assertEqual(len(cache._entries), 2)
        with patch.object(cache, '_validate', wraps=cache._validate) as validate:
            self.assertTrue(self.check(cache, wires[0]))
            self.assertEqual(validate.call_count, 1)

    def test_instances_do_not_share_retained_documents(self):
        first, second = memo.CanonicalBlobs(), memo.CanonicalBlobs()
        self.assertTrue(self.check(first, b'{}'))
        self.assertEqual(second.retained_bytes, 0)
        self.assertTrue(self.check(second, b'{}'))
        self.assertIsNot(first._entries, second._entries)

    def test_changed_caller_parser_or_encoder_uses_original_path(self):
        for which in ('parser','canonical'):
            cache = memo.CanonicalBlobs(); wire = b'{"a":1}'
            self.assertTrue(self.check(cache, wire))
            original = contracts.parse_json if which == 'parser' else contracts.canonical
            with patch.object(configuration, 'parse_json' if which == 'parser' else 'canonical', wraps=original) as changed:
                for _ in range(2):
                    self.assertTrue(self.check(cache, wire, **{which:changed}))
                self.assertEqual(changed.call_count, 2)
            self.assertEqual((len(cache._entries), cache.retained_bytes), (0, 0))

    def test_changed_transitive_object_parser_refuses_prior_hit(self):
        cache = memo.CanonicalBlobs(); wire = b'{"a":1}'
        self.assertTrue(self.check(cache, wire))
        with patch.object(contracts, '_object', side_effect=contracts.ContractError('changed parser')):
            with self.assertRaisesRegex(contracts.ContractError, 'changed parser'):
                self.check(cache, wire)
        self.assertEqual((len(cache._entries), cache.retained_bytes), (0, 0))
        self.assertTrue(self.check(cache, wire))

    def test_in_place_parser_code_change_refuses_prior_hit(self):
        cache = memo.CanonicalBlobs(); wire = b'{"a":1}'
        self.assertTrue(self.check(cache, wire))
        def replacement(pairs):
            raise ContractError('changed object code')
        original = contracts._object.__code__
        try:
            contracts._object.__code__ = replacement.__code__
            with self.assertRaisesRegex(contracts.ContractError, 'changed object code'):
                self.check(cache, wire)
        finally:
            contracts._object.__code__ = original
        self.assertEqual((len(cache._entries), cache.retained_bytes), (0, 0))

    def test_encoder_escape_table_change_does_not_reuse_prior_result(self):
        cache = memo.CanonicalBlobs(); wire = b'"\\n"'
        self.assertTrue(self.check(cache, wire))
        with patch.dict(memo.encoder._ESCAPE_DCT, {'\n':'X'}):
            self.assertFalse(self.check(cache, wire))
            self.assertEqual((len(cache._entries), cache.retained_bytes), (0, 0))
        self.assertTrue(self.check(cache, wire))

    def test_capacity_constant_changes_disable_reuse_instead_of_widening(self):
        for name, value in [('MAX_ENTRIES',128),('MAX_RETAINED_BYTES',1024*1024),('MAX_DOCUMENT_BYTES',65537)]:
            cache = memo.CanonicalBlobs(); self.assertTrue(self.check(cache, b'{}'))
            with patch.object(memo, name, value):
                self.assertTrue(self.check(cache, b'{}'))
                self.assertEqual((len(cache._entries), cache.retained_bytes), (0, 0))

    def test_dependency_change_during_validation_prevents_publication(self):
        cache = memo.CanonicalBlobs(); validate = cache._validate
        def changed(value, canonical, parser):
            result = validate(value, canonical, parser)
            contracts.MAX_NODES = 1
            return result
        with patch.object(contracts, 'MAX_NODES', contracts.MAX_NODES), patch.object(cache, '_validate', changed):
            self.assertTrue(self.check(cache, b'{"a":1}'))
            self.assertEqual((len(cache._entries), cache.retained_bytes), (0, 0))

    def test_warm_validation_still_rereads_every_storage_query(self):
        engine = self.engine(); db = Database([(b'{"a":1}',)])
        first = engine._configuration_table(db, 'sample', ('value','blob',8))
        queries = list(db.queries); cache = engine._canonical_blob_checks
        with patch.object(cache, '_validate', wraps=cache._validate) as validate:
            self.assertEqual(engine._configuration_table(db, 'sample', ('value','blob',8)), first)
            self.assertEqual(validate.call_count, 0)
        self.assertEqual(db.queries, queries+queries)
        self.assertEqual(len(engine.configuration_records), 1)

    def test_warm_storage_still_refuses_changed_metadata(self):
        engine = self.engine(); db = Database([(b'{"a":1}',)])
        engine._configuration_table(db, 'sample', ('value','blob',8))
        for attr, value, code in [('columns',['wrong'],'STORAGE_SHAPE'),('count_override',9,'STORAGE_LIMIT'),
                                  ('count_override',2,'STORAGE_CHANGED'),('size_override',65537,'STORAGE_LIMIT'),
                                  ('type_override',[('text',)],'STORAGE_TYPE')]:
            original = getattr(db,attr); setattr(db,attr,value)
            try:
                with self.subTest(attr=attr), self.assertRaisesRegex(PatError,code):
                    engine._configuration_table(db,'sample',('value','blob',8))
            finally:
                setattr(db,attr,original)

    def test_changed_fresh_blob_bytes_are_validated_before_publication(self):
        engine = self.engine(); db = Database([(b'{"a":1}',)])
        first = engine._configuration_table(db,'sample',('value','blob',8))
        db.rows = [(b'{"a":2}',)]
        self.assertNotEqual(engine._configuration_table(db,'sample',('value','blob',8)),first)
        db.rows = [(b'{ "a":1}',)]
        with self.assertRaisesRegex(PatError,'STORAGE_DOCUMENT'):
            engine._configuration_table(db,'sample',('value','blob',8))
        db.rows = [(b'{"a":1,"a":2}',)]
        with self.assertRaisesRegex(contracts.ContractError,'duplicate'):
            engine._configuration_table(db,'sample',('value','blob',8))
        self.assertEqual(len(engine.configuration_records),2)

    def test_validated_bytes_do_not_hide_failed_durable_publication(self):
        engine = self.engine(); db = Database([(b'{"a":1}',)])
        with patch.object(configuration.os,'fsync',side_effect=OSError('injected sync')):
            with self.assertRaisesRegex(OSError,'injected sync'):
                engine._configuration_table(db,'sample',('value','blob',8))
        self.assertEqual(engine.configuration_records,[])
        self.assertTrue((engine._configuration_directory/'000000.json').exists())
        with self.assertRaises(FileExistsError):
            engine._configuration_table(db,'sample',('value','blob',8))
        self.assertEqual(engine.configuration_records,[])

    def test_repeated_document_work_observation_has_no_latency_acceptance_threshold(self):
        wire = contracts.canonical({'sensor_'+str(i):{'range':[0,1000],'unit':'mV','metadata':'x'*20} for i in range(32)})
        repeats = 1000
        started = time.monotonic_ns(); cpu = time.process_time_ns()
        for _ in range(repeats):
            self.assertTrue(memo.CanonicalBlobs._validate(wire,contracts.canonical,contracts.parse_json))
        baseline = dict(wallNs=time.monotonic_ns()-started,cpuNs=time.process_time_ns()-cpu)
        class Counted(memo.CanonicalBlobs):
            calls = 0
            def _validate(self, value, canonical, parser):
                self.calls += 1
                return super()._validate(value, canonical, parser)
        cache = Counted(); started = time.monotonic_ns(); cpu = time.process_time_ns()
        for _ in range(repeats):
            self.assertTrue(self.check(cache,wire))
        observed = dict(wallNs=time.monotonic_ns()-started,cpuNs=time.process_time_ns()-cpu)
        self.assertEqual((len(cache._entries),cache.retained_bytes),(1,len(wire)))
        self.assertEqual(cache.calls,1)
        directory = Path(tempfile.gettempdir())/self._testMethodName
        directory.mkdir(mode=0o700)
        (directory/'work-observation.json').write_text(json.dumps(dict(scope='Single bounded repeated-document observation; no deployment or deadline guarantee.',
            repeats=repeats,documentBytes=len(wire),original=baseline,reuse=observed,
            originalFullValidations=repeats,reuseFullValidations=cache.calls,latencyAcceptanceThreshold=False),indent=2)+'\n')
