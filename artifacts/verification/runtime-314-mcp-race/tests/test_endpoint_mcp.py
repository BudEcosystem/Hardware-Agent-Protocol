"""Actual MCP stdio -> separate HMS daemon -> original native C endpoint.

Modern wire testing is original code; legacy interoperability uses the installed
MCP SDK only as a client. The external real-clock relay records exact OP frames.
No physical port, deterministic control FD, or observer-side invoke is used.
"""
import copy
from contextlib import asynccontextmanager
from datetime import timedelta
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import select
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest

from jsonschema import Draft202012Validator

from hms.endpoint_wire import Execution, Opcode, Operation, Receipt, Request, decode_response
from protocol.serial.frame import Decoder
from tests.test_endpoint_cli import ReplyGate

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / 'artifacts/verification/endpoint-scenarios-build/endpoint-scenarios-pipe'
MODERN = '2026-07-28'
LEGACY = '2025-11-25'
PREFIX = 'io.modelcontextprotocol/'
CASES = (
    ('sim:home-fan', 'set_level', {'level': 25, 'unit': 'percent'}, 25, 0x1001),
    ('sim:microscope', 'move_absolute', {'position': 42, 'unit': 'um', 'frame': 'sim:microscope'}, 42, 0x1002),
    ('sim:inspection-cell', 'inspect', {'recipe': 1, 'partId': 'mcp:α'}, 1, 0x1003),
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def sdk_available():
    try:
        return importlib.metadata.version('mcp') == '1.26.0'
    except importlib.metadata.PackageNotFoundError:
        return False


class NativeHarness:
    """Launcher-owned endpoint/socket lifetime, independent of daemon lifetime."""

    def __init__(self, directory, report):
        assert BINARY.is_file(), 'Build scripts/check_endpoint_scenarios.py first'
        self.base, self.report = directory, report
        self.path, self.state = directory / 'control.sock', directory / 'state'
        self.daemon = None
        self.host, relay_host = socket.socketpair()
        relay_native, native = socket.socketpair()
        self.fixture = subprocess.Popen([str(BINARY), '--boot', '83'], stdin=native, stdout=native,
                                        stderr=subprocess.PIPE)
        native.close()
        self.relay = ReplyGate(relay_host, relay_native)

    def start(self, *, create=False):
        command = [sys.executable, '-B', '-m', 'hms', 'serve', '--socket', str(self.path),
                   '--state-dir', str(self.state), '--endpoint-fd', str(self.host.fileno())]
        if create:
            command.append('--init-compact-simulation')
        self.daemon = subprocess.Popen(command, cwd=ROOT, pass_fds=(self.host.fileno(),),
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert select.select([self.daemon.stdout], [], [], 10)[0], 'Daemon readiness timeout'
        line = self.daemon.stdout.readline()
        assert line, 'Daemon exited before readiness'
        ready = json.loads(line)
        assert ready['ready'] and ready['deployment'] == 'simulation:compact', ready
        info = self.path.lstat()
        assert stat.S_ISSOCK(info.st_mode)
        self.socket_identity = info.st_dev, info.st_ino
        assert self.fixture.poll() is None
        self.report['daemonStarts'].append({'command': command, 'readiness': ready})

    def stop(self, *, kill=False):
        process, self.daemon = self.daemon, None
        if process is None:
            return
        if kill:
            process.kill()
        else:
            process.terminate()
        try:
            output, error = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=3)
            raise AssertionError('Daemon cleanup timeout')
        expected = -signal.SIGKILL if kill else 0
        assert process.returncode == expected and not error and not output, (process.returncode, output, error)
        assert self.fixture.poll() is None, 'Endpoint must outlive daemon'
        self.report['daemonExits'].append(process.returncode)
        if kill:
            # Explicit test-owner reclamation only, after reaping our daemon.
            info = self.path.lstat()
            assert stat.S_ISSOCK(info.st_mode) and (info.st_dev, info.st_ino) == self.socket_identity
            self.path.unlink()
        else:
            assert not self.path.exists()

    def rows(self, sql, parameters=()):
        with sqlite3.connect(f'file:{self.state / "authority.db"}?mode=ro', uri=True, timeout=1) as db:
            return db.execute(sql, parameters).fetchall()

    def snapshot(self):
        assert self.daemon is None, 'Freeze host writes before retaining evidence'
        assert not (self.state / 'simulated-plant.db').exists()
        with self.relay.lock:
            requests, responses = list(self.relay.requests), list(self.relay.responses)
        packet_rows = self.rows('SELECT direction,wire FROM ep_packets ORDER BY id')
        transmitted = []
        for direction, raw in packet_rows:
            decoder = Decoder()
            frames = []
            for byte in raw:
                event = decoder.feed(byte)
                if event is not None:
                    assert event[0] == 'frame', event
                    frames.append(event[1])
            assert len(frames) == 1
            if direction == 'tx' and frames[0].payload[1] == Opcode.OP:
                transmitted.append(raw)
        forwarded = self.relay.op_frames()
        assert transmitted == [raw for _, raw in forwarded]
        assert len(forwarded) == 3, 'Each run must dispatch exactly three original OP frames'
        request_by_sequence = {frame.sequence: frame for frame, _ in requests}
        independent_results = []
        for (frame, _), case in zip(forwarded, CASES):
            operation = Operation.parse(frame.payload)
            assert frame.session == 83 and operation.primitive_id == case[4]
            expected_arguments = (bytes((1, len('mcp:α'.encode()))) + 'mcp:α'.encode()
                                  if case[4] == 0x1003 else bytes((case[3],)))
            assert operation.arguments == expected_arguments
            committed = []
            for response, _ in responses:
                original = request_by_sequence.get(int.from_bytes(response.payload[2:6], 'big'))
                if original is None:
                    continue
                if original.payload != frame.payload and original.payload not in (
                        operation.reference.payload(Opcode.QUERY), operation.reference.payload(Opcode.CANCEL)):
                    continue
                receipt = decode_response(response, Request(original), operation=operation, simulator_only=True)
                if isinstance(receipt, Receipt) and receipt.execution == Execution.COMPLETED:
                    assert receipt.evidence_kind == 5 and len(receipt.result) == 12
                    sample, value = int.from_bytes(receipt.result[:8], 'big'), int.from_bytes(receipt.result[8:], 'big')
                    assert value == case[3]
                    committed.append({'sampleTick': sample, 'value': value})
            assert committed and all(value == committed[0] for value in committed)
            assert self.report['scenarios'][len(independent_results)]['result']['output'] == {
                'effectCommitted': True, **committed[0]}
            independent_results.append({'instanceId': case[0], **committed[0]})
        def capture(items):
            return [{'session': frame.session, 'sequence': frame.sequence,
                     'opcode': frame.payload[1], 'wireHex': raw.hex()} for frame, raw in items]
        self.report['endpointFrames'] = {'requests': capture(requests), 'responses': capture(responses)}
        self.report['retainedPackets'] = [{'direction': direction, 'wireHex': raw.hex()} for direction, raw in packet_rows]
        self.report['retainedCommands'] = [
            {'operationId': op, 'payloadHex': payload.hex(), 'txSequence': sequence,
             'mapping': json.loads(mapping), 'receiptHex': receipt.hex() if receipt else None,
             'result': json.loads(result) if result else None, 'retireIntent': retire_intent, 'retired': retired}
            for op, payload, sequence, mapping, receipt, result, retire_intent, retired in self.rows(
                'SELECT operation_id,payload,tx_sequence,mapping,receipt,result,retire_intent,retired FROM ep_commands ORDER BY rowid')]
        self.report['independentEvidence'] = {
            'forwardedOpFrames': len(forwarded), 'exactMatchToDurableTxFrames': True,
            'inspectionResultCounter': 1, 'sqlitePlantAbsent': True,
            'independentlyDecodedNativeCompletedResults': independent_results,
            'separateEffectCounterChannel': False,
            'qualification': 'Fan/focus values are idempotent; exact OP-frame count is handoff evidence, not an independently measured physical effect count.'}

    def close(self):
        try:
            self.stop()
        finally:
            self.host.close()
            try:
                self.relay.close()
            finally:
                try:
                    _, error = self.fixture.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    self.fixture.kill()
                    self.fixture.communicate(timeout=3)
                    raise AssertionError('Endpoint did not exit after launcher stream close')
                assert self.fixture.returncode == 0 and not error, (self.fixture.returncode, error)


class ModernStdio:
    def __init__(self, path, report):
        self.report, self.sequence = report, 0
        self.process = subprocess.Popen([sys.executable, '-B', '-m', 'hms.mcp', '--socket', str(path)],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        official = json.loads((ROOT / 'research/mcp/raw/schema__2026-07-28__schema.json').read_text())
        self.validators = {method: Draft202012Validator({'$ref': '#/$defs/' + definition, '$defs': official['$defs']})
            for method, definition in {'server/discover': 'DiscoverResultResponse',
                                      'tools/list': 'ListToolsResultResponse', 'tools/call': 'CallToolResultResponse'}.items()}

    async def rpc(self, method, params=None):
        self.sequence += 1
        request = {'jsonrpc': '2.0', 'id': self.sequence, 'method': method,
                   'params': {**(params or {}), '_meta': {PREFIX + 'protocolVersion': MODERN,
                                                       PREFIX + 'clientCapabilities': {}}}}
        self.process.stdin.write(json.dumps(request, ensure_ascii=False).encode() + b'\n')
        self.process.stdin.flush()
        assert select.select([self.process.stdout], [], [], 8)[0], 'MCP stdio response timeout'
        raw = self.process.stdout.readline(524289)
        assert raw.endswith(b'\n') and len(raw) <= 524288, 'Bounded complete MCP line required'
        reply = json.loads(raw)
        self.report['mcpMessages'].append({'request': request, 'reply': reply})
        assert reply.get('id') == self.sequence and 'error' not in reply, reply
        self.validators[method].validate(reply)
        assert reply['result']['resultType'] == 'complete'
        return reply['result']

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)
            raise AssertionError('MCP projection did not exit on EOF')
        output, error = self.process.stdout.read(), self.process.stderr.read()
        self.process.stdout.close()
        self.process.stderr.close()
        assert self.process.returncode == 0 and not output and not error, (self.process.returncode, output, error)
        self.report['mcpClosures'].append({'transport': 'modern-stdio', 'exitCode': 0, 'stdinEOF': True})


class Probe:
    def __init__(self, protocol, client, report):
        self.protocol, self.client, self.report = protocol, client, report
        self.tools, self.last_call = {}, 0.0

    async def initialize(self):
        if self.protocol == MODERN:
            initialized = await self.client.rpc('server/discover')
            assert initialized['supportedVersions'] == [MODERN, LEGACY]
        else:
            initialized = await self.client.initialize()
            assert initialized.protocolVersion == LEGACY
            self.report['mcpMessages'].append({'sdkInitialization': initialized.model_dump(exclude_none=True)})
        pages, cursor = [], None
        while True:
            if self.protocol == MODERN:
                page = await self.client.rpc('tools/list', {} if cursor is None else {'cursor': cursor})
            else:
                from mcp import types
                page = (await self.client.list_tools(params=types.PaginatedRequestParams(cursor=cursor))).model_dump(exclude_none=True)
                self.report['mcpMessages'].append({'sdkToolsPage': page})
            pages.append([tool['name'] for tool in page['tools']])
            for tool in page['tools']:
                assert tool['name'] not in self.tools
                for field in ('inputSchema', 'outputSchema'):
                    Draft202012Validator.check_schema(tool[field])
                self.tools[tool['name']] = tool
            if 'nextCursor' not in page:
                break
            cursor = page['nextCursor']
        assert sorted(self.tools) == sorted('hardware_' + name for name in
            ('discover', 'describe', 'observe', 'namespace', 'prepare', 'invoke', 'operation', 'events', 'cancel'))
        self.report['catalogs'].append({'protocol': self.protocol, 'pages': pages,
            'schemas': {name: {field: digest(tool[field]) for field in ('inputSchema', 'outputSchema')}
                        for name, tool in self.tools.items()}})

    async def call(self, method, arguments, *, error=None):
        import anyio
        await anyio.sleep(max(0.0, self.last_call + 0.15 - time.monotonic()))
        self.last_call = time.monotonic()
        name = 'hardware_' + method
        Draft202012Validator(self.tools[name]['inputSchema']).validate(arguments)
        if self.protocol == MODERN:
            result = await self.client.rpc('tools/call', {'name': name, 'arguments': arguments})
        else:
            result = (await self.client.call_tool(name, arguments)).model_dump(exclude_none=True)
            self.report['mcpMessages'].append({'sdkToolCall': {'name': name, 'arguments': copy.deepcopy(arguments)}, 'reply': result})
        body = result['structuredContent']
        Draft202012Validator(self.tools[name]['outputSchema']).validate(body)
        assert len(result['content']) == 1 and result['content'][0]['type'] == 'text'
        assert json.loads(result['content'][0]['text']) == body
        assert result['isError'] is (not body['ok'])
        self.report['validatedToolReplies'] += 1
        if error is not None:
            assert body == {'ok': False, 'error': {'code': error, 'outcome': 'unconfirmed'}}, body
            return body
        assert body['ok'], body
        return body['result']


@asynccontextmanager
async def projection(protocol, path, report):
    if protocol == MODERN:
        client = ModernStdio(path, report)
        try:
            probe = Probe(protocol, client, report)
            await probe.initialize()
            yield probe
        finally:
            client.close()
    else:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        parameters = StdioServerParameters(command=sys.executable,
            args=['-B', '-m', 'hms.mcp', '--socket', str(path)], cwd=ROOT)
        with tempfile.TemporaryFile(mode='w+') as errors:
            async with stdio_client(parameters, errlog=errors) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=8)) as client:
                    probe = Probe(protocol, client, report)
                    await probe.initialize()
                    yield probe
            errors.seek(0)
            assert errors.read() == '', 'SDK-spawned projection wrote stderr'
        report['mcpClosures'].append({'transport': 'legacy-sdk-stdio', 'clientContextExited': True,
                                    'childExitCodeExposedBySDK': False})


