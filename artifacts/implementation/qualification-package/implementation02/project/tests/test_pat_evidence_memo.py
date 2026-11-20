"""Memo integration against fresh original-worker outputs and live HMS modules.

No historical producer code or successful fixture flags are imported. Each module
run captures trusted inputs before execution, retains raw worker results when the
proof runner requests it, and verifies current store bytes even for memo hits.
"""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from hms import pat_evidence_memo as f
from hms import pat_simulation_evidence as e
from hms.contracts import canonical
from hms.journal import Context

ROOT = Path(__file__).resolve().parents[1]
RETAIN_OUTPUT_ROOT = None
RETAINED = None
LAST_REPORT = {'profile': 'hms-pat-current-memo-tests/0.1', 'workers': []}
TRUSTS = {}
_TEMP = None


def setUpModule():
    global RETAINED, _TEMP
    from test_pat_simulation_worker import fixture, replan
    from hms.pat_simulation_worker import run_worker
    from hms.pat_simulation_contracts import CEILINGS
    _TEMP = tempfile.TemporaryDirectory(prefix='hms-current-memo-') if RETAIN_OUTPUT_ROOT is None else None
    RETAINED = Path(_TEMP.name if _TEMP is not None else RETAIN_OUTPUT_ROOT)
    RETAINED.mkdir(exist_ok=True)
    for case, options in [('case-04', {}), ('case-01', {'alias': True, 'constant': True, 'rebind': True}),
                          ('case-00', {'limits': {**CEILINGS, 'maxOutputBytes': 1}}), ('case-02', {})]:
        cap = fixture(**options)
        cap['attemptId'] = 'attempt:memo:' + case
        if case == 'case-02':
            cap['artifact']['name'] = 'fan-level-pair-alternative'
            cap = replan(cap)
        trust = {'profile': e.TRUST_PROFILE, 'deployment': cap['evaluationEnvironment']['deployment'],
            'runId': 'memo:' + case, 'evaluator': {'evaluatorId': 'sim:current-memo-fan',
                'implementationDigest': f.validation_identity(), 'policyDigest': cap['identities']['policyDigest'],
                'requiredChecks': [{'id': key, 'category': category} for key, category in e.CHECKS],
                'evidenceProfile': e.PROFILE}, 'input': copy.deepcopy(cap)}
        TRUSTS[case] = copy.deepcopy(trust)
        path = RETAINED / case; path.mkdir(mode=0o700)
        (RETAINED / (case + '-trust.json')).write_bytes(canonical(trust))
        result = run_worker(cap, path)
        (path / 'test-return.json').write_bytes(canonical(result))
        LAST_REPORT['workers'].append({'case': case, 'result': result,
            'trustSha256': hashlib.sha256(canonical(trust)).hexdigest()})
        if result['outcome'] != ('inconclusive' if case == 'case-00' else 'passed'):
            raise AssertionError(result)


def tearDownModule():
    if _TEMP is not None:
        _TEMP.cleanup()


def sample(case='case-04'):
    return copy.deepcopy(TRUSTS[case]), e.read_retained_attempt(RETAINED / case)


def receipt(trust,result):
    cap=trust['input']
    return {'protocol':'hms.pat-evaluation/0.1','runId':trust['runId'],'artifactDigest':e.pat_digest(cap['artifact']),
        'artifactDomainDigest':e.hash_document(b'HMS-PAT-DOMAIN-v0.1',cap['artifact']),
        'evaluator':trust['evaluator'],'environment':cap['evaluationEnvironment'],'environmentDigest':cap['environmentDigest'],
        'outcome':'passed','result':result,'evaluatorError':None,'physicalObjectiveVerified':False}

def guard(action,one,two,database,trigger):
    if action in (sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ) and database in (None,'main'):return sqlite3.SQLITE_OK
    if action==sqlite3.SQLITE_FUNCTION and two in ('typeof','length'):return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY

