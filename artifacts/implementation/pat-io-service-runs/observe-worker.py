"""One fixed diagnostic run with bounded read-only process/pressure sampling.

This observes known child descendants. It never signals, changes scheduling,
reads another application's command line, or alters project/worker execution.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

B = Path(__file__).resolve().parent
H = B / 'harness17'
ATTEMPT = 'attempt04-diagnostic-reserved'
A = H / 'attempts' / ATTEMPT
OUTPUT = B / 'diagnostic-worker-observations.json'
assert not OUTPUT.exists() and not A.exists()
hz = os.sysconf('SC_CLK_TCK')


def text(path, maximum=4096):
    try:
        with path.open('rb') as stream: value = stream.read(maximum + 1)
        if len(value) > maximum: return None
        return value.decode('ascii')
    except (OSError, UnicodeError): return None


def process(pid):
    body = text(Path('/proc') / str(pid) / 'stat')
    if body is None: return None
    fields = body.rsplit(')', 1)[1].split()
    return dict(pid=pid, state=fields[0], parent=int(fields[1]), minorFaults=int(fields[7]),
        majorFaults=int(fields[9]), userTicks=int(fields[11]), systemTicks=int(fields[12]),
        startTicks=int(fields[19]), residentPages=int(fields[21]))


def known_children(pid):
    body = text(Path('/proc') / str(pid) / 'task' / str(pid) / 'children')
    return [] if body is None else [int(value) for value in body.split() if value.isdecimal()]


def snapshot(parent):
    rows = []
    for child in known_children(parent):
        state = process(child)
        if state is not None: rows.append(dict(role='test-child', **state))
        for worker in known_children(child):
            # The frozen child audit permits only the exact original worker.
            state = process(worker)
            if state is not None: rows.append(dict(role='owned-worker', **state))
    return dict(elapsedSeconds=time.monotonic() - started, loadAverage=os.getloadavg(),
        pressure={name: text(Path('/proc/pressure') / name) for name in ('cpu', 'memory', 'io')}, processes=rows)


started = time.monotonic(); samples = []; errors = []
with (B / (ATTEMPT + '-launcher.log')).open('xb') as output:
    child = subprocess.Popen([sys.executable, '-B', str(H / 'run_attempt.py'), ATTEMPT, '--parent-released'],
                             cwd=B.parents[2], stdout=output, stderr=subprocess.STDOUT)
    # Original launcher owns its180s deadline and collection/recovery. This
    # observer cannot terminate it or reinterpret an observation gap as exit.
    while child.poll() is None:
        if len(samples) < 240:
            try: samples.append(snapshot(child.pid))
            except (ValueError, IndexError, OSError) as error: errors.append(type(error).__name__)
        time.sleep(1)
    code = child.wait()
value = dict(scope='Passive diagnostic sampling of one unchanged reserved-worker method; no causal conclusion from system pressure alone.',
    observedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),harness='harness17',attempt=ATTEMPT,
    parentPid=child.pid,parentExitCode=code,clockTicksPerSecond=hz,pageBytes=os.sysconf('SC_PAGE_SIZE'),
    elapsedSeconds=time.monotonic()-started,samples=samples,samplingErrors=errors,
    observerSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),deadlineChanged=False,
    schedulingChanged=False,processesSignaled=False,projectSourcesChanged=False)
wire=(json.dumps(value,indent=2)+'\n').encode();assert len(wire)<=4*1024*1024
with OUTPUT.open('xb')as output:output.write(wire)
print(json.dumps(dict(attempt=ATTEMPT,parentExitCode=code,samples=len(samples),errors=errors,elapsedSeconds=value['elapsedSeconds'])))
