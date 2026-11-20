"""Trusted I/O service configuration joined to original supervised run inputs.

Construction and fresh preparation are trusted host APIs, not public tools.
Configuration selects installed semantics and bindings, never execution code.
Each preparation requires new explicit trusted descriptor snapshots; this module
does not manufacture live authority, presence or permission. Pins must eventually
be retained by the owning authority. No configuration database is installed here.
Historical parsing uses external retained anchors and performs no source reads.
"""
from functools import wraps
import hashlib
import re

from hms.contracts import ContractError, SAFE_INTEGER, canonical, identifier, parse_json
from hms.journal import JournalError
from hms.pat_contracts import parse_pat, pat_digest
from hms.pat_io_bindings import FIXED_UNIT_PROFILE, MAX_CACHE_BYTES, MAX_INSTANCES, _UNITS
from hms.pat_io_combined_matrix import POLICY, ROLES
from hms.pat_io_group_worker import _identities
from hms.pat_io_run_bundle import CEILINGS, parse_io_run_bundle, prepare_io_run_bundle
from hms.synthetic_io_installation import DRIVER, definitions, installation_digest, normalize_installation
from supervisor_contracts import (DEFAULT_LIMITS, parse_limits, parse_request, prepare_request, request_digest,
                                  same, snapshot_bundle, supervisor_identity)

CONFIG_PROFILE = 'hms.pat.io-simulation-services/0.1'
PIN_PROFILE = 'hms.pat.io-service-pin/0.1'
_DESCRIPTOR_FIELDS = {'type', 'binding', 'endpointSession', 'driverProfile', 'driverDigest',
                      'installationDigest', 'argumentMetadata'}


class IoServiceError(JournalError):
    def __init__(self, suffix):
        super().__init__('PAT_IO_SERVICE_' + suffix)


def require(condition, code):
    if not condition: raise IoServiceError(code)