def preparation(case, namespace, key, *, delay=0):
    now = time.time_ns() // 1_000_000
    return {'instanceId': case[0], 'actionId': case[1], 'arguments': copy.deepcopy(case[2]),
            'operationKey': key, 'replayNamespace': namespace, 'requiredEffect': 'capability_completion',
            'timing': {'notBeforeUnixMs': now + delay, 'latestStartUnixMs': now + 15000 + delay,
                       'maxRunMs': 2000, 'latestCompletionUnixMs': now + 20000 + delay}}


async def completed(probe, harness, operation_id):
    deadline = time.monotonic() + 8
    status = None
    while time.monotonic() < deadline:
        if harness.relay.error is not None:
            raise harness.relay.error
        status = await probe.call('operation', {'operationId': operation_id})
        if status['executionState'] == 'completed' and not status['resourceClaims']:
            if harness.rows('SELECT retired FROM ep_commands WHERE operation_id=?', (operation_id,)) == [(1,)]:
                assert status['effectVerification'] == 'unverified'
                assert status['result']['evidenceKind'] == 'simulation'
                assert status['result']['output']['effectCommitted'] is True
                return status
        assert status['executionState'] not in {'failed', 'canceled', 'rejected_before_dispatch', 'rejected_before_start'}, status
    raise AssertionError(f'Native operation did not complete and retire: {status}')


