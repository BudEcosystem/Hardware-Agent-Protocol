"""Explicit runtime selection and public I/O initialization boundaries."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from hms.contracts import MAX_BYTES, canonical
from hms.journal import Context, JournalError
from hms.runtime import Runtime, open_runtime
from hms.synthetic_io_installation import implementation_digest, normalize_installation
from scripts.build_io_example import build

ROOT = Path(__file__).resolve().parents[1]
LAST_REPORT = {'scope': 'Explicit runtime factory and actual CLI startup refusals; synthetic I/O only',
               'startupRefusals': [], 'exampleBuilds': []}


class RuntimeProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hms-runtime-profile-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.state = self.base / 'runtime'
        self.owner = Context('profile-owner', 'simulation:io-hub')
        self.clock = 1000

    def open_io(self, **kwargs):
        runtime = open_runtime(self.state, io_simulation=True,
                               wall_clock_ms=lambda: self.clock, monotonic_ms=lambda: self.clock, **kwargs)
        self.addCleanup(runtime.close)
        return runtime

    def refusal(self, flags, code, *, existing=False):
        command = [sys.executable, '-m', 'hms', '--socket', str(self.base / 'control.sock'),
                   'serve', '--state-dir', str(self.state), *flags]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
        LAST_REPORT['startupRefusals'].append({'case': self.id(), 'flags': flags, 'returncode': result.returncode,
                                             'stdout': result.stdout, 'stderr': result.stderr,
                                             'stateCreated': self.state.exists()})
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(json.loads(result.stderr), {'error': {'code': code}})
        self.assertEqual(self.state.exists(), existing)

    def test_factory_rejects_ambiguous_or_non_boolean_selection_before_state_access(self):
        cases = [({'io_simulation': value}, 'INVALID_RUNTIME_PROFILE') for value in (0, 1, None, 'true', [])]
        cases += [({'io_simulation': True, **extra}, 'AMBIGUOUS_RUNTIME_CONFIGURATION') for extra in (
            {'installations': []}, {'endpoint_fd': 0}, {'endpoint_fds': {}}, {'endpoint_fds': {'io:routeA': 0}})]
        cases.append(({'io_installation': {}}, 'INVALID_RUNTIME_PROFILE'))
        for options, code in cases:
            with self.subTest(options=options):
                with self.assertRaisesRegex(JournalError, code):
                    open_runtime(self.state, create=True, owner=self.owner, **options)
                self.assertFalse(self.state.exists())

    def test_factory_requires_explicit_installation_and_matching_owner_on_creation(self):
        for options in ({'owner': self.owner}, {'io_installation': build()},
                        {'owner': Context('profile-owner', 'simulation:wrong'), 'io_installation': build()}):
            with self.subTest(options=list(options)):
                with self.assertRaisesRegex(JournalError, 'EXPLICIT_IO_SIMULATION_OWNER_REQUIRED'):
                    self.open_io(create=True, **options)
                self.assertFalse(self.state.exists())

    def test_factory_keeps_original_runtime_and_discovery(self):
        owner = Context('profile-owner', 'simulation:local')
        runtime = open_runtime(self.state, create=True, owner=owner,
                               wall_clock_ms=lambda: 1000, monotonic_ms=lambda: 1000)
        self.addCleanup(runtime.close)
        self.assertIs(type(runtime), Runtime)
        self.assertEqual({item['instanceId'] for item in runtime.request(owner, 'discover', {})['items']},
                         {'sim:home-fan', 'sim:microscope', 'sim:inspection-cell'})

    def test_example_builds_current_pins_and_reopens_explicitly_without_reset(self):
        output = self.base / 'io.json'
        command = [sys.executable, str(ROOT / 'scripts/build_io_example.py'), '--output', str(output)]
        first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(first.returncode, 0, first.stderr)
        data = output.read_bytes()
        configuration = normalize_installation(data)
        self.assertEqual(configuration['driverDigest'], implementation_digest())
        for node in configuration['topology']['nodes'].values():
            if node['kind'] == 'driver':
                self.assertEqual(node['properties']['implementationDigest'], configuration['driverDigest'])
        second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(output.read_bytes(), data)
        LAST_REPORT['exampleBuilds'].append({'firstReturncode': first.returncode, 'overwriteReturncode': second.returncode,
                                            'installation': configuration, 'sha256': hashlib.sha256(data).hexdigest()})
        runtime = self.open_io(create=True, owner=self.owner, io_installation=configuration)
        items = runtime.request(self.owner, 'discover', {})['items']
        self.assertEqual({item['instanceId'] for item in items},
                         {'sim:gpio5', 'sim:gpio6', 'sim:pwm5', 'sim:gpio5:other-route'})
        authority = runtime.journal.authority_id
        epoch = runtime.journal.owner_epoch
        board_path = self.state / runtime.catalog.board_filename()
        inode = board_path.stat().st_ino
        runtime.close()
        reopened = self.open_io()
        self.assertEqual(reopened.journal.authority_id, authority)
        self.assertEqual(reopened.journal.owner_epoch, epoch + 1)
        self.assertEqual(board_path.stat().st_ino, inode)
        self.assertEqual(len(reopened.request(self.owner, 'discover', {})['items']), 4)

    def test_optional_reopen_installation_must_match_exactly(self):
        configuration = build()
        runtime = self.open_io(create=True, owner=self.owner, io_installation=configuration)
        board_path = self.state / runtime.catalog.board_filename()
        runtime.close()
        before = board_path.read_bytes()
        changed = copy.deepcopy(configuration)
        changed['routes']['adapters']['io:routeC'] = changed['routes']['adapters'].pop('io:routeB')
        normalize_installation(changed)  # Valid configuration, different installed authority.
        with self.assertRaisesRegex(JournalError, 'IO_INSTALLATION_CHANGED'):
            self.open_io(io_installation=changed)
        self.assertEqual(board_path.read_bytes(), before)
        reopened = self.open_io(io_installation=configuration)
        self.assertEqual(len(reopened.request(self.owner, 'discover', {})['items']), 4)

    def test_wrong_profile_refuses_in_both_directions_without_creating_another_board(self):
        runtime = self.open_io(create=True, owner=self.owner, io_installation=build())
        board_path = self.state / runtime.catalog.board_filename()
        runtime.close()
        before = board_path.read_bytes()
        with self.assertRaisesRegex(JournalError, 'INVALID_ADAPTER_CATALOG'):
            open_runtime(self.state)
        self.assertEqual(board_path.read_bytes(), before)
        self.assertFalse((self.state / 'simulated-plant.db').exists())
        legacy_path = self.base / 'legacy'
        legacy = open_runtime(legacy_path, create=True, owner=Context('owner', 'simulation:local'))
        legacy.close()
        with self.assertRaisesRegex(JournalError, 'IO_CATALOG_PROFILE'):
            open_runtime(legacy_path, io_simulation=True)
        self.assertEqual(list(legacy_path.glob('synthetic-io-board-*.db')), [])

    def test_cli_requires_profile_and_installation_before_state_access(self):
        missing = str(self.base / 'missing.json')
        self.refusal(['--init-io-simulation'], 'IO_INSTALLATION_REQUIRED')
        self.refusal(['--io-installation-file', missing], 'INVALID_IO_INITIALIZATION')
        for extra in (['--endpoint-fd', '0'], ['--endpoint-route', 'io:routeA=0'],
                      ['--installations-file', missing], ['--init-simulation'],
                      ['--init-compact-simulation'], ['--init-multi-simulation']):
            with self.subTest(extra=extra):
                self.refusal(['--io-simulation', *extra], 'INVALID_IO_INITIALIZATION')

    def test_cli_rejects_invalid_bounded_installation_before_state_access(self):
        path = self.base / 'invalid.json'
        stale = build()
        stale['driverDigest'] = 'sha256:' + '0' * 64
        for data, code in ((b'{', 'INVALID_REQUEST'), (b' ' * (MAX_BYTES + 1), 'INVALID_REQUEST'),
                           (canonical(stale), 'IO_DRIVER_CHANGED')):
            with self.subTest(code=code, bytes=len(data)):
                path.write_bytes(data)
                self.refusal(['--init-io-simulation', '--io-installation-file', str(path)], code)
        for primitive in ([], {}, 1, True, None):
            with self.subTest(primitive=primitive):
                malformed = build()
                malformed['handlers'][0]['primitive'] = primitive
                path.write_bytes(canonical(malformed))
                self.refusal(['--init-io-simulation', '--io-installation-file', str(path)], 'IO_HANDLER_UNSUPPORTED')

    def test_cli_missing_or_tampered_board_refuses_without_resetting_effect_history(self):
        runtime = self.open_io(create=True, owner=self.owner, io_installation=build())
        namespace = runtime.request(self.owner, 'namespace', {'expiresUnixMs': 10000})['token']
        request = runtime.request(self.owner, 'prepare', {
            'instanceId': 'sim:gpio5', 'actionId': 'gpio_pulse', 'arguments': {'durationMs': 20, 'level': 1},
            'operationKey': 'profile:effect', 'replayNamespace': namespace, 'requiredEffect': 'capability_completion',
            'timing': {'notBeforeUnixMs': 1000, 'latestStartUnixMs': 5000, 'maxRunMs': 1000,
                       'latestCompletionUnixMs': 6000}})['request']
        accepted = runtime.request(self.owner, 'invoke', {'request': request})
        runtime.tick()
        self.clock += 20
        runtime.tick()
        self.assertEqual(runtime.request(self.owner, 'operation', {'operationId': accepted['operationId']})['executionState'],
                         'completed')
        board_path = self.state / runtime.catalog.board_filename()
        runtime.close()
        saved = board_path.with_suffix('.retained')
        board_path.rename(saved)
        self.refusal(['--io-simulation'], 'IO_BOARD_MISSING', existing=True)
        self.assertFalse(board_path.exists())
        saved.rename(board_path)
        with sqlite3.connect(board_path) as database:
            database.execute("UPDATE io_meta SET value='authority:changed' WHERE key='authority'")
        before = board_path.read_bytes()
        self.refusal(['--io-simulation'], 'IO_BOARD_IDENTITY_CHANGED', existing=True)
        self.assertEqual(board_path.read_bytes(), before)
        with sqlite3.connect('file:' + str(board_path) + '?mode=ro', uri=True) as database:
            self.assertEqual(database.execute("SELECT activations,completed,canceled FROM io_effects WHERE instance='sim:gpio5'").fetchone(),
                             (1, 1, 0))


if __name__ == '__main__':
    unittest.main()
