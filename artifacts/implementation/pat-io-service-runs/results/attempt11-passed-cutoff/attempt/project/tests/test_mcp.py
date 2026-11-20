"""Modern MCP wire checks and cancellation across an actual admitted operation."""
import copy
import json
import os
from pathlib import Path
import queue
import select
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from jsonschema import Draft202012Validator

from hms.client import Client
from hms.ipc import Server
from hms.journal import Context
from hms.mcp import MODERN, PREFIX, Projection, TransportClosed, catalog, dumps
from hms.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
META = {PREFIX + 'protocolVersion': MODERN, PREFIX + 'clientCapabilities': {}}


def request(identifier, method, params=None):
    return {'jsonrpc': '2.0', 'id': identifier, 'method': method,
            'params': {**(params or {}), '_meta': copy.deepcopy(META)}}


class RejectClient:
    def request(self, method, params):
        raise AssertionError('unexpected hardware dispatch')


class McpContract(unittest.TestCase):
    def setUp(self):
        self.messages = queue.Queue()
        self.projection = Projection(RejectClient(), self.messages.put_nowait, clock=lambda: 1)
        self.addCleanup(self.projection.close)

    def send(self, value):
        self.projection.receive(dumps(value).encode())
        return self.messages.get(timeout=2)

    def test_current_discovery_is_valid_against_retained_official_schema(self):
        reply = self.send(request(1, 'server/discover'))
        schema = json.loads((ROOT / 'research/mcp/raw/schema__2026-07-28__schema.json').read_text())
        validator = Draft202012Validator({'$ref': '#/$defs/DiscoverResultResponse', '$defs': schema['$defs']})
        validator.validate(reply)
        self.assertEqual(reply['result']['supportedVersions'], [MODERN, '2025-11-25'])
        self.assertEqual(reply['result']['capabilities'], {'tools': {'listChanged': False}})

    def test_tool_pages_are_stable_complete_and_self_contained(self):
        tools = []
        params = {}
        for identifier in range(5):
            reply = self.send(request(identifier, 'tools/list', params))['result']
            self.assertEqual(reply['cacheScope'], 'private')
            self.assertEqual(reply['ttlMs'], 60000)
            tools.extend(reply['tools'])
            if 'nextCursor' not in reply:
                break
            params = {'cursor': reply['nextCursor']}
        self.assertEqual([t['name'] for t in tools], sorted('hardware_' + name for name in (
            'discover', 'describe', 'observe', 'namespace', 'prepare', 'invoke', 'operation', 'events', 'cancel',
            'procedure_submit', 'procedure_status', 'procedure_cancel', 'procedure_resume', 'procedure_events')))
        for tool in tools:
            for field in ('inputSchema', 'outputSchema'):
                Draft202012Validator.check_schema(tool[field])
                stack = [tool[field]]
                while stack:
                    value = stack.pop()
                    if type(value) is dict:
                        if '$ref' in value:
                            self.assertTrue(value['$ref'].startswith('#/$defs/'))
                            self.assertIn(value['$ref'][8:], tool[field]['$defs'])
                        stack.extend(value.values())
                    elif type(value) is list:
                        stack.extend(value)
        other = Projection(RejectClient(), lambda _: None)
        self.assertEqual(other.page_tokens, self.projection.page_tokens)
        self.assertEqual(self.send(request(9, 'tools/list', {'cursor': ''}))['error']['code'], -32602)

    def test_modern_metadata_is_required_on_every_request_and_not_an_identity(self):
        self.send(request(1, 'server/discover'))
        bare = {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}
        self.assertEqual(self.send(bare)['error']['code'], -32602)
        for meta in ({}, {PREFIX + 'protocolVersion': MODERN},
                     {**META, PREFIX + 'clientCapabilities': []},
                     {**META, PREFIX + 'clientInfo': {'name': 'root'}},
                     {**META, PREFIX + 'logLevel': []}):
            value = request(3, 'tools/list')
            value['params']['_meta'] = meta
            self.assertEqual(self.send(value)['error']['code'], -32602)
        value = request(4, 'tools/list')
        value['params']['_meta'][PREFIX + 'clientInfo'] = {'name': 'posix:0', 'version': 'administrator'}
        self.assertIn('tools', self.send(value)['result'])

    def test_unsupported_version_and_methods_fail_before_hardware(self):
        value = request(1, 'tools/call', {'name': 'hardware_invoke', 'arguments': {}})
        value['params']['_meta'][PREFIX + 'protocolVersion'] = '1900-01-01'
        self.assertEqual(self.send(value)['error']['code'], -32022)
        for method in ('initialize', 'ping', 'resources/list', 'tasks/get'):
            self.assertEqual(self.send(request(2, method))['error']['code'], -32601)
        self.assertEqual(self.send(request(3, 'tools/call', {'name': 'shell'}))['error']['code'], -32602)
        self.assertEqual(self.send(request(4, 'tools/call', {'name': 'hardware_discover', 'task': {}}))['error']['code'], -32602)

    def test_invalid_tool_arguments_are_sanitized_structured_errors(self):
        reply = self.send(request(1, 'tools/call', {'name': 'hardware_discover', 'arguments': {'limit': 1.0}}))['result']
        self.assertTrue(reply['isError'])
        self.assertEqual(reply['structuredContent'], {'ok': False, 'error': {'code': 'INVALID_REQUEST', 'outcome': 'unconfirmed'}})
        self.assertEqual(json.loads(reply['content'][0]['text']), reply['structuredContent'])
        schema = next(t['outputSchema'] for t in catalog() if t['name'] == 'hardware_discover')
        Draft202012Validator(schema).validate(reply['structuredContent'])

    def test_notifications_never_dispatch_tools_and_malformed_json_is_rejected(self):
        self.projection.receive(dumps({'jsonrpc': '2.0', 'method': 'tools/call', 'params': {'name': 'hardware_invoke'}}).encode())
        self.assertTrue(self.messages.empty())
        for payload in (b'{"jsonrpc":"2.0","id":1,"id":2}', b'{"id":NaN}', b'\xff'):
            self.projection.receive(payload)
            self.assertEqual(self.messages.get(timeout=2)['error']['code'], -32700)
        for identifier in (None, True, 1.0, 'x' * 129):
            self.assertEqual(self.send(request(identifier, 'tools/list'))['error']['code'], -32600)

    def test_subscriptions_acknowledge_only_supported_filters_and_cancel_silently(self):
        value = request(7, 'subscriptions/listen', {'notifications': {'toolsListChanged': True, 'resourceSubscriptions': ['file:///x']}})
        reply = self.send(value)
        self.assertEqual(reply['method'], 'notifications/subscriptions/acknowledged')
        self.assertEqual(reply['params']['notifications'], {})
        self.assertEqual(reply['params']['_meta'][PREFIX + 'subscriptionId'], 7)
        with self.assertRaises(TransportClosed):
            self.projection.receive(dumps(value).encode())
        self.projection.receive(dumps({'jsonrpc': '2.0', 'method': 'notifications/cancelled', 'params': {'requestId': 7}}).encode())
        self.assertTrue(self.messages.empty())
        self.assertEqual(self.projection.subscriptions, set())

    def test_legacy_handshake_is_separate_from_modern_requests(self):
        initialized = self.send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'tester', 'version': '1'}}})
        self.assertEqual(initialized['result']['protocolVersion'], '2025-11-25')
        self.assertNotIn('resultType', initialized['result'])
        bare = {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}
        self.assertEqual(self.send(bare)['error']['code'], -32602)
        self.projection.receive(b'{"jsonrpc":"2.0","method":"notifications/initialized"}')
        self.assertNotIn('resultType', self.send(bare)['result'])
        modern = request(3, 'tools/list')
        del modern['params']['_meta'][PREFIX + 'clientCapabilities']
        self.assertEqual(self.send(modern)['error']['code'], -32602)


