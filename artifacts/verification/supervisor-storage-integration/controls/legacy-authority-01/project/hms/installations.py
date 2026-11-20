"""Trusted installation descriptors for the two original simulation drivers.

Descriptions do not load code. Only these installed, versioned driver profiles
are recognized. Files, commands, network URLs and credentials are not config.
"""
import copy
import hashlib
import json
from pathlib import Path
import re

from .contracts import canonical, identifier
from .demo import definitions
from .journal import JournalError

PROFILE = 'hms.adapter-installation/1'
ROLES = ('fan', 'focus', 'inspection')
BASE_INSTANCES = dict(zip(ROLES, ('sim:home-fan', 'sim:microscope', 'sim:inspection-cell')))
RESOURCE_ROLES = dict(zip(ROLES, ('fan-control', 'focus-zone', 'cell-zone')))
LEGACY_LOCAL = 'simulator:local'
LEGACY_COMPACT = 'endpoint:compact-simulation'
TEMPLATE_DIGEST = 'f82db3e3066e987b7dbb702396a434d00cd1a7cec5af29f25a17791fc2219c4e'
TEMPLATE = Path(__file__).resolve().parents[1] / 'protocol/endpoint/scenario-manifest.json'


def legacy_installation(compact=False):
    result = {'profile': PROFILE, 'adapterId': LEGACY_COMPACT if compact else LEGACY_LOCAL,
              'driver': 'compact-simulation' if compact else 'sqlite-simulation',
              'instances': dict(BASE_INSTANCES),
              'resources': {role: BASE_INSTANCES[role] + ':' + RESOURCE_ROLES[role] for role in ROLES}}
    if compact:
        result['incarnationHex'] = '7a402b2aced8a97c6b77261321dff098'
    return result


def normalize_installations(values):
    if type(values) is not list or not 1 <= len(values) <= 16:
        raise JournalError('INVALID_INSTALLATIONS')
    # Snapshot caller-owned containers before checking configuration identity.
    data = canonical(values)
    if len(data) > 65536:
        raise JournalError('INSTALLATIONS_TOO_LARGE')
    values = json.loads(data)
    adapters, instances, incarnations = set(), set(), set()
    for value in values:
        if type(value) is not dict or value.get('profile') != PROFILE:
            raise JournalError('INVALID_INSTALLATION_PROFILE')
        driver = value.get('driver')
        if driver not in {'sqlite-simulation', 'compact-simulation'}:
            raise JournalError('UNSUPPORTED_ADAPTER_DRIVER')
        expected = {'profile', 'adapterId', 'driver', 'instances', 'resources'}
        if driver == 'compact-simulation':
            expected.add('incarnationHex')
        if set(value) != expected:
            raise JournalError('INVALID_INSTALLATION_FIELDS')
        adapter = identifier(value['adapterId'])
        if adapter in adapters:
            raise JournalError('DUPLICATE_ADAPTER_INSTALLATION')
        adapters.add(adapter)
        for field in ('instances', 'resources'):
            if type(value[field]) is not dict or set(value[field]) != set(ROLES):
                raise JournalError('INVALID_INSTALLATION_MAP')
            for item in value[field].values():
                identifier(item)
        for instance in value['instances'].values():
            if instance in instances:
                raise JournalError('DUPLICATE_INSTALLED_INSTANCE')
            instances.add(instance)
        if len(value['instances']['focus']) > 64:
            raise JournalError('INVALID_INSTALLED_FRAME')
        if driver == 'compact-simulation':
            incarnation = value['incarnationHex']
            if type(incarnation) is not str or re.fullmatch('[0-9a-f]{32}', incarnation) is None:
                raise JournalError('INVALID_INSTALLED_INCARNATION')
            if incarnation in incarnations:
                raise JournalError('DUPLICATE_INSTALLED_INCARNATION')
            incarnations.add(incarnation)
    return sorted(values, key=lambda item: item['adapterId'])


def definitions_for(installation):
    result = []
    for role, (old, action, original) in zip(ROLES, definitions()):
        instance = installation['instances'][role]
        document = copy.deepcopy(original)
        if instance != old:
            # Frames belong to this installed synthetic instance. Capability
            # search still identifies the original handler's family.
            def rename(value):
                if type(value) is str:
                    return instance if value == old else value
                if type(value) is list:
                    return [rename(item) for item in value]
                if type(value) is dict:
                    return {key: rename(item) for key, item in value.items()}
                return value
            document = rename(document)
            document['execution']['capabilities'] = list(original['execution']['capabilities'])
            document['td']['id'] = 'urn:bud:hms:simulation:' + hashlib.sha256(instance.encode()).hexdigest()
        result.append((instance, action, document))
    return result


def resource_map(installation, instance):
    for role in ROLES:
        if installation['instances'][role] == instance:
            return {RESOURCE_ROLES[role]: installation['resources'][role]}
    raise JournalError('ADAPTER_INSTALLATION_UNSUPPORTED')


def manifest_for(installation):
    """Return the exact per-endpoint manifest bytes/digest for the C fixture.

    The fixture's existing identity options must be set to this manifest and
    incarnation by its trusted launcher. This is a simulation enrollment, not
    attestation or qualification of arbitrary firmware.
    """
    data = TEMPLATE.read_bytes()
    if hashlib.sha256(data).hexdigest() != TEMPLATE_DIGEST:
        raise JournalError('ENDPOINT_MANIFEST_CHANGED')
    if installation == legacy_installation(True):
        return data, TEMPLATE_DIGEST
    manifest = json.loads(data)
    manifest['incarnationHex'] = installation['incarnationHex']
    for role, primitive, resource in zip(ROLES, manifest['primitives'], manifest['resources']):
        instance = installation['instances'][role]
        primitive['instanceId'] = instance
        resource['instanceId'] = instance
        if role == 'focus':
            primitive['arguments']['frame'] = instance
    data = canonical(manifest)
    return data, hashlib.sha256(data).hexdigest()


def plant_filename(installation, *, legacy=False):
    if legacy:
        return 'simulated-plant.db'
    return 'simulated-plant-' + hashlib.sha256(installation['adapterId'].encode()).hexdigest() + '.db'


def installation_digest(installation):
    return hashlib.sha256(b'hms.adapter-installation/1\0' + canonical(installation)).hexdigest()
