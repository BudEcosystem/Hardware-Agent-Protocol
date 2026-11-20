"""Pure checks of the exact composed harness, using fake owned-process handles."""
import ast
import copy
import fcntl
from pathlib import Path
import os
import re
import resource
import stat
import sys
import time
import unittest

from test_observer import sample

BASE = Path(__file__).resolve().parent
CHILD = ast.parse((BASE / 'harness01/attempt_child.py').read_bytes())
ORIGINAL = ast.parse((BASE / 'harness01/references/original-attempt_child.py').read_bytes())
OBSERVER = ast.parse((BASE / 'observer.py').read_bytes())
TARGET = 'test_vault_original_run.VaultOriginalRunTests.test_actual_original_matrix_import_and_cold_vault_history'

def functions(tree):
    return {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}

class CompositionTests(unittest.TestCase):
    def context(self):
        names = set(functions(OBSERVER)) | {'audit', 'native_boundary', 'verify_native_image', 'remember', 'is_stdlib'}
        constants = {'_RU_FIELDS', '_ADDITIVE_FIELDS', 'native_load', 'native_image', 'native_scans', 'NATIVE_DIGEST'}
        nodes = [node for node in CHILD.body if
            isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names or
            isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in constants for target in node.targets)]
        context = dict(os=os, resource=resource, stat=stat, time=time, fcntl=fcntl, Path=Path, re=re, sys=sys,
            root=Path('/copied/project'), scratch=Path('/owned/scratch'), current_test=TARGET,
            config=dict(targets=[TARGET]), prohibited=[], accounting_launch_audit=[], native_scans={})
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<exact-composed-harness>', 'exec'), context)
        # The image is a prevalidated-state fixture. No image verification is
        # claimed by these pure composition cases; that has separate real controls.
        context['native_image'] = {'prevalidatedFixture': True}
        ticks = iter(range(1, 100))
        emissions = []
        recorder = context['_WorkerAccounting'](snapshot=lambda: sample(next(ticks)), clock=lambda: 123,
            identify=lambda fd: dict(available=True, descriptor=fd, inode=fd+100),
            persist=lambda name, value: emissions.append((name, copy.deepcopy(value))))
        recorder.start_test(TARGET)
        expected = context['scratch'] / 'test_actual_original_matrix_import_and_cold_vault_history/supervisor'
        image = expected / ('code-' + 'a' * 64)
        argv = [sys.executable, '-I', '-B', str(image / 'supervisor/worker_entry.py'), '10', '11', '12']
        calls = []
        class OriginalProcess:
            pid = 73
            returncode = None
            def __init__(self, args, *positional, **keywords):
                calls.append(('init', list(args), positional, dict(keywords)))
                context['audit']('subprocess.Popen', (sys.executable, args, keywords['cwd'], keywords['env']))
            def poll(self):
                calls.append(('poll',))
                return self.returncode
            def wait(self, timeout=None):
                calls.append(('wait', timeout))
                self.returncode = -15
                return self.returncode
        factory = context['_observed_popen'](OriginalProcess, recorder)
        options = dict(cwd=str(image), env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}, pass_fds=(10, 11, 12))
        return context, recorder, factory, argv, options, calls, emissions, expected

    def test_embedded_observer_and_native_validation_asts_are_unchanged(self):
        actual, original = functions(CHILD), functions(ORIGINAL)
        for name, node in functions(OBSERVER).items():
            self.assertEqual(ast.dump(actual[name]), ast.dump(node))
        for name in ('native_boundary', 'verify_native_image', 'actual_origins'):
            self.assertEqual(ast.dump(actual[name]), ast.dump(original[name]))
        # Remove exactly the new one-launch cap/receipt from the subprocess branch.
        audit = copy.deepcopy(actual['audit'])
        branch = next(node for node in audit.body if isinstance(node, ast.If)
                      and ast.unparse(node.test) == "event == 'subprocess.Popen'")
        self.assertEqual(ast.unparse(branch.body[-2].test), 'accounting_launch_audit')
        self.assertTrue(ast.unparse(branch.body[-1]).startswith('accounting_launch_audit.append('))
        branch.body = branch.body[:-2]
        self.assertEqual(ast.dump(audit), ast.dump(original['audit']))

    def test_scans_and_launch_share_guards_without_extra_process_calls(self):
        c, recorder, factory, argv, options, calls, emissions, root = self.context()
        c['audit']('hms.retention.scan.v1', (os.fsencode(root), 262144, 268435456))
        self.assertEqual(c['accounting_launch_audit'], [])
        process = factory(argv, **options)
        self.assertIsNone(process.poll())
        c['audit']('hms.retention.scan.v1', (os.fsencode(root / ('b' * 32)), 8192, 67108864))
        self.assertEqual(process.wait(timeout=3), -15)
        self.assertEqual(process.poll(), -15)
        recorder.stop_test()
        self.assertEqual(calls[1:], [('poll',), ('wait', 3), ('poll',)])
        self.assertEqual(len(c['accounting_launch_audit']), 1)
        self.assertEqual(c['accounting_launch_audit'][0]['argv'], argv)
        self.assertEqual(len(c['native_scans']), 2)
        self.assertEqual([name for name, _ in emissions], ['worker-accounting-start.json', 'worker-accounting-launch.json',
            'worker-accounting-terminal.json', 'worker-accounting.json'])
        self.assertEqual(recorder.report()['launch']['terminal']['observedBy'], 'original-wait')

    def test_native_veto_does_not_create_worker_accounting(self):
        c, recorder, _, _, _, calls, _, _ = self.context()
        with self.assertRaisesRegex(RuntimeError, 'outside the owned supervisor scope'):
            c['audit']('hms.retention.scan.v1', (b'/foreign/root', 1, 1))
        self.assertEqual(calls, [])
        self.assertIsNone(recorder.report()['launch'])
        self.assertEqual(c['accounting_launch_audit'], [])

    def test_rejected_launch_preserves_original_audit_and_partial_snapshot(self):
        c, recorder, factory, argv, options, calls, _, _ = self.context()
        argv[3] = '/foreign/worker_entry.py'
        with self.assertRaisesRegex(RuntimeError, 'Only exact owned I/O entry'):
            factory(argv, **options)
        self.assertEqual(len(calls), 1)
        self.assertEqual(c['accounting_launch_audit'], [])
        self.assertEqual(recorder.report()['launch']['launchFailure'], 'RuntimeError')
        self.assertIsNone(recorder.report()['launch']['pid'])
        self.assertIsNone(recorder.report()['launchToReapDelta'])

    def test_second_launch_is_refused_before_constructor_and_audit(self):
        c, recorder, factory, argv, options, calls, _, _ = self.context()
        factory(argv, **options)
        with self.assertRaisesRegex(RuntimeError, 'Exactly one original launch'):
            factory(argv, **options)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(c['accounting_launch_audit']), 1)
        self.assertIsNone(recorder.report()['launch']['terminal'])

    def test_native_veto_during_work_cannot_fabricate_terminal_usage(self):
        c, recorder, factory, argv, options, calls, _, root = self.context()
        process = factory(argv, **options)
        c['current_test'] = None
        with self.assertRaisesRegex(RuntimeError, 'only authorized inside the exact actual test'):
            c['audit']('hms.retention.scan.v1', (os.fsencode(root), 1, 1))
        self.assertIsNone(recorder.report()['launchToReapDelta'])
        self.assertEqual(len(calls), 1)
        process.returncode = -15
        self.assertEqual(process.poll(), -15)
        self.assertEqual(recorder.report()['launch']['terminal']['observedBy'], 'original-poll')
        self.assertEqual(len(calls), 2)