def errors(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try: return function(*args, **kwargs)
        except IoServiceError: raise
        except (JournalError, ContractError, TypeError, ValueError, KeyError, IndexError, RecursionError) as error:
            raise IoServiceError('INVALID_INPUT_OR_DEPENDENCY') from error
    return checked


def snapshot(value):
    raw = parse_json(value) if type(value) is bytes else value
    encoded = canonical(raw)  # Bounds and exact builtin types before traversal.
    pending = [raw]
    while pending:
        item = pending.pop()
        require(type(item) is not float, 'INTEGER_CONFIGURATION_REQUIRED')
        if type(item) is dict: pending.extend(item.values())
        elif type(item) is list: pending.extend(item)
    return parse_json(encoded)


def exact(value, fields, code='CONFIGURATION'):
    require(type(value) is dict and set(value) == set(fields), code)


def integer(value, low=1, high=SAFE_INTEGER):
    require(type(value) is int and low <= value <= high, 'INTEGER')


def digest(value):
    require(type(value) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', value), 'DIGEST')


def name(value):
    identifier(value)
    require(len(value) <= 128, 'IDENTIFIER')


def _hash(domain, value):
    return 'sha256:' + hashlib.sha256(domain + b'\0' + canonical(value)).hexdigest()


@errors
def parse_configuration(value):
    value = snapshot(value)
    exact(value, {'profile', 'policy', 'deployment', 'evaluatorId', 'revision', 'installationDigest',
                  'initialRegistryRevision', 'groupLimits', 'supervisorLimits', 'registrations',
                  'qualifications', 'challengeBindings'})
    require(value['profile'] == CONFIG_PROFILE and value['policy'] == POLICY, 'POLICY')
    name(value['deployment']); name(value['evaluatorId'])
    require(value['deployment'].startswith('simulation:'), 'SIMULATION_REQUIRED')
    integer(value['revision']); integer(value['initialRegistryRevision']); digest(value['installationDigest'])
    exact(value['groupLimits'], CEILINGS, 'LIMITS')
    for key, limit in CEILINGS.items(): integer(value['groupLimits'][key], 1, limit)
    value['supervisorLimits'] = parse_limits(value['supervisorLimits'])
    registrations, qualifications = value['registrations'], value['qualifications']
    require(type(registrations) is list and 1 <= len(registrations) <= MAX_INSTANCES, 'REGISTRATIONS')
    require(type(qualifications) is list and 1 <= len(qualifications) <= 128, 'QUALIFICATIONS')
    instances = set()
    for row in registrations:
        exact(row, {'instanceId', 'driverProfile', 'typeDigest', 'argumentMetadata'})
        name(row['instanceId']); digest(row['typeDigest'])
        require(row['driverProfile'] == DRIVER and row['instanceId'] not in instances, 'REGISTRATIONS')
        require(type(row['argumentMetadata']) is dict and 1 <= len(row['argumentMetadata']) <= 32 and
                len(canonical(row['argumentMetadata'])) <= 16384, 'METADATA')
        instances.add(row['instanceId'])
    artifacts = set()
    for row in qualifications:
        exact(row, {'artifactDigest', 'roleInstances'})
        digest(row['artifactDigest'])
        require(row['artifactDigest'] not in artifacts, 'QUALIFICATIONS'); artifacts.add(row['artifactDigest'])
        roles = row['roleInstances']; require(type(roles) is dict and len(roles) == 1, 'ROLE_MAP')
        for role, instance in roles.items():
            name(role); name(instance); require(instance in instances, 'UNREGISTERED_INSTANCE')
    exact(value['challengeBindings'], ROLES, 'CHALLENGE_BINDINGS')
    for row in value['challengeBindings'].values():
        exact(row, {'instanceId', 'actionId'}, 'CHALLENGE_BINDINGS')
        name(row['instanceId']); name(row['actionId'])
        require(row['instanceId'] in instances, 'UNREGISTERED_INSTANCE')
    require(len({row['instanceId'] for row in value['challengeBindings'].values()}) == len(ROLES), 'CHALLENGE_BINDINGS')
    value['registrations'].sort(key=lambda row: row['instanceId'])
    value['qualifications'].sort(key=lambda row: row['artifactDigest'])
    canonical(value)
    return value


@errors
def configuration_digest(value):
    return _hash(b'HMS-PAT-IO-SERVICE-CONFIG-v0.1', parse_configuration(value))


def _installation(config, value):
    document = normalize_installation(value)
    require(document['topology']['deployment'] == config['deployment'] and
            installation_digest(document) == config['installationDigest'], 'INSTALLATION_CHANGED')
    expected = definitions(document); semantics = {key: {} for key in expected}
    for handler in document['handlers']:
        semantics[handler['instanceId']][handler['actionId']] = {
            argument: dict(profile=FIXED_UNIT_PROFILE, unit=unit, frame=None, unitArgument=None, frameArgument=None)
            for argument, unit in _UNITS[handler['primitive']].items()}
    for row in config['registrations']:
        require(row['instanceId'] in expected, 'REGISTRATION_CHANGED')
        definition = expected[row['instanceId']]
        require(row['typeDigest'] == definition['binding']['typeDigest'] and
                same(row['argumentMetadata'], semantics[row['instanceId']]), 'REGISTRATION_CHANGED')
    for row in config['challengeBindings'].values():
        require(row['actionId'] in semantics[row['instanceId']], 'CHALLENGE_BINDINGS')
    return document, expected


@errors
def parse_service_pin(value):
    value = snapshot(value)
    exact(value, {'profile', 'policy', 'deployment', 'evaluatorId', 'configurationDigest',
                  'configurationRevision', 'installationDigest', 'implementation', 'supervisorIdentity'}, 'PIN')
    require(value['profile'] == PIN_PROFILE and value['policy'] == POLICY, 'PIN')
    name(value['deployment']); name(value['evaluatorId']); integer(value['configurationRevision'])
    require(value['deployment'].startswith('simulation:'), 'SIMULATION_REQUIRED')
    for key in ('configurationDigest', 'installationDigest', 'supervisorIdentity'): digest(value[key])
    exact(value['implementation'], {'compilerDigest', 'driverDigest', 'workerDigest', 'storageProfile'}, 'PIN')
    for key in ('compilerDigest', 'driverDigest', 'workerDigest'): digest(value['implementation'][key])
    require(value['implementation']['storageProfile'] == 'hms.sqlite.compact/0.1', 'PIN')
    return value


def _pin_context(config):
    return dict(policy=config['policy'], deployment=config['deployment'], evaluatorId=config['evaluatorId'],
                configurationDigest=configuration_digest(config), configurationRevision=config['revision'],
                installationDigest=config['installationDigest'])


@errors
def prepare_service_pin(configuration, installation):
    """Derive a candidate setup pin from installed code; retaining it is separate."""
    config = parse_configuration(configuration)
    _installation(config, installation)
    implementation = _identities()
    return parse_service_pin(dict(profile=PIN_PROFILE, **_pin_context(config), implementation=implementation,
                                  supervisorIdentity=supervisor_identity(implementation)))


def _assignment(config, candidate):
    artifact = parse_pat(candidate); artifact_id = pat_digest(artifact)
    row = next((row for row in config['qualifications'] if row['artifactDigest'] == artifact_id), None)
    require(row is not None, 'ARTIFACT_NOT_CONFIGURED')
    require(set(row['roleInstances']) == set(artifact['roles']), 'ROLE_MAP')
    return artifact, next(iter(row['roleInstances'].values()))


def _authority(config):
    owner = dict(principal='pat-io-trial-worker', deployment=config['deployment'])
    return owner | dict(profile='hms.pat.io-trusted-authority/0.1', initialRegistryRevision=config['initialRegistryRevision'],
                        initialGrants=[owner | dict(target='*', verb='admin')], grantChanges=[])


def _descriptors(config, installation, expected, supplied):
    require(type(supplied) is dict and 1 <= len(supplied) <= MAX_INSTANCES, 'DESCRIPTORS')
    # Validate exact key types before set/membership/hash operations.
    require(all(type(key) is str for key in supplied), 'DESCRIPTORS')
    records = {row['instanceId']: row for row in config['registrations']}
    require(set(supplied) == set(records), 'DESCRIPTOR_CLOSURE')
    copied = {}; total = 0
    for instance in sorted(supplied):
        value = snapshot(supplied[instance]); exact(value, _DESCRIPTOR_FIELDS, 'DESCRIPTOR')
        total += len(canonical(value)); require(total <= MAX_CACHE_BYTES, 'DESCRIPTOR_LIMIT')
        name(value['endpointSession']); definition = expected[instance]; row = records[instance]
        require(same(value['type'], definition['type']) and same(value['binding'], definition['binding']) and
                value['driverProfile'] == DRIVER and value['driverDigest'] == installation['driverDigest'] and
                value['installationDigest'] == config['installationDigest'] and
                same(value['argumentMetadata'], row['argumentMetadata']), 'DESCRIPTOR_CHANGED')
        copied[instance] = value
    return copied


@errors
def parse_prepared_run(value, *, expected_pin, expected_run_id, expected_request_digest):
    """Check historical structural association without replanning or source I/O.

This does not attest live registration/authority, current source or successful
qualification. The expected pin and logical run ID must come from retained state.
"""
    require(type(value) is dict and all(type(key) is str for key in value), 'PREPARED')
    exact(value, {'configuration', 'servicePin', 'request', 'requestDigest', 'bundle'}, 'PREPARED')
    require(type(value['configuration']) is bytes and type(value['servicePin']) is bytes, 'PREPARED')
    config = parse_configuration(value['configuration']); pin = parse_service_pin(value['servicePin'])
    require(canonical(config) == value['configuration'] and canonical(pin) == value['servicePin'], 'CANONICAL')
    require(same(pin, parse_service_pin(expected_pin)), 'PIN_CHANGED')
    require(all(same(pin[key], item) for key, item in _pin_context(config).items()), 'CONFIGURATION_CHANGED')
    name(expected_run_id)
    context = {key: pin[key] for key in ('deployment', 'evaluatorId', 'configurationDigest', 'configurationRevision')}
    context['runId'] = expected_run_id
    request = parse_request(snapshot(value['request'])); bundle = snapshot_bundle(value['bundle'])
    digest(expected_request_digest); digest(value['requestDigest'])
    require(value['requestDigest'] == expected_request_digest == request_digest(request), 'REQUEST_DIGEST')
    require(same(request['context'], context) and same(request['implementation'], pin['implementation']) and
            request['supervisorIdentity'] == pin['supervisorIdentity'], 'REQUEST_CHANGED')
    require(same(request['limits'], config['supervisorLimits']) and same(request['groupLimits'], config['groupLimits']), 'LIMITS_CHANGED')
    require(canonical(request['bundleHeader']) == bundle['header'] and request['bundleDigest'] == bundle['bundleDigest'], 'BUNDLE_CHANGED')
    parsed = parse_io_run_bundle(bundle['header'], bundle['documents'], expected_context=context,
                                expected_bundle_digest=bundle['bundleDigest'])
    inputs = parsed['expected_inputs']; artifact, instance = _assignment(config, inputs['candidate'])
    require(inputs['descriptor']['binding']['instanceId'] == instance and
            installation_digest(inputs['installation']) == config['installationDigest'] and
            same(inputs['matrix']['limits'], config['groupLimits']) and same(inputs['implementation'], pin['implementation']) and
            same(parsed['authority'], _authority(config)), 'BUNDLE_CHANGED')
    exact(inputs['bindings'], ROLES, 'CHALLENGE_BINDINGS')
    for role, row in config['challengeBindings'].items():
        actual = inputs['bindings'][role]
        require(actual['actionId'] == row['actionId'] and actual['descriptor']['binding']['instanceId'] == row['instanceId'], 'CHALLENGE_BINDINGS')
    return dict(configuration=canonical(config), servicePin=canonical(pin), request=request,
                requestDigest=expected_request_digest, bundle=bundle)


class ConfiguredIoService:
    """Immutable trusted setup; fresh descriptor snapshots are required per run.

No worker is started and no SQL/evidence/catalog state is changed by this API.
The next durable host boundary must authorize and retain pins before use.
"""
    @errors
    def __init__(self, configuration, installation, *, expected_pin):
        config = parse_configuration(configuration); document, _ = _installation(config, installation)
        pin = parse_service_pin(expected_pin)
        require(same(prepare_service_pin(config, document), pin), 'PIN_CHANGED')
        self._configuration = canonical(config); self._installation = canonical(document); self._pin = canonical(pin)

    @errors
    def prepare_run(self, candidate, run_id, *, trusted_descriptors):
        config = parse_configuration(self._configuration); pin = parse_service_pin(self._pin)
        artifact, instance = _assignment(config, snapshot(candidate)); name(run_id)
        document, expected = _installation(config, self._installation)
        require(same(prepare_service_pin(config, document), pin), 'PIN_CHANGED')
        descriptors = _descriptors(config, document, expected, trusted_descriptors)
        challenges = {role: dict(actionId=row['actionId'], descriptor=descriptors[row['instanceId']])
                      for role, row in config['challengeBindings'].items()}
        context = {key: pin[key] for key in ('deployment', 'evaluatorId', 'configurationDigest', 'configurationRevision')}
        context['runId'] = run_id
        bundle = prepare_io_run_bundle(context=context, candidate=artifact, installation=document,
                    descriptor=descriptors[instance], challenge_bindings=challenges, authority=_authority(config),
                    limits=config['groupLimits'])
        request = prepare_request(bundle, context=context, limits=config['supervisorLimits'])
        request_id = request_digest(request)
        return parse_prepared_run(dict(configuration=self._configuration, servicePin=self._pin, request=request,
                                       requestDigest=request_id, bundle=bundle),
                                  expected_pin=pin, expected_run_id=run_id, expected_request_digest=request_id)
