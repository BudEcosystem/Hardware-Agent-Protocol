"""Original mixed-route procedure transport probes; no hardware/MCU execution.

Real CLI/UDS/MCP cases use a real-clock native C fixture and external byte relay.
The separate queue regression uses the original fixture's synthetic time channel.
Neither source is physical evidence or an availability/timing qualification.
"""
import copy
from contextlib import asynccontextmanager
from datetime import timedelta
import hashlib
import json
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

from hms.client import Client
from hms.contracts import canonical
from hms.endpoint_wire import Opcode, Operation
from hms.installations import manifest_for, plant_filename
from hms.ipc import IpcError
from protocol.serial.frame import Decoder
from tests.test_endpoint_cli import ReplyGate
from tests.test_endpoint_mcp import LEGACY, MODERN, ModernStdio, sdk_available
from test_multi_adapter import BINARY, ROOT, MultiHarness, installation, scenario


LAST_REPORT = {'schema': 'hms-procedure-transport-tests/1', 'cases': {},
    'scope': 'Original local simulations through real transports plus a separate synthetic-clock queue regression; no physical effects, MCU execution, latency or availability qualification.'}


def new_report(name):
    report = {'passed': False, 'daemonStarts': [], 'daemonExits': [], 'cliCalls': [], 'refusals': [],
              'mcpMessages': [], 'mcpClosures': [], 'catalogs': [], 'validatedToolReplies': 0}
    LAST_REPORT['cases'][name] = report
    return report


def envelope(namespace, key, timing, requests):
    return {'protocol': 'hms.procedure/0.1', 'replayNamespace': namespace, 'procedureKey': key,
            'procedure': {'profile': 'hms.bound-sequence/0.1',
                'timing': {k: timing[k] for k in ('notBeforeUnixMs','latestStartUnixMs','latestCompletionUnixMs')},
                'steps': [{'stepId': 'step:' + str(i), 'request': request} for i, request in enumerate(requests)]}}


def timing(*, delay=0):
    now = time.time_ns() // 1_000_000
    return {'notBeforeUnixMs': now + delay, 'latestStartUnixMs': now + delay + 30000,
            'maxRunMs': 2000, 'latestCompletionUnixMs': now + delay + 35000}


