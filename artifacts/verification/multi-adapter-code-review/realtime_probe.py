#!/usr/bin/env python3
"""Original diagnostic: one Python plant and two original native host fixtures.

No hardware/AVR target execution. Logs first failure without retrying admission.
"""
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
SOURCE_PINS = json.loads((BASE/'frozen-sources.json').read_text())
for pin in SOURCE_PINS:
    assert hashlib.sha256((ROOT/pin['path']).read_bytes()).hexdigest() == pin['sha256'], pin['path']
sys.path.insert(0, str(ROOT))
from hms.installations import ROLES, legacy_installation, manifest_for
from hms.journal import Context
from hms.runtime import Runtime

BINARY = ROOT / 'artifacts/verification/endpoint-scenarios-build/endpoint-scenarios-pipe'


def installation(name, compact=False):
    result = legacy_installation(compact)
    result['adapterId'] = 'review-route:' + name
    result['instances'] = {role: 'sim:review-' + name + '-' + role for role in ROLES}
    result['resources'] = {role: 'review-resource:' + name + '-' + role for role in ROLES}
    if compact:
        result['incarnationHex'] = hashlib.sha256(name.encode()).hexdigest()[:32]
    return result


def main():
    retained = json.loads((ROOT / 'artifacts/verification/endpoint-scenarios.json').read_text())
    pin = next(row for row in retained['outputs'] if row['path'].endswith('/endpoint-scenarios-pipe'))
    assert hashlib.sha256(BINARY.read_bytes()).hexdigest() == pin['sha256']
    configs = [installation('local'), installation('c1', True), installation('c2', True)]
    fixtures, sockets, runtime = [], [], None
    timings = deque(maxlen=200)
    timing_lock = threading.Lock()
    report = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'fixture': pin,
              'source_pins': SOURCE_PINS, 'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'requests': [], 'errors': [], 'scope': 'Original native host simulation; no hardware or AVR execution.'}
    with tempfile.TemporaryDirectory(prefix='hms-independent-live-multi-') as directory:
        try:
            streams = {}
            for config in configs[1:]:
                host, native = socket.socketpair()
                sockets.append(host)
                manifest, digest = manifest_for(config)
                fixtures.append(subprocess.Popen([str(BINARY), '--manifest', digest,
                    '--incarnation', config['incarnationHex'], '--firmware', json.loads(manifest)['firmwareDigest']],
                    stdin=native, stdout=native, stderr=subprocess.PIPE))
                native.close()
                streams[config['adapterId']] = host.fileno()
            owner = Context('independent-review', 'simulation:multi')
            runtime = Runtime(directory, create=True, owner=owner, installations=configs, endpoint_fds=streams)
            for route, backend in runtime.adapters.items():
                original = backend.refresh
                def timed_refresh(*args, _original=original, _route=route, **kwargs):
                    started = time.monotonic_ns()
                    error = None
                    try:
                        return _original(*args, **kwargs)
                    except Exception as exc:
                        error = getattr(exc, 'code', type(exc).__name__)
                        raise
                    finally:
                        elapsed = (time.monotonic_ns()-started)/1e6
                        with timing_lock:
                            timings.append({'route': _route, 'start_ms': started//1000000,
                                            'elapsed_ms': round(elapsed, 3), 'error': error})
                backend.refresh = timed_refresh
            runtime.start()
            runtime.request(owner, 'discover', {})
            namespace = runtime.request(owner, 'namespace', {'expiresUnixMs': time.time_ns()//1000000+30000})['token']
            for config in configs:
                for role in ROLES:
                    instance = config['instances'][role]
                    action, arguments = {'fan': ('set_level', {'level':25,'unit':'percent'}),
                        'focus': ('move_absolute', {'position':42,'unit':'um','frame':instance}),
                        'inspection': ('inspect', {'recipe':1,'partId':'review-part'})}[role]
                    now = time.time_ns()//1000000
                    phase = 'prepare'
                    started = time.monotonic_ns()
                    try:
                        request = runtime.request(owner, 'prepare', {'instanceId':instance,'actionId':action,
                            'arguments':arguments,'operationKey':instance,'replayNamespace':namespace,
                            'requiredEffect':'capability_completion','timing':{'notBeforeUnixMs':now,
                                'latestStartUnixMs':now+5000,'maxRunMs':500,'latestCompletionUnixMs':now+5500}})['request']
                        prepared = time.monotonic_ns()
                        phase = 'invoke'
                        op = runtime.request(owner, 'invoke', {'request':request})
                        invoked = time.monotonic_ns()
                        phase = 'completion'
                        deadline = time.monotonic()+6
                        while time.monotonic() < deadline:
                            state = runtime.request(owner,'operation',{'operationId':op['operationId']})
                            if state['executionState'] in {'completed','failed','canceled','rejected_before_dispatch','outcome_unknown'}:
                                if not state['resourceClaims'] or state['executionState'] != 'completed':
                                    break
                            time.sleep(.02)
                        report['requests'].append({'instance':instance,'prepare_ms':round((prepared-started)/1e6,3),
                            'invoke_ms':round((invoked-prepared)/1e6,3),'state':state})
                        if state['executionState'] != 'completed' or state['resourceClaims']:
                            raise RuntimeError('noncomplete operation')
                    except Exception as error:
                        report['errors'].append({'instance':instance,'phase':phase,
                            'code':getattr(error,'code',type(error).__name__),'text':str(error),
                            'elapsed_ms':round((time.monotonic_ns()-started)/1e6,3)})
                        raise
        except Exception as error:
            report['passed'] = False
            report['exception'] = {'type':type(error).__name__,'text':str(error)}
            if runtime is not None:
                with runtime.journal._mutex:
                    report['sampled_monotonic_ms'] = time.monotonic_ns()//1000000
                    report['route_errors'] = dict(runtime.route_errors)
                    report['ready_observations'] = [json.loads(row[0]) for row in runtime.journal._db.execute(
                        "SELECT document FROM reg_observations WHERE property='ready'")]
                    report['presence'] = [dict(row) for row in runtime.journal._db.execute('SELECT * FROM reg_presence')]
                    report['compact_states'] = [dict(row) | {'document':json.loads(row['document'])}
                        for row in runtime.journal._db.execute('SELECT * FROM ep_state')]
        else:
            report['passed'] = True
        finally:
            if runtime is not None:
                runtime.close()
            for stream in sockets:
                stream.close()
            for fixture in fixtures:
                _, error = fixture.communicate(timeout=3)
                assert fixture.returncode == 0, error
            report['refresh_timings'] = list(timings)
    path = BASE/'realtime-diagnostic.json'
    for pin in SOURCE_PINS:
        assert hashlib.sha256((ROOT/pin['path']).read_bytes()).hexdigest() == pin['sha256'], pin['path']
    report['source_pins_checked_before_and_after'] = len(SOURCE_PINS)
    path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'completed_requests':len(report['requests']),
                      'errors':report['errors'],'report':str(path.relative_to(ROOT))}))


if __name__ == '__main__':
    main()
