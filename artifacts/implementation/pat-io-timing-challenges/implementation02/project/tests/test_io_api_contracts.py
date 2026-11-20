"""Typed finite-I/O receipt projections at the public API boundary.

These are original bounded carrier specimens, not physical or provider evidence.
Real provider receipt validation and transport execution have separate suites.
"""
import copy
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from hms.api_contracts import ResponseError, validate_result
from hms.synthetic_io_adapter import IoRouteAdapter

PROFILE = 'hms.synthetic-io-result/1'
PIN = {'kind': 'pin', 'mode': 'high_impedance', 'level': None}
TIMER = {'kind': 'timer', 'enabled': False, 'frequencyHz': 0, 'resolutionBits': 0}
CHANNEL = {'kind': 'timer_channel', 'enabled': False, 'dutyPermille': 0}


def operation(state='completed', *, primitive='gpio_pulse', cycle=None):
    if cycle is None:
        cycle = state == 'completed'
    idle = {'atom:pin5': copy.deepcopy(PIN)}
    if primitive == 'pwm_burst':
        idle.update({'atom:timer0': copy.deepcopy(TIMER), 'atom:channel0': copy.deepcopy(CHANNEL)})
    return {'protocol': 'hms.operation/0.1', 'operationId': 'op:carrier',
            'requestDigest': 'sha256:' + '1' * 64, 'instanceId': 'sim:io-alias',
            'actionId': 'custom:finite-action', 'executionState': state,
            'cancellationState': 'confirmed' if state == 'canceled' else 'not_requested',
            'effectVerification': 'unverified', 'mayHaveActed': True, 'eventSequence': 5,
            'resourceClaims': [], 'result': {'evidenceKind': 'simulation', 'output': {
                'profile': PROFILE, 'primitive': primitive, 'receiptDigest': 'sha256:' + '2' * 64,
                'result': {'activationCommitted': True, 'cycleCompleted': cycle, 'safeIdle': True,
                           'reason': None if cycle else 'authority_or_binding_lost'},
                'safeIdleState': idle}}}