def rehashed_mutation(original, *, semantic):
    """Forge a self-consistent byte graph; qualification must still refuse it."""
    bundle=copy.deepcopy(original);docs=bundle['documents'];manifest=json.loads(docs[bundle['groupDigest']])
    changes={}
    def changed(key,value):
        body=canonical(value);new=e.digest(body);docs[new]=body;changes[key]=new;return new
    if semantic:
        key=next(k for k,b in docs.items() if (r:=json.loads(b)).get('kind')=='operation' and r['value']['trial']==0)
        row=json.loads(docs[key]);row['value']['receipt']['result']['level']=51
        changed(key,row)
        for page in manifest['evidencePages']:
            row=json.loads(docs[page['digest']])
            for ref in row['value']['records']:
                old='sha256:'+ref['sha256']
                if old in changes:ref['sha256']=changes[old][7:];ref['bytes']=len(docs[changes[old]])
            page['digest']=changed(page['digest'],row)
        result=json.loads(docs[manifest['resultDigest']])
        for ref in result['evidencePages']:
            old='sha256:'+ref['sha256'];ref['sha256']=changes[old][7:];ref['bytes']=len(docs[changes[old]])
        manifest['resultDigest']=changed(manifest['resultDigest'],result)
    for ref in manifest['cases']:
        row=json.loads(docs[ref['digest']]);dirty=False
        for item in row['records']:
            if item['digest'] in changes:item['digest']=changes[item['digest']];dirty=True
        if not semantic and row['trial']==0:row['observed']['committedEffects']=99;dirty=True
        if dirty:ref['digest']=changed(ref['digest'],row)
    old=bundle['groupDigest'];new=changed(old,manifest);bundle['groupDigest']=new
    for old in changes:docs.pop(old,None)
    return bundle


class FastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.trust,cls.source=sample();cls.memo=f.ValidatedReducerMemo()
        cls.bundle=cls.memo.warm(cls.trust,cls.source['result'],cls.source['files'])
        cls.path=Path(cls.tmp.name)/'baseline.sqlite'
        with sqlite3.connect(cls.path) as db:
            cls.result=e.EvidenceStore(db,cls.trust).import_bundle(cls.bundle)
        cls.receipt=receipt(cls.trust,cls.result)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'hms_qualification.evidence.sqlite';shutil.copyfile(self.__class__.path,self.path)
        self.db=sqlite3.connect(self.path);self.addCleanup(self.db.close)
        self.store=f.FastEvidenceStore(self.db,self.trust,memo=self.memo)
        self.context=Context('review-reader',self.trust['deployment'])

    def verify(self, store=None, rec=None):
        self.db.execute('BEGIN');self.db.set_authorizer(guard)
        try:return (store or self.store).verify_evidence(self.context,rec or self.receipt)
        finally:self.db.set_authorizer(None);self.db.rollback()

    def test_full_reducer_ast_preserved_except_explicit_loader_seam(self):
        original=ast.parse((ROOT/'tests/fixtures/pat_evidence_before_memo.py').read_text())
        current=ast.parse(Path(e.__file__).read_text())
        for tree in (original,current):
            for node in ast.walk(tree):
                if isinstance(node,ast.FunctionDef) and node.name=='_load':
                    node.args.kwonlyargs=[];node.args.kw_defaults=[]
                    for call in ast.walk(node):
                        if isinstance(call,ast.Name) and call.id=='_reduce':call.id='reduce_attempt'
        self.assertEqual(ast.dump(original,include_attributes=False),ast.dump(current,include_attributes=False))

    def test_imports_resolve_inside_exact_copied_tree(self):
        import hms.contracts
        self.assertEqual(Path(f.__file__).resolve().parent,ROOT/'hms')
        self.assertEqual(Path(e.__file__).resolve().parent,ROOT/'hms')
        self.assertTrue(Path(hms.contracts.__file__).resolve().is_relative_to(ROOT/'hms'))

    def test_every_document_is_reread_even_when_semantics_are_cached(self):
        with mock.patch.object(self.store,'_read',wraps=self.store._read) as reads:
            self.assertTrue(self.verify())
        self.assertEqual({call.args[0] for call in reads.call_args_list},set(self.bundle['documents']))
        self.assertEqual(reads.call_count,len(self.bundle['documents']))

    def test_hot_is_identical_without_compile_io_or_mutation(self):
        before=self.memo.usage();changes=self.db.total_changes
        with mock.patch.object(e,'reduce_attempt',side_effect=AssertionError('cold semantic work')), \
             mock.patch.object(e,'compile_pat',side_effect=AssertionError('compile')), \
             mock.patch('builtins.open',side_effect=AssertionError('filesystem')), \
             mock.patch.object(Path,'read_bytes',side_effect=AssertionError('filesystem')), \
             mock.patch.object(Path,'read_text',side_effect=AssertionError('filesystem')):
            self.assertTrue(self.verify())
            actual=self.memo.lookup(self.trust,self.source['result'],self.source['files'])
        self.assertEqual(actual,self.bundle);self.assertEqual(self.memo.usage(),before);self.assertEqual(self.db.total_changes,changes)

    def test_cold_restart_does_not_compile_under_readonly_guard(self):
        empty=f.ValidatedReducerMemo();store=f.FastEvidenceStore(self.db,self.trust,memo=empty)
        with mock.patch.object(e,'reduce_attempt',side_effect=AssertionError('cold compile')):
            with self.assertRaisesRegex(e.EvidenceError,'PAT_EVIDENCE_CACHE_COLD'):self.verify(store)
        self.assertEqual(empty.usage()['entries'],0)

    def test_actual_process_restart_requires_full_explicit_warm(self):
        script="""import json,sqlite3,sys
from test_pat_evidence_memo import receipt,guard
from hms import pat_simulation_evidence as e
from hms import pat_evidence_memo as f
import hms.contracts
from pathlib import Path
from hms.journal import Context
root=Path(sys.argv[2]).resolve()
assert Path(f.__file__).resolve().parent == root/'hms'
assert Path(e.__file__).resolve().parent == root/'hms'
assert Path(hms.contracts.__file__).resolve().is_relative_to(root/'hms')
trust=json.loads(Path(sys.argv[3]).read_bytes());db=sqlite3.connect(sys.argv[1]);memo=f.ValidatedReducerMemo();store=f.FastEvidenceStore(db,trust,memo=memo)
row=db.execute('SELECT group_digest FROM se_runs').fetchone();rec=receipt(trust,e._evaluation_result(row[0]));ctx=Context('restart-reader',trust['deployment'])
db.execute('BEGIN');db.set_authorizer(guard)
try:
 try:store.verify_evidence(ctx,rec)
 except e.EvidenceError as error:assert error.code=='PAT_EVIDENCE_CACHE_COLD'
 else:raise AssertionError('persisted pass flag bypassed cold validation')
finally:db.set_authorizer(None);db.rollback()
before=db.total_changes
memo.warm_stored(e.EvidenceStore(db,trust),row[0])
db.execute('BEGIN');db.set_authorizer(guard)
try:assert store.verify_evidence(ctx,rec) is True
finally:db.set_authorizer(None);db.rollback()
assert db.total_changes==before
print('cold_refused_then_explicit_full_warm_verified');db.close()
"""
        env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(ROOT/'tests'),str(ROOT)]))
        done=subprocess.run([sys.executable,'-B','-c',script,str(self.path),str(ROOT),str(RETAINED/'case-04-trust.json')],env=env,cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stdout+done.stderr)
        self.assertIn('cold_refused_then_explicit_full_warm_verified',done.stdout)

    def test_mutating_returned_bundle_and_source_never_poison_cache(self):
        value=self.memo.lookup(self.trust,self.source['result'],self.source['files'])
        value['documents'].clear();value['groupDigest']='bad'
        trust=copy.deepcopy(self.trust);trust['input']['artifact']['name']='changed'
        with self.assertRaisesRegex(e.EvidenceError,'CACHE_COLD'):self.memo.lookup(trust,self.source['result'],self.source['files'])
        self.assertEqual(self.memo.lookup(self.trust,self.source['result'],self.source['files']),self.bundle)
        self.assertTrue(self.verify())

    def test_typed_trust_float_boolean_and_config_run_changes_cannot_hit(self):
        for field,value in [('revision',1.0),('revision',True),('revision',2),('runId','other:run')]:
            trust=copy.deepcopy(self.trust)
            if field=='runId':trust[field]=value
            else:trust['input']['configuration'][field]=value
            with self.assertRaisesRegex(e.EvidenceError,'CACHE_COLD'):self.memo.lookup(trust,self.source['result'],self.source['files'])
        with self.assertRaises(e.EvidenceError):
            self.memo.lookup({'x':['x']*100000},self.source['result'],self.source['files'])

    def test_validation_closure_change_invalidates_same_compiler_pin(self):
        before=self.memo.usage()
        with mock.patch.object(f,'VALIDATION_ID','sha256:'+'0'*64):
            with self.assertRaisesRegex(e.EvidenceError,'VALIDATOR_CHANGED'):
                self.memo.lookup(self.trust,self.source['result'],self.source['files'])
            new=f.ValidatedReducerMemo()
            with self.assertRaisesRegex(e.EvidenceError,'CACHE_COLD'):
                new.lookup(self.trust,self.source['result'],self.source['files'])
        self.assertEqual(before,self.memo.usage())

    def test_current_document_corruption_and_missing_document_refuse_hot_cache(self):
        key=next(iter(self.bundle['documents']))
        body=self.bundle['documents'][key]
        self.db.execute('UPDATE se_documents SET body=? WHERE digest=?',(body[:-1]+b'x',key.encode()));self.db.commit()
        with self.assertRaises(e.EvidenceError):self.verify()
        self.db.execute('DELETE FROM se_documents WHERE digest=?',(key.encode(),));self.db.commit()
        with self.assertRaises(e.EvidenceError):self.verify()

    def test_rehashed_semantic_mutation_is_cold_and_fails_full_warming(self):
        changed=rehashed_mutation(self.bundle,semantic=True)
        self._install_corrupt_graph(changed)
        rec=receipt(self.trust,e._evaluation_result(changed['groupDigest']))
        with self.assertRaisesRegex(e.EvidenceError,'CACHE_COLD'):self.verify(rec=rec)
        clean=f.ValidatedReducerMemo()
        with self.assertRaises(e.EvidenceError):clean.warm_stored(e.EvidenceStore(self.db,self.trust),changed['groupDigest'])
        self.assertEqual(clean.usage()['entries'],0)

    def test_rehashed_capsule_mutation_cannot_reuse_same_raw_input_hit(self):
        changed=rehashed_mutation(self.bundle,semantic=False);self._install_corrupt_graph(changed)
        rec=receipt(self.trust,e._evaluation_result(changed['groupDigest']))
        with self.assertRaises(e.EvidenceError):self.verify(rec=rec)

    def _install_corrupt_graph(self,bundle):
        for key,body in bundle['documents'].items():
            self.db.execute('INSERT OR REPLACE INTO se_documents VALUES(?,?,?)',(key.encode(),len(body),body))
        self.db.execute('UPDATE se_runs SET group_digest=?',(bundle['groupDigest'],));self.db.commit()

    def test_receipt_run_evaluator_check_and_link_association_still_required(self):
        for mutation in [lambda r:r.update(runId='other:run'),lambda r:r['evaluator'].update(implementationDigest='sha256:'+'0'*64),
                         lambda r:r['result']['checks'][0].update(category='fault')]:
            rec=copy.deepcopy(self.receipt);mutation(rec)
            with self.assertRaises(e.EvidenceError):self.verify(rec=rec)
        self.db.execute('UPDATE se_runs SET group_digest=?',('sha256:'+'0'*64,));self.db.commit()
        with self.assertRaises(e.EvidenceError):self.verify()

    def test_actual_blob_bounds_remain_before_fetch_on_hot_path(self):
        key=self.bundle['groupDigest'];statements=[]
        self.db.execute('UPDATE se_documents SET body=?,byte_count=1 WHERE digest=?',(b'x'*1000000,key.encode()));self.db.commit()
        self.db.set_trace_callback(statements.append)
        with self.assertRaises(e.EvidenceError):self.verify()
        self.db.set_trace_callback(None)
        self.assertFalse(any(sql.startswith('SELECT body ') for sql in statements))

    def test_no_pass_bundle_ingress_and_failed_actual_worker_not_cached(self):
        with self.assertRaisesRegex(e.EvidenceError,'USE_FULL_IMPORT'):self.store.import_bundle(self.bundle)
        empty=f.ValidatedReducerMemo();trust,bad=sample('case-00')
        with self.assertRaises(e.EvidenceError):empty.warm(trust,bad['result'],bad['files'])
        self.assertEqual(empty.usage()['entries'],0)

    def test_actual_alias_constant_domain_and_rebound_generation_remain_verifiable(self):
        trust, source = sample('case-01')
        memo = f.ValidatedReducerMemo()
        reduced = memo.warm(trust, source['result'], source['files'])
        with sqlite3.connect(':memory:') as db:
            result = e.EvidenceStore(db, trust).import_bundle(reduced)
            store = f.FastEvidenceStore(db, trust, memo=memo)
            db.execute('BEGIN'); db.set_authorizer(guard)
            try:
                self.assertTrue(store.verify_evidence(Context('alias-reader', trust['deployment']), receipt(trust, result)))
            finally:
                db.set_authorizer(None); db.rollback()
        self.assertEqual(json.loads(source['result'])['completedCases'], 10)

    def test_capacity_counts_keys_capsules_and_fifo_lookup_no_mutation(self):
        cache=f.ValidatedReducerMemo(entries=1)
        cache.warm(self.trust,self.source['result'],self.source['files'])
        first=cache.usage();self.assertGreater(first['chargedBytes'],sum(map(len,self.bundle['documents'].values())))
        cache.lookup(self.trust,self.source['result'],self.source['files']);self.assertEqual(first,cache.usage())
        trust=copy.deepcopy(self.trust);trust['runId']='other:trusted-run'
        cache.warm(trust,self.source['result'],self.source['files'])
        with self.assertRaisesRegex(e.EvidenceError,'CACHE_COLD'):cache.lookup(self.trust,self.source['result'],self.source['files'])
        tiny=f.ValidatedReducerMemo(byte_limit=1)
        with self.assertRaisesRegex(e.EvidenceError,'CACHE_CAPACITY'):tiny.warm(self.trust,self.source['result'],self.source['files'])
        self.assertEqual(tiny.usage()['entries'],0)

    def test_warm_requires_separate_context_and_lookup_uses_complete_raw_order(self):
        full=e.EvidenceStore(self.db,self.trust)
        self.db.execute('BEGIN')
        with self.assertRaisesRegex(e.EvidenceError,'WARM_CONTEXT'):
            f.ValidatedReducerMemo().warm_stored(full,self.bundle['groupDigest'])
        self.db.rollback()
        files=list(self.source['files']);files[0],files[1]=files[1],files[0]
        with self.assertRaisesRegex(e.EvidenceError,'CACHE_COLD'):self.memo.lookup(self.trust,self.source['result'],files)

