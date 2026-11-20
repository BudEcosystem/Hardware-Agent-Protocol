"""Prepared behavioral tests; fixture proposals are not agent/learning evidence."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from hms.contracts import canonical, parse_json
from intent_handoff.consumer import AgentConsumer, Dispatcher
from intent_handoff.contracts import HandoffError, MAX_RECORD
from intent_handoff.store import IntentStore

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'planning-owner'
STORE = 'test-intent-store'
CAPACITY = {'maxRecords': 129, 'maxBytes': 8 * 1024 * 1024}


def intent(key='intent:1', revision=0, prompt='Set the simulated fan to 40%, then 20%.'):
    return dict(profile='hms.application-intent/0.1', applicationId='application:fan',
                operationKey=key, expectedRevision=revision, prompt=prompt)


def candidate(receipt, key='proposal:1'):
    return dict(profile='hms.application-proposal/0.1', applicationId=receipt['applicationId'],
        intentRevision=receipt['revision'], operationKey=key, expectedHandoffDigest=receipt['handoffDigest'],
        interpretation='A finite pair of simulated fan commands; no standing control or physical claim.',
        discovery=[], proposal=dict(kind='supported_candidate',
            artifact=parse_json((ROOT / 'tests/fan-artifact.json').read_bytes()),
            initialParameters={'initialLevel': 40, 'finalLevel': 20}),
        plannerAttribution=dict(kind='scripted-fixture', sessionId=None, callId=None, model=None))


class CommitFault:
    def __init__(self, connection, *, after):
        self.connection, self.after, self.armed = connection, after, True

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, sql, *args):
        if sql == 'COMMIT' and self.armed:
            self.armed = False
            if self.after:
                self.connection.execute(sql, *args)
            raise sqlite3.OperationalError('injected ambiguous commit result')
        return self.connection.execute(sql, *args)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='hms-intent-test-')
        self.path = Path(self.directory.name) / 'intent.db'
        self.capacity = dict(CAPACITY)
        self.store = self.open(create=True)

    def open(self, *, create=False, owner=OWNER, store_id=STORE, capacity=None):
        return IntentStore(self.path, owner=owner, store_id=store_id,
                           capacity=self.capacity if capacity is None else capacity, create=create)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def call(self, method, params):
        return self.store.request(OWNER, method, params)

    def failure(self, code, call):
        with self.assertRaises(HandoffError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def status(self, **extra):
        return self.call('intent_get', {'applicationId': 'application:fan', **extra})

    def raw_mutate(self, sql, args=()):
        with sqlite3.connect(self.path) as connection:
            connection.execute(sql, args)

    def test_exact_prompt_bytes_and_replay_after_proposal_and_revision(self):
        prompt = '  Cafe\u0301\r\n café\n🙂  '
        request = intent(prompt=prompt)
        first = self.call('intent_put', request)
        proposal = candidate(first)
        committed = self.call('proposal_put', proposal)
        self.call('intent_put', intent('intent:2', 1, 'A new requirement.'))
        self.assertEqual(self.call('intent_put', request), first)
        self.assertEqual(self.call('proposal_put', proposal), committed)
        historical = self.status(revision=1)
        self.assertTrue(historical['superseded'])
        self.assertEqual(historical['intent']['prompt'].encode('utf-8'), prompt.encode('utf-8'))
        self.assertEqual(historical['state'], 'proposed')
        self.assertEqual(self.status()['state'], 'awaiting_proposal')
        self.assertNotEqual(first['handoffDigest'], self.status()['receipt']['handoffDigest'])

    def test_one_key_cannot_change_text_or_change_method(self):
        request = intent()
        receipt = self.call('intent_put', request)
        self.failure('IH_KEY_CONFLICT', lambda: self.call('intent_put', {**request, 'prompt': request['prompt'] + ' '}))
        self.failure('IH_KEY_CONFLICT', lambda: self.call('proposal_put', candidate(receipt, request['operationKey'])))
        self.assertEqual(self.status()['usage']['records'], 2)

    def test_stale_uncommitted_proposal_and_single_proposal_slot(self):
        first = self.call('intent_put', intent())
        old = candidate(first)
        second = self.call('intent_put', intent('intent:2', 1, 'Changed objective.'))
        self.failure('IH_STALE_PROPOSAL', lambda: self.call('proposal_put', old))
        current = candidate(second)
        self.call('proposal_put', current)
        self.failure('IH_PROPOSAL_ALREADY_COMMITTED',
                     lambda: self.call('proposal_put', {**current, 'operationKey': 'proposal:2'}))

    def test_wrong_handoff_and_revision_do_not_create_records(self):
        first = self.call('intent_put', intent())
        value = candidate(first)
        value['expectedHandoffDigest'] = 'sha256:' + '0' * 64
        self.failure('IH_HANDOFF_CONFLICT', lambda: self.call('proposal_put', value))
        self.failure('IH_REVISION_CONFLICT', lambda: self.call('intent_put', intent('intent:wrong', 0)))
        self.assertEqual(self.status()['usage']['records'], 2)

    def test_unsupported_result_is_retained_without_pass_or_execution(self):
        receipt = self.call('intent_put', intent(prompt='Maintain airflow forever using a physical fan.'))
        value = candidate(receipt)
        value['proposal'] = dict(kind='unresolved', reason='unsupported_profile',
            details='This finite simulation profile cannot express standing physical feedback.')
        reply = self.call('proposal_put', value)
        self.assertEqual(reply['state'], 'unresolved')
        self.assertIsNone(reply['artifactDigest'])
        self.assertEqual(reply['qualification']['state'], 'unavailable')
        self.assertEqual(self.status()['proposal']['request'], value)

    def test_plain_and_wire_requests_reject_unknown_shapes_and_numeric_coercion(self):
        dispatcher = Dispatcher(self.store, principal=OWNER)
        cases = [dict(intent(), principal=OWNER), dict(intent(), expectedRevision=False),
                 dict(intent(), expectedRevision=0.0), dict(intent(), prompt=''),
                 dict(intent(), prompt='🙂' * 2049)]
        for value in cases:
            with self.subTest(value=list(value)):
                self.assertFalse(dispatcher.request('intent_put', value)['ok'])
        wire = b'{"method":"intent_put","params":{"profile":"hms.application-intent/0.1","applicationId":"application:fan","operationKey":"intent:1","expectedRevision":0.0,"prompt":"hello"}}'
        self.assertFalse(parse_json(dispatcher.dispatch(wire))['ok'])
        duplicate = b'{"method":"intent_get","method":"intent_put","params":{}}'
        self.assertFalse(parse_json(dispatcher.dispatch(duplicate))['ok'])
        self.assertFalse(parse_json(dispatcher.dispatch(b'{"method":"invoke","params":{}}'))['ok'])
        self.assertFalse(parse_json(dispatcher.dispatch(b'{"method":"intent_get","params":{},"principal":"planning-owner"}'))['ok'])

    def test_parser_and_static_initial_parameters_are_enforced(self):
        receipt = self.call('intent_put', intent())
        original = candidate(receipt)
        variants = []
        value = copy.deepcopy(original); value['proposal']['initialParameters']['initialLevel'] = 40.0; variants.append(value)
        value = copy.deepcopy(original); value['proposal']['initialParameters']['initialLevel'] = True; variants.append(value)
        value = copy.deepcopy(original); value['proposal']['initialParameters']['initialLevel'] = 101; variants.append(value)
        value = copy.deepcopy(original); value['proposal']['artifact']['outcomeContract']['physicalObjectiveVerified'] = True; variants.append(value)
        value = copy.deepcopy(original); value['proposal']['artifact']['steps'][0]['code'] = 'arbitrary program'; variants.append(value)
        value = copy.deepcopy(original); value['proposal']['passed'] = True; variants.append(value)
        value = copy.deepcopy(original); value['proposal']['artifact']['applicability']['all'].append(
            dict(field='parameters.initialLevel', op='range', minimum=50, maximum=100)); variants.append(value)
        for value in variants:
            self.assertFalse(Dispatcher(self.store, principal=OWNER).request('proposal_put', value)['ok'])
        self.assertEqual(self.status()['usage']['records'], 2)

    def test_principal_is_not_request_authority(self):
        self.failure('IH_ACCESS_DENIED', lambda: self.store.request('different-owner', 'intent_put', intent()))
        dispatcher = Dispatcher(self.store, principal='different-owner')
        reply = dispatcher.request('intent_put', intent())
        self.assertEqual(reply['error']['code'], 'IH_ACCESS_DENIED')
        self.call('intent_put', intent())
        self.failure('IH_ACCESS_DENIED', lambda: self.store.request('different-owner', 'intent_get', {'applicationId': 'application:fan'}))

    def test_reopen_requires_original_identity_owner_and_caps(self):
        self.call('intent_put', intent())
        before = self.status()
        self.store.close()
        for options in ({'owner': 'other-owner'}, {'store_id': 'another-store'},
                        {'capacity': {'maxRecords': 128, 'maxBytes': CAPACITY['maxBytes']}}):
            self.failure('IH_METADATA_CHANGED', lambda options=options: self.open(**options))
        self.store = self.open()
        self.assertEqual(self.status(), before)

    def test_record_full_refuses_before_append_and_preserves_reads_and_replay(self):
        self.store.close(); self.path.unlink()
        self.capacity['maxRecords'] = 2
        self.store = self.open(create=True)
        request = intent(); receipt = self.call('intent_put', request)
        before = self.status()
        self.failure('IH_CAPACITY', lambda: self.call('proposal_put', candidate(receipt)))
        self.failure('IH_CAPACITY', lambda: self.call('intent_put', intent('intent:2', 1)))
        self.assertEqual(self.status(), before)
        self.assertEqual(self.call('intent_put', request), receipt)

    def test_total_byte_cap_includes_retained_request_result_and_metadata(self):
        self.store.close(); self.path.unlink()
        self.capacity['maxBytes'] = 1200
        self.store = self.open(create=True)
        self.failure('IH_CAPACITY', lambda: self.call('intent_put', intent(prompt='x' * 900)))
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM ih_records').fetchone()[0], 0)
        self.failure('IH_INTENT_NOT_FOUND', self.status)

    def test_detached_aliases_cannot_rewrite_retained_input_or_output(self):
        request = intent(); receipt = self.call('intent_put', request)
        original_id = receipt['handoffDigest']
        request['prompt'] = 'mutated'; receipt['qualification']['state'] = 'passed'
        value = candidate({**receipt, 'handoffDigest': original_id})
        self.call('proposal_put', value)
        value['proposal']['artifact']['name'] = 'changed-after-commit'
        saved = self.status()
        self.assertNotEqual(saved['intent']['prompt'], 'mutated')
        self.assertEqual(saved['qualification']['state'], 'unavailable')
        self.assertNotEqual(saved['proposal']['request']['proposal']['artifact']['name'], 'changed-after-commit')

    def test_two_connections_serialize_one_revision_slot(self):
        other = self.open()
        try:
            def attempt(store, key):
                try:
                    return store.request(OWNER, 'intent_put', intent(key))
                except HandoffError as error:
                    return error.code
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(attempt, self.store, 'intent:a'), pool.submit(attempt, other, 'intent:b')]
                results = [future.result() for future in futures]
            self.assertEqual(sum(type(result) is dict for result in results), 1)
            self.assertIn('IH_REVISION_CONFLICT', results)
            self.assertEqual(self.status()['usage']['records'], 2)
        finally:
            other.close()

    def test_concurrent_close_waits_for_the_inflight_commit(self):
        entered, release, closing, closed = (threading.Event() for _ in range(4))
        connection = self.store._db
        class PausedInsert:
            def __getattr__(self, name):
                return getattr(connection, name)

            def execute(self, sql, *args):
                result = connection.execute(sql, *args)
                if sql.startswith('INSERT INTO ih_records'):
                    entered.set()
                    if not release.wait(5):
                        raise AssertionError('test did not release the pending commit')
                return result
        self.store._db = PausedInsert()
        def close():
            closing.set()
            self.store.close()
            closed.set()
        with ThreadPoolExecutor(max_workers=2) as pool:
            mutation = pool.submit(self.call, 'intent_put', intent())
            self.assertTrue(entered.wait(5))
            ending = pool.submit(close)
            try:
                self.assertTrue(closing.wait(5))
                self.assertFalse(closed.wait(0.05))
            finally:
                release.set()
            receipt = mutation.result(timeout=5)
            ending.result(timeout=5)
        self.assertTrue(closed.is_set())
        self.store.close()  # Idempotent after the racing close.
        self.store = self.open()
        self.assertEqual(self.status()['receipt'], receipt)

    def test_failed_commit_rolls_back_and_ambiguous_commit_replays_exactly(self):
        for after in (False, True):
            with self.subTest(after=after):
                request = intent('intent:after' if after else 'intent:before')
                connection = self.store._db
                self.store._db = CommitFault(connection, after=after)
                try:
                    self.failure('IH_STORAGE_UNAVAILABLE', lambda: self.call('intent_put', request))
                finally:
                    self.store._db = connection
                if after:
                    original = self.status()['receipt']
                    self.assertEqual(self.call('intent_put', request), original)
                else:
                    self.failure('IH_INTENT_NOT_FOUND', self.status)

    def test_independent_process_reopen_retains_exact_proposal(self):
        receipt = self.call('intent_put', intent())
        value = candidate(receipt)
        self.call('proposal_put', value)
        expected = self.status()
        self.store.close()
        completed = subprocess.run([sys.executable, '-B', '-I', str(ROOT / 'run_tests.py'),
            '--reopen-child', str(self.path)], check=True, capture_output=True, timeout=30,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        attempt = os.environ.get('HMS_INTENT_TEST_ATTEMPT')
        if attempt:
            with (Path(attempt) / 'reopen-child.json').open('x', encoding='utf-8') as retained:
                json.dump(dict(exitCode=completed.returncode, stdoutBytes=len(completed.stdout),
                    stdoutSha256=hashlib.sha256(completed.stdout).hexdigest(),
                    stderrBytes=len(completed.stderr), stderrSha256=hashlib.sha256(completed.stderr).hexdigest(),
                    timeoutSeconds=30, reaped=True), retained, indent=2)
        self.assertEqual(json.loads(completed.stdout), expected)
        self.store = self.open()

    def test_corrupt_record_result_refuses_without_repair_or_new_mutation(self):
        self.call('intent_put', intent())
        row = self.store._db.execute('SELECT body FROM ih_records').fetchone()[0]
        value = parse_json(row); value['result']['intentDigest'] = 'sha256:' + '0' * 64
        damaged = canonical(value)
        self.raw_mutate('UPDATE ih_records SET body=? WHERE sequence=1', (damaged,))
        self.failure('IH_CORRUPT', self.status)
        self.failure('IH_CORRUPT', lambda: self.call('intent_put', intent('intent:2', 1)))
        self.assertEqual(self.store._db.execute('SELECT body FROM ih_records').fetchone()[0], damaged)

    def test_oversized_blob_and_sequence_gap_are_refused(self):
        self.call('intent_put', intent())
        self.raw_mutate('UPDATE ih_records SET body=zeroblob(?)', (MAX_RECORD + 1,))
        self.failure('IH_CORRUPT', self.status)
        self.raw_mutate('DELETE FROM ih_records')
        self.raw_mutate('INSERT INTO ih_records VALUES (2,?)', (b'{}',))
        self.failure('IH_CORRUPT', self.status)

    def test_extra_schema_and_metadata_change_refuse_before_mutation(self):
        self.call('intent_put', intent())
        self.raw_mutate('CREATE TABLE surprise (body BLOB)')
        self.failure('IH_CORRUPT', self.status)
        self.raw_mutate('DROP TABLE surprise')
        self.raw_mutate('UPDATE ih_meta SET body=?', (b'{}',))
        self.failure('IH_METADATA_CHANGED', self.status)

    def test_existing_read_contracts_run_before_callback_and_validate_reply(self):
        calls = []
        def read(method, params):
            calls.append((method, params))
            return {'ok': False, 'error': {'code': 'OBSERVATION_UNAVAILABLE'}, 'outcome': 'unconfirmed'}
        consumer = AgentConsumer(Dispatcher(self.store, principal=OWNER), read_hardware=read)
        self.failure('IH_READ_METHOD_REQUIRED', lambda: consumer.inspect('invoke', {'request': {}}))
        self.failure('IH_INVALID_DISCOVERY', lambda: consumer.inspect('observe',
            {'instanceId': 'sim:fan', 'property': 'level', 'maxAgeMs': 600001}))
        self.failure('IH_INVALID_DISCOVERY', lambda: consumer.inspect('describe',
            {'instanceId': 'sim:fan', 'digest': 'not-a-digest'}))
        self.assertEqual(calls, [])
        accepted = consumer.inspect('observe', {'instanceId': 'sim:fan', 'property': 'level'})
        self.assertFalse(accepted['ok'])
        self.assertEqual(len(calls), 1)
        bad = AgentConsumer(consumer.dispatcher, read_hardware=lambda *args: {'ok': True, 'result': {}})
        self.failure('IH_INVALID_DISCOVERY', lambda: bad.inspect('discover', {}))

    def test_attributed_discovery_is_checked_but_never_promotes(self):
        receipt = self.call('intent_put', intent())
        value = candidate(receipt)
        value['discovery'] = [dict(method='discover', params={}, sessionId='fixture', callId='fixture:read',
            reply={'ok': True, 'result': {'items': [], 'cursor': None, 'registryRevision': 1}})]
        reply = self.call('proposal_put', value)
        self.assertEqual(reply['qualification']['state'], 'unavailable')
        self.assertEqual(reply['attributionVerification'], 'unverified')

    def test_store_and_replay_never_call_planner_or_hardware(self):
        calls = []
        consumer = AgentConsumer(Dispatcher(self.store, principal=OWNER),
                                 read_hardware=lambda *args: calls.append(args))
        with patch('hms.journal.Journal.__init__', side_effect=AssertionError('authority must not be constructed')):
            receipt = self.call('intent_put', intent())
            value = candidate(receipt)
            consumer.propose(value); consumer.handoff('application:fan'); consumer.propose(value)
            self.store.close(); self.store = self.open()
            self.call('proposal_put', value)
        self.assertEqual(calls, [])
        self.assertNotIn('hms.runtime', sys.modules)
        self.assertFalse(any(name.startswith('hms_qualification') for name in sys.modules))


if __name__ == '__main__':
    unittest.main()
