"""Closed installation for original finite synthetic GPIO/PWM handlers.

This module describes one shared board. It neither imports a provider nor opens
devices. A driver digest pins the installed source closure, not physical trust.
"""
from __future__ import annotations

import copy
from collections import OrderedDict
import threading
from types import FunctionType
import hashlib
from pathlib import Path

from . import contracts as _contracts, resource_topology as _topology, resource_catalog as _catalog, registry as _registry
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
    current_source = implementation_digest()  # Never memoize the current source check.
    require(value['driverDigest'] == current_source, 'IO_DRIVER_CHANGED')
    cached = _cached_normalization(encoded, current_source)
    if cached is not None:
        return _thaw_normalization(cached)
    result = _normalize_validated(value)
    _remember_normalization(encoded, current_source, result)
    return result


def _normalize_validated(value):
    # Original pure semantic validation, after the unchanged bounded/type/profile
    # and fresh source checks. This path remains the fallback for changed helpers.
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


# Only exact already-validated immutable data is retained. Every caller still
# bounds/encodes its original input, rejects floats, detaches/parses it, checks
# the closed profile and recomputes the installed source identity before lookup.
# Eight keys retain at most512KiB plus their bounded frozen normalized trees.
# This is not an RSS limit, authority cache, source attestation or disk quota.
_NORMALIZATION_LIMIT = 8
_NORMALIZATION_KEY_LIMIT = 8 * 65536
_NORMALIZATION_MEMO = OrderedDict()
_NORMALIZATION_KEY_BYTES = 0
_NORMALIZATION_LOCK = threading.Lock()


def _freeze_normalization(value, depth=0):
    if depth > 32:
        return None
    kind = type(value)
    if kind is dict:
        if len(value)>16384 or not all(type(key)is str for key in value):return None
        rows=tuple((key,_freeze_normalization(child,depth+1))for key,child in value.items())
        return None if any(child is None for _,child in rows) else ('dict',rows)
    if kind is list:
        if len(value)>16384:return None
        rows=tuple(_freeze_normalization(child,depth+1)for child in value)
        return None if any(child is None for child in rows) else ('list',rows)
    if kind in (str,int,bool,float,type(None)):
        return ('scalar',kind,value)
    if kind in (set,frozenset) and len(value)<=16384 and all(type(item)is str for item in value):
        return ('set',kind,frozenset(value))
    return None


def _same_normalization_config(value, frozen):
    if frozen is None:return False
    if frozen[0]=='dict':
        if type(value)is not dict or len(value)!=len(frozen[1]) or not all(type(key)is str for key in value):return False
        return all(key in value and _same_normalization_config(value[key],child)for key,child in frozen[1])
    if frozen[0]=='list':
        return type(value)is list and len(value)==len(frozen[1]) and all(_same_normalization_config(a,b)for a,b in zip(value,frozen[1]))
    if frozen[0]=='set':
        return type(value)is frozen[1] and all(type(item)is str for item in value) and frozenset(value)==frozen[2]
    return type(value)is frozen[1] and value==frozen[2]


def _thaw_normalization(frozen):
    if frozen[0]=='dict':return {key:_thaw_normalization(child)for key,child in frozen[1]}
    if frozen[0]=='list':return [_thaw_normalization(child)for child in frozen[1]]
    # Accepted normalization results contain only JSON scalars, never sets.
    assert frozen[0]=='scalar'
    return frozen[2]


def _function_anchor(function):
    if type(function)is not FunctionType:return None
    cells=tuple(cell.cell_contents for cell in function.__closure__ or ())
    children=tuple((child,child.__code__ if type(child)is FunctionType else None)for child in cells)
    return (function,function.__code__,function.__defaults__,function.__kwdefaults__,children)


def _same_normalization_function(function, anchor):
    if anchor is None or function is not anchor[0] or type(function)is not FunctionType:return False
    if function.__code__ is not anchor[1] or function.__defaults__ is not anchor[2] or function.__kwdefaults__ is not anchor[3]:return False
    cells=function.__closure__ or ()
    if len(cells)!=len(anchor[4]):return False
    for cell,(expected,code) in zip(cells,anchor[4]):
        actual=cell.cell_contents
        if actual is not expected or code is not None and (type(actual)is not FunctionType or actual.__code__ is not code):return False
    return True


