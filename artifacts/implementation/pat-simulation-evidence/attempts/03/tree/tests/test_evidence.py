import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

import pat_simulation_evidence as e
from hms.contracts import canonical
from hms.journal import Context

ROOT = Path(__file__).resolve().parents[1]
RETAINED = ROOT / 'retained'
# Explicit historical test trust, never an inference that current live code is
# qualified. The service's complete implementation pin is calculated at setup.
SOURCE_PIN = 'sha256:' + hashlib.sha256(Path(e.__file__).read_bytes() +
    (ROOT / 'before.json').read_bytes()).hexdigest()


def sample(case='case-04'):
    acquired = e.read_retained_attempt(RETAINED / case)
    cap = json.loads(acquired['files'][0]['body'])['value']
    trust = {'profile': e.TRUST_PROFILE, 'deployment': cap['evaluationEnvironment']['deployment'],
        'runId': 'historical:' + case, 'evaluator': {'evaluatorId': 'sim:retained-fan',
            'implementationDigest': SOURCE_PIN, 'policyDigest': cap['identities']['policyDigest'],
            'requiredChecks': [{'id': key, 'category': category} for key, category in e.CHECKS],
            'evidenceProfile': e.PROFILE}, 'input': cap}
    return trust, acquired


def bundle(case='case-04'):
    trust, source = sample(case)
    return trust, e.reduce_attempt(trust, source['result'], source['files'])


def receipt(trust, result):
    cap = trust['input']
    return {'protocol': 'hms.pat-evaluation/0.1', 'runId': trust['runId'],
        'artifactDigest': e.pat_digest(cap['artifact']),
        'artifactDomainDigest': e.hash_document(b'HMS-PAT-DOMAIN-v0.1', cap['artifact']),
        'evaluator': trust['evaluator'], 'environment': cap['evaluationEnvironment'],
        'environmentDigest': cap['environmentDigest'], 'outcome': 'passed', 'result': result,
        'evaluatorError': None, 'physicalObjectiveVerified': False}


def authorizer(functions=()):
    def check(action, one, two, database, trigger):
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ) and database in (None, 'main'):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and two in functions:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    return check


def alter_record(source, predicate, mutate):
    """Rehash tampered raw records/indexes to test semantics beyond hash checks.

    Not qualification evidence. Every mutated specimen is created only in memory
    from actual retained original-worker output and is required to be rejected.
    """
    source = copy.deepcopy(source)
    changed = False
    for file in source['files']:
        row = json.loads(file['body'])
        if not changed and predicate(row):
            mutate(row); file['body'] = canonical(row); changed = True
    assert changed
    bypath = {f['path']: f for f in source['files']}
    for file in source['files']:
        row = json.loads(file['body'])
        if row['kind'] == 'evidence_index':
            for ref in row['value']['records']:
                raw = bypath[ref['path']]['body']
                ref['bytes'] = len(raw); ref['sha256'] = hashlib.sha256(raw).hexdigest()
            file['body'] = canonical(row)
    result = json.loads(source['result'])
    for ref in result['evidencePages']:
        raw = bypath[ref['path']]['body']
        ref['bytes'] = len(raw); ref['sha256'] = hashlib.sha256(raw).hexdigest()
    result['outputBytes'] = sum(len(f['body']) for f in source['files'])
    result['totalDiskBytes'] = result['outputBytes'] + result['scratchBytes']
    source['result'] = canonical(result)
    return source


