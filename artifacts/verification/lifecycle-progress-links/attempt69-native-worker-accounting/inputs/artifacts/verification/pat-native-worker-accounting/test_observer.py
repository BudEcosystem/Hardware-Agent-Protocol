"""Pure observer controls: fake process handles, counters and pressure only."""
import copy
import io
import types
import unittest
from unittest.mock import patch

import observer as observed


ARGV = ['/python', '-I', '-B', '/image/supervisor/worker_entry.py', '10', '11', '12']


def usage(number):
    return types.SimpleNamespace(**{name: number for name in observed._RU_FIELDS})


def sample(number):
    return {'beforeMonotonicNs': number * 1000, 'afterMonotonicNs': number * 1000 + 10,
        'usage': {name: {'available': True, 'raw': vars(usage(number))} for name in ('self', 'children')},
        'pressure': {}}


class Process:
    pid = 73
    def __init__(self, args, *positional, **keywords):
        self.calls = [('init', args, positional, keywords)]
        self.returncode = None
    def poll(self):
        self.calls.append(('poll',))
        return self.returncode
    def wait(self, timeout=None):
        self.calls.append(('wait', timeout))
        if timeout == 0:
            raise TimeoutError('existing wait timeout')
        self.returncode = -15
        return self.returncode


class ObserverTests(unittest.TestCase):
    def make(self, process_type=Process):
        ticks = iter(range(1, 100))
        emissions = []
        def snapshot(): return sample(next(ticks))
        recorder = observed._WorkerAccounting(snapshot=snapshot, clock=lambda: 123,
            identify=lambda fd: {'available': True, 'descriptor': fd, 'inode': fd + 100},
            persist=lambda name, value: emissions.append((name, copy.deepcopy(value))))
        recorder.start_test('exact.original.test')
        return recorder, observed._observed_popen(process_type, recorder), emissions

    def test_launch_poll_and_wait_preserve_original_calls(self):
        recorder, factory, emissions = self.make()
        process = factory(ARGV, 'argument', cwd='/image', pass_fds=(10, 11, 12))
        self.assertEqual(process.calls, [('init', ARGV, ('argument',), {'cwd': '/image', 'pass_fds': (10, 11, 12)})])
        self.assertIsNone(process.poll())
        self.assertIsNone(recorder.report()['launchToReapDelta'])
        self.assertEqual(process.wait(timeout=5), -15)
        self.assertEqual(process.poll(), -15)
        recorder.stop_test()
        self.assertEqual(process.calls, [('init', ARGV, ('argument',), {'cwd': '/image', 'pass_fds': (10, 11, 12)}), ('poll',), ('wait', 5), ('poll',)])
        self.assertEqual([name for name, _ in emissions], ['worker-accounting-start.json', 'worker-accounting-launch.json', 'worker-accounting-terminal.json', 'worker-accounting.json'])
        report = recorder.report()
        self.assertEqual(report['launch']['pid'], 73)
        self.assertEqual(report['launch']['terminal']['observedBy'], 'original-wait')
        self.assertEqual(report['launch']['descriptors']['writerLease']['inode'], 112)
        self.assertEqual(report['launchToReapDelta']['children']['additiveCounters']['ru_utime'], 1)

    def test_original_poll_terminal_and_duplicate_observation(self):
        recorder, factory, emissions = self.make()
        process = factory(ARGV)
        process.returncode = 0
        self.assertEqual(process.poll(), 0)
        initial = copy.deepcopy(recorder.report())
        self.assertEqual(process.poll(), 0)
        self.assertEqual(recorder.report(), initial)
        self.assertEqual(len(emissions), 3)
        self.assertEqual(initial['launch']['terminal']['observedBy'], 'original-poll')

    def test_timeout_propagates_without_terminal_or_extra_wait(self):
        recorder, factory, _ = self.make()
        process = factory(ARGV)
        with self.assertRaisesRegex(TimeoutError, 'existing wait timeout'):
            process.wait(timeout=0)
        self.assertEqual(process.calls[-1], ('wait', 0))
        self.assertEqual(len(process.calls), 2)
        self.assertIsNone(recorder.report()['launchToReapDelta'])

    def test_interrupted_without_reap_never_fabricates_child_usage(self):
        recorder, factory, _ = self.make()
        factory(ARGV)
        recorder.stop_test()
        self.assertIsNone(recorder.report()['launch']['terminal'])
        self.assertIsNone(recorder.report()['launchToReapDelta'])
        self.assertIsNotNone(recorder.report()['testDelta'])

    def test_same_pid_different_object_cannot_finish_original(self):
        recorder, factory, _ = self.make()
        factory(ARGV)
        foreign = Process(ARGV)
        recorder.observed_return(foreign, 0, 'foreign')
        self.assertIsNone(recorder.report()['launchToReapDelta'])
        self.assertEqual(recorder.report()['errors'][0]['phase'], 'foreign-process-object')

    def test_second_launch_never_reaches_original_constructor(self):
        calls = []
        class Counted(Process):
            def __init__(self, *args, **kwargs):
                calls.append('constructed')
                super().__init__(*args, **kwargs)
        recorder, factory, _ = self.make(Counted)
        factory(ARGV)
        with self.assertRaisesRegex(RuntimeError, 'Exactly one original launch'):
            factory(ARGV)
        self.assertEqual(calls, ['constructed'])
        self.assertIsNone(recorder.report()['launchToReapDelta'])

    def test_failed_spawn_preserves_exception_and_partial_evidence(self):
        class Broken(Process):
            def __init__(self, *args, **kwargs): raise PermissionError('original spawn refusal')
        recorder, factory, emissions = self.make(Broken)
        with self.assertRaisesRegex(PermissionError, 'original spawn refusal'):
            factory(ARGV)
        self.assertEqual(recorder.report()['launch']['launchFailure'], 'PermissionError')
        self.assertIsNone(recorder.report()['launch']['pid'])
        self.assertIsNone(recorder.report()['launchToReapDelta'])
        self.assertEqual(emissions[-1][0], 'worker-accounting-launch-failed.json')

    def test_observer_failure_does_not_replace_original_return(self):
        recorder, factory, _ = self.make()
        process = factory(ARGV)
        def broken(): raise OSError('observation unavailable')
        recorder.snapshot = broken
        self.assertEqual(process.wait(timeout=3), -15)
        self.assertIsNone(recorder.report()['launchToReapDelta'])
        self.assertEqual(recorder.report()['errors'][0]['phase'], 'terminal-wait-observation')

    def test_missing_usage_is_unavailable_and_pressure_separate(self):
        calls = []
        def get(selector):
            calls.append(selector)
            if selector == observed.resource.RUSAGE_CHILDREN: raise OSError()
            return usage(7)
        result = observed._usage_snapshot(get, lambda: 100, lambda path: 'some avg10=0.00 total=3\n')
        self.assertEqual(calls, [observed.resource.RUSAGE_SELF, observed.resource.RUSAGE_CHILDREN])
        self.assertEqual(result['usage']['children'], {'available': False, 'errorType': 'OSError'})
        self.assertEqual(result['usage']['self']['raw']['ru_utime'], 7)
        self.assertEqual(set(result['pressure']), {'cpu', 'memory', 'io'})
        delta = observed._usage_delta(result, result)
        self.assertFalse(delta['children']['available'])

    def test_deltas_exclude_peak_rss_and_unmaintained_fields(self):
        first, last = sample(5), sample(9)
        last['usage']['children']['raw']['ru_maxrss'] = 4
        delta = observed._usage_delta(first, last)
        counters = delta['children']['additiveCounters']
        self.assertEqual(counters, {name: 4 for name in observed._ADDITIVE_FIELDS})
        self.assertNotIn('ru_maxrss', counters)
        self.assertNotIn('ru_nswap', counters)
        self.assertNotIn('ru_nsignals', counters)

    def test_regressing_counter_is_not_silently_clamped(self):
        first, last = sample(5), sample(9)
        last['usage']['children']['raw']['ru_utime'] = 4
        self.assertEqual(observed._usage_delta(first, last)['children'], {'available': False, 'reason': 'counter_regression'})

    def test_pressure_missing_oversized_and_non_ascii_are_unavailable(self):
        def read(path):
            if path.endswith('/cpu'): raise PermissionError()
            if path.endswith('/memory'): return 'a' * 4097
            return '\u2603'
        result = observed._usage_snapshot(lambda selector: usage(0), lambda: 1, read)
        self.assertEqual([row['available'] for row in result['pressure'].values()], [False, False, False])
        self.assertEqual(result['pressure']['cpu']['errorType'], 'PermissionError')

    def test_pressure_reader_never_accepts_over_bound(self):
        with patch('builtins.open', return_value=io.BytesIO(b'a' * 5000)):
            with self.assertRaisesRegex(ValueError, '4096-byte'):
                observed._pressure_read('/proc/pressure/cpu')

    def test_descriptor_failure_is_explicit_without_pid_fallback(self):
        calls = []
        def failed(fd): calls.append(fd); raise OSError()
        self.assertEqual(observed._descriptor_identity(13, failed), {'available': False, 'descriptor': 13, 'errorType': 'OSError'})
        self.assertEqual(calls, [13])

    def test_missing_start_and_repeated_test_refused(self):
        recorder = observed._WorkerAccounting()
        with self.assertRaisesRegex(RuntimeError, 'Exactly one original launch'):
            recorder.before_launch(ARGV)
        recorder, _, _ = self.make()
        with self.assertRaisesRegex(RuntimeError, 'Exactly one original test'):
            recorder.start_test('replacement')


if __name__ == '__main__':
    unittest.main(verbosity=2)
