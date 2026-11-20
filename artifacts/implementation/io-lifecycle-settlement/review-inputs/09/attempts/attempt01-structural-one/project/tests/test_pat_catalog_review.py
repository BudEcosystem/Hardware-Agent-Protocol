"""Independent catalog authority/race/crash checks using original local code.

The test evaluator supplies synthetic outcomes only; no PAT, model, native
endpoint, acquired program, hardware driver or physical I/O is executed.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from hms.contracts import ContractError, SAFE_INTEGER
from hms.journal import Context, Journal, JournalError
from hms.pat_catalog import Evaluator, PatCatalog
from hms.pat_contracts import pat_digest
from hms.registry import Registry, RegistryPolicy


OWNER = Context('review-owner', 'review-deployment')
OTHER = Context('review-other', 'review-deployment')
DIGEST = 'sha256:' + 'a' * 64
CHECKS = (('nominal', 'positive'), ('edge', 'boundary'), ('refusal', 'negative'), ('loss', 'fault'))
LAST_REPORT = {'schema': 'hms-pat-catalog-independent-tests/1', 'crashCases': [],
               'scope': 'Original local catalog and synthetic evaluator checks; no PAT execution or hardware qualification.'}


def artifact():
    """A separate minimal fixture: all arguments literal, no reusable keys/time."""
    return {'protocol': 'hms.pat/0.1', 'profile': 'hms.pat.bound-sequence/0.1',
        'name': 'review:literal-fan', 'version': 'v1', 'taskKind': 'review:fan',
        'inputProfile': 'review:none', 'parameters': {},
        'roles': {'fan': {'capabilityFamily': 'review:fan', 'actions': ['set_level'],
                         'driverProfiles': ['review:simulation']}},
        'applicability': {'phase': 'selection', 'all': []},
        'targetProfile': 'hms.bound-sequence/0.1', 'executionPlacement': 'hms-host-orchestration',
        'runtimeGuardProfile': 'installed_primitive_guards_only',
        'timingBudget': {'latestStartOffsetMs': 1000, 'latestCompletionOffsetMs': 2000, 'maxRunSumMs': 500},
        'steps': [{'stepId': 'set-fan', 'role': 'fan', 'actionId': 'set_level',
            'arguments': {'level': {'literal': 20}, 'unit': {'literal': 'percent'}},
            'timing': {'notBeforeOffsetMs': 0, 'latestStartOffsetMs': 1000,
                       'maxRunMs': 500, 'latestCompletionOffsetMs': 2000}}],
        'effectBudget': {'maxInvocations': 1, 'scope': 'simulation_only'},
        'outcomeContract': {'requiredEffect': 'capability_completion', 'requiredCompletedSteps': ['set-fan'],
                            'evidenceMode': 'simulation', 'physicalObjectiveVerified': False}}


def result(outcome='passed'):
    return {'checks': [{'id': name, 'category': category, 'outcome': outcome,
                        'evidenceDigest': DIGEST} for name, category in CHECKS],
            'unresolvedEffects': 0, 'limitations': ['Synthetic review outcome; no physical objective tested']}


def environment(context, document):
    return {'profile': 'hms.pat.environment/0.1', 'deployment': context.deployment,
        'evidenceMode': 'simulation', 'compilerDigest': DIGEST,
        'roles': {name: {'typeDigest': DIGEST, 'bindingDigest': DIGEST,
            'installationDigest': DIGEST, 'argumentMetadataDigest': DIGEST,
            'driverProfile': 'review:simulation', 'driverDigest': DIGEST} for name in document['roles']}}


def open_authority(path, *, create=False):
    policy = RegistryPolicy()
    journal = Journal(path, policy, clock_ms=lambda: 2000, create=create)
    registry = Registry(journal, monotonic_ms=lambda: 1000, bootstrap_owner=OWNER if create else None)
    policy.attach(registry)
    return journal, registry


def catalog(journal, *, evaluate=None, enabled=None, env=None):
    evaluator = Evaluator('review-evaluator', DIGEST, DIGEST, CHECKS,
                          evaluate or (lambda _a, _e: result()), enabled or (lambda: True))
    return PatCatalog(journal, compiler_digest=lambda: DIGEST,
                      environment=env or environment, evaluators=(evaluator,))


def business_rows(journal):
    with journal._mutex:
        tables = [row[0] for row in journal._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'pc_*' ORDER BY name")]
        return {table: [tuple(row) for row in journal._db.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                for table in tables}


def crash_worker(path, phase):
    """Abrupt exit inside/after an actual SQLite transaction, original code only."""
    journal, _registry = open_authority(Path(path))
    store = catalog(journal)
    document = artifact()
    digest = pat_digest(document)
    journal._db.execute('PRAGMA cache_size=1')
    original = store._event
    wanted = {'publish_inside': 'candidate_published', 'evaluate_inside': 'evaluation_recorded',
              'activate_inside': 'catalog_transition'}.get(phase)

    def interrupt(context, now, kind, payload):
        if kind == wanted:
            journal._db.execute('INSERT INTO review_crash_spill VALUES (?)', (b'x' * 200000,))
            rollback = Path(str(path) + '-journal')
            header = rollback.read_bytes()[:8]
            assert header != b'\0' * 8
            Path(str(path) + '.dirty.json').write_text(json.dumps({'header': header.hex(), 'bytes': rollback.stat().st_size}))
            os._exit(79)
        return original(context, now, kind, payload)

    store._event = interrupt
    if phase.startswith('publish'):
        store.publish(OWNER, document)
    elif phase.startswith('evaluate'):
        store.evaluate(OWNER, digest, 'review-evaluator', 'crash-run')
    else:
        revision = store.describe(OWNER, digest)['catalogRevision']
        store.transition(OWNER, digest, expected_revision=revision, target='active')
    os._exit(80)


class PatCatalogIndependentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hms-pat-review-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'authority.db'
        self.journal, self.registry = open_authority(self.path, create=True)
        self.addCleanup(lambda: self.journal.close())
        self.enabled = True
        self.env = environment(OWNER, artifact())
        self.eval_result = result()
        self.store = catalog(self.journal, evaluate=lambda _a, _e: copy.deepcopy(self.eval_result),
                             enabled=lambda: self.enabled, env=lambda _c, _a: copy.deepcopy(self.env))
        self.digest = self.store.publish(OWNER, artifact())['artifactDigest']

    def code(self, expected, function, *args, **kwargs):
        with self.assertRaises(JournalError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected)

    def evaluate(self, run='run'):
        return self.store.evaluate(OWNER, self.digest, 'review-evaluator', run)

    def activate(self):
        self.evaluate()
        revision = self.store.describe(OWNER, self.digest)['catalogRevision']
        return self.store.transition(OWNER, self.digest, expected_revision=revision, target='active')

    def test_actual_registry_admin_and_deployment_scope_on_every_surface(self):
        evaluation = self.evaluate()['evaluationDigest']
        candidates = [OTHER, Context(OWNER.principal, 'another-deployment')]
        for caller in candidates:
            calls = [lambda: self.store.publish(caller, artifact()),
                lambda: self.store.describe(caller, self.digest),
                lambda: self.store.artifact(caller, self.digest),
                lambda: self.store.evaluation(caller, evaluation),
                lambda: self.store.snapshot(caller), lambda: self.store.events(caller),
                lambda: self.store.evaluate(caller, self.digest, 'review-evaluator', 'untrusted'),
                lambda: self.store.transition(caller, self.digest, expected_revision=2, target='active')]
            for call in calls:
                with self.subTest(caller=caller, call=call):
                    before = business_rows(self.journal)
                    self.code('ACCESS_DENIED', call)
                    self.assertEqual(business_rows(self.journal), before)

    def test_auth_revoked_during_evaluator_rejected_before_commit(self):
        self.registry.grant(OWNER, OTHER.principal, '*', 'admin')
        calls = []
        def evaluate(_artifact, _environment):
            calls.append(True)
            self.assertFalse(self.journal._db.in_transaction)
            self.registry.grant(OWNER, OTHER.principal, '*', 'admin', enabled=False)
            return result()
        store = catalog(self.journal, evaluate=evaluate)
        before = business_rows(self.journal)
        self.code('ACCESS_DENIED', store.evaluate, OTHER, self.digest, 'review-evaluator', 'revoked')
        self.assertEqual(calls, [True]); self.assertEqual(business_rows(self.journal), before)

    def test_evaluator_revocation_inflight_and_replay_cannot_bypass_registration(self):
        enabled = True
        def evaluate(_artifact, _environment):
            nonlocal enabled
            enabled = False
            return result()
        store = catalog(self.journal, evaluate=evaluate, enabled=lambda: enabled)
        before = business_rows(self.journal)
        self.code('PAT_EVALUATOR_UNTRUSTED', store.evaluate, OWNER, self.digest, 'review-evaluator', 'revoked')
        self.assertEqual(business_rows(self.journal), before)
        self.evaluate(); self.enabled = False
        self.code('PAT_EVALUATOR_UNTRUSTED', self.evaluate)
        self.assertFalse(self.store.describe(OWNER, self.digest)['eligibleForPromotion'])

    def test_environment_change_during_trial_retains_old_facts_but_prevents_promotion(self):
        def evaluate(_artifact, frozen):
            self.assertEqual(frozen['roles']['fan']['bindingDigest'], DIGEST)
            self.env['roles']['fan']['bindingDigest'] = 'sha256:' + 'b' * 64
            return result()
        store = catalog(self.journal, evaluate=evaluate, env=lambda _c, _a: copy.deepcopy(self.env))
        receipt = store.evaluate(OWNER, self.digest, 'review-evaluator', 'changed')['receipt']
        self.assertEqual(receipt['environment']['roles']['fan']['bindingDigest'], DIGEST)
        entry = store.describe(OWNER, self.digest)
        self.assertFalse(entry['eligibleForPromotion'])
        self.code('PAT_DEPENDENCIES_CHANGED', store.transition, OWNER, self.digest,
                  expected_revision=entry['catalogRevision'], target='active')

    def test_result_mutation_and_receipt_return_mutation_do_not_change_evidence(self):
        owned = result()
        store = catalog(self.journal, evaluate=lambda _a, _e: owned)
        received = store.evaluate(OWNER, self.digest, 'review-evaluator', 'immutable')
        retained = copy.deepcopy(received['receipt'])
        owned['checks'][0]['outcome'] = 'failed'
        received['receipt']['result']['checks'][0]['outcome'] = 'failed'
        self.assertEqual(store.evaluation(OWNER, received['evaluationDigest']), retained)
        published = store.artifact(OWNER, self.digest); published['version'] = 'corrupted'
        self.assertEqual(store.artifact(OWNER, self.digest), artifact())

    def test_replay_does_not_run_again_and_run_key_cannot_bind_another_artifact(self):
        calls = []
        store = catalog(self.journal, evaluate=lambda _a, _e: calls.append(True) or result())
        receipt = store.evaluate(OWNER, self.digest, 'review-evaluator', 'once')
        before = business_rows(self.journal)
        self.assertEqual(store.evaluate(OWNER, self.digest, 'review-evaluator', 'once'), receipt)
        self.assertEqual(calls, [True]); self.assertEqual(business_rows(self.journal), before)
        different = artifact(); different['version'] = 'v2'
        other_digest = store.publish(OWNER, different)['artifactDigest']
        self.code('PAT_EVALUATION_KEY_CONFLICT', store.evaluate, OWNER, other_digest, 'review-evaluator', 'once')
        self.assertEqual(calls, [True])

    def test_concurrent_same_run_disagreeing_results_conflict_without_overwrite(self):
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        counter = 0
        def evaluate(_a, _e):
            nonlocal counter
            with lock:
                counter += 1; index = counter
            barrier.wait(timeout=3)
            return result('passed' if index == 1 else 'failed')
        store = catalog(self.journal, evaluate=evaluate)
        def run():
            try: return store.evaluate(OWNER, self.digest, 'review-evaluator', 'same')
            except JournalError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(lambda _: run(), range(2)))
        receipts = [value for value in values if type(value) is dict]
        self.assertEqual(len(receipts), 1); self.assertIn('PAT_EVALUATION_KEY_CONFLICT', values)
        self.assertEqual(store.evaluation(OWNER, receipts[0]['evaluationDigest']), receipts[0]['receipt'])
        state = store.describe(OWNER, self.digest)
        self.assertEqual(state['catalogRevision'], 3)
        self.assertTrue(state['evaluationConflicted'])
        self.assertEqual(state['state'], 'suspended'); self.assertFalse(state['eligibleForPromotion'])
        conflict = store.events(OWNER)['events'][-1]
        self.assertEqual(conflict['kind'], 'evaluation_conflict')
        incoming = store.evaluation(OWNER, conflict['payload']['conflictingEvaluationDigest'])
        self.assertEqual({incoming['outcome'], receipts[0]['receipt']['outcome']}, {'passed', 'failed'})

    def test_concurrent_identical_run_results_are_one_immutable_evaluation(self):
        barrier = threading.Barrier(2)
        def evaluate(_a, _e):
            barrier.wait(timeout=3)
            return result()
        store = catalog(self.journal, evaluate=evaluate)
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(lambda _: store.evaluate(OWNER, self.digest, 'review-evaluator', 'same'), range(2)))
        self.assertEqual(values[0], values[1])
        state = store.describe(OWNER, self.digest)
        self.assertEqual(state['catalogRevision'], 2); self.assertFalse(state['evaluationConflicted'])
        self.assertTrue(state['eligibleForPromotion'])

    def test_duplicate_conflict_suspends_intervening_promotion_once_and_survives_reopen(self):
        barrier, release = threading.Barrier(3), threading.Event()
        def passed(_a, _e):
            barrier.wait(timeout=3)
            return result()
        def failed(_a, _e):
            barrier.wait(timeout=3)
            if not release.wait(3): raise AssertionError('review thread not released')
            return result('failed')
        passing, failing = catalog(self.journal, evaluate=passed), catalog(self.journal, evaluate=failed)
        def run(store):
            try: return store.evaluate(OWNER, self.digest, 'review-evaluator', 'shared')
            except JournalError as error: return error.code
        with ThreadPoolExecutor(max_workers=3) as pool:
            fail_one, fail_two = pool.submit(run, failing), pool.submit(run, failing)
            pass_one = pool.submit(run, passing)
            try:
                receipt = pass_one.result(timeout=3)
                self.assertIsInstance(receipt, dict)
                active = self.store.transition(OWNER, self.digest, expected_revision=2, target='active')
                self.assertTrue(active['eligibleForNewInstances'])
            finally:
                release.set()
            self.assertEqual(fail_one.result(timeout=3), 'PAT_EVALUATION_KEY_CONFLICT')
            self.assertEqual(fail_two.result(timeout=3), 'PAT_EVALUATION_KEY_CONFLICT')
        state = self.store.describe(OWNER, self.digest)
        self.assertEqual(state['catalogRevision'], 4)
        self.assertTrue(state['evaluationConflicted']); self.assertEqual(state['state'], 'suspended')
        conflicts = [e for e in self.store.events(OWNER)['events'] if e['kind'] == 'evaluation_conflict']
        self.assertEqual(len(conflicts), 1)
        before = business_rows(self.journal)
        self.assertEqual(self.store.evaluate(OWNER, self.digest, 'review-evaluator', 'shared'), receipt)
        self.assertEqual(business_rows(self.journal), before)
        self.code('PAT_EVALUATION_CONFLICT', self.store.transition, OWNER, self.digest,
                  expected_revision=4, target='active')
        self.journal.close()
        self.journal, self.registry = open_authority(self.path)
        self.store = catalog(self.journal)
        self.assertEqual(business_rows(self.journal), before)
        self.assertTrue(self.store.describe(OWNER, self.digest)['evaluationConflicted'])
        self.evaluate('fresh-after-conflict')
        refreshed = self.store.describe(OWNER, self.digest)
        self.assertFalse(refreshed['evaluationConflicted']); self.assertTrue(refreshed['eligibleForPromotion'])
        self.assertEqual(refreshed['state'], 'suspended')

    def test_cross_artifact_run_conflict_inhibits_both_and_preserves_retirement(self):
        other = artifact(); other['version'] = 'v2'
        other_digest = self.store.publish(OWNER, other)['artifactDigest']
        barrier, release = threading.Barrier(2), threading.Event()
        def evaluate(document, _environment):
            barrier.wait(timeout=3)
            if document['version'] == 'v2':
                if not release.wait(3): raise AssertionError('review thread not released')
                return result('failed')
            return result()
        store = catalog(self.journal, evaluate=evaluate)
        def run(digest):
            try: return store.evaluate(OWNER, digest, 'review-evaluator', 'cross-artifact')
            except JournalError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            one, two = pool.submit(run, self.digest), pool.submit(run, other_digest)
            try:
                self.assertIsInstance(one.result(timeout=3), dict)
                store.transition(OWNER, self.digest, expected_revision=3, target='active')
                store.transition(OWNER, other_digest, expected_revision=4, target='retired')
            finally:
                release.set()
            self.assertEqual(two.result(timeout=3), 'PAT_EVALUATION_KEY_CONFLICT')
        original, retired = store.describe(OWNER, self.digest), store.describe(OWNER, other_digest)
        self.assertEqual(original['catalogRevision'], 6)
        self.assertEqual(original['state'], 'suspended'); self.assertEqual(retired['state'], 'retired')
        for state in (original, retired):
            self.assertTrue(state['evaluationConflicted'])
            self.assertFalse(state['eligibleForPromotion']); self.assertFalse(state['eligibleForNewInstances'])
        event = store.events(OWNER)['events'][-1]
        conflicting = store.evaluation(OWNER, event['payload']['conflictingEvaluationDigest'])
        self.assertEqual(conflicting['artifactDigest'], other_digest)
        self.assertEqual(conflicting['outcome'], 'failed')
        self.evaluate('fresh-original-only')
        self.assertFalse(store.describe(OWNER, self.digest)['evaluationConflicted'])
        self.assertTrue(store.describe(OWNER, other_digest)['evaluationConflicted'])

    def test_negative_trial_completion_invalidates_older_promotion_revision(self):
        self.evaluate()
        stale_revision = self.store.describe(OWNER, self.digest)['catalogRevision']
        began, release = threading.Event(), threading.Event()
        def evaluate(_a, _e):
            began.set()
            if not release.wait(3): raise AssertionError('review thread not released')
            return result('failed')
        store = catalog(self.journal, evaluate=evaluate)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(store.evaluate, OWNER, self.digest, 'review-evaluator', 'late-failure')
            try:
                self.assertTrue(began.wait(3))
                activated = self.store.transition(OWNER, self.digest, expected_revision=stale_revision, target='active')
                self.assertEqual(activated['state'], 'active')
            finally:
                release.set()
            failed = future.result(timeout=3)
        self.assertEqual(failed['receipt']['outcome'], 'failed')
        current = self.store.describe(OWNER, self.digest)
        self.assertEqual(current['state'], 'suspended'); self.assertFalse(current['eligibleForNewInstances'])
        self.code('PAT_CATALOG_REVISION_CONFLICT', self.store.transition, OWNER, self.digest,
                  expected_revision=stale_revision, target='active')

    def test_successful_new_trial_also_requires_new_promotion(self):
        self.activate()
        self.evaluate('new-pass')
        state = self.store.describe(OWNER, self.digest)
        self.assertEqual(state['state'], 'suspended'); self.assertTrue(state['eligibleForPromotion'])
        self.assertFalse(state['eligibleForNewInstances'])

    def test_malformed_and_exception_results_record_inconclusive_not_eligibility(self):
        bad = [None, {}, result(), result(), result()]
        bad[2]['unresolvedEffects'] = True
        bad[3]['checks'].append(copy.deepcopy(bad[3]['checks'][0]))
        bad[4]['checks'][0]['evidenceDigest'] = 'sha256:' + 'A' * 64
        for i, value in enumerate(bad):
            with self.subTest(index=i):
                self.evaluate('before-bad:' + str(i))
                self.store.transition(OWNER, self.digest,
                    expected_revision=self.store._revision(OWNER.deployment), target='active')
                store = catalog(self.journal, evaluate=lambda _a, _e: value)
                receipt = store.evaluate(OWNER, self.digest, 'review-evaluator', 'bad:' + str(i))['receipt']
                self.assertEqual(receipt['outcome'], 'inconclusive')
                self.assertIsNotNone(receipt['evaluatorError']); self.assertFalse(receipt['physicalObjectiveVerified'])
                self.assertIsNone(receipt['result']['unresolvedEffects'])
                state = store.describe(OWNER, self.digest)
                self.assertEqual(state['state'], 'suspended')
                self.assertFalse(state['eligibleForPromotion']); self.assertFalse(state['eligibleForNewInstances'])
        def raising(_a, _e): raise RuntimeError('secret evaluator diagnostic must not be copied')
        self.evaluate('before-exception')
        self.store.transition(OWNER, self.digest,
            expected_revision=self.store._revision(OWNER.deployment), target='active')
        store = catalog(self.journal, evaluate=raising)
        receipt = store.evaluate(OWNER, self.digest, 'review-evaluator', 'exception')['receipt']
        self.assertEqual(receipt['evaluatorError'], 'RuntimeError')
        self.assertIsNone(receipt['result']['unresolvedEffects'])
        self.assertEqual(store.describe(OWNER, self.digest)['state'], 'suspended')
        self.assertNotIn('secret', json.dumps(receipt))

    def test_transient_inconclusive_trial_suspends_active_without_erasing_history(self):
        self.activate()
        prior = self.store.describe(OWNER, self.digest)['evaluationDigest']
        self.eval_result = result('inconclusive')
        newest = self.evaluate('transient-unavailable')
        self.assertIsNone(newest['receipt']['evaluatorError'])
        self.assertEqual(newest['receipt']['outcome'], 'inconclusive')
        state = self.store.describe(OWNER, self.digest)
        self.assertEqual(state['state'], 'suspended')
        self.assertEqual(state['evaluationDigest'], newest['evaluationDigest'])
        self.assertFalse(state['eligibleForNewInstances'])
        self.assertEqual(self.store.evaluation(OWNER, prior)['outcome'], 'passed')

    def test_suspend_and_retire_survive_unavailable_or_malformed_environment(self):
        self.activate()
        self.env['unrecognized'] = 'invalid'
        revision = self.store._revision(OWNER.deployment)
        suspended = self.store.transition(OWNER, self.digest, expected_revision=revision, target='suspended')
        self.assertEqual(suspended['state'], 'suspended'); self.assertFalse(suspended['eligibleForNewInstances'])
        retired = self.store.transition(OWNER, self.digest, expected_revision=suspended['catalogRevision'], target='retired')
        self.assertEqual(retired['state'], 'retired')
        self.code('PAT_TRANSITION_NOT_ALLOWED', self.store.transition, OWNER, self.digest,
                  expected_revision=retired['catalogRevision'], target='active')

    def test_nonreentrant_environment_provider_cannot_mutate_authority(self):
        self.evaluate()
        def reentrant(_context, _artifact):
            self.registry.grant(OWNER, OTHER.principal, '*', 'admin')
            return environment(OWNER, artifact())
        store = catalog(self.journal, env=reentrant)
        before = business_rows(self.journal)
        state = store.describe(OWNER, self.digest)
        self.assertFalse(state['eligibleForPromotion'])
        self.assertEqual(business_rows(self.journal), before)
        self.assertFalse(self.registry.allowed(OTHER, 'admin', '*'))

    def test_clock_loss_blocks_activation_but_not_authority_reduction(self):
        self.activate()
        def broken_clock(): raise RuntimeError('clock offline')
        self.journal.clock_ms = broken_clock
        revision = self.store._revision(OWNER.deployment)
        suspended = self.store.transition(OWNER, self.digest, expected_revision=revision, target='suspended')
        self.code('INVALID_CLOCK', self.store.transition, OWNER, self.digest,
                  expected_revision=suspended['catalogRevision'], target='active')
        retired = self.store.transition(OWNER, self.digest, expected_revision=suspended['catalogRevision'], target='retired')
        self.assertEqual(retired['state'], 'retired')
        events = self.store.events(OWNER)['events']
        self.assertEqual(events[-1]['clock_status'], 'unavailable_clamped')

    def test_revision_exhaustion_rolls_back_candidate_evaluation_and_event(self):
        self.activate()
        self.journal._db.execute('UPDATE pc_deployments SET revision=?', (SAFE_INTEGER,))
        before = business_rows(self.journal)
        state = self.store.describe(OWNER, self.digest)
        self.assertFalse(state['eligibleForNewInstances'])
        self.assertEqual(state['eligibilityReason'], 'PAT_REVISION_EXHAUSTED')
        self.code('PAT_REVISION_EXHAUSTED', self.evaluate, 'past-exhaustion')
        self.assertEqual(business_rows(self.journal), before)
        different = artifact(); different['version'] = 'v2'
        self.code('PAT_REVISION_EXHAUSTED', self.store.publish, OWNER, different)
        self.assertEqual(business_rows(self.journal), before)
        for invalid in (True, 1.0, -1, SAFE_INTEGER + 1):
            with self.subTest(revision=invalid), self.assertRaises(ContractError):
                self.store.transition(OWNER, self.digest, expected_revision=invalid, target='active')

    def test_event_cursor_must_not_exceed_committed_head(self):
        page = self.store.events(OWNER)
        self.assertEqual(page['headSequence'], 1)
        self.assertEqual(self.store.events(OWNER, after=1)['nextSequence'], 1)
        self.code('PAT_INVALID_CURSOR', self.store.events, OWNER, after=2)
        for invalid in (True, 1.0, -1, SAFE_INTEGER + 1):
            with self.subTest(cursor=invalid), self.assertRaises(ContractError):
                self.store.events(OWNER, after=invalid)


class PatCatalogAbruptProcessTests(unittest.TestCase):
    def test_dirty_transaction_and_postcommit_process_death(self):
        phases = ('publish_inside','evaluate_inside','activate_inside',
                  'publish_after','evaluate_after','activate_after')
        for phase in phases:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory(prefix='hms-pat-crash-review-') as directory:
                path = Path(directory) / 'authority.db'
                journal, _registry = open_authority(path, create=True)
                store = catalog(journal)
                document = artifact(); digest = pat_digest(document)
                journal._db.execute('CREATE TABLE review_crash_spill (payload BLOB NOT NULL)')
                if not phase.startswith('publish'):
                    store.publish(OWNER, document)
                if phase.startswith('activate'):
                    store.evaluate(OWNER, digest, 'review-evaluator', 'baseline-run')
                before = business_rows(journal)
                journal.close()
                command = [sys.executable, '-B', str(Path(__file__).resolve()), '--crash', str(path), phase]
                root = Path(__file__).resolve().parents[1]
                child_env = dict(os.environ)
                child_env['PYTHONPATH'] = str(root) + os.pathsep + child_env.get('PYTHONPATH', '')
                child = subprocess.run(command, cwd=root, env=child_env,
                                       capture_output=True, timeout=10)
                self.assertEqual(child.returncode, 79 if phase.endswith('inside') else 80, child.stderr)
                self.assertFalse(child.stdout); self.assertFalse(child.stderr)
                journal, _registry = open_authority(path)
                try:
                    store = catalog(journal)
                    if phase.endswith('inside'):
                        self.assertEqual(business_rows(journal), before)
                        marker = json.loads(Path(str(path) + '.dirty.json').read_text())
                        self.assertGreater(marker['bytes'], 0)
                        self.assertNotEqual(marker['header'], '0000000000000000')
                    else:
                        expected = {'publish_after':'candidate','evaluate_after':'evaluated','activate_after':'active'}[phase]
                        entry = store.describe(OWNER, digest)
                        self.assertEqual(entry['state'], expected)
                        current = business_rows(journal)
                        self.assertEqual(entry['catalogRevision'], len(before['pc_events']) + 1)
                        self.assertEqual(store.publish(OWNER, document)['artifactDigest'], digest)
                        if phase == 'evaluate_after':
                            store.evaluate(OWNER, digest, 'review-evaluator', 'crash-run')
                        self.assertEqual(business_rows(journal), current)
                    self.assertEqual(journal._db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                    self.assertEqual(journal._db.execute('SELECT count(*) FROM review_crash_spill').fetchone()[0], 0)
                    LAST_REPORT['crashCases'].append({'phase':phase,'exitCode':child.returncode,
                        'dirtyRollbackObserved':phase.endswith('inside'),'reopenedIntegrity':'ok',
                        'partialBusinessTransitionAbsent':phase.endswith('inside'),
                        'committedStateRetained':phase.endswith('after')})
                finally:
                    journal.close()


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--crash':
        crash_worker(sys.argv[2], sys.argv[3])
    else:
        unittest.main()
