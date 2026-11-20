"""Exact pages, bounded memo storage and unchanged validation/durable writes."""
import copy
import hashlib
import unittest
from unittest.mock import patch

from hms import pat_io_page_encoding as memo
from hms import pat_io_trials as trials
from hms import pat_io_configuration_capture as configuration
from hms.contracts import ContractError, canonical
from hms.pat_contracts import PatError
from test_pat_io_encoding import IoEncodingTests


def page(value='sample', tag='text'):
    return dict(store='authority', table='sample', columns=['value'], first=0,
        totalRows=1, rows=[[dict(type=tag, value=value)]])


class Cursor:
    def __init__(self, rows): self.rows = rows
    def fetchone(self): return self.rows[0]
    def fetchall(self): return self.rows
    def fetchmany(self, n): return self.rows[:n]


class Database:
    """Closed response fixture; no SQLite or runtime is created by these tests."""
    def __init__(self, rows):
        self.rows, self.columns, self.queries = rows, ['value'], []
        self.count_override = self.size_override = self.type_override = None

    def execute(self, sql, params=()):
        self.queries.append((sql, params))
        if sql.startswith('PRAGMA'):
            return Cursor([(i, name) for i, name in enumerate(self.columns)])
        if sql.startswith('SELECT count'):
            return Cursor([(len(self.rows) if self.count_override is None else self.count_override,)])
        if sql.startswith('SELECT DISTINCT'):
            types = self.type_override or [('blob' if type(r[0]) is bytes else 'integer' if type(r[0]) is int else 'text',) for r in self.rows]
            return Cursor(list(dict.fromkeys(types)))
        if sql.startswith('SELECT max'):
            size = max((len(v if type(v) is bytes else str(v).encode()) for r in self.rows for v in r), default=None)
            return Cursor([(size if self.size_override is None else self.size_override,)])
        return Cursor(self.rows[:params[-1]])