class IoApiContractsTests(unittest.TestCase):
    def valid(self, value):
        self.assertIs(validate_result('operation', value, {'operationId': value['operationId']}), value)

    def invalid(self, value):
        with self.assertRaises(ResponseError):
            self.valid(value)

    def test_completed_gpio_and_pwm_keep_explicit_cycle_semantics(self):
        for primitive in ('gpio_pulse', 'pwm_burst'):
            with self.subTest(primitive=primitive):
                value = operation(primitive=primitive)
                self.valid(value)
                self.assertNotIn('effectCommitted', value['result']['output'])
                self.assertEqual(value['actionId'], 'custom:finite-action')

    def test_canceled_and_failed_results_preserve_prior_activation(self):
        for state, reason in (('canceled', 'client_cancel'), ('failed', 'authority_or_binding_lost')):
            with self.subTest(state=state):
                value = operation(state)
                value['result']['output']['result']['reason'] = reason
                self.valid(value)
                self.assertTrue(value['mayHaveActed'])
                self.assertTrue(value['result']['output']['result']['activationCommitted'])
                self.assertFalse(value['result']['output']['result']['cycleCompleted'])

    def test_historical_terminal_receipt_can_precede_authority_settlement(self):
        for state in ('dispatching', 'running', 'outcome_unknown'):
            for cycle in (False, True):
                with self.subTest(state=state, cycle=cycle):
                    value = operation(state, cycle=cycle)
                    value['resourceClaims'] = [{'resource': 'atom:pin5', 'fence': 8}]
                    self.valid(value)
                    # The historical idle snapshot does not mean this authority
                    # has released its claim or promise that the pad is idle now.
                    self.assertEqual(value['resourceClaims'][0]['fence'], 8)

    def test_terminal_state_and_receipt_outcome_cannot_contradict(self):
        for state, cycle in (('completed', False), ('canceled', True), ('failed', True)):
            with self.subTest(state=state):
                self.invalid(operation(state, cycle=cycle))
        for state in ('accepted', 'rejected_before_start', 'rejected_before_dispatch'):
            with self.subTest(state=state):
                value = operation(state)
                value['mayHaveActed'] = False
                self.invalid(value)
        for state in ('completed', 'canceled', 'failed'):
            value = operation(state)
            value['mayHaveActed'] = False
            self.invalid(value)

    def test_flags_are_exact_booleans_and_terminal_activation_idle_are_true(self):
        for field in ('activationCommitted', 'cycleCompleted', 'safeIdle'):
            for malformed in (0, 1, 0.0, 1.0, None, 'true', [], {}):
                with self.subTest(field=field, malformed=malformed):
                    value = operation()
                    value['result']['output']['result'][field] = malformed
                    self.invalid(value)
        for field in ('activationCommitted', 'safeIdle'):
            value = operation()
            value['result']['output']['result'][field] = False
            self.invalid(value)

    def test_closed_output_and_result_fields_do_not_hide_conflicting_claims(self):
        for location in ('output', 'result'):
            exemplar = operation()['result']['output']
            keys = exemplar if location == 'output' else exemplar['result']
            for missing in keys:
                with self.subTest(location=location, missing=missing):
                    value = operation()
                    target = value['result']['output']
                    if location == 'result':
                        target = target['result']
                    del target[missing]
                    self.invalid(value)
            value = operation()
            target = value['result']['output']
            if location == 'result':
                target = target['result']
            target['effectCommitted'] = False
            self.invalid(value)
        for malformed in (None, [], True, 1, 'done'):
            value = operation()
            value['result']['output']['result'] = malformed
            self.invalid(value)

    def test_explicit_unknown_profiles_and_physical_labels_refuse(self):
        for profile in ('hms.synthetic-io-result/2', 'other:profile', None, 1, True, [], {}):
            with self.subTest(profile=profile):
                value = operation()
                value['result']['output']['profile'] = profile
                self.invalid(value)
        for evidence in ('sensor', 'controller'):
            for verification in ('unverified', 'verified'):
                with self.subTest(evidence=evidence, verification=verification):
                    value = operation()
                    value['result']['evidenceKind'] = evidence
                    value['effectVerification'] = verification
                    self.invalid(value)
        value = operation()
        value['effectVerification'] = 'verified'
        self.invalid(value)

    def test_primitive_digest_and_outcome_reason_have_exact_carriers(self):
        for field, invalid_values in (
                ('primitive', ('gpio', 'pwm', '', 1, True, [], {})),
                ('receiptDigest', ('sha256:' + 'A' * 64, 'sha256:' + '0' * 63,
                                   'sha256:' + '0' * 64 + '\n', 'md5:' + '0' * 64, None, 1, []))):
            for malformed in invalid_values:
                with self.subTest(field=field, malformed=malformed):
                    value = operation()
                    value['result']['output'][field] = malformed
                    self.invalid(value)
        for malformed in (None, '', 'with space', 1, [], {}):
            value = operation('failed')
            value['result']['output']['result']['reason'] = malformed
            self.invalid(value)
        value = operation()
        value['result']['output']['result']['reason'] = 'client_cancel'
        self.invalid(value)

    def test_idle_leaves_are_closed_exact_typed_canonical_shapes(self):
        mutations = [
            ('atom:pin5', 'mode', 'push_pull_output'), ('atom:pin5', 'level', 0),
            ('atom:timer0', 'enabled', 0), ('atom:timer0', 'frequencyHz', False),
            ('atom:timer0', 'frequencyHz', 0.0), ('atom:timer0', 'resolutionBits', 8),
            ('atom:channel0', 'enabled', True), ('atom:channel0', 'dutyPermille', 0.0),
            ('atom:channel0', 'dutyPermille', False), ('atom:pin5', 'kind', []),
            ('atom:pin5', 'kind', {}), ('atom:pin5', 'kind', 'physical_pin')]
        for resource, field, malformed in mutations:
            with self.subTest(resource=resource, field=field, malformed=malformed):
                value = operation(primitive='pwm_burst')
                value['result']['output']['safeIdleState'][resource][field] = malformed
                self.invalid(value)
        for resource in ('atom:pin5', 'atom:timer0', 'atom:channel0'):
            for mode in ('extra', 'missing'):
                value = operation(primitive='pwm_burst')
                leaf = value['result']['output']['safeIdleState'][resource]
                if mode == 'extra':
                    leaf['currentlyIdle'] = True
                else:
                    del leaf['kind']
                self.invalid(value)

    def test_idle_inventory_is_bounded_with_valid_identifiers(self):
        for malformed in ({}, [], None, 1, {'bad resource': copy.deepcopy(PIN)},
                          {'atom:pin5': None}, {'atom:pin5': []}):
            value = operation()
            value['result']['output']['safeIdleState'] = malformed
            self.invalid(value)
        value = operation()
        value['result']['output']['safeIdleState'] = {'atom:pin%d' % i: copy.deepcopy(PIN) for i in range(32)}
        self.invalid(value)
        value['result']['output']['safeIdleState']['atom:pin32'] = copy.deepcopy(PIN)
        self.invalid(value)

    def test_primitive_has_exact_supported_idle_footprint(self):
        malformed = [
            ('gpio_pulse', {'atom:timer': TIMER}),
            ('gpio_pulse', {'atom:pin5': PIN, 'atom:pin6': PIN}),
            ('pwm_burst', {'atom:pin5': PIN}),
            ('pwm_burst', {'atom:pin5': PIN, 'atom:timer': TIMER}),
            ('pwm_burst', {'atom:pin5': PIN, 'atom:channel': CHANNEL}),
            ('pwm_burst', {'atom:pin5': PIN, 'atom:timer': TIMER, 'atom:timer2': TIMER}),
            ('pwm_burst', {'atom:pin5': PIN, 'atom:timer': TIMER, 'atom:channel': CHANNEL,
                           'atom:pin6': PIN}),
        ]
        for primitive, idle in malformed:
            with self.subTest(primitive=primitive, resources=list(idle)):
                value = operation(primitive=primitive)
                value['result']['output']['safeIdleState'] = copy.deepcopy(idle)
                self.invalid(value)

    def test_unprofiled_legacy_simulation_contract_remains_unchanged(self):
        for state, committed in (('completed', True), ('canceled', False), ('failed', False)):
            with self.subTest(state=state):
                value = operation(state)
                value['result']['output'] = {'effectCommitted': committed, 'legacyResult': 'retained'}
                self.valid(value)
                for invalid in (not committed, 1, 0, None):
                    changed = copy.deepcopy(value)
                    changed['result']['output']['effectCommitted'] = invalid
                    self.invalid(changed)
                changed = copy.deepcopy(value)
                changed['result']['output']['profile'] = 'unknown:output'
                self.invalid(changed)
        value = operation()
        value['result']['output'] = {'legacyResult': 'missing flag'}
        self.invalid(value)

    def test_adapter_projection_tags_only_available_terminal_receipts(self):
        value = operation()
        payload = value['result']['output']
        record = {'id': value['operationId'], 'intent': {'instanceId': value['instanceId'], 'actionId': value['actionId']}}
        receipt = {'state': 'completed', 'result': copy.deepcopy(payload['result']),
                   'idleState': copy.deepcopy(payload['safeIdleState'])}
        adapter = IoRouteAdapter.__new__(IoRouteAdapter)
        adapter.journal = SimpleNamespace(_mutex=threading.RLock(), _operation=lambda _id: record)
        adapter.board = SimpleNamespace(validated_receipt=Mock(return_value=receipt),
            _details={(value['instanceId'], value['actionId']): {'primitive': 'gpio_pulse'}})
        adapter._check_receipt = Mock()
        value['result'] = adapter.result(value['operationId'])
        adapter._check_receipt.assert_called_once_with(record, receipt)
        self.assertEqual(value['result']['output']['profile'], PROFILE)
        self.assertNotIn('effectCommitted', value['result']['output'])
        self.valid(value)
        for state in ('pending', 'rejected_before_start'):
            receipt['state'] = state
            self.assertIsNone(adapter.result(value['operationId']))
        adapter.board.validated_receipt.return_value = None
        self.assertIsNone(adapter.result(value['operationId']))

    def test_operation_identity_and_cancellation_checks_still_apply(self):
        value = operation()
        with self.assertRaises(ResponseError):
            validate_result('operation', value, {'operationId': 'op:another'})
        value = operation('canceled')
        value['cancellationState'] = 'requested'
        self.invalid(value)
        value = operation()
        value['cancellationState'] = 'confirmed'
        self.invalid(value)


if __name__ == '__main__':
    unittest.main()
