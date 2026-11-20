#!/usr/bin/env python3
"""Lint synthetic TD/HMS profile fixtures; never authorize execution."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_BYTES = (ROOT / 'research/protocols/wot-artifacts/td-schema-1.1.json').read_bytes()
SCHEMA_SHA256 = 'fd44f319f94c6f16f66978860ef2f9f4e0e9fd7fc5835a2f3840b9cf2002e0f1'
if hashlib.sha256(SCHEMA_BYTES).hexdigest() != SCHEMA_SHA256:
    raise ValueError('Pinned TD schema digest mismatch')
SCHEMA = json.loads(SCHEMA_BYTES)
Draft7Validator.check_schema(SCHEMA)
TD = Draft7Validator(SCHEMA)
PROFILE = 'https://example.invalid/hms/profiles/host-control/0.1'
FEATURES = frozenset({'durable-operations/1', 'binding-generations/1', 'physical-evidence/1'})
HOST_SCHEMA = json.loads((ROOT / 'schemas/invoke.schema.json').read_text())
ENVELOPE_KEYS = frozenset(HOST_SCHEMA['required'])
INTENT_SCHEMA = HOST_SCHEMA['$defs']['intent']
INTENT_KEYS = frozenset(INTENT_SCHEMA['required'])
TIMING_SCHEMA = INTENT_SCHEMA['properties']['timing']
ID_SCHEMA = HOST_SCHEMA['$defs']['id']
GENERATION_KEYS = ('endpointSession', 'controlGeneration', 'bindingGeneration', 'calibrationRevision')
INPUT_TERMS = frozenset({'type', 'properties', 'required', 'const', 'enum', 'pattern',
                         'minimum', 'maximum', 'unit', 'title', 'description'})
CONTEXT = ['https://www.w3.org/2022/wot/td/v1.1', {'hms': 'https://example.invalid/hms/vocab#'}]
FORM_OPERATIONS = {'properties': {'readproperty'}, 'actions': {'invokeaction'},
                   'events': {'subscribeevent', 'unsubscribeevent'}}


def _object_schema(schema, keys, label):
    if schema.get('type') != 'object':
        raise ValueError(f'{label} must be an object')
    required = schema.get('required', [])
    if len(required) != len(set(required)) or set(required) != keys:
        raise ValueError(f'Missing or unexpected required {label} keys')
    properties = schema.get('properties', {})
    if set(properties) != keys:
        raise ValueError(f'Missing or unexpected {label} schemas')
    return properties


def _schema_fields(actual, expected, label):
    if any(actual.get(key) != value for key, value in expected.items()):
        raise ValueError(f'Incorrect {label} schema constraints')


def _input_terms(schema):
    """Keep this fixture projection inside its explicit TD DataSchema subset."""
    if any(key not in INPUT_TERMS and not key.startswith('hms:') for key in schema):
        raise ValueError('Unsupported TD invocation DataSchema keyword')
    for child in schema.get('properties', {}).values():
        _input_terms(child)


def _invocation_schema(document, action_id, inputs):
    _input_terms(inputs)
    fields = _object_schema(inputs, ENVELOPE_KEYS, 'Invocation envelope')
    _schema_fields(fields['protocol'], {'type': 'string', 'const': 'hms.invoke/0.1'}, 'protocol')
    for key in ('operationKey', 'replayNamespace'):
        _schema_fields(fields[key], ID_SCHEMA, 'invocation identity fields')
    intent = _object_schema(fields['intent'], INTENT_KEYS, 'invocation intent')
    pins = {'instanceId': document['id'], 'actionId': action_id,
            **{key: document[f'hms:{key}'] for key in GENERATION_KEYS}}
    for key, value in pins.items():
        Draft7Validator(ID_SCHEMA).validate(value)
        _schema_fields(intent[key], {**ID_SCHEMA, 'const': value}, f'pinned {key}')
    _schema_fields(intent['descriptionDigest'], {
        **INTENT_SCHEMA['properties']['descriptionDigest'],
        'const': document['hms:descriptionDigest'],
    }, 'pinned descriptionDigest')
    if intent['arguments'].get('type') != 'object':
        raise ValueError('Invocation arguments must be an object')
    _schema_fields(intent['requiredEffect'], {
        'type': 'string', **INTENT_SCHEMA['properties']['requiredEffect'],
    }, 'required effect')
    timing = _object_schema(intent['timing'], frozenset(TIMING_SCHEMA['required']), 'timing')
    for key, expected in TIMING_SCHEMA['properties'].items():
        resolved = HOST_SCHEMA['$defs'][expected['$ref'].removeprefix('#/$defs/')] if '$ref' in expected else expected
        _schema_fields(timing[key], resolved, f'timing {key}')


def validate(document, understood_features):
    """Check only this exploratory host fixture profile, not generic WoT TDs."""
    TD.validate(document)
    if document.get('@context') != CONTEXT:
        raise ValueError('Expected pinned draft fixture context')
    profiles = document.get('profile', [])
    if isinstance(profiles, str):
        profiles = [profiles]
    if PROFILE not in profiles:
        raise ValueError('Expected draft HMS host profile')
    required = document.get('hms:requiredFeatures')
    if not isinstance(required, list) or not all(isinstance(x, str) for x in required):
        raise ValueError('Required features must be an explicit list')
    if len(required) != len(set(required)) or not FEATURES <= set(required):
        raise ValueError('Missing or duplicate required features')
    if not set(required) <= set(understood_features):
        raise ValueError('Unsupported required physical semantics')
    if document.get('hms:commissioned') is not False:
        raise ValueError('Fixtures must remain explicitly uncommissioned')
    for key in GENERATION_KEYS:
        if not isinstance(document.get(f'hms:{key}'), str) or not document[f'hms:{key}']:
            raise ValueError(f'Missing {key} generation')
    # These are retained synthetic physical-contract inputs, not the TD bytes:
    # hashing the TD that embeds its own digest would be self-referential.
    contracts = {}
    for path in (ROOT / 'examples').glob('*.json'):
        data = path.read_bytes()
        contracts[json.loads(data)['id']] = 'sha256:' + hashlib.sha256(data).hexdigest()
    expected_digest = contracts.get(document.get('id'))
    if expected_digest is None or document.get('hms:descriptionDigest') != expected_digest:
        raise ValueError('Description digest must pin the retained physical-contract fixture')
    if document.get('forms'):
        raise ValueError('Top-level bulk forms are outside this exploratory fixture profile')
    definitions = document['securityDefinitions']
    for kind in ('properties', 'actions', 'events'):
        for affordance_id, affordance in document.get(kind, {}).items():
            if kind == 'properties' and affordance.get('readOnly') is not True:
                raise ValueError('This fixture profile exposes only read-only state properties')
            if kind == 'actions':
                _invocation_schema(document, affordance_id, affordance.get('input', {}))
            forms = affordance.get('forms', [])
            if not forms:
                raise ValueError('Fixture affordance needs an access form')
            for form in forms:
                operations = form.get('op', [])
                operations = [operations] if isinstance(operations, str) else operations
                if not operations or not set(operations) <= FORM_OPERATIONS[kind]:
                    raise ValueError('Unsupported form operation in this fixture profile')
                endpoint = urlsplit(form['href'])
                if endpoint.scheme != 'https' or not endpoint.netloc or endpoint.username or endpoint.password:
                    raise ValueError('Host fixture forms require HTTPS without embedded credentials')
                security = form.get('security', document['security'])
                security = [security] if isinstance(security, str) else security
                if not security or any(name not in definitions for name in security):
                    raise ValueError('Unresolved effective form security')
                # Compound security needs its own negotiated profile; do not treat it
                # as authenticated merely because it names a security definition.
                if any(definitions[name].get('scheme') != 'bearer' for name in security):
                    raise ValueError('This host fixture profile requires effective bearer security')
    return True


if __name__ == '__main__':
    for path in sorted((ROOT / 'examples/wot').glob('*.json')):
        validate(json.loads(path.read_text()), FEATURES)
        print('valid exploratory TD/HMS fixture:', path.name)
    print('Informative-schema and selected static checks only; no live execution or conformance certification.')