async def exercise(protocol, harness, report):
    retained = []
    async with projection(protocol, harness.path, report) as probe:
        found = await probe.call('discover', {'limit': 10})
        assert {item['instanceId'] for item in found['items']} == {case[0] for case in CASES}
        namespace = (await probe.call('namespace', {'expiresUnixMs': time.time_ns() // 1_000_000 + 180000}))['token']
        for ordinal, case in enumerate(CASES, 1):
            described = await probe.call('describe', {'instanceId': case[0]})
            assert described['instance']['identity_kind'] == 'simulation'
            assert described['type']['td']['hms:commissioned'] is False
            prepared = await probe.call('prepare', preparation(case, namespace, f'mcp:compact:{ordinal}'))
            request = copy.deepcopy(prepared['request'])
            assert prepared['admitted'] is False
            assert request['intent']['descriptionDigest'] == described['descriptionDigest']
            crash = protocol == MODERN and ordinal == 3
            if crash:
                harness.relay.arm()
            accepted = await probe.call('invoke', {'request': request})
            assert accepted['executionState'] == 'accepted'
            operation_id = accepted['operationId']
            if crash:
                assert harness.relay.gated.wait(3), 'Actual native OP reply was not observed'
                harness.stop(kill=True)
                frame, raw = harness.relay.op_frames()[-1]
                operation = Operation.parse(frame.payload)
                reply_frame, _ = harness.relay.gated_reply
                receipt = decode_response(reply_frame, Request(frame), operation=operation, simulator_only=True)
                assert isinstance(receipt, Receipt) and receipt.execution in {Execution.QUEUED, Execution.RUNNING}
                assert operation.reference.intent_digest.hex() == accepted['requestDigest'][7:]
                before = harness.rows('SELECT payload,tx_sequence,receipt FROM ep_commands WHERE operation_id=?', (operation_id,))
                assert before == [(frame.payload, frame.sequence, None)], before
                with harness.relay.lock:
                    restart_index = len(harness.relay.requests)
                harness.relay.release.set()
                harness.start()
                # Reuse the same MCP process; only the independent daemon died.
                replay = await probe.call('invoke', {'request': request})
                assert replay['operationId'] == operation_id and replay['requestDigest'] == accepted['requestDigest']
                report['hostProcessLoss'] = {'operationId': operation_id, 'signal': 'SIGKILL',
                    'gatedNativeExecution': int(receipt.execution), 'noReceiptPersistedAtDeath': True,
                    'endpointStayedAlive': True, 'oldOpWireHex': raw.hex(), 'sameMcpProcess': True}
            state = await completed(probe, harness, operation_id)
            assert state['result']['output']['value'] == case[3]
            replay = await probe.call('invoke', {'request': request})
            assert replay['operationId'] == operation_id and replay['result'] == state['result']
            observed = await probe.call('observe', {'instanceId': case[0], 'property': 'value',
                                                    'maxAgeMs': 10000, 'evidenceKind': 'simulation'})
            assert observed['value'] == case[3]
            assert observed['acquisition']['ticksMs'] == state['result']['output']['sampleTick']
            events = await probe.call('events', {'operationId': operation_id, 'after': 0, 'limit': 100})
            assert not events['gap'] and events['events']
            assert len(harness.relay.op_frames()) == ordinal
            if crash:
                with harness.relay.lock:
                    recovered = [f for f, _ in harness.relay.requests[restart_index:]]
                assert any(f.payload == operation.reference.payload(Opcode.QUERY) for f in recovered)
                assert harness.rows('SELECT payload,tx_sequence FROM ep_commands WHERE operation_id=?', (operation_id,)) == [before[0][:2]]
                report['hostProcessLoss']['matchingRecoveryQuery'] = True
                report['hostProcessLoss']['noOpRetransmission'] = True
            retained.append((request, state))
            report['scenarios'].append({'instanceId': case[0], 'operationId': operation_id,
                'requestDigest': accepted['requestDigest'], 'result': state['result'],
                'effectVerification': state['effectVerification'], 'sameOperationAndResultOnReplay': True})
        changed = copy.deepcopy(retained[0][0])
        changed['intent']['arguments']['level'] = 26
        await probe.call('invoke', {'request': changed}, error='KEY_CONFLICT')
        future_case = (CASES[0][0], CASES[0][1], {'level': 99, 'unit': 'percent'})
        future = (await probe.call('prepare', preparation(future_case, namespace, 'mcp:compact:future', delay=30000)))['request']
        admitted_future = await probe.call('invoke', {'request': future})
        assert admitted_future['executionState'] == 'accepted' and admitted_future['mayHaveActed'] is False
        future_id = admitted_future['operationId']
    # Close the actual MCP transport/process. Read by its returned operation ID;
    # an observer never invokes a request to manufacture missing admission.
    assert harness.fixture.poll() is None and harness.daemon.poll() is None
    async with projection(protocol, harness.path, report) as probe:
        after_close = await probe.call('operation', {'operationId': future_id})
        assert after_close['executionState'] == 'accepted' and after_close['cancellationState'] == 'not_requested'
        assert len(harness.relay.op_frames()) == 3
        canceled = await probe.call('cancel', {'operationId': future_id})
        assert canceled['executionState'] == 'canceled' and canceled['mayHaveActed'] is False
        replay = await probe.call('invoke', {'request': future})
        assert replay['operationId'] == future_id and replay['executionState'] == 'canceled'
        assert len(harness.relay.op_frames()) == 3
        for request, state in retained:
            replay = await probe.call('invoke', {'request': request})
            assert replay['operationId'] == state['operationId'] and replay['result'] == state['result']
        report['closeVersusCancel'] = {'operationIdFromActualMcpInvoke': future_id,
            'afterMcpClose': after_close, 'afterExplicitHmsCancel': canceled,
            'noFutureOpFrame': True, 'sameCanceledOperationOnExactReplay': True,
            'scope': 'Accepted future host work before dispatch; not a running endpoint cancellation or independent stop test.'}


@unittest.skipUnless(sys.platform == 'linux' and hasattr(socket, 'SO_PEERCRED'), 'Linux peer credentials required')
class CompactMcpTests(unittest.TestCase):
    def run_protocol(self, protocol):
        import anyio
        report = {'protocol': protocol, 'passed': False, 'daemonStarts': [], 'daemonExits': [],
                  'catalogs': [], 'mcpMessages': [], 'mcpClosures': [], 'validatedToolReplies': 0, 'scenarios': []}
        try:
            with tempfile.TemporaryDirectory(prefix='hms-compact-mcp-') as temporary:
                harness = NativeHarness(Path(temporary), report)
                try:
                    harness.start(create=True)
                    anyio.run(exercise, protocol, harness, report)
                    harness.stop()
                    harness.snapshot()
                    report['passed'] = True
                finally:
                    harness.close()
        finally:
            if os.environ.get('HMS_COMPACT_MCP_TRACE_DIR'):
                destination = Path(os.environ['HMS_COMPACT_MCP_TRACE_DIR'])
                destination.mkdir(parents=True, exist_ok=True)
                (destination / f'{protocol}.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')

    def test_modern_mcp_native_scenarios_host_SIGKILL_replay_and_explicit_cancel(self):
        self.run_protocol(MODERN)

    @unittest.skipUnless(sdk_available(), 'Installed MCP SDK 1.26.0 is a legacy tester dependency only')
    def test_legacy_sdk_native_scenarios_mcp_close_replay_and_explicit_cancel(self):
        self.run_protocol(LEGACY)


if __name__ == '__main__':
    unittest.main()