class ReducerTests(unittest.TestCase):
    def test_actual_original_full_matrix_and_alias_runs(self):
        for case, count, operations in [('case-04', 27, 25), ('case-01', 10, 9)]:
            with self.subTest(case=case):
                trust, reduced = bundle(case)
                manifest = json.loads(reduced['documents'][reduced['groupDigest']])
                self.assertEqual(len(manifest['cases']), count)
                capsules = [json.loads(reduced['documents'][ref['digest']]) for ref in manifest['cases']]
                self.assertEqual(sum(len(c['observed']['operationIds']) for c in capsules), operations)
                self.assertEqual(manifest['closureBytes'], sum(map(len, reduced['documents'].values())))
                self.assertEqual(manifest['closureDocuments'], len(reduced['documents']))
                self.assertEqual({c['caseId'] for c in capsules if c['categories'] == ['fault']},
                                 {'lifecycle:' + f for f in e.FAULTS})
                # Raw nondeterministic IDs and records stay byte-identical.
                acquired = e.read_retained_attempt(RETAINED / case)
                for f in acquired['files']:
                    self.assertEqual(reduced['documents'][e.digest(f['body'])], f['body'])

    def test_actual_retained_negative_outcomes_never_qualify(self):
        seen = []
        for path in sorted(RETAINED.iterdir()):
            if path.name in ('case-01', 'case-04'):
                continue
            source = e.read_retained_attempt(path)
            result = json.loads(source['result']); seen.append(result['outcome'])
            # Several budget failures emit no input record; trust cannot be
            # recovered from output. The independent positive capsule still
            # must not turn those actual failed results into a pass.
            trust, _ = sample()
            with self.subTest(case=path.name), self.assertRaises(e.EvidenceError):
                e.reduce_attempt(trust, source['result'], source['files'])
        self.assertEqual(len(seen), 9)
        self.assertIn('failed', seen); self.assertIn('inconclusive', seen)

    def test_byte_corruption_missing_extra_duplicate_and_noncanonical(self):
        trust, source = sample()
        mutations = []
        bad = copy.deepcopy(source); bad['files'][10]['body'] += b' '; mutations.append(bad)
        bad = copy.deepcopy(source); bad['files'].pop(10); mutations.append(bad)
        bad = copy.deepcopy(source); bad['files'].append(bad['files'][-1]); mutations.append(bad)
        bad = copy.deepcopy(source); bad['files'][5] = bad['files'][4]; mutations.append(bad)
        bad = copy.deepcopy(source); bad['result'] += b'\n'; mutations.append(bad)
        for bad in mutations:
            with self.assertRaises(e.EvidenceError):
                e.reduce_attempt(trust, bad['result'], bad['files'])

    def test_rehashed_wrong_receipt_level_boolean_and_extra_effect(self):
        trust, source = sample()
        cases = [
            (lambda r: r['kind'] == 'operation' and r['value']['label'] == 'final',
             lambda r: r['value']['receipt']['result'].update(level=True)),
            (lambda r: r['kind'] == 'checkpoint',
             lambda r: r['value']['plants']['sim:home-fan'].update(effectCount=999)),
            (lambda r: r['kind'] == 'checkpoint',
             lambda r: r['value']['plants']['sim:microscope'].update(value=1)),
            (lambda r: r['kind'] == 'compiled_request',
             lambda r: r['value']['plan']['request']['procedure']['steps'][0]['request']['intent']['arguments'].update(level=1)),
        ]
        for predicate, mutate in cases:
            bad = alter_record(source, predicate, mutate)
            with self.assertRaises(e.EvidenceError):
                e.reduce_attempt(trust, bad['result'], bad['files'])

    def test_rehashed_event_gap_missing_child_and_fake_loss_boundary(self):
        trust, source = sample()
        cases = [
            (lambda r: r['kind'] == 'operation_events', lambda r: r['value']['page']['events'][1].update(sequence=99)),
            (lambda r: r['kind'] == 'checkpoint' and r['value']['label'] == 'final',
             lambda r: r['value']['procedure']['steps'][0].update(operationId=None)),
            (lambda r: r['kind'] == 'operation' and r['value']['trial'] == 26 and r['value']['label'] == 'before_reopen',
             lambda r: r['value']['receipt'].update(state='pending', result=None)),
            (lambda r: r['kind'] == 'trial_result' and r['value']['trial'] == 26,
             lambda r: r['value']['events'][1].update(realProcessCrash=True)),
        ]
        for predicate, mutate in cases:
            bad = alter_record(source, predicate, mutate)
            with self.assertRaises(e.EvidenceError):
                e.reduce_attempt(trust, bad['result'], bad['files'])

    def test_rehashed_case_category_refusal_and_environment_drift(self):
        trust, source = sample()
        bad = alter_record(source, lambda r: r['kind'] == 'trial_result' and r['value']['trial'] == 9,
                           lambda r: r['value']['events'][0].update(code='UNRELATED'))
        with self.assertRaises(e.EvidenceError):
            e.reduce_attempt(trust, bad['result'], bad['files'])
        for change in ('configuration', 'matrix', 'producer', 'checks', 'deployment'):
            altered = copy.deepcopy(trust)
            if change == 'configuration': altered['input']['configuration']['revision'] += 1
            if change == 'matrix': altered['input']['caseMatrix']['cases'].pop()
            if change == 'producer': altered['input']['identities']['compilerDigest'] = 'sha256:' + '0' * 64
            if change == 'checks': altered['evaluator']['requiredChecks'].pop()
            if change == 'deployment': altered['deployment'] = 'other:deployment'
            with self.subTest(change=change), self.assertRaises(e.EvidenceError):
                e.reduce_attempt(altered, source['result'], source['files'])

    def test_unhashable_wrong_types_and_float_boolean_are_controlled(self):
        trust, source = sample()
        for path, value in [(('input', 'configuration', 'revision'), 1.0),
                            (('input', 'configuration', 'revision'), True),
                            (('input', 'runtimeLayout'), []), (('evaluator', 'requiredChecks'), {}),
                            (('profile',), {})]:
            altered = copy.deepcopy(trust); node = altered
            for part in path[:-1]: node = node[part]
            node[path[-1]] = value
            with self.assertRaises(e.EvidenceError):
                e.reduce_attempt(altered, source['result'], source['files'])

    def test_no_io_in_exported_pure_reduction(self):
        trust, source = sample()
        with mock.patch('builtins.open', side_effect=AssertionError('filesystem read')), \
             mock.patch.object(Path, 'read_bytes', side_effect=AssertionError('filesystem read')), \
             mock.patch.object(Path, 'read_text', side_effect=AssertionError('filesystem read')), \
             mock.patch('os.open', side_effect=AssertionError('filesystem open')):
            result = e.reduce_attempt(trust, source['result'], source['files'])
        self.assertTrue(result['groupDigest'].startswith('sha256:'))

    def test_acquisition_refuses_symlink_extra_name_and_file_size(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root/'evidence').mkdir()
            original = RETAINED/'case-04/test-return.json'
            (root/'test-return.json').symlink_to(original)
            with self.assertRaises(OSError): e.read_retained_attempt(root)
            (root/'test-return.json').unlink(); (root/'test-return.json').write_bytes(original.read_bytes())
            (root/'evidence/stray').write_bytes(b'x')
            with self.assertRaises(e.EvidenceError): e.read_retained_attempt(root)
            (root/'evidence/stray').unlink(); (root/'evidence/000000.json').write_bytes(b'x'*(e.MAX_DOCUMENT+1))
            with self.assertRaises(e.EvidenceError): e.read_retained_attempt(root)

    def test_fresh_baseline_required_and_oversized_tree_no_copy(self):
        trust, source = sample()
        bad = alter_record(source, lambda r: r['kind']=='trial_started',
            lambda r: r['value']['baseline']['sim:home-fan'].update(effectCount=100))
        with self.assertRaises(e.EvidenceError): e.reduce_attempt(trust,bad['result'],bad['files'])
        class Hostile:
            def __deepcopy__(self,memo): raise AssertionError('deepcopy called')
        trust['input']['bindings']['fan']['surprise']=Hostile()
        with self.assertRaises(e.EvidenceError): e.trusted_binding(trust)
        trust, _ = sample(); trust['input']['bindings']['fan']['surprise']=['x']*100000
        with self.assertRaises(e.EvidenceError): e.trusted_binding(trust)


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trust, cls.bundle = bundle()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'evidence.sqlite'
        self.db = sqlite3.connect(self.path); self.addCleanup(self.db.close)
        self.store = e.EvidenceStore(self.db, self.trust)
        self.result = self.store.import_bundle(self.bundle)
        self.receipt = receipt(self.trust, self.result)
        self.context = Context('historical-reader', self.trust['deployment'])

    def verify(self):
        self.db.execute('BEGIN')
        self.db.set_authorizer(authorizer(('typeof', 'length')))
        try: return self.store.verify_evidence(self.context, self.receipt)
        finally: self.db.set_authorizer(None); self.db.rollback()

    def test_import_verify_reopen_exact_dedup_and_no_filesystem(self):
        changes = self.db.total_changes
        self.assertEqual(self.store.import_bundle(self.bundle), self.result)
        self.assertEqual(self.db.total_changes, changes)
        self.assertTrue(self.verify())
        self.db.close(); self.db = sqlite3.connect(self.path); self.addCleanup(self.db.close)
        self.store = e.EvidenceStore(self.db, self.trust)
        with mock.patch('builtins.open', side_effect=AssertionError('filesystem')), \
             mock.patch.object(Path, 'read_bytes', side_effect=AssertionError('filesystem')), \
             mock.patch.object(Path, 'read_text', side_effect=AssertionError('filesystem')), \
             mock.patch('os.open', side_effect=AssertionError('filesystem')):
            self.assertTrue(self.verify())

    def test_old_select_only_hook_refuses_required_functions(self):
        self.db.execute('BEGIN'); self.db.set_authorizer(authorizer())
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                self.store.verify_evidence(self.context, self.receipt)
        finally:
            self.db.set_authorizer(None); self.db.rollback()

    def test_receipt_exact_check_ids_categories_outcomes_no_extra(self):
        original = copy.deepcopy(self.receipt)
        mutations = [lambda r: r.update(runId='other:run'),
                     lambda r: r.update(physicalObjectiveVerified=True),
                     lambda r: r['result']['checks'].append(r['result']['checks'][0]),
                     lambda r: r['result']['checks'].pop(),
                     lambda r: r['result']['checks'][0].update(category='fault'),
                     lambda r: r['result']['checks'][0].update(outcome='failed'),
                     lambda r: r['result']['checks'][1].update(evidenceDigest='sha256:'+'0'*64)]
        for mutate in mutations:
            self.receipt = copy.deepcopy(original); mutate(self.receipt)
            with self.assertRaises(e.EvidenceError): self.verify()
        self.receipt = original

    def test_missing_and_corrupt_documents_abort(self):
        group = json.loads(self.bundle['documents'][self.bundle['groupDigest']])
        key = group['cases'][0]['digest']
        self.db.execute('DELETE FROM se_documents WHERE digest=?', (key.encode('ascii'),)); self.db.commit()
        with self.assertRaises(e.EvidenceError): self.verify()
        body = self.bundle['documents'][key]
        self.db.execute('INSERT INTO se_documents VALUES(?,?,?)', (key.encode('ascii'), len(body), body[:-1]+b'x')); self.db.commit()
        with self.assertRaises(e.EvidenceError): self.verify()

    def test_malicious_actual_blob_length_and_nul_text_never_fetched(self):
        key = self.bundle['groupDigest']
        originals = self.bundle['documents'][key]
        for payload in (b'x'*(e.MAX_DOCUMENT+1), 'x\0'+'y'*1000000):
            self.db.execute('UPDATE se_documents SET body=?,byte_count=1 WHERE digest=?', (payload,key.encode('ascii'))); self.db.commit()
            queries = []; self.db.set_trace_callback(queries.append)
            with self.assertRaises(e.EvidenceError): self.verify()
            self.db.set_trace_callback(None)
            self.assertFalse(any(q.startswith('SELECT body ') for q in queries))
            if type(payload) is str:
                self.assertFalse(any(q.startswith('SELECT length(body)') for q in queries))
        self.db.execute('UPDATE se_documents SET body=?,byte_count=? WHERE digest=?', (originals,len(originals),key.encode('ascii'))); self.db.commit()
        self.assertTrue(self.verify())

    def test_declared_count_cannot_hide_actual_length_or_wrong_scalar(self):
        key = self.bundle['groupDigest']
        for count in (1, 'x'*1000000, None):
            if count is None: continue  # SQL NOT NULL enforces this at writes.
            self.db.execute('UPDATE se_documents SET byte_count=? WHERE digest=?', (count,key.encode('ascii'))); self.db.commit()
            queries=[]; self.db.set_trace_callback(queries.append)
            with self.assertRaises(e.EvidenceError): self.verify()
            self.db.set_trace_callback(None)
            self.assertFalse(any(q.startswith('SELECT body ') for q in queries))

    def test_logical_retention_quota_refuses_before_inserts(self):
        with sqlite3.connect(':memory:') as db:
            store = e.EvidenceStore(db, self.trust, byte_quota=1)
            before=db.total_changes
            with self.assertRaises(e.EvidenceError): store.import_bundle(self.bundle)
            self.assertEqual(db.total_changes,before)
            self.assertEqual(db.execute('SELECT count(*) FROM se_documents').fetchone()[0],0)
        with sqlite3.connect(':memory:') as db:
            store=e.EvidenceStore(db,self.trust,document_quota=1)
            with self.assertRaises(e.EvidenceError): store.import_bundle(self.bundle)
            self.assertEqual(db.execute('SELECT count(*) FROM se_documents').fetchone()[0],0)

    def test_partial_schema_missing_version_and_no_nested_transaction(self):
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE se_documents(x)'); db.commit()
            with self.assertRaises(e.EvidenceError): e.EvidenceStore(db,self.trust)
        self.db.execute("DELETE FROM se_meta WHERE key='version'");self.db.commit()
        with self.assertRaises(e.EvidenceError): e.EvidenceStore(self.db,self.trust)
        self.db.execute('BEGIN')
        with self.assertRaises(e.EvidenceError): self.store.import_bundle(self.bundle)
        self.db.rollback()

    def test_extra_document_and_bad_case_capsule_roll_back_all_import_writes(self):
        for change in ('extra','case'):
            bad=copy.deepcopy(self.bundle)
            if change=='extra':
                body=canonical({'extra':True});bad['documents'][e.digest(body)]=body
            else:
                manifest=json.loads(bad['documents'][bad['groupDigest']]);key=manifest['cases'][0]['digest']
                row=json.loads(bad['documents'][key]);row['observed']['committedEffects']=99
                body=canonical(row);bad['documents'].pop(key);bad['documents'][e.digest(body)]=body
            with sqlite3.connect(':memory:') as db:
                store=e.EvidenceStore(db,self.trust)
                with self.assertRaises(e.EvidenceError):store.import_bundle(bad)
                self.assertEqual(db.execute('SELECT count(*) FROM se_documents').fetchone()[0],0)
                self.assertEqual(db.execute('SELECT count(*) FROM se_runs').fetchone()[0],0)

    def test_key_link_mismatch_and_cycle_refuse(self):
        self.db.execute('UPDATE se_runs SET group_digest=?',('sha256:'+'0'*64,));self.db.commit()
        with self.assertRaises(e.EvidenceError):self.verify()
        # Rehashed group cycle cannot provide any complete source closure.
        bad=copy.deepcopy(self.bundle);manifest=json.loads(bad['documents'][bad['groupDigest']])
        manifest['resultDigest']=bad['groupDigest']
        body=canonical(manifest);bad['documents'][e.digest(body)]=body;bad['groupDigest']=e.digest(body)
        with sqlite3.connect(':memory:') as db:
            store=e.EvidenceStore(db,self.trust)
            with self.assertRaises(e.EvidenceError):store.import_bundle(bad)
            self.assertEqual(db.execute('SELECT count(*) FROM se_runs').fetchone()[0],0)

    def test_run_identity_conflict_never_overwrites_and_quota_includes_overhead(self):
        different=copy.deepcopy(self.trust)
        different['evaluator']['implementationDigest']='sha256:'+'a'*64
        source=e.read_retained_attempt(RETAINED/'case-04')
        other=e.reduce_attempt(different,source['result'],source['files'])
        other_store=e.EvidenceStore(self.db,different)
        before=self.db.execute('SELECT count(*) FROM se_documents').fetchone()[0]
        with self.assertRaises(e.EvidenceError):other_store.import_bundle(other)
        self.assertEqual(self.db.execute('SELECT count(*) FROM se_documents').fetchone()[0],before)
        self.assertTrue(self.verify())
        manifest=json.loads(self.bundle['documents'][self.bundle['groupDigest']])
        with sqlite3.connect(':memory:') as db:
            store=e.EvidenceStore(db,self.trust,byte_quota=manifest['producerBytes']+1)
            with self.assertRaises(e.EvidenceError):store.import_bundle(self.bundle)
            self.assertEqual(db.execute('SELECT count(*) FROM se_documents').fetchone()[0],0)

    def test_oversized_digest_metadata_refused_without_fetch(self):
        self.db.execute('INSERT INTO se_documents VALUES(?,?,?)',(b'x'*1000000,1,b'x'));self.db.commit()
        statements=[];self.db.set_trace_callback(statements.append)
        with self.assertRaises(e.EvidenceError):self.store.import_bundle(self.bundle)
        self.db.set_trace_callback(None)
        # Every fetched key was first proven to have fixed byte width; the bad
        # row stops at length(), even though its supplied body count is small.
        last=[q for q in statements if q.startswith('SELECT')][-1]
        self.assertTrue(last.startswith('SELECT length(digest)'),last)

    def test_process_death_before_and_after_import_commit(self):
        import subprocess, sys
        for phase, expected, code in [('before',0,70),('after',1,71)]:
            path=Path(self.temp.name)/('crash-'+phase+'.sqlite')
            script = """import os,sqlite3,sys
from test_evidence import bundle
import pat_simulation_evidence as e
class Connection(sqlite3.Connection):
 def execute(self,sql,*a,**kw):
  result=super().execute(sql,*a,**kw)
  if sys.argv[2]=='before' and sql.startswith('INSERT INTO se_runs'):os._exit(70)
  return result
trust,reduced=bundle()
db=sqlite3.connect(sys.argv[1],factory=Connection)
e.EvidenceStore(db,trust).import_bundle(reduced)
os._exit(71)
"""
            env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(ROOT/'tests'),str(ROOT/'src'),str(ROOT/'baseline/producer')]))
            done=subprocess.run([sys.executable,'-B','-c',script,str(path),phase],env=env,capture_output=True,text=True)
            self.assertEqual(done.returncode,code,done.stdout+done.stderr)
            with sqlite3.connect(path) as db:
                store=e.EvidenceStore(db,self.trust)
                self.assertEqual(db.execute('SELECT count(*) FROM se_runs').fetchone()[0],expected)
                if expected:
                    db.execute('BEGIN');self.assertTrue(store.verify_evidence(self.context,self.receipt));db.rollback()
                else:self.assertEqual(db.execute('SELECT count(*) FROM se_documents').fetchone()[0],0)


if __name__ == '__main__':
    unittest.main()