class MixedDaemon:
    def __init__(self, base, report):
        assert BINARY.is_file(), 'Build original endpoint-scenarios fixture first'
        self.base, self.report, self.daemon = base, report, None
        self.path, self.state = base / 'control.sock', base / 'state'
        self.local = installation('procedure-transport-local')
        self.compact = installation('procedure-transport-native', compact=True)
        self.config_path = base / 'installations.json'
        self.config_path.write_bytes(canonical([self.local, self.compact]))
        self.host, relay_host = socket.socketpair()
        relay_native, native = socket.socketpair()
        data, digest = manifest_for(self.compact)
        self.fixture = subprocess.Popen([str(BINARY), '--manifest', digest,
            '--incarnation', self.compact['incarnationHex'], '--firmware', json.loads(data)['firmwareDigest']],
            stdin=native, stdout=native, stderr=subprocess.PIPE)
        native.close()
        self.relay = ReplyGate(relay_host, relay_native)
        self.client = Client(self.path)

    def start(self, *, create=False):
        args = [sys.executable, '-B', '-m', 'hms', 'serve', '--socket', str(self.path),
                '--state-dir', str(self.state), '--endpoint-route',
                self.compact['adapterId'] + '=' + str(self.host.fileno())]
        if create:
            args += ['--init-multi-simulation', '--installations-file', str(self.config_path)]
        self.daemon = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       pass_fds=(self.host.fileno(),))
        assert select.select([self.daemon.stdout], [], [], 10)[0], 'Daemon ready timeout'
        line = self.daemon.stdout.readline()
        assert line, 'Daemon ended before readiness'
        ready = json.loads(line)
        assert ready['ready'] and ready['deployment'] == 'simulation:multi', ready
        info = self.path.lstat()
        assert stat.S_ISSOCK(info.st_mode)
        self.socket_identity = info.st_dev, info.st_ino
        assert self.fixture.poll() is None
        self.report['daemonStarts'].append({'command': args, 'readiness': ready})

    def stop(self, *, kill=False):
        process, self.daemon = self.daemon, None
        if process is None:
            return
        process.kill() if kill else process.terminate()
        try:
            output, error = process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill(); process.communicate(timeout=3)
            raise AssertionError('Daemon stop timeout')
        assert process.returncode == (-signal.SIGKILL if kill else 0) and not output and not error, (process.returncode, output, error)
        assert self.fixture.poll() is None, 'Original endpoint must outlive daemon'
        self.report['daemonExits'].append(process.returncode)
        if kill:
            info = self.path.lstat()
            assert stat.S_ISSOCK(info.st_mode) and (info.st_dev, info.st_ino) == self.socket_identity
            self.path.unlink()  # Reaped launcher-owned stale socket only.
        else:
            assert not self.path.exists()

    def rows(self, sql, values=()):
        with sqlite3.connect(f'file:{self.state / "authority.db"}?mode=ro', uri=True, timeout=1) as db:
            return db.execute(sql, values).fetchall()

    def call(self, method, **params):
        return self.client.request(method, params)

    def cli(self, command, *arguments, request=None):
        args = [sys.executable, '-B', '-m', 'hms', '--socket', str(self.path), command, *arguments]
        if request is not None:
            path = self.base / 'plan.json'
            path.write_bytes(canonical(request))
            args += ['--request-file', str(path)]
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0 and not result.stderr, (args, result.stdout, result.stderr)
        body = json.loads(result.stdout)
        self.report['cliCalls'].append({'command': command, 'arguments': list(arguments), 'result': body})
        return body

    def prepare(self, config, role, namespace, key, bounds):
        instance, action, arguments = scenario(config, role)
        params = dict(instanceId=instance, actionId=action, arguments=arguments,
            operationKey=key, replayNamespace=namespace, requiredEffect='capability_completion', timing=bounds)
        wire = canonical(params)
        tables = ('operations','claims','ep_commands','pr_procedures','pr_keys')
        before = [self.rows('SELECT count(*) FROM ' + table)[0][0] for table in tables]
        deadline = time.monotonic() + 3
        while True:
            assert canonical(params) == wire
            try:
                return self.call('prepare', **params)['request']
            except IpcError as error:
                if error.code not in {'OBSERVATION_STALE','DEVICE_UNAVAILABLE'}:
                    raise
                # Only prepare is retried, and only after proving no authority
                # admission/key/claim/dispatch mapping changed. No invoke,
                # parent submit, transport uncertainty, or changed intent retry.
                after = [self.rows('SELECT count(*) FROM ' + table)[0][0] for table in tables]
                assert after == before
                assert not self.rows('SELECT operation_id FROM replay_keys WHERE namespace=? AND caller_key=?', (namespace,key))
                self.report['refusals'].append({'method': 'prepare', 'code': error.code,
                    'paramsSha256': hashlib.sha256(wire).hexdigest(), 'countsBefore': before,
                    'countsAfter': after, 'replayKeyAbsent': True})
                assert time.monotonic() < deadline, 'Bounded pre-admission freshness retry exhausted'
                time.sleep(.05)

    def wait(self, method, parameters, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.relay.error:
                raise self.relay.error
            result = self.call(method, **parameters)
            if predicate(result):
                return result
            time.sleep(.03)
        raise AssertionError(('State did not converge', method, result))

    def snapshot(self, expected_native_children):
        assert self.daemon is None
        operations = self.relay.op_frames()
        assert len(operations) == len(expected_native_children)
        observed = [Operation.parse(frame.payload) for frame, _ in operations]
        assert {item.reference.intent_digest.hex() for item in observed} == {
            item['requestDigest'].removeprefix('sha256:') for item in expected_native_children}
        assert len({item.reference.intent_digest for item in observed}) == len(observed)
        transmitted = []
        for (raw,) in self.rows("SELECT wire FROM ep_packets WHERE direction='tx' ORDER BY id"):
            decoder = Decoder()
            frames = [event[1] for byte in raw if (event := decoder.feed(byte)) is not None and event[0] == 'frame']
            assert len(frames) == 1
            if frames[0].payload[1] == Opcode.OP:
                transmitted.append(raw)
        assert transmitted == [raw for _,raw in operations]
        self.report['nativeEvidence'] = {'forwardedOpFrames': len(operations),
            'oneOpPerNativeChild': True, 'exactMatchToDurableTransmittedFrames': True,
            'wireHex': [raw.hex() for _,raw in operations],
            'scope': 'External original-byte relay handoff evidence; no independent physical effect counter.'}
        with sqlite3.connect(f'file:{self.state / plant_filename(self.local)}?mode=ro', uri=True) as db:
            devices = {instance: {'value':json.loads(value),'effectCount':effects}
                       for instance,value,effects in db.execute('SELECT id,value,effects FROM devices')}
            assert devices[self.local['instances']['fan']] == {'value':25,'effectCount':1}
            assert all(devices[self.local['instances'][role]] == {'value':0,'effectCount':0}
                       for role in ('focus','inspection'))
            self.report['sqlitePlantEvidence'] = {'devices':devices,
                'scope':'Original persistent SQLite simulation effect counts, not physical evidence.'}

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
                    self.fixture.kill(); self.fixture.communicate(timeout=3)
                    raise AssertionError('Native fixture exit timeout')
                assert self.fixture.returncode == 0 and not error, (self.fixture.returncode, error)


class ProcedureProbe:
    def __init__(self, protocol, client, report):
        self.protocol, self.client, self.report = protocol, client, report
        self.tools = {}

    async def initialize(self):
        if self.protocol == MODERN:
            assert (await self.client.rpc('server/discover'))['supportedVersions'] == [MODERN,LEGACY]
        else:
            initialized = await self.client.initialize()
            assert initialized.protocolVersion == LEGACY
            self.report['mcpMessages'].append({'sdkInitialization': initialized.model_dump(exclude_none=True)})
        cursor, pages = None, []
        while True:
            if self.protocol == MODERN:
                page = await self.client.rpc('tools/list', {} if cursor is None else {'cursor':cursor})
            else:
                from mcp import types
                page = (await self.client.list_tools(params=types.PaginatedRequestParams(cursor=cursor))).model_dump(exclude_none=True)
                self.report['mcpMessages'].append({'sdkToolsPage': page})
            pages.append([tool['name'] for tool in page['tools']])
            for tool in page['tools']:
                assert tool['name'] not in self.tools
                for field in ('inputSchema','outputSchema'):
                    Draft202012Validator.check_schema(tool[field])
                self.tools[tool['name']] = tool
            cursor = page.get('nextCursor')
            if cursor is None:
                break
        expected = {'hardware_procedure_' + name for name in ('submit','status','cancel','resume','events')}
        assert expected <= self.tools.keys()
        for name in expected:
            assert self.tools[name]['annotations']['readOnlyHint'] == (name.endswith('_status') or name.endswith('_events'))
        self.report['catalogs'].append({'protocol': self.protocol, 'pages': pages, 'procedureTools': sorted(expected)})

    async def call(self, method, **arguments):
        name = 'hardware_' + method
        Draft202012Validator(self.tools[name]['inputSchema']).validate(arguments)
        if self.protocol == MODERN:
            result = await self.client.rpc('tools/call', {'name':name,'arguments':arguments})
        else:
            result = (await self.client.call_tool(name, arguments)).model_dump(exclude_none=True)
            self.report['mcpMessages'].append({'sdkToolCall': {'name':name,'arguments':copy.deepcopy(arguments)}, 'reply':result})
        body = result['structuredContent']
        Draft202012Validator(self.tools[name]['outputSchema']).validate(body)
        assert len(result['content']) == 1 and result['content'][0]['type'] == 'text'
        assert json.loads(result['content'][0]['text']) == body
        assert result['isError'] is (not body['ok']) and body['ok'], body
        self.report['validatedToolReplies'] += 1
        return body['result']


@asynccontextmanager
async def projection(protocol, harness):
    report = harness.report
    if protocol == MODERN:
        client = ModernStdio(harness.path, report)
        try:
            probe = ProcedureProbe(protocol, client, report)
            await probe.initialize()
            yield probe
        finally:
            client.close()
    else:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        parameters = StdioServerParameters(command=sys.executable,
            args=['-B','-m','hms.mcp','--socket',str(harness.path)], cwd=ROOT)
        with tempfile.TemporaryFile(mode='w+') as errors:
            async with stdio_client(parameters, errlog=errors) as (read,write):
                async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=8)) as client:
                    probe = ProcedureProbe(protocol,client,report)
                    await probe.initialize()
                    yield probe
            errors.seek(0)
            assert errors.read() == ''
        report['mcpClosures'].append({'transport':'legacy-sdk-stdio','clientContextExited':True,
                                    'childExitCodeExposedBySDK':False})


