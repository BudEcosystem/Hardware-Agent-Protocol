"""Independent compact scheduling/support probes; original native simulator only."""
import copy
from pathlib import Path
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import test_endpoint_binding as support
from hms.endpoint_wire import Opcode
from hms.journal import Context, JournalError


class InstalledSupportOrderingReview(unittest.TestCase):
    def harness(self):
        h = support.CompactBindingTests()
        self.addCleanup(h.doCleanups)
        h.setUp()
        return h

    def user(self, h):
        user = Context('ordering-review', 'simulation:compact')
        for verb in ('read', 'invoke:set_level', 'cancel'):
            h.runtime.registry.grant(h.owner, user.principal, 'sim:home-fan', verb)
        h.runtime.registry.grant(h.owner, user.principal, '*', 'namespace')
        namespace = h.runtime.request(user, 'namespace', {'expiresUnixMs': 150000})['token']
        return user, namespace

    def test_future_operation_does_not_arm_or_recheck_until_startable(self):
        h = self.harness()
        user, namespace = self.user(h)
        timing = {'notBeforeUnixMs': h.wall + 500, 'latestStartUnixMs': h.wall + 2000,
                  'latestCompletionUnixMs': h.wall + 5000, 'maxRunMs': 1000}
        request = h.prepare(timing=timing)
        request['replayNamespace'] = namespace
        op = h.runtime.request(user, 'invoke', {'request': request})
        h.runtime.registry.grant(h.owner, user.principal, 'sim:home-fan', 'invoke:set_level', enabled=False)
        original = h.runtime.policy.recheck
        def forbidden(*args):
            raise AssertionError('Future work was rechecked before notBefore')
        h.runtime.policy.recheck = forbidden
        try:
            h.runtime.tick()
        finally:
            h.runtime.policy.recheck = original
        self.assertEqual(h.runtime.request(user, 'operation', {'operationId': op['operationId']})['executionState'], 'accepted')
        self.assertEqual(h.packet_count(Opcode.ARM), 0)
        self.assertEqual(h.packet_count(Opcode.OP), 0)
        self.assertIsNone(h.runtime.compact._state()['fault'])
        h.runtime.registry.grant(h.owner, user.principal, 'sim:home-fan', 'invoke:set_level')
        h.advance(500)
        self.assertEqual(h.packet_count(Opcode.ARM), 1)
        self.assertEqual(h.packet_count(Opcode.OP), 1)
        for _ in range(6):
            h.advance(100)
            status = h.runtime.request(user, 'operation', {'operationId': op['operationId']})
            if status['executionState'] == 'completed' and not status['resourceClaims']:
                break
        self.assertEqual(status['executionState'], 'completed')
        self.assertEqual(status['resourceClaims'], [])
        self.assertEqual(h.control_call(5), 1)

    def test_cancel_after_selection_is_reloaded_before_any_arm(self):
        h = self.harness()
        op = h.invoke()
        original = h.runtime.compact._arm_for
        calls = []
        def cancel_first(selected):
            calls.append(selected['id'])
            canceled = h.call('cancel', operationId=selected['id'])
            self.assertEqual(canceled['executionState'], 'canceled')
            return original(selected)
        h.runtime.compact._arm_for = cancel_first
        h.runtime.tick()
        self.assertEqual(calls, [op['operationId']])
        self.assertEqual(h.status(op)['executionState'], 'canceled')
        self.assertFalse(h.status(op)['mayHaveActed'])
        self.assertEqual(h.packet_count(Opcode.ARM), 0)
        self.assertEqual(h.packet_count(Opcode.OP), 0)
        self.assertIsNone(h.runtime.compact._state()['fault'])

    def test_expiry_after_selection_is_reloaded_before_any_arm(self):
        h = self.harness()
        op = h.invoke()
        original = h.runtime.compact._arm_for
        def expire_first(selected):
            h.advance(2000, tick=False)
            return original(selected)
        h.runtime.compact._arm_for = expire_first
        h.runtime.tick()
        status = h.status(op)
        self.assertEqual(status['executionState'], 'rejected_before_dispatch')
        self.assertFalse(status['mayHaveActed'])
        self.assertEqual(status['resourceClaims'], [])
        self.assertEqual(h.packet_count(Opcode.ARM), 0)
        self.assertEqual(h.packet_count(Opcode.OP), 0)
        self.assertIsNone(h.runtime.compact._state()['fault'])

    def test_arm_handoff_keeps_authority_mutex_against_other_thread(self):
        h = self.harness()
        op = h.invoke()
        selected = h.runtime.journal._operation(op['operationId'])
        started = threading.Event()
        acquired = threading.Event()
        errors = []
        def contender():
            started.set()
            try:
                with h.runtime.journal._mutex:
                    acquired.set()
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=contender)
        original = h.runtime.compact._arm_installed
        def observed(current, now):
            thread.start()
            self.assertTrue(started.wait(2))
            self.assertFalse(acquired.wait(0.05), 'Authority mutex not held through ARM handoff')
            return original(current, now)
        h.runtime.compact._arm_installed = observed
        try:
            h.runtime.compact._arm_for(selected)
        finally:
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertTrue(acquired.is_set())
        self.assertEqual(errors, [])
        self.assertEqual(h.packet_count(Opcode.ARM), 1)
        self.assertEqual(h.packet_count(Opcode.OP), 0)
        h.call('cancel', operationId=op['operationId'])

    def test_exact_replay_uses_receipt_without_current_support_check(self):
        h = self.harness()
        request = h.prepare()
        op = h.invoke(request)
        h.runtime.tick()
        completed = h.finish(op)
        original = h.runtime.compact.validate_admission
        def unsupported(*args):
            raise AssertionError('Retained replay performed new installed admission')
        h.runtime.compact.validate_admission = unsupported
        try:
            replayed = h.invoke(copy.deepcopy(request))
        finally:
            h.runtime.compact.validate_admission = original
        self.assertEqual(replayed, completed)
        self.assertEqual(h.packet_count(Opcode.OP), 1)
        self.assertEqual(h.control_call(5), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