class CatalogIntegrationTests(unittest.TestCase):
    def test_cold_promotion_and_selection_refuse_without_false_uniqueness_or_replay_loss(self):
        from hms.journal import JournalError
        from hms.pat_catalog import Evaluator, PatCatalog
        from hms.pat_compiler import compiler_digest
        from hms.pat_execution import PatExecutionStore
        from hms.runtime import Runtime

        samples = [sample(case) for case in ('case-04', 'case-02')]
        trust, source = samples[0]
        cap = trust['input']; program = cap['artifact']; identity = trust['evaluator']
        owner = Context('current-memo-owner', trust['deployment'])
        by_artifact = {e.pat_digest(t['input']['artifact']): (t, s) for t, s in samples}
        memo = f.ValidatedReducerMemo(); stores = {}; calls = []
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(directory, create=True, owner=owner,
                wall_clock_ms=lambda: 1000, monotonic_ms=lambda: 1000)
            try:
                db = runtime.journal._db
                full = {t['runId']: e.EvidenceStore(db, t) for t, s in samples}
                stores.update({t['runId']: f.FastEvidenceStore(db, t, memo=memo) for t, s in samples})
                def evaluate(artifact, environment):
                    t, s = by_artifact[e.pat_digest(artifact)]
                    self.assertEqual(artifact, t['input']['artifact'])
                    self.assertEqual(environment, t['input']['evaluationEnvironment'])
                    calls.append(t['runId'])
                    return full[t['runId']].import_bundle(e.reduce_attempt(t, s['result'], s['files']))
                def verify(context, evaluated):
                    return stores[evaluated['runId']].verify_evidence(context, evaluated)
                evaluator = Evaluator(identity['evaluatorId'], identity['implementationDigest'],
                    identity['policyDigest'], e.CHECKS, evaluate,
                    evidence_profile=e.PROFILE, verify_evidence=verify)
                catalog = PatCatalog(runtime.journal, compiler_digest=compiler_digest,
                    environment=lambda context, artifact: copy.deepcopy(by_artifact[e.pat_digest(artifact)][0]['input']['evaluationEnvironment']),
                    evaluators=(evaluator,))
                bindings = copy.deepcopy(cap['bindings'])
                bindings['fan']['endpointSession'] = runtime.plant.session
                executions = PatExecutionStore(runtime.journal, catalog, runtime.procedures,
                    resolver=lambda *args: {'complete': True, 'assignments': [copy.deepcopy(bindings)]})
                key = e.pat_digest(program)
                catalog.publish(owner, program)
                evaluated = catalog.evaluate(owner, key, evaluator.evaluator_id, trust['runId'])
                self.assertEqual(evaluated['receipt']['outcome'], 'passed')
                tables = ('px_instances', 'px_triggers', 'pr_procedures', 'pr_steps', 'pr_keys', 'operations', 'replay_keys')
                counts = lambda: tuple(db.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in tables)
                revision, before = catalog._revision(owner.deployment), counts()
                with self.assertRaises(JournalError) as refused:
                    catalog.transition(owner, key, expected_revision=revision, target='active')
                self.assertEqual(refused.exception.code, 'PAT_EVIDENCE_UNAVAILABLE')
                self.assertEqual(catalog._revision(owner.deployment), revision)
                self.assertEqual(counts(), before)
                memo.warm(trust, source['result'], source['files'])
                catalog.transition(owner, key, expected_revision=revision, target='active')
                namespace = runtime.request(owner, 'namespace', {'expiresUnixMs': 10000})['token']
                request = {'protocol': 'hms.pat-run/0.1', 'replayNamespace': namespace, 'runKey': 'memo:run',
                    'taskKind': program['taskKind'], 'inputProfile': program['inputProfile'],
                    'parameters': {'initialLevel': 12, 'finalLevel': 73}, 'evidenceMode': 'simulation',
                    'originUnixMs': 1000, 'latestCompletionUnixMs': 4000}
                admitted = executions.run(owner, request)
                alt, alt_source = samples[1]; alternate = alt['input']['artifact']; alt_key = e.pat_digest(alternate)
                catalog.publish(owner, alternate)
                catalog.evaluate(owner, alt_key, evaluator.evaluator_id, alt['runId'])
                memo.warm(alt, alt_source['result'], alt_source['files'])
                catalog.transition(owner, alt_key, expected_revision=catalog._revision(owner.deployment), target='active')
                before = counts()
                with self.assertRaises(JournalError) as ambiguous:
                    executions.run(owner, dict(request, runKey='memo:ambiguous'))
                self.assertEqual(ambiguous.exception.code, 'PAT_AMBIGUOUS')
                self.assertEqual(counts(), before)
                stores[trust['runId']] = f.FastEvidenceStore(db, trust, memo=f.ValidatedReducerMemo())
                self.assertEqual(executions.run(owner, request), admitted)
                self.assertEqual(catalog.evaluate(owner, key, evaluator.evaluator_id, trust['runId']), evaluated)
                with self.assertRaises(JournalError) as cold:
                    executions.run(owner, dict(request, runKey='memo:cold'))
                self.assertEqual(cold.exception.code, 'PAT_EVIDENCE_UNAVAILABLE')
                self.assertEqual(counts(), before)
                self.assertEqual(calls, [t['runId'] for t, s in samples])
                LAST_REPORT['catalog'] = {'coldPromotion': refused.exception.code,
                    'warmAmbiguity': ambiguous.exception.code, 'coldSelection': cold.exception.code,
                    'historicalReplayPreserved': True, 'refusalsAllocateNothing': True}
            finally:
                runtime.close()


if __name__=='__main__':unittest.main()