@unittest.skipUnless(sys.platform == 'linux' and hasattr(socket,'SO_PEERCRED'), 'Linux UDS peer credentials required')
class ProcedureTransportTests(unittest.TestCase):
    def test_cli_mixed_sequence_SIGKILL_exact_replay_and_explicit_resume(self):
        report = new_report('cli-mixed-restart')
        with tempfile.TemporaryDirectory(prefix='hms-procedure-cli-') as temporary:
            harness = MixedDaemon(Path(temporary),report)
            try:
                harness.start(create=True)
                namespace = harness.call('namespace',expiresUnixMs=time.time_ns() // 1_000_000 + 180000)['token']
                bounds = timing()
                selected = [(harness.compact,'inspection'),(harness.local,'fan'),(harness.compact,'focus')]
                requests = [harness.prepare(config,role,namespace,'cli-child:'+str(i),bounds)
                            for i,(config,role) in enumerate(selected)]
                request = envelope(namespace,'cli-parent',bounds,requests)
                harness.relay.arm()
                parent = harness.cli('procedure-submit',request=request)
                procedure_id = parent['procedureId']
                self.assertTrue(harness.relay.gated.wait(3), 'Actual native OP reply not captured')
                interrupted_child = harness.rows('SELECT operation_id FROM pr_steps WHERE procedure_id=? AND ordinal=0', (procedure_id,))[0][0]
                self.assertIsNotNone(interrupted_child)
                harness.stop(kill=True)
                before = harness.rows('SELECT operation_id,payload,tx_sequence FROM ep_commands')
                self.assertEqual(len(before),1)
                self.assertEqual(harness.rows('SELECT receipt FROM ep_commands'),[(None,)])
                original_operation = Operation.parse(before[0][1])
                with harness.relay.lock:
                    restart_index = len(harness.relay.requests)
                harness.relay.release.set()
                harness.start()
                child = harness.wait('operation',{'operationId':interrupted_child},
                    lambda state: state['executionState']=='completed' and not state['resourceClaims'])
                paused = harness.cli('procedure-status',procedure_id)
                self.assertEqual(paused['executionState'],'interrupted')
                self.assertEqual([step['operationId'] for step in paused['steps']],[interrupted_child,None,None])
                self.assertEqual(len(harness.relay.op_frames()),1)
                replay = harness.cli('procedure-submit',request=request)
                self.assertEqual(replay['procedureId'],procedure_id)
                self.assertEqual(replay['executionState'],'interrupted')
                self.assertEqual(harness.rows('SELECT operation_id,payload,tx_sequence FROM ep_commands'),before)
                with harness.relay.lock:
                    self.assertTrue(any(frame.payload == original_operation.reference.payload(Opcode.QUERY)
                                        for frame,_ in harness.relay.requests[restart_index:]))
                resumed = harness.cli('procedure-resume',procedure_id)
                self.assertEqual(resumed['steps'][0]['operationId'],interrupted_child)
                completed = harness.wait('procedure_status',{'procedureId':procedure_id},lambda state:state['executionState']=='completed')
                self.assertEqual(completed['cursor'],3)
                self.assertFalse(completed['unresolvedOperations'])
                results = [harness.call('operation',operationId=step['operationId']) for step in completed['steps']]
                self.assertEqual(results[0]['result'],child['result'])
                self.assertTrue(all(result['executionState']=='completed' and not result['resourceClaims'] for result in results))
                self.assertTrue(all(result['result']['evidenceKind']=='simulation' for result in results))
                self.assertEqual(results[1]['result']['output']['level'],25)
                self.assertEqual(results[2]['result']['output']['value'],42)
                self.assertEqual(harness.cli('procedure-submit',request=request),completed)
                for child_request,result in zip(requests,results):
                    self.assertEqual(harness.call('invoke',request=child_request)['operationId'],result['operationId'])
                events, cursor = [], 0
                while True:
                    page = harness.cli('procedure-events',procedure_id,'--after',str(cursor),'--limit','2')
                    self.assertFalse(page['gap']); events += page['events']; cursor = page['next']
                    if cursor == page['head']:
                        break
                self.assertEqual([event['sequence'] for event in events],list(range(1,len(events)+1)))
                later = timing(delay=60000)
                future_child = harness.prepare(harness.local,'focus',namespace,'cli-future-child',later)
                future_request = envelope(namespace,'cli-future-parent',later,[future_child])
                future = harness.cli('procedure-submit',request=future_request)
                canceled = harness.cli('procedure-cancel',future['procedureId'])
                self.assertTrue(canceled['cancelRequested'])
                self.assertEqual(canceled['delivery']['status'],'no_active_child')
                self.assertEqual(harness.cli('procedure-status',future['procedureId'])['executionState'],'canceled')
                report.update(request=request,completed=completed,children=results,events=events,
                    restart={'signal':'SIGKILL','endpointStayedAlive':True,'interruptedChildId':interrupted_child,
                             'noAutomaticContinuation':True,'sameChildOnReplayAndResume':True,
                             'noReceiptPersistedAtDeath':True,'matchingRecoveryQuery':True},cancellation=canceled)
                harness.stop(); harness.snapshot([results[0],results[2]])
                report['passed'] = True
            finally:
                harness.close()

    def run_mcp(self, protocol):
        import anyio
        report = new_report('mcp-' + protocol)
        async def exercise(harness):
            namespace = harness.call('namespace',expiresUnixMs=time.time_ns() // 1_000_000 + 180000)['token']
            bounds = timing()
            requests = [harness.prepare(config,role,namespace,'mcp-child:'+str(i),bounds)
                        for i,(config,role) in enumerate(((harness.local,'fan'),(harness.compact,'inspection')))]
            request = envelope(namespace,'mcp-parent',bounds,requests)
            async with projection(protocol,harness) as probe:
                parent = await probe.call('procedure_submit',request=request)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    completed = await probe.call('procedure_status',procedureId=parent['procedureId'])
                    if completed['executionState']=='completed':
                        break
                    await anyio.sleep(.08)
                self.assertEqual(completed['executionState'],'completed',completed)
                self.assertEqual((await probe.call('procedure_submit',request=request))['procedureId'],parent['procedureId'])
                events = await probe.call('procedure_events',procedureId=parent['procedureId'],after=0,limit=100)
                self.assertFalse(events['gap']); self.assertEqual(events['next'],events['head'])
                results = [harness.call('operation',operationId=step['operationId']) for step in completed['steps']]
                self.assertEqual(results[0]['result']['output']['level'],25)
                self.assertTrue(all(result['result']['evidenceKind']=='simulation' for result in results))
                later = timing(delay=60000)
                future_child = harness.prepare(harness.local,'focus',namespace,'mcp-future-child',later)
                future_request = envelope(namespace,'mcp-future-parent',later,[future_child])
                future = await probe.call('procedure_submit',request=future_request)
                self.assertEqual(future['executionState'],'accepted')
            # EOF closes only projection; durable authority state survives.
            after_close = harness.call('procedure_status',procedureId=future['procedureId'])
            self.assertEqual(after_close['executionState'],'accepted')
            self.assertFalse(after_close['cancelRequested'])
            harness.stop(); harness.start()
            async with projection(protocol,harness) as probe:
                paused = await probe.call('procedure_status',procedureId=future['procedureId'])
                self.assertEqual(paused['executionState'],'interrupted')
                resumed = await probe.call('procedure_resume',procedureId=future['procedureId'])
                self.assertEqual(resumed['executionState'],'accepted')
                canceled = await probe.call('procedure_cancel',procedureId=future['procedureId'])
                self.assertTrue(canceled['cancelRequested'])
                self.assertEqual(canceled['delivery']['status'],'no_active_child')
                replay = await probe.call('procedure_submit',request=future_request)
                self.assertEqual(replay['procedureId'],future['procedureId']); self.assertEqual(replay['executionState'],'canceled')
                retained = await probe.call('procedure_submit',request=request)
                self.assertEqual([s['operationId'] for s in retained['steps']],[s['operationId'] for s in completed['steps']])
                for child_request,result in zip(requests,results):
                    self.assertEqual(harness.call('invoke',request=child_request)['result'],result['result'])
            report.update(request=request,completed=completed,children=results,events=events,
                projectionClose={'afterClose':after_close,'afterRestart':paused,'afterExplicitResume':resumed,'cancel':canceled})
            return results
        with tempfile.TemporaryDirectory(prefix='hms-procedure-mcp-') as temporary:
            harness = MixedDaemon(Path(temporary),report)
            try:
                harness.start(create=True)
                results = anyio.run(exercise,harness)
                harness.stop(); harness.snapshot([results[1]])
                report['passed'] = True
            finally:
                harness.close()

    def test_modern_mcp_procedure_tools_mixed_routes_replay_and_cancel(self):
        self.run_mcp(MODERN)

    @unittest.skipUnless(sdk_available(),'Installed MCP SDK 1.26.0 required only for legacy tester')
    def test_legacy_mcp_procedure_tools_mixed_routes_replay_and_cancel(self):
        self.run_mcp(LEGACY)


class ProcedurePausedRouteTests(MultiHarness):
    def test_paused_native_head_does_not_starve_focus_and_expiry_releases_claims(self):
        report = new_report('paused-native-route')
        config = installation('procedure-paused-route',compact=True)
        self.open([config],create=True)
        child = self.prepare(config,'fan',key='paused-fan')
        request = envelope(self.namespace,'paused-parent',child['intent']['timing'],[child])
        parent = self.call('procedure_submit',request=request)
        self.runtime.procedures.tick()  # Admit only; native backend has not handed off.
        accepted = self.call('procedure_status',procedureId=parent['procedureId'])
        operation_id = accepted['steps'][0]['operationId']
        self.assertIsNotNone(operation_id)
        self.assertEqual(self.call('operation',operationId=operation_id)['executionState'],'accepted')
        self.assertEqual(self.packet_count(config['adapterId']),0)
        self.reopen()
        paused = self.call('procedure_status',procedureId=parent['procedureId'])
        self.assertEqual(paused['executionState'],'interrupted')
        focus = self.invoke(self.prepare(config,'focus',key='independent-focus'))
        self.assertEqual([row['id'] for row in self.runtime.work_items(config['adapterId'],('accepted',),limit=1)], [operation_id])
        self.assertEqual([row['id'] for row in self.runtime.work_items(config['adapterId'],('accepted',),limit=1,skip_paused=True)], [focus['operationId']])
        completed = self.finish([focus])[0]
        held = self.call('operation',operationId=operation_id)
        self.assertEqual(held['executionState'],'accepted'); self.assertTrue(held['resourceClaims'])
        self.assertEqual(self.packet_count(config['adapterId']),1)
        self.advance(3100)
        expired = self.call('operation',operationId=operation_id)
        self.assertEqual(expired['executionState'],'rejected_before_dispatch')
        self.assertFalse(expired['mayHaveActed']); self.assertFalse(expired['resourceClaims'])
        self.assertEqual(self.packet_count(config['adapterId']),1)
        self.assertEqual(self.endpoints[config['adapterId']].command(4),1)
        self.assertEqual(self.endpoints[config['adapterId']].command(5),1)
        report.update(passed=True,parent=parent,paused=paused,independentCompleted=completed,
                      pausedBeforeExpiry=held,pausedAfterExpiry=expired,nativeOpFrames=1,
                      syntheticDispatchCounter=1,syntheticEffectCounter=1,
                      scope='Original synthetic time/effect-count channel, not real-clock or physical timing evidence.')


if __name__ == '__main__':
    unittest.main()
