"""Selection and deadline regressions on real authority rows and local routes."""
from unittest.mock import patch

from test_multi_adapter import MultiHarness as _MultiHarness, installation


class ProcedureSchedulerTests(_MultiHarness):
    def test_expired_selection_precedes_limit_and_keeps_unexpired_claims(self):
        config = installation('expiry-filter')
        self.open([config], create=True)
        first = self.invoke(self.prepare(config, 'fan', key='long-fan'))
        second = self.invoke(self.prepare(config, 'focus', key='long-focus'))
        expired = self.invoke(self.prepare(config, 'inspection', key='short-inspection', timing={
            'notBeforeUnixMs': self.wall, 'latestStartUnixMs': self.wall + 100,
            'maxRunMs': 1000, 'latestCompletionUnixMs': self.wall + 5000}))
        self.wall += 200
        self.mono += 200
        selected = self.runtime.work_items(config['adapterId'], ('accepted',),
                                          limit=1, expired_ms=self.wall)
        self.assertEqual([op['id'] for op in selected], [expired['operationId']])
        # Exercise the actual expiry path with a small page, so earlier waiting
        # rows cannot hide the later expired item. No synthetic ledger rows.
        original = self.runtime.work_items

        def small_page(*args, **kwargs):
            kwargs['limit'] = 1
            return original(*args, **kwargs)

        with patch.object(self.runtime, 'work_items', side_effect=small_page):
            self.runtime.expire_unstarted(config['adapterId'])
        current = self.status(expired)
        self.assertEqual(current['executionState'], 'rejected_before_dispatch')
        self.assertFalse(current['resourceClaims'])
        for operation in (first, second):
            self.assertEqual(self.status(operation)['executionState'], 'accepted')
            self.assertTrue(self.status(operation)['resourceClaims'])

    def test_missed_later_child_start_expires_parent_without_new_child(self):
        config = installation('later-deadline')
        self.open([config], create=True)
        first = self.prepare(config, 'fan', key='first')
        later = self.prepare(config, 'focus', key='later', timing={
            'notBeforeUnixMs': self.wall, 'latestStartUnixMs': self.wall + 100,
            'maxRunMs': 1000, 'latestCompletionUnixMs': self.wall + 5000})
        request = {'protocol': 'hms.procedure/0.1', 'replayNamespace': self.namespace,
            'procedureKey': 'deadline-parent', 'procedure': {'profile': 'hms.bound-sequence/0.1',
                'timing': {'notBeforeUnixMs': self.wall, 'latestStartUnixMs': self.wall + 3000,
                           'latestCompletionUnixMs': self.wall + 5000},
                'steps': [{'stepId': 'first', 'request': first}, {'stepId': 'later', 'request': later}]}}
        parent = self.call('procedure_submit', request=request)
        self.runtime.tick()
        self.advance(200)
        status = self.call('procedure_status', procedureId=parent['procedureId'])
        self.assertEqual(status['executionState'], 'expired')
        self.assertEqual(status['reason'], 'START_EXPIRED')
        self.assertEqual(status['steps'][0]['executionState'], 'completed')
        self.assertIsNone(status['steps'][1]['operationId'])
        self.assertEqual(self.runtime.adapters[config['adapterId']].plant.observe(
            config['instances']['focus'])['effectCount'], 0)