def _normalization_allowed(source):
    if source != _NORMALIZATION_IMPORTED_SOURCE:return False
    for namespace,name,anchor in _NORMALIZATION_FUNCTIONS:
        if not _same_normalization_function(namespace.get(name),anchor):return False
    for namespace,name,frozen in _NORMALIZATION_CONSTANTS:
        if not _same_normalization_config(namespace.get(name),frozen):return False
    for profile,validator,schema,method,type_checker,keywords,format_checker in _NORMALIZATION_VALIDATORS:
        if _topology._VALIDATORS.get(profile) is not validator:return False
        if not _same_normalization_config(validator.schema,schema):return False
        cls=type(validator)
        if not _same_normalization_function(cls.iter_errors,method) or cls.TYPE_CHECKER is not type_checker or validator.format_checker is not format_checker:return False
        current=cls.VALIDATORS
        if type(current)is not dict or len(current)!=len(keywords) or not all(type(key)is str for key in current):return False
        if any(not _same_normalization_function(current.get(key),anchor)for key,anchor in keywords):return False
    return True


def _cached_normalization(encoded, source):
    global _NORMALIZATION_KEY_BYTES
    with _NORMALIZATION_LOCK:
        if not _normalization_allowed(source):
            _NORMALIZATION_MEMO.clear();_NORMALIZATION_KEY_BYTES=0
            return None
        frozen=_NORMALIZATION_MEMO.get(encoded)
        if frozen is not None:_NORMALIZATION_MEMO.move_to_end(encoded)
        return frozen


def _remember_normalization(encoded, source, value):
    global _NORMALIZATION_KEY_BYTES
    with _NORMALIZATION_LOCK:
        if not _normalization_allowed(source):
            _NORMALIZATION_MEMO.clear();_NORMALIZATION_KEY_BYTES=0
            return
        frozen=_freeze_normalization(value)
        if frozen is None:return
        if encoded in _NORMALIZATION_MEMO:
            _NORMALIZATION_MEMO.move_to_end(encoded)
            return
        while _NORMALIZATION_MEMO and (len(_NORMALIZATION_MEMO)>=_NORMALIZATION_LIMIT or
                _NORMALIZATION_KEY_BYTES+len(encoded)>_NORMALIZATION_KEY_LIMIT):
            old,_=_NORMALIZATION_MEMO.popitem(last=False);_NORMALIZATION_KEY_BYTES-=len(old)
        if len(encoded)<=_NORMALIZATION_KEY_LIMIT:
            _NORMALIZATION_MEMO[encoded]=frozen;_NORMALIZATION_KEY_BYTES+=len(encoded)


# Imported code is trusted; these conservative guards disable reuse when selected
# validation dependencies change. They are not complete Python-process attestation.
# In-place mutation of private validator machinery retains the original fallback
# semantics; runtime configuration is installed through explicit source/schema
# versions and validator replacement, not through a public mutation API.
_NORMALIZATION_FUNCTIONS = tuple((namespace,name,_function_anchor(value))
    for namespace in (globals(),vars(_topology),vars(_catalog),vars(_registry),vars(_contracts))
    for name,value in tuple(namespace.items()) if type(value)is FunctionType)
_NORMALIZATION_CONSTANTS = tuple((namespace,name,_freeze_normalization(namespace[name]))for namespace,names in (
    (globals(),('PROFILE','DRIVER','PRIMITIVES','MAX_DURATION_MS','_NORMALIZATION_LIMIT','_NORMALIZATION_KEY_LIMIT')),
    (vars(_topology),('PROFILE','GENERATION_PROFILE','PROOF_PROFILE','MAX_DEPTH','MAX_CLAIMS','_PHYSICAL','_ACCESS')),
    (vars(_contracts),('MAX_BYTES','MAX_DEPTH','MAX_NODES','SAFE_INTEGER')))
    for name in names)
_NORMALIZATION_VALIDATORS = tuple((profile,validator,_freeze_normalization(validator.schema),
    _function_anchor(type(validator).iter_errors),type(validator).TYPE_CHECKER,
    tuple((key,_function_anchor(function))for key,function in type(validator).VALIDATORS.items()),validator.format_checker)
    for profile in (_topology.PROFILE,_topology.GENERATION_PROFILE)
    for validator in (_topology._VALIDATORS[profile],))
_NORMALIZATION_IMPORTED_SOURCE = implementation_digest()
