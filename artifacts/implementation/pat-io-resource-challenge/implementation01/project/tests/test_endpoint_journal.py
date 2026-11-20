"""Independent compact-adapter journal invariants; trusted test policy, no I/O."""
from pathlib import Path
import tempfile
import unittest

from hms.api_contracts import validate_result
from hms.journal import Journal, JournalError
from journal_support import CONTEXT, TestPolicy, evidence, request


class EndpointJournalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'authority.db'
        self.policy = TestPolicy()
        self.now = 1000
        self.journal = Journal(self.path, self.policy, clock_ms=lambda: self.now, create=True)
        self.addCleanup(lambda: self.journal.close())
        namespace = self.journal.issue_namespace(CONTEXT, 3000)['token']
        self.operation = self.journal.submit(CONTEXT, request(namespace))
        self.id = self.operation['id']

    def reopen(self):
        self.journal.close()
        self.journal = Journal(self.path, self.policy, clock_ms=lambda: self.now)

    def status(self):
        return self.journal.status(CONTEXT, self.id)

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(JournalError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def check_api(self):
        op = self.status()
        public = {'protocol': 'hms.operation/0.1', 'operationId': op['id'],
                  'requestDigest': op['digest'], 'instanceId': op['intent']['instanceId'],
                  'actionId': op['intent']['actionId'], 'executionState': op['state'],
                  'cancellationState': op['cancel_state'], 'effectVerification': op['verification'],
                  'mayHaveActed': op['may_have_acted'], 'eventSequence': op['sequence'],
                  'resourceClaims': op['claims'], 'result': None}
        self.assertEqual(validate_result('operation', public, {'operationId': self.id}), public)
        events = self.journal.events(CONTEXT, self.id)
        self.assertEqual(validate_result('events', events, {'operationId': self.id}), events)

    def mapping_table(self):
        self.journal._db.execute('CREATE TABLE test_endpoint_mapping(operation TEXT PRIMARY KEY, attempt TEXT NOT NULL, owner INTEGER NOT NULL, payload BLOB NOT NULL)')

    def reserve(self, snapshot, ticket, now):
        self.assertEqual(now, self.now)
        self.journal._db.execute('INSERT INTO test_endpoint_mapping VALUES (?,?,?,?)',
                                (snapshot['id'], ticket.attempt_id, ticket.owner_epoch, b'bounded exact OP bytes'))
        # The installed callback receives a private snapshot, not authority aliases.
        snapshot['intent']['arguments']['distance'] = 999
        snapshot['claims'].clear()

    def test_reserve_failure_rolls_back_mapping_and_dispatch_together(self):
        self.mapping_table()
        def fail(snapshot, ticket, now):
            self.reserve(snapshot, ticket, now)
            raise OSError('synthetic reservation write failure')
        with self.assertRaises(OSError):
            self.journal.claim_dispatch(self.id, _reserve=fail)
        self.assertEqual(self.status(), self.operation)
        self.assertEqual(self.journal._db.execute('SELECT COUNT(*) FROM test_endpoint_mapping').fetchone()[0], 0)

    def test_event_failure_after_reserve_rolls_back_and_reopen_has_no_mapping(self):
        self.mapping_table()
        original = self.journal._event
        def fail_event(*_):
            raise OSError('synthetic dispatch-event write failure')
        self.journal._event = fail_event
        try:
            with self.assertRaises(OSError):
                self.journal.claim_dispatch(self.id, _reserve=self.reserve)
        finally:
            self.journal._event = original
        self.reopen()
        self.assertEqual(self.status()['state'], 'accepted')
        self.assertFalse(self.status()['may_have_acted'])
        self.assertEqual(self.status()['claims'], self.operation['claims'])
        self.assertEqual(self.journal._db.execute('SELECT COUNT(*) FROM test_endpoint_mapping').fetchone()[0], 0)

    def test_mapping_and_ticket_survive_reopen_without_new_dispatch(self):
        self.mapping_table()
        ticket = self.journal.claim_dispatch(self.id, _reserve=self.reserve)
        self.assertEqual(self.status()['intent'], self.operation['intent'])
        self.assertEqual(self.status()['claims'], self.operation['claims'])
        self.reopen()
        stored = dict(self.journal._db.execute('SELECT * FROM test_endpoint_mapping').fetchone())
        self.assertEqual(stored, {'operation': self.id, 'attempt': ticket.attempt_id,
                                 'owner': ticket.owner_epoch, 'payload': b'bounded exact OP bytes'})
        self.assertEqual(self.status()['state'], 'outcome_unknown')
        self.assertTrue(self.status()['may_have_acted'])
        self.assertEqual(self.status()['claims'], self.operation['claims'])
        self.assert_code('STALE_WORKER', self.journal.record_execution, ticket, 'running', evidence('running'))
        self.assert_code('NOT_DISPATCHABLE', self.journal.claim_dispatch, self.id, _reserve=self.reserve)

    def test_proven_start_exclusion_after_handoff_has_distinct_state_and_valid_api(self):
        ticket = self.journal.claim_dispatch(self.id)
        excluded = self.journal.record_execution(ticket, 'rejected_before_start', evidence('start_excluded'))
        self.assertEqual(excluded['state'], 'rejected_before_start')
        self.assertFalse(excluded['may_have_acted'])
        self.assertFalse(excluded['claims'])
        self.check_api()
        self.assertEqual(self.journal.events(CONTEXT, self.id)['events'][-1]['kind'], 'execution_evidence')

    def test_proven_start_exclusion_after_owner_reopen_has_valid_reconciled_event(self):
        self.journal.claim_dispatch(self.id)
        self.reopen()
        self.journal.reconcile(self.id, 'rejected_before_start', evidence('start_excluded'))
        self.check_api()
        self.assertEqual(self.journal.events(CONTEXT, self.id)['events'][-1]['kind'], 'reconciled')

    def test_canceled_before_endpoint_start_can_clear_claims_with_explicit_exclusion(self):
        ticket = self.journal.claim_dispatch(self.id)
        self.journal.request_cancel(CONTEXT, self.id)
        canceled = self.journal.record_execution(ticket, 'canceled', evidence('terminated', 'start_excluded'))
        self.assertEqual(canceled['cancel_state'], 'confirmed')
        self.assertFalse(canceled['may_have_acted'])
        self.assertFalse(canceled['claims'])
        self.check_api()

    def test_recorded_running_cannot_be_erased_by_unknown_then_start_exclusion(self):
        ticket = self.journal.claim_dispatch(self.id)
        self.journal.record_execution(ticket, 'running', evidence('running'))
        self.journal.mark_unknown(ticket, 'lost_response')
        for reopen in (False, True):
            with self.subTest(reopen=reopen):
                if reopen:
                    self.reopen()
                for state, assertions in [('rejected_before_start', ('start_excluded',)),
                                          ('canceled', ('terminated', 'start_excluded'))]:
                    self.assert_code('INVALID_START_EXCLUSION', self.journal.reconcile,
                                     self.id, state, evidence(*assertions))
                self.assertEqual(self.status()['state'], 'outcome_unknown')
                self.assertTrue(self.status()['may_have_acted'])
                self.assertEqual(self.status()['claims'], self.operation['claims'])

    def test_disputed_completion_latches_and_retains_claims_after_reopen(self):
        ticket = self.journal.claim_dispatch(self.id)
        completed = self.journal.record_execution(ticket, 'completed', evidence('completed', 'disputed'))
        self.assertEqual(completed['verification'], 'disputed')
        self.assert_code('QUIESCENCE_REQUIRED', self.journal.release_resources,
                         self.id, evidence('resources_quiescent'))
        self.reopen()
        self.assertEqual(self.status()['verification'], 'disputed')
        self.assertEqual(self.status()['claims'], self.operation['claims'])
        self.assert_code('QUIESCENCE_REQUIRED', self.journal.release_resources,
                         self.id, evidence('resources_quiescent'))
        self.check_api()

    def test_quiescence_assertion_cannot_hide_same_evidence_dispute(self):
        ticket = self.journal.claim_dispatch(self.id)
        self.journal.record_execution(ticket, 'completed', evidence('completed'))
        prior = self.status()
        self.assert_code('QUIESCENCE_REQUIRED', self.journal.release_resources, self.id,
                         evidence('resources_quiescent', 'disputed'))
        self.assertEqual(self.status(), prior)

    def test_no_effect_cancellation_refuses_dispute_without_corrupting_api(self):
        self.journal.request_cancel(CONTEXT, self.id)
        prior = self.status()
        self.assert_code('INVALID_DISPUTE', self.journal.dispute, self.id, evidence('disputed'))
        self.assertEqual(self.status(), prior)
        self.check_api()

    def test_start_exclusion_rejects_contradictory_verification_assertions(self):
        ticket = self.journal.claim_dispatch(self.id)
        prior = self.status()
        for contradiction in ('verification_failed', 'disputed'):
            with self.subTest(contradiction=contradiction):
                self.assert_code('INVALID_START_EXCLUSION', self.journal.record_execution,
                                 ticket, 'rejected_before_start', evidence('start_excluded', contradiction))
                self.assertEqual(self.status(), prior)


if __name__ == '__main__':
    unittest.main()
