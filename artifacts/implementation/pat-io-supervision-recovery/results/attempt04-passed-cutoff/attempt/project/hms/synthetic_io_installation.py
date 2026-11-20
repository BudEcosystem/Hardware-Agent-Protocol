"""Closed installation for original finite synthetic GPIO/PWM handlers.

This module describes one shared board. It neither imports a provider nor opens
devices. A driver digest pins the installed source closure, not physical trust.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from .contracts import canonical, identifier, parse_json
from .demo import object_schema, type_bundle
from .journal import JournalError
from .registry import exact, validate_type_bundle
from .resource_catalog import _routes, control_generation
from .resource_topology import binding_proof, parse_generations, parse_topology

PROFILE = 'hms.synthetic-io-installation/1'
DRIVER = 'sqlite-finite-io/1'
PRIMITIVES = {'gpio_pulse': 'gpio_access', 'pwm_burst': 'pwm_access'}
MAX_DURATION_MS = 5000


def require(condition, code):
    if not condition:
        raise JournalError(code)


def implementation_digest():
    root = Path(__file__).resolve().parent
    # Deliberately conservative project closure, including inherited Runtime,
    # parsers, schema data and unused project modules. External Python/validator
    # environment is separately pinned by test receipts; this is not attestation.
    files = sorted([*root.glob('*.py'),*root.glob('_vendor/**/*.py'),*root.parent.glob('schemas/*.json'),
                    root.parent/'research/protocols/wot-artifacts/td-schema-1.1.json',
                    root.parent/'protocol/endpoint/scenario-manifest.json'])
    pins = [{'path': str(path.relative_to(root.parent)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in files]
    return 'sha256:' + hashlib.sha256(b'HMS-SYNTHETIC-IO-DRIVER-v1\0' + canonical(pins)).hexdigest()


def normalize_installation(value):
    raw = parse_json(value) if type(value) is bytes else value
    encoded = canonical(raw)  # Bound the original tree before walking or copying it.
    pending = [raw]
    while pending:
        item = pending.pop()
        require(type(item) is not float, 'IO_INTEGER_CONFIGURATION_REQUIRED')
        if type(item) is dict:
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)
    value = parse_json(encoded)
    exact(value, {'profile', 'driver', 'driverDigest', 'boardId', 'topology', 'initialGenerations', 'routes', 'handlers'})
    require(value['profile'] == PROFILE and value['driver'] == DRIVER, 'IO_INSTALLATION_PROFILE')
    require(value['driverDigest'] == implementation_digest(), 'IO_DRIVER_CHANGED')
    document = parse_topology(value['topology'])
    require(document['deployment'].startswith('simulation:'), 'IO_SIMULATION_DEPLOYMENT_REQUIRED')
    generations = parse_generations(document, value['initialGenerations'])
    require(generations['revision'] == 1, 'IO_INITIAL_GENERATION_REVISION')
    board = identifier(value['boardId'])
    require([key for key, node in document['nodes'].items() if node['kind'] == 'board'] == [board], 'IO_BOARD_INVENTORY')
    routes = _routes(value['routes'], document)
    handlers = value['handlers']
    require(type(handlers) is list and 1 <= len(handlers) <= 128, 'IO_HANDLER_INVENTORY')
    expected = {(row['instanceId'], row['actionId']): row for row in document['consumers']}
    seen = set()
    descendants = {board}
    pending = [board]
    while pending:
        for child in document['nodes'][pending.pop()]['contains']:
            if child not in descendants:
                descendants.add(child); pending.append(child)
    for handler in handlers:
        exact(handler, {'instanceId', 'actionId', 'primitive'})
        key = (identifier(handler['instanceId']), identifier(handler['actionId']))
        require(len(key[1]) <= 64, 'IO_ACTION_IDENTIFIER_LIMIT')
        require(key in expected and key not in seen, 'IO_HANDLER_CLOSURE')
        seen.add(key)
        consumer = expected[key]
        require(type(handler['primitive']) is str and handler['primitive'] in PRIMITIVES and
                len(consumer['rootAliases']) == 1, 'IO_HANDLER_UNSUPPORTED')
        access = document['nodes'][document['aliases'][consumer['rootAliases'][0]]['node']]
        require(access['kind'] == PRIMITIVES[handler['primitive']], 'IO_HANDLER_TYPE_MISMATCH')
        if access['kind'] == 'gpio_access':
            pin = access['properties']['pin']; touched = {pin}
        else:
            channel = access['properties']['channel']; channel_node = document['nodes'][channel]
            pin, timer = channel_node['properties']['pin'], channel_node['properties']['timer']
            touched = {pin, timer, channel}
            props = document['nodes'][timer]['properties']
            require(props['resolutionBits'] == 8 and 100 <= props['minFrequencyHz'] <= props['maxFrequencyHz'] <= 10000,
                    'IO_PWM_ENVELOPE_UNSUPPORTED')
        require(touched <= descendants, 'IO_FOOTPRINT_OUTSIDE_BOARD')
        electrical = document['nodes'][pin]['properties']['electrical']
        mode = 'push_pull_output' if access['kind'] == 'gpio_access' else 'pwm_output'
        require(electrical['evidenceMode'] == 'simulation' and mode in electrical['modes'] and
                electrical['idleMode'] == 'high_impedance', 'IO_ELECTRICAL_MODE_UNSUPPORTED')
    require(seen == set(expected), 'IO_HANDLER_CLOSURE')
    return value | {'topology': document, 'initialGenerations': generations, 'routes': routes,
                    'handlers': sorted(handlers, key=lambda item: (item['instanceId'], item['actionId']))}


def installation_digest(document):
    return 'sha256:' + hashlib.sha256(b'HMS-SYNTHETIC-IO-INSTALLATION-v1\0' + canonical(document)).hexdigest()


def handler_details(document, instance, action):
    row = next((item for item in document['handlers'] if item['instanceId'] == instance and item['actionId'] == action), None)
    require(row is not None, 'IO_HANDLER_UNSUPPORTED')
    topology = document['topology']
    consumer = next(item for item in topology['consumers'] if item['instanceId'] == instance and item['actionId'] == action)
    root = consumer['rootAliases'][0]
    access = topology['nodes'][topology['aliases'][root]['node']]
    details = {'primitive': row['primitive'], 'root': root}
    if row['primitive'] == 'gpio_pulse':
        details['pin'] = access['properties']['pin']
    else:
        details['channel'] = access['properties']['channel']
        channel = topology['nodes'][details['channel']]['properties']
        details.update(pin=channel['pin'], timer=channel['timer'])
        details['timerEnvelope'] = copy.deepcopy(topology['nodes'][channel['timer']]['properties'])
    proof = binding_proof(topology, document['initialGenerations'], instance)
    details['claims'] = proof['expandedClaims'][action]
    return details


def argument_schema(details):
    properties = {'durationMs': {'type': 'integer', 'minimum': 1, 'maximum': MAX_DURATION_MS}}
    if details['primitive'] == 'gpio_pulse':
        properties['level'] = {'type': 'integer', 'minimum': 0, 'maximum': 1}
    else:
        timer = details['timerEnvelope']
        properties.update(frequencyHz={'type': 'integer', 'minimum': timer['minFrequencyHz'], 'maximum': timer['maxFrequencyHz']},
                          dutyPermille={'type': 'integer', 'minimum': 0, 'maximum': 1000},
                          resolutionBits={'type': 'integer', 'const': timer['resolutionBits']})
    return object_schema(properties)


def definitions(document):
    """Return original I/O type bundles and proof-derived exact bindings."""
    result = {}
    instances = sorted({row['instanceId'] for row in document['handlers']})
    for instance in instances:
        bundle = None; resources = {}
        for row in (item for item in document['handlers'] if item['instanceId'] == instance):
            action = row['actionId']; detail = handler_details(document, instance, action)
            role = 'io-root:' + action
            part = type_bundle('finite-io-' + hashlib.sha256(instance.encode()).hexdigest()[:16], action,
                argument_schema(detail), {'type': 'integer', 'minimum': 0, 'maximum': 9007199254740991},
                unit='1', effect=detail['primitive'], resource=role)
            part['execution']['actions'][action]['preconditions'] = []
            part['execution']['capabilities'] = ['sim:finite-gpio-pwm']
            part['td']['description'] = 'Original finite synthetic I/O; value counts activations, not measured electrical state.'
            if bundle is None:
                bundle = part
            else:
                bundle['execution']['actions'].update(part['execution']['actions'])
                bundle['td']['actions'].update(part['td']['actions'])
            resources[role] = detail['root']
        digest = validate_type_bundle(bundle)
        proof = binding_proof(document['topology'], document['initialGenerations'], instance)
        adapter = next(key for key, values in document['routes']['adapters'].items() if instance in values)
        binding = {'profile': 'hms.binding/0.1', 'instanceId': instance, 'generation': proof['bindingGeneration'],
            'typeDigest': digest, 'calibrationRevision': 'synthetic:finite-io:1', 'controlGeneration': control_generation(proof),
            'mode': 'simulation', 'adapterId': adapter, 'resourceMap': resources,
            'argumentSchemas': {key: copy.deepcopy(item['inputSchema']) for key, item in bundle['execution']['actions'].items()}}
        result[instance] = {'type': bundle, 'binding': binding, 'proof': proof}
    return result