class McpDaemon(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='hms-mcp-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'control.sock'
        self.owner = Context(f'posix:{os.getuid()}', 'simulation:local')
        self.runtime = Runtime(Path(self.directory.name) / 'state', create=True, owner=self.owner)
        self.server = Server(self.runtime, self.path)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.runtime.start()
        self.addCleanup(self.stop)
        self.client = Client(self.path)

    def stop(self):
        self.server.close()
        self.thread.join(3)
        self.runtime.close()

    def prepared(self, key='mcp:1'):
        now = time.time_ns() // 1000000
        ns = self.client.request('namespace', {'expiresUnixMs': now + 60000})
        return self.client.request('prepare', {
            'instanceId': 'sim:home-fan', 'actionId': 'set_level', 'arguments': {'level': 43, 'unit': 'percent'},
            'replayNamespace': ns['token'], 'operationKey': key, 'requiredEffect': 'capability_completion',
            'timing': {'notBeforeUnixMs': now, 'latestStartUnixMs': now + 10000,
                       'maxRunMs': 1000, 'latestCompletionUnixMs': now + 11000}})['request']

    def test_cancelled_mcp_reply_does_not_cancel_an_accepted_hms_operation(self):
        entered, release = threading.Event(), threading.Event()
        messages = queue.Queue()
        actual = self.client
        accepted = []
        class GatedClient:
            def request(self, method, arguments):
                result = actual.request(method, arguments)
                if method == 'invoke':
                    accepted.append(result)
                    entered.set()
                    if not release.wait(3):
                        raise RuntimeError('test gate timed out')
                return result
        projection = Projection(GatedClient(), messages.put_nowait)
        self.addCleanup(projection.close)
        self.addCleanup(release.set)
        intent = self.prepared()
        projection.receive(dumps(request(1, 'tools/call', {'name': 'hardware_invoke', 'arguments': {'request': intent}})).encode())
        self.assertTrue(entered.wait(3))
        projection.receive(b'{"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":1}}')
        operation_id = accepted[0]['operationId']
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = self.client.request('operation', {'operationId': operation_id})
            if state['executionState'] == 'completed':
                break
            time.sleep(0.02)
        self.assertEqual(state['executionState'], 'completed')
        self.assertEqual(state['cancellationState'], 'not_requested')
        release.set()
        deadline = time.monotonic() + 3
        while projection.calls and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertFalse(projection.calls)
        self.assertTrue(messages.empty())
        self.assertEqual(self.client.request('invoke', {'request': intent})['operationId'], operation_id)
        self.assertEqual(self.runtime.plant.observe('sim:home-fan')['effectCount'], 1)

    def test_actual_stdio_modern_prepare_invoke_replay_and_read(self):
        process = subprocess.Popen([sys.executable, '-m', 'hms.mcp', '--socket', str(self.path)],
                                   cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        def cleanup():
            process.stdin.close()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            process.stdout.close()
            process.stderr.close()
        self.addCleanup(cleanup)
        sequence = 0
        def call(method, params=None):
            nonlocal sequence
            sequence += 1
            process.stdin.write(dumps(request(sequence, method, params)).encode() + b'\n')
            process.stdin.flush()
            self.assertTrue(select.select([process.stdout], [], [], 5)[0], 'MCP response timeout')
            reply = json.loads(process.stdout.readline())
            self.assertEqual(reply['id'], sequence)
            self.assertNotIn('error', reply)
            self.assertEqual(reply['result']['resultType'], 'complete')
            return reply['result']
        self.assertIn(MODERN, call('server/discover')['supportedVersions'])
        tools = []
        params = {}
        while True:
            page = call('tools/list', params)
            tools.extend(page['tools'])
            if 'nextCursor' not in page:
                break
            params = {'cursor': page['nextCursor']}
        schemas = {t['name']: Draft202012Validator(t['outputSchema']) for t in tools}
        def tool(name, arguments):
            result = call('tools/call', {'name': 'hardware_' + name, 'arguments': arguments})
            self.assertFalse(result['isError'], result)
            schemas['hardware_' + name].validate(result['structuredContent'])
            self.assertEqual(json.loads(result['content'][0]['text']), result['structuredContent'])
            return result['structuredContent']['result']
        inventory = tool('discover', {})
        self.assertEqual(len(inventory['items']), 3)
        tool('describe', {'instanceId': 'sim:home-fan'})
        tool('observe', {'instanceId': 'sim:home-fan', 'property': 'value', 'maxAgeMs': 5000, 'evidenceKind': 'simulation'})
        now = time.time_ns() // 1000000
        namespace = tool('namespace', {'expiresUnixMs': now + 60000})
        params = {'instanceId': 'sim:home-fan', 'actionId': 'set_level', 'arguments': {'level': 53, 'unit': 'percent'},
                  'replayNamespace': namespace['token'], 'operationKey': 'stdio:1', 'requiredEffect': 'capability_completion',
                  'timing': {'notBeforeUnixMs': now, 'latestStartUnixMs': now + 10000,
                             'maxRunMs': 1000, 'latestCompletionUnixMs': now + 11000}}
        intent = tool('prepare', params)['request']
        accepted = tool('invoke', {'request': intent})
        deadline = time.monotonic() + 3
        while True:
            time.sleep(0.15)
            state = tool('operation', {'operationId': accepted['operationId']})
            if state['executionState'] != 'running' and state['executionState'] != 'accepted' or time.monotonic() >= deadline:
                break
        self.assertEqual(state['executionState'], 'completed')
        self.assertEqual(state['effectVerification'], 'unverified')
        self.assertEqual(tool('invoke', {'request': intent})['operationId'], accepted['operationId'])
        self.assertTrue(tool('events', {'operationId': accepted['operationId']})['events'])
        self.assertEqual(self.runtime.plant.observe('sim:home-fan')['effectCount'], 1)
        error = call('tools/call', {'name': 'hardware_cancel', 'arguments': {'operationId': accepted['operationId']}})
        self.assertTrue(error['isError'])
        self.assertEqual(error['structuredContent']['error']['code'], 'ALREADY_TERMINAL')
        schemas['hardware_cancel'].validate(error['structuredContent'])


if __name__ == '__main__':
    unittest.main()
