"""Prepared two-stage external-agent demo. Collection never generates a proposal.

Use after review with a retained runtime_probe.py transcript. This process never
imports Runtime or a model. Its only mutations are isolated planning records and
exclusive trace files. The invoking local host supplies the single-owner anchor.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
LIMITS = {}
for name, kind, limit in (('cpuSeconds', resource.RLIMIT_CPU, 15),
                         ('addressSpaceBytes', resource.RLIMIT_AS, 512 * 1024 * 1024),
                         ('fileBytes', resource.RLIMIT_FSIZE, 1024 * 1024),
                         ('openFiles', resource.RLIMIT_NOFILE, 64),
                         ('coreBytes', resource.RLIMIT_CORE, 0)):
    _soft, hard = resource.getrlimit(kind)
    actual = limit if hard == resource.RLIM_INFINITY else min(limit, hard)
    resource.setrlimit(kind, (actual, actual))
    LIMITS[name] = list(resource.getrlimit(kind))

from intent_handoff.integrity import verify
verify()
core_manifest = (ROOT / 'CORE_SOURCE.sha256').read_bytes()
if hashlib.sha256(core_manifest).hexdigest() != '616364d2a564830b954a483c568fe4853c129c996d2d67939b1732492849dad6':
    raise ValueError('reviewed core manifest changed')
for line in core_manifest.decode('ascii').splitlines():
    expected, relative = line.split('  ', 1)
    if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
        raise ValueError('reviewed core source changed')
sys.path.insert(0, str(ROOT / 'dependencies'))
from hms.contracts import canonical, parse_json
from intent_handoff.contracts import checked_request, closed, discovery, require
from intent_handoff.consumer import Dispatcher
from intent_handoff.store import IntentStore


def read_bounded(path, limit):
    if not path.is_file():
        raise ValueError('a regular retained input file is required')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('retained input exceeds declared limit')
    return raw


def write(path, value):
    body = canonical(value)
    with path.open('xb') as stream:
        stream.write(body)


def pins():
    paths = {Path(__file__).resolve(), ROOT / 'DEPENDENCIES.sha256', ROOT / 'CORE_SOURCE.sha256'}
    paths.update((ROOT / 'intent_handoff').glob('*.py'))
    for line in (ROOT / 'DEPENDENCIES.sha256').read_text().splitlines():
        paths.add(ROOT / line.split('  ', 1)[1])
    result = {}
    for path in sorted(paths):
        raw = path.read_bytes()
        result[str(path.relative_to(ROOT))] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return result


def configuration(path):
    value = parse_json(read_bounded(path, 4096))
    closed(value, {'profile', 'owner', 'storeId', 'capacity', 'applicationId'})
    require(value['profile'] == 'hms.intent-handoff-demo-config/0.1')
    return value


def prepare(args, attempt):
    prompt_wire = read_bounded(args.prompt, 8192)
    prompt = prompt_wire.decode('utf-8')
    discovery_wire = read_bounded(args.discovery, 16384)
    observations = parse_json(discovery_wire)
    discovery(observations)
    require(bool(observations), 'DISCOVERY_REQUIRED')
    config = dict(profile='hms.intent-handoff-demo-config/0.1', owner=args.owner,
        storeId='intent-demo:' + uuid.uuid4().hex, capacity={'maxRecords': 16, 'maxBytes': 262144},
        applicationId=args.application)
    request = dict(profile='hms.application-intent/0.1', applicationId=args.application,
        operationKey='intent:initial', expectedRevision=0, prompt=prompt)
    checked_request('intent_put', request)
    with (attempt / 'prompt.utf8').open('xb') as stream:
        stream.write(prompt_wire)
    with (attempt / 'discovery-input.json').open('xb') as stream:
        stream.write(discovery_wire)
    write(attempt / 'discovery.json', observations)
    write(attempt / 'configuration.json', config)
    args.state_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    write(args.state_dir / 'configuration.json', config)
    store = IntentStore(args.state_dir / 'intent.db', owner=config['owner'], store_id=config['storeId'],
                        capacity=config['capacity'], create=True)
    try:
        dispatcher = Dispatcher(store, principal=config['owner'])
        write(attempt / 'request.json', {'method': 'intent_put', 'params': request})
        reply = dispatcher.request('intent_put', request)
        write(attempt / 'reply.json', reply)
        require(reply['ok'], 'DEMO_REQUEST_REFUSED')
        status = dispatcher.request('intent_get', {'applicationId': args.application})
        write(attempt / 'status.json', status)
        require(status['ok'] and status['result']['state'] == 'awaiting_proposal', 'DEMO_STATE')
        require(status['result']['intent']['prompt'].encode('utf-8') == prompt_wire, 'DEMO_PROMPT_CHANGED')
    finally:
        store.close()
    return dict(state='awaiting_proposal', handoffDigest=reply['result']['handoffDigest'],
        stateDirectory=str(args.state_dir.resolve()),
        planningInvocations=0, proposalGenerated=False, qualification='unavailable',
        promptSha256=hashlib.sha256(prompt_wire).hexdigest(),
        discoveryInputSha256=hashlib.sha256(discovery_wire).hexdigest())


def submit(args, attempt):
    config = configuration(args.prepared / 'configuration.json')
    live_config = configuration(args.state_dir / 'configuration.json')
    require(canonical(config) == canonical(live_config), 'DEMO_CONFIGURATION_CHANGED')
    preparation = parse_json(read_bounded(args.prepared / 'receipt.json', 65536))
    require(preparation['successful'] is True and preparation['mode'] == 'prepare' and
            preparation['result']['stateDirectory'] == str(args.state_dir.resolve()), 'DEMO_PREPARATION_CHANGED')
    observations = parse_json(read_bounded(args.prepared / 'discovery.json', 16384))
    discovery(observations)
    supplied_wire = read_bounded(args.proposal, 32768)
    request = parse_json(supplied_wire)
    checked_request('proposal_put', request)  # Original numeric types before canonicalization.
    require(request['plannerAttribution']['kind'] == 'external-agent', 'EXTERNAL_AGENT_ATTRIBUTION_REQUIRED')
    require(request['applicationId'] == config['applicationId'], 'DEMO_APPLICATION_CHANGED')
    require(canonical(request['discovery']) == canonical(observations), 'DEMO_DISCOVERY_CHANGED')
    with (attempt / 'proposal-input.json').open('xb') as stream:
        stream.write(supplied_wire)
    write(attempt / 'configuration.json', config)
    store = IntentStore(args.state_dir / 'intent.db', owner=config['owner'], store_id=config['storeId'],
                        capacity=config['capacity'])
    try:
        dispatcher = Dispatcher(store, principal=config['owner'])
        before = dispatcher.request('intent_get', {'applicationId': config['applicationId']})
        write(attempt / 'status-before.json', before)
        write(attempt / 'request.json', {'method': 'proposal_put', 'params': request})
        reply = dispatcher.request('proposal_put', request)
        write(attempt / 'reply.json', reply)
        require(reply['ok'], 'DEMO_REQUEST_REFUSED')
        after = dispatcher.request('intent_get', {'applicationId': config['applicationId']})
        write(attempt / 'status-after.json', after)
        require(after['ok'], 'DEMO_STATE')
        # Exact supplied request replay confirms durable identity; it does not
        # execute the proposed PAT and is not an application-context fast path.
        replay = dispatcher.request('proposal_put', request)
        write(attempt / 'replay.json', replay)
        require(canonical(reply) == canonical(replay), 'DEMO_REPLAY_CHANGED')
        require(after['result']['qualification']['state'] == 'unavailable', 'DEMO_STATE')
    finally:
        store.close()
    return dict(state=reply['result']['state'], proposalDigest=reply['result']['proposalDigest'],
        proposalInputSha256=hashlib.sha256(supplied_wire).hexdigest(),
        attribution='external-agent, unverified identifiers; no Harness model invocation',
        generatedByCommand=False, qualification='unavailable', exactProposalReplay=True)


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_subparsers(dest='mode', required=True)
    collect = modes.add_parser('prepare')
    collect.add_argument('--attempt', type=Path, required=True)
    collect.add_argument('--state-dir', type=Path, required=True)
    collect.add_argument('--prompt', type=Path, required=True)
    collect.add_argument('--discovery', type=Path, required=True)
    collect.add_argument('--owner', required=True)
    collect.add_argument('--application', required=True)
    commit = modes.add_parser('submit')
    commit.add_argument('--attempt', type=Path, required=True)
    commit.add_argument('--state-dir', type=Path, required=True)
    commit.add_argument('--prepared', type=Path, required=True)
    commit.add_argument('--proposal', type=Path, required=True)
    args = parser.parse_args()
    args.attempt.mkdir(mode=0o700, parents=False, exist_ok=False)
    before = pins()
    write(args.attempt / 'source-pins-before.json', before)
    interpreter = Path(sys.executable).resolve()
    interpreter_before = hashlib.sha256(interpreter.read_bytes()).hexdigest()
    started = time.monotonic()
    result, failure = None, None
    try:
        result = prepare(args, args.attempt) if args.mode == 'prepare' else submit(args, args.attempt)
    except Exception as error:
        failure = dict(type=type(error).__name__, code=getattr(error, 'code', 'DEMO_FAILURE'))
    elapsed = time.monotonic() - started
    after = pins()
    write(args.attempt / 'source-pins-after.json', after)
    interpreter_after = hashlib.sha256(interpreter.read_bytes()).hexdigest()
    stable = before == after and interpreter_before == interpreter_after
    receipt = dict(profile='hms.intent-handoff-demo-receipt/0.1', mode=args.mode,
        successful=failure is None and stable, failure=failure, result=result,
        monotonicElapsedSeconds=elapsed, sourcePinsUnchanged=before == after,
        interpreter=dict(path=str(interpreter), beforeSha256=interpreter_before,
                         afterSha256=interpreter_after, unchanged=interpreter_before == interpreter_after),
        enforcedSoftHardLimits=LIMITS,
        scope='planning records only; no Runtime/model/qualification import or application execution',
        limitations=['external-agent proposal provenance is not attested',
                     'logical caps and per-process limits are not aggregate protected capacity'])
    write(args.attempt / 'receipt.json', receipt)
    print(json.dumps(receipt))
    return 0 if receipt['successful'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