class PageEncodingTests(unittest.TestCase):
    def engine(self, configured=False, name='engine'):
        engine = IoEncodingTests.engine(self, configured, name)
        engine._page_encodings = memo.PageEncodings()
        return engine

    def test_exact_encoding_reordered_keys_detachment_and_changed_content(self):
        cache = memo.PageEncodings(); value = page('µ'); original = copy.deepcopy(value)
        data = canonical(dict(profile='profile:a', kind='table_page', value=value))
        with patch.object(memo, 'canonical', wraps=canonical) as encode:
            first = cache.encode('profile:a', value)
            self.assertEqual(first, (data, hashlib.sha256(data).hexdigest()))
            self.assertEqual(cache.encode('profile:a', dict(reversed(list(value.items())))), first)
            self.assertEqual(encode.call_count, 1)
            value['rows'][0][0]['value'] = 'changed'
            self.assertNotEqual(cache.encode('profile:a', value), first)
            self.assertEqual(cache.encode('profile:a', original), first)
            self.assertEqual(encode.call_count, 2)

    def test_profiles_metadata_columns_offsets_counts_and_cell_tags_separate_keys(self):
        cache = memo.PageEncodings(); base = page()
        variants = [('profile:b', base)]
        for key, value in [('store', 'board'), ('table', 'other'), ('columns', ['other']),
                ('first', 8), ('totalRows', 2)]:
            variants.append(('profile:a', base | {key: value}))
        changed = page(tag='blob-utf8'); variants.append(('profile:a', changed))
        changed = copy.deepcopy(base); del changed['store']; changed['projection'] = 'complete'
        variants.append(('profile:a', changed))
        first = cache.encode('profile:a', base)
        for profile, value in variants:
            with self.subTest(profile=profile, value=value):
                actual = cache.encode(profile, value)
                expected = canonical(dict(profile=profile, kind='table_page', value=value))
                self.assertEqual(actual[0], expected)
                self.assertNotEqual(actual, first)

    def test_numeric_aliases_and_unsupported_shapes_keep_original_canonical_path(self):
        cache = memo.PageEncodings()
        cache.encode('profile', page(1, 'integer'))
        values = [page(True, 'integer'), page(1.0, 'integer'), page('1', 'integer'),
            page() | {'first': True}, page() | {'totalRows': 1.0}, page() | {'extra': None}]
        with patch.object(memo, 'canonical', wraps=canonical) as encode:
            for value in values:
                actual = cache.encode('profile', value)[0]
                self.assertEqual(actual, canonical(dict(profile='profile', kind='table_page', value=value)))
            self.assertEqual(encode.call_count, len(values))

    def test_invalid_and_oversized_values_preserve_refusal_without_cache_entry(self):
        cache = memo.PageEncodings(); cycle = []; cycle.append(cycle)
        values = [page('x' * 65536), page(2**53, 'integer'), page('\ud800'), page() | {'rows': cycle},
            page() | {'extra': object()}, page() | {'columns': ('value',)}]
        for value in values:
            with self.subTest(value_type=type(value)):
                with self.assertRaises(ContractError) as original:
                    canonical(dict(profile='profile', kind='table_page', value=value))
                with self.assertRaises(ContractError) as actual:
                    cache.encode('profile', value)
                self.assertEqual(str(actual.exception), str(original.exception))
                self.assertEqual((len(cache._entries), cache.encoding_bytes), (0, 0))

    def test_entry_and_byte_eviction_only_recompute_exact_encodings(self):
        cache = memo.PageEncodings(); first = cache.encode('profile', page('old'))
        for i in range(memo.MAX_PAGES):
            cache.encode('profile', page(str(i)))
            self.assertLessEqual(len(cache._entries), memo.MAX_PAGES)
            self.assertLessEqual(cache.encoding_bytes, memo.MAX_ENCODING_BYTES)
        with patch.object(memo, 'canonical', wraps=canonical) as encode:
            self.assertEqual(cache.encode('profile', page('old')), first)
            self.assertEqual(encode.call_count, 1)
        cache = memo.PageEncodings(); first = cache.encode('profile', page('old'))
        for i in range(70):
            cache.encode('profile', page(str(i) + 'x' * 16000))
            self.assertLessEqual(cache.encoding_bytes, memo.MAX_ENCODING_BYTES)
        self.assertLess(len(cache._entries), 70)
        self.assertEqual(cache.encoding_bytes, sum(len(x[0]) for x in cache._entries.values()))
        with patch.object(memo, 'canonical', wraps=canonical) as encode:
            self.assertEqual(cache.encode('profile', page('old')), first)
            self.assertEqual(encode.call_count, 1)

    def test_base_and_both_configured_streams_keep_exact_records_and_durability(self):
        for configured in (False, True):
            engine = self.engine(configured, str(configured)); value = page()
            writers = [(engine._write, engine.record_directory, engine._record_profile)]
            if configured: writers.append((engine._configuration_write, engine._configuration_directory, configuration.PROFILE))
            with patch.object(memo, 'canonical', wraps=canonical) as encode, \
                 patch.object(trials.os, 'fsync', wraps=trials.os.fsync) as sync:
                for write, directory, profile in writers:
                    first = write('table_page', value, reuse=True)
                    second = write('table_page', value, reuse=True)
                    self.assertEqual(first, second)
                    second['path'] = 'caller-mutated'
                    self.assertEqual(write('table_page', value, reuse=True), first)
                    self.assertEqual((directory / first['path']).read_bytes(),
                        canonical(dict(profile=profile, kind='table_page', value=value)))
                self.assertEqual(encode.call_count, len(writers))
                self.assertEqual(sync.call_count, len(writers))
            self.assertEqual(sum(e == 'check' for e in engine._group_budget.events), 3 * len(writers))
            self.assertEqual(len([e for e in engine._group_budget.events if type(e) is tuple]), len(writers))

    def test_warm_page_keeps_budget_checks_and_combined_limit_precedence(self):
        for configured in (False, True):
            engine = self.engine(configured, str(configured)); value = page()
            first = engine._write('table_page', value, reuse=True)
            with patch.object(trials, 'MAX_RECORDS', 1):
                self.assertEqual(engine._write('table_page', value, reuse=True), first)
                engine._started -= 61
                with self.assertRaisesRegex(PatError, 'PAT_IO_TRIAL_WALL_LIMIT'):
                    engine._write('table_page', value, reuse=True)
                if configured:
                    with self.assertRaisesRegex(PatError, 'PAT_IO_CONFIGURATION_EVIDENCE_LIMIT'):
                        engine._write('table_page', page('new'), reuse=True)
            engine._group_budget.stopped = True
            with self.assertRaisesRegex(PatError, 'TEST_GROUP_STOPPED'):
                engine._write('table_page', value, reuse=True)

    def test_encoded_page_does_not_publish_or_refund_after_write_failure(self):
        for mode in ('existing', 'fsync'):
            engine = self.engine(True, mode); path = engine.record_directory / '000000.json'
            if mode == 'existing': path.write_bytes(b'retained')
            with patch.object(trials.os, 'fsync', side_effect=OSError('injected sync')):
                with self.assertRaises(FileExistsError if mode == 'existing' else OSError):
                    engine._write('table_page', page(), reuse=True)
            self.assertEqual((engine.records, engine.output_bytes, engine._objects), ([], 0, {}))
            self.assertEqual(len(engine._page_encodings._entries), 1)
            self.assertEqual(len([e for e in engine._group_budget.events if type(e) is tuple]), 1)
            self.assertEqual(path.read_bytes(), b'retained' if mode == 'existing' else
                canonical(dict(profile=engine._record_profile, kind='table_page', value=page())))

    def test_trial_table_rereads_shape_counts_sizes_and_cells_on_warm_page(self):
        engine = self.engine(); db = Database([('a',)])
        first = engine._table(db, 'authority', 'sample', ('value', 8)); queries = list(db.queries)
        self.assertEqual(engine._table(db, 'authority', 'sample', ('value', 8)), first)
        self.assertEqual(db.queries, queries + queries)
        for attr, value, code in [('columns', ['changed'], 'STORAGE_SHAPE'), ('count_override', 9, 'STORAGE_LIMIT'),
                ('count_override', 2, 'STORAGE_CHANGED'), ('size_override', 65537, 'STORAGE_LIMIT'),
                ('rows', [(1.0,)], 'STORAGE_TYPE')]:
            original = getattr(db, attr); setattr(db, attr, value)
            with self.subTest(attr=attr, value=value), self.assertRaisesRegex(PatError, code):
                engine._table(db, 'authority', 'sample', ('value', 8))
            setattr(db, attr, original)
        db.rows = [('b',)]
        self.assertNotEqual(engine._table(db, 'authority', 'sample', ('value', 8))['pages'], first['pages'])

    def test_configuration_table_revalidates_document_and_storage_classes_on_hit(self):
        engine = self.engine(True); db = Database([(b'{"a":1}',)])
        with patch.object(configuration, 'parse_json', wraps=configuration.parse_json) as parse:
            first = engine._configuration_table(db, 'sample', ('value', 'blob', 8)); queries = list(db.queries)
            self.assertEqual(engine._configuration_table(db, 'sample', ('value', 'blob', 8)), first)
            self.assertEqual(db.queries, queries + queries)
            self.assertEqual(parse.call_count, 2)
        for attr, value, code in [('type_override', [('text',)], 'STORAGE_TYPE'),
                ('size_override', 65537, 'STORAGE_LIMIT'), ('count_override', 2, 'STORAGE_CHANGED'),
                ('columns', ['changed'], 'STORAGE_SHAPE'), ('rows', [(b'{ "a":1}',)], 'STORAGE_DOCUMENT')]:
            original = getattr(db, attr); setattr(db, attr, value)
            with self.subTest(attr=attr), self.assertRaisesRegex(PatError, code):
                engine._configuration_table(db, 'sample', ('value', 'blob', 8))
            setattr(db, attr, original)
        self.assertEqual(len(engine.configuration_records), 1)
