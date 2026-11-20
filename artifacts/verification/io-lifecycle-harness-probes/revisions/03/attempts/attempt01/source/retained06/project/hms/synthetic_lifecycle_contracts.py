"""Closed original synthetic lifecycle installation and immutable management identity."""
import hashlib

from .contracts import SAFE_INTEGER, canonical, identifier, parse_json
from .demo import object_schema, type_bundle
from .registry import exact, validate_type_bundle
from .resource_topology import generation_change_claims
from .synthetic_io_installation import normalize_installation, require

PROFILE = 'hms.synthetic-lifecycle-installation/1'
DRIVER = 'sqlite-finite-io-lifecycle/1'
ROOT_PROFILE = 'hms.lifecycle-roots/0.1'
STORAGE_PROFILE = 'hms.registry/lifecycle-roots/0.1'


def digest(domain, value):
    return 'sha256:' + hashlib.sha256(domain.encode() + b'\0' + canonical(value)).hexdigest()


def snapshot(value):
    if type(value) is bytes:
        value = parse_json(value)
    canonical(value)  # Bound before traversal, without normalizing scalar types.
    pending = [value]
    while pending:
        item = pending.pop()
        require(type(item) is not float, 'LIFECYCLE_EXACT_TYPES_REQUIRED')
        if type(item) is dict:
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)
    return parse_json(canonical(value))


def normalize(value):
    value = snapshot(value)
    exact(value, {'profile', 'io', 'management'})
    require(value['profile'] == PROFILE, 'LIFECYCLE_INSTALLATION_PROFILE')
    io = normalize_installation(value['io'])
    management = value['management']
    require(type(management) is list and 1 <= len(management) <= 16, 'LIFECYCLE_MANAGEMENT_INVENTORY')
    ordinary = {row['instanceId'] for row in io['handlers']}
    routes, instances = set(io['routes']['adapters']), set(ordinary)
    seen_routes = set()
    for entry in management:
        exact(entry, {'instanceId', 'adapterId', 'actions'})
        instance, adapter = identifier(entry['instanceId']), identifier(entry['adapterId'])
        require(instance not in instances and adapter not in routes, 'LIFECYCLE_MANAGEMENT_SEPARATION')
        instances.add(instance); seen_routes.add(adapter)
        actions = entry['actions']
        require(type(actions) is dict and 1 <= len(actions) <= 8, 'LIFECYCLE_ACTION_INVENTORY')
        for action, target in actions.items():
            identifier(action); identifier(target)
            require(len(action) <= 64, 'LIFECYCLE_ACTION_INVENTORY')
            generation_change_claims(io['topology'], target)  # Target kind and full sibling cap.
    require(len(routes | seen_routes) <= 16 and len(instances) <= 128, 'LIFECYCLE_INSTALLATION_LIMIT')
    value['io'] = io
    value['management'] = sorted(management, key=lambda row: row['instanceId'])
    return value


def installation_digest(value):
    return digest('HMS-SYNTHETIC-LIFECYCLE-INSTALLATION-v1', value)


def action_for(document, instance, action):
    entry = next((item for item in document['management'] if item['instanceId'] == instance), None)
    require(entry is not None and action in entry['actions'], 'LIFECYCLE_HANDLER_UNSUPPORTED')
    return entry, entry['actions'][action]


def root_id(instance, action):
    return 'lifecycle-root:' + hashlib.sha256(canonical([instance, action])).hexdigest()


def arguments(value):
    value = snapshot(value)
    exact(value, {'expectedGeneration', 'newGeneration', 'expectedRevision'})
    identifier(value['expectedGeneration']); identifier(value['newGeneration'])
    require(value['expectedGeneration'] != value['newGeneration'], 'RESOURCE_GENERATION_REUSED')
    require(type(value['expectedRevision']) is int and 1 <= value['expectedRevision'] < SAFE_INTEGER,
            'LIFECYCLE_REVISION_LIMIT')
    return value


def definitions(document):
    result = {}
    envelope = object_schema({
        'expectedGeneration': {'type': 'string', 'minLength': 1, 'maxLength': 128},
        'newGeneration': {'type': 'string', 'minLength': 1, 'maxLength': 128},
        'expectedRevision': {'type': 'integer', 'minimum': 1, 'maximum': SAFE_INTEGER - 1}})
    for entry in document['management']:
        instance = entry['instanceId']; bundle = None; resources = {}
        for action in sorted(entry['actions']):
            role = 'lifecycle:' + action
            part = type_bundle('lifecycle-' + hashlib.sha256(instance.encode()).hexdigest()[:16], action,
                envelope, {'type': 'integer', 'minimum': 0, 'maximum': SAFE_INTEGER},
                unit='1', effect='advance_generation', resource=role)
            part['execution']['actions'][action]['preconditions'] = []
            part['execution']['capabilities'] = ['sim:finite-generation-change']
            part['td']['description'] = 'Original synthetic generation effect; no OS or physical service restart.'
            if bundle is None:
                bundle = part
            else:
                bundle['execution']['actions'].update(part['execution']['actions'])
                bundle['td']['actions'].update(part['td']['actions'])
            resources[role] = root_id(instance, action)
        type_digest = validate_type_bundle(bundle)
        identity = digest('HMS-LIFECYCLE-MANAGEMENT-BINDING-v1',
            {'installationDigest': installation_digest(document), 'instanceId': instance, 'typeDigest': type_digest})
        binding = {'profile': 'hms.binding/0.1', 'instanceId': instance,
            'generation': 'lifecycle-binding:' + identity[7:], 'controlGeneration': 'lifecycle-control:' + identity[7:],
            'typeDigest': type_digest, 'calibrationRevision': 'synthetic:lifecycle:1', 'mode': 'simulation',
            'adapterId': entry['adapterId'], 'resourceMap': resources,
            'argumentSchemas': {action: envelope for action in entry['actions']}}
        result[instance] = {'type': bundle, 'binding': binding}
    return snapshot(result)
