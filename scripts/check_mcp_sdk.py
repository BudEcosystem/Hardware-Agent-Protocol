#!/usr/bin/env python3
"""Independent legacy MCP interoperability probe; SDK is a tester dependency only.

Runs the real HMS daemon and stdio projection against a temporary simulated
plant. No installation, downloaded executable, remote service, or real device.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import select
import sqlite3
import subprocess
import sys
import tempfile
import time

import anyio
from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ('sim:home-fan', 'set_level', {'level': 37, 'unit': 'percent'}, 37),
    ('sim:microscope', 'move_absolute', {'position': 12.5, 'unit': 'um', 'frame': 'sim:microscope'}, 12.5),
    ('sim:inspection-cell', 'inspect', {'recipe': 2, 'partId': 'synthetic-part'}, 1),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provenance():
    dist = importlib.metadata.distribution('mcp')
    selected = {
        'mcp/__init__.py': 'entry exports; complete file inspected',
        'mcp/client/stdio/__init__.py': 'stdio spawn, environment, framing and shutdown; complete file inspected',
        'mcp/client/session.py': 'lines 1-228, 368-428, 497-546: constructor, initialize, ping, call/output validation, tool pagination',
        'mcp/shared/session.py': 'lines 240-330: request identity, timeout, cleanup and notification sending',
        'mcp/shared/version.py': 'complete file: supported versions',
        'mcp/types.py': 'selected LATEST_PROTOCOL_VERSION declaration; SDK models exercised, not whole-file review',
    }
    files = []
    for relative, coverage in selected.items():
        path = Path(dist.locate_file(relative))
        files.append({'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size, 'coverage': coverage})
    for relative in dist.files:
        if str(relative).endswith('.dist-info/METADATA'):
            path = Path(dist.locate_file(relative))
            files.append({'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size,
                          'coverage': 'Name, Version, Requires-Python and Requires-Dist metadata fields inspected'})
    return {'distribution': 'mcp', 'version': dist.version, 'requiresPython': dist.metadata['Requires-Python'],
            'latestProtocol': types.LATEST_PROTOCOL_VERSION, 'python': sys.version,
            'role': 'isolated legacy compatibility tester only; not an HMS production dependency', 'files': files}


@contextmanager
def daemon(directory, *, initialize):
    socket = directory / 'control.sock'
    command = [sys.executable, '-m', 'hms', 'serve', '--state-dir', str(directory / 'state'), '--socket', str(socket)]
    if initialize:
        command.append('--init-simulation')
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert select.select([process.stdout], [], [], 15)[0], 'daemon readiness timed out'
        ready = json.loads(process.stdout.readline())
        assert ready['ready'] and ready['deployment'] == 'simulation:local', ready
        yield socket
    finally:
        process.terminate()
        try:
            output, error = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)
            raise AssertionError('daemon did not stop gracefully')
        assert process.returncode == 0 and not output and not error, (process.returncode, output, error)
        assert not socket.exists(), 'daemon left its socket behind'


class Probe:
    def __init__(self, session, report):
        self.session, self.report, self.tools = session, report, {}
        self.last_call = 0.0

    async def initialize(self):
        initialized = await self.session.initialize()
        assert initialized.protocolVersion == '2025-11-25', initialized
        assert initialized.capabilities.tools.listChanged is False
        assert initialized.capabilities.resources is None and initialized.capabilities.prompts is None
        assert (await self.session.send_ping()).model_dump(exclude_none=True) == {}
        self.report['initializations'] += 1
        pages, cursor = [], None
        while True:
            page = await self.session.list_tools(params=types.PaginatedRequestParams(cursor=cursor))
            pages.append([tool.name for tool in page.tools])
            for tool in page.tools:
                assert tool.name not in self.tools
                self.tools[tool.name] = tool
                Draft202012Validator.check_schema(tool.inputSchema)
                Draft202012Validator.check_schema(tool.outputSchema)
            if page.nextCursor is None:
                break
            assert page.nextCursor != cursor
            cursor = page.nextCursor
        expected = sorted('hardware_' + name for name in
                          ('cancel', 'describe', 'discover', 'events', 'invoke', 'namespace', 'observe', 'operation', 'prepare'))
        assert [name for page in pages for name in page] == expected, pages
        assert [tool.name for tool in (await self.session.list_tools()).tools] == pages[0]
        self.report['catalogPages'].append(pages)
        self.report['advertisedSchemaHashes'] = {
            name: {field: hashlib.sha256(json.dumps(getattr(tool, field), sort_keys=True).encode()).hexdigest()
                   for field in ('inputSchema', 'outputSchema')}
            for name, tool in self.tools.items()}

    async def call(self, method, params, *, error=None):
        # Respect the documented 8/s admission bucket; never retry a mutation.
        await anyio.sleep(max(0.0, self.last_call + 0.14 - time.monotonic()))
        self.last_call = time.monotonic()
        name = 'hardware_' + method
        if error is None:
            Draft202012Validator(self.tools[name].inputSchema).validate(params)
        result = await self.session.call_tool(name, params)
        body = result.structuredContent
        # SDK validates only successful results. Validate both arms independently.
        Draft202012Validator(self.tools[name].outputSchema).validate(body)
        assert len(result.content) == 1 and result.content[0].type == 'text'
        assert json.loads(result.content[0].text) == body
        assert result.isError is (not body['ok'])
        self.report['validatedReplies'] += 1
        if error is not None:
            assert body == {'ok': False, 'error': {'code': error, 'outcome': 'unconfirmed'}}, body
            self.report['typedErrors'].append(error)
            return body
        assert body['ok'], body
        return body['result']

    async def prepare(self, instance, action, arguments, namespace, key, *, delay=0):
        now = time.time_ns() // 1_000_000
        result = await self.call('prepare', {
            'instanceId': instance, 'actionId': action, 'arguments': arguments,
            'replayNamespace': namespace, 'operationKey': key, 'requiredEffect': 'capability_completion',
            'timing': {'notBeforeUnixMs': now + delay, 'latestStartUnixMs': now + 120000,
                       'maxRunMs': 5000, 'latestCompletionUnixMs': now + 180000}})
        assert result['admitted'] is False
        return result

    async def complete(self, operation):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = await self.call('operation', {'operationId': operation})
            if state['executionState'] == 'completed':
                assert state['effectVerification'] == 'unverified'
                assert state['result']['evidenceKind'] == 'simulation'
                assert state['result']['output']['effectCommitted'] is True
                return state
            assert state['executionState'] not in ('failed', 'canceled', 'rejected_before_dispatch'), state
            await anyio.sleep(0.05)
        raise AssertionError('simulated operation did not complete')


async def session_probe(socket, report, action):
    params = StdioServerParameters(command=sys.executable, args=['-m', 'hms.mcp', '--socket', str(socket)], cwd=ROOT)
    with tempfile.TemporaryFile(mode='w+') as errors:
        async with stdio_client(params, errlog=errors) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=10)) as session:
                probe = Probe(session, report)
                await probe.initialize()
                await action(probe)
        errors.seek(0)
        assert errors.read() == '', 'MCP subprocess wrote unexpected stderr'


async def exercise(directory, report):
    retained = []

    async def initial(probe):
        discovery = await probe.call('discover', {'limit': 10})
        assert {item['instanceId'] for item in discovery['items']} == {case[0] for case in CASES}
        namespace = (await probe.call('namespace', {'expiresUnixMs': time.time_ns() // 1_000_000 + 300000}))['token']
        for ordinal, (instance, action, arguments, expected) in enumerate(CASES):
            described = await probe.call('describe', {'instanceId': instance})
            assert described['instance']['identity_kind'] == 'simulation'
            assert described['type']['td']['hms:commissioned'] is False
            prepared = await probe.prepare(instance, action, arguments, namespace, f'sdk:{ordinal}')
            assert prepared['request']['intent']['descriptionDigest'] == described['descriptionDigest']
            # Preserve exactly this envelope; replay is explicit and deliberate.
            request = json.loads(json.dumps(prepared['request']))
            accepted = await probe.call('invoke', {'request': request})
            completed = await probe.complete(accepted['operationId'])
            replay = await probe.call('invoke', {'request': request})
            assert replay['operationId'] == accepted['operationId']
            observation = await probe.call('observe', {'instanceId': instance, 'property': 'value',
                                                      'maxAgeMs': 1000, 'evidenceKind': 'simulation'})
            assert observation['value'] == expected and observation['quality'] == 'valid'
            events = await probe.call('events', {'operationId': accepted['operationId'], 'after': 0, 'limit': 100})
            assert not events['gap'] and events['next'] == completed['eventSequence']
            retained.append((request, accepted['operationId']))
            report['scenarios'].append({'instanceId': instance, 'operationId': accepted['operationId'],
                                        'requestDigest': prepared['requestDigest'], 'executionState': completed['executionState'],
                                        'evidenceKind': 'simulation', 'effectVerification': completed['effectVerification'],
                                        'expectedPlantValue': expected, 'sameOperationOnReplay': True})
        changed = json.loads(json.dumps(retained[0][0]))
        changed['intent']['arguments']['level'] = 38
        await probe.call('invoke', {'request': changed}, error='KEY_CONFLICT')
        await probe.call('discover', {'principal': 'posix:0'}, error='INVALID_REQUEST')
        future = await probe.prepare(CASES[0][0], CASES[0][1], {'level': 99, 'unit': 'percent'}, namespace,
                                     'sdk:future', delay=60000)
        accepted = await probe.call('invoke', {'request': future['request']})
        assert accepted['executionState'] == 'accepted'
        canceled = await probe.call('cancel', {'operationId': accepted['operationId']})
        assert canceled['executionState'] == 'canceled' and canceled['mayHaveActed'] is False
        replay = await probe.call('invoke', {'request': future['request']})
        assert replay['operationId'] == accepted['operationId'] and replay['executionState'] == 'canceled'
        report['explicitCancellation'] = {'operationId': accepted['operationId'], 'executionState': 'canceled',
                                          'mayHaveActed': False, 'sameOperationOnReplay': True}

    async def restored(probe):
        for request, operation in retained:
            replay = await probe.call('invoke', {'request': request})
            assert replay['operationId'] == operation and replay['executionState'] == 'completed'

    with daemon(directory, initialize=True) as socket:
        await session_probe(socket, report, initial)
        await session_probe(socket, report, restored)
        report['mcpProcessRestartReplay'] = True
    with daemon(directory, initialize=False) as socket:
        await session_probe(socket, report, restored)
        report['daemonReopenReplay'] = True
    with sqlite3.connect(f'file:{directory / "state/simulated-plant.db"}?mode=ro', uri=True) as db:
        rows = {instance: {'value': json.loads(value), 'effects': effects}
                for instance, value, effects in db.execute('SELECT id,value,effects FROM devices')}
    assert rows == {instance: {'value': expected, 'effects': 1} for instance, _, _, expected in CASES}, rows
    report['independentPlantRows'] = rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/verification/mcp-sdk.json')
    options = parser.parse_args()
    report = {'status': 'running', 'startedUtc': datetime.now(timezone.utc).isoformat(), 'sdk': provenance(),
              'scope': 'real Linux UDS daemon + real MCP stdio subprocess; legacy 2025-11-25 only; local simulation',
              'initializations': 0, 'catalogPages': [], 'validatedReplies': 0, 'typedErrors': [], 'scenarios': [],
              'limitations': ['No modern SDK interoperability claim; installed SDK lacks 2026-07-28.',
                              'Same-UID shared authority; clientInfo/Session/request IDs confer no authority.',
                              'SDK request timeouts do not emit cancellation automatically; not used as a cancellation oracle.',
                              'Cancellation here is explicit HMS cancel before dispatch; no physical stop proof.']}
    report['inputsSha256'] = {str(path.relative_to(ROOT)): sha(path) for path in sorted(
        [*ROOT.glob('hms/**/*.py'), *ROOT.glob('schemas/*.json'), *ROOT.glob('examples/wot/*.json'),
         ROOT / 'scripts/check_mcp_sdk.py', ROOT / 'research/protocols/wot-artifacts/td-schema-1.1.json'] ) if path.is_file()}
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='hms-mcp-sdk-') as temporary:
            anyio.run(exercise, Path(temporary), report)
        report['status'] = 'passed'
    except BaseException as error:
        report['status'] = 'failed'
        report['failureType'] = type(error).__name__
        raise
    finally:
        report['elapsedSeconds'] = round(time.monotonic() - started, 3)
        report['finishedUtc'] = datetime.now(timezone.utc).isoformat()
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': report['status'], 'validatedReplies': report['validatedReplies'],
                      'scenarios': len(report['scenarios']), 'output': str(options.output)}))


if __name__ == '__main__':
    main()
