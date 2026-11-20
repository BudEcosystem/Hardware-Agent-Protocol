"""Closed standing host records for the explicit local SQLite ordering test.

No physical capability, protected capacity, executable selection or evidence
assertion is accepted from an application request.
"""
from __future__ import annotations
import copy
from contextlib import contextmanager
import hashlib
import os
import stat
from pathlib import Path
import re
import sys
import threading
import time

from .contracts import canonical, parse_json, identifier, SAFE_INTEGER
from .journal import JournalError, Context, Admission
from .resource_topology import binding_proof, parse_topology, parse_generations, generation_change_claims

PROFILE = 'hms.standing-host/local-sqlite-ordering-test/0.1'
REQUEST = 'hms.standing-deploy/0.1'
CAPACITY = {'profile': 'local-sqlite-ordering-test', 'protectedCapacity': False,
            'physicalEligible': False, 'publicEligible': False,
            'accountingScope': 'closed-installed-profile-all-user-tables',
            'wholeDatabaseBound': True, 'maxLogicalBytes': 16 * 1024 * 1024,
            'maxDeployments': 16, 'maxStandingLogicalBytes': (14 * 1024 + 512) * 1024,
            'maxMutationRecords': 128, 'lossMutationReserve': 8,
            'maxEpisodes': 32, 'lossEpisodeReserve': 8}
ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAMES = ('hms/standing_contracts.py', 'hms/standing_wire.py',
    'hms/standing_store.py', 'hms/standing_endpoint.py', 'hms/standing_pat.py',
    'hms/standing_capacity.py', 'hms/journal.py', 'hms/registry.py', 'hms/resource_catalog.py',
    'hms/resource_topology.py', 'hms/endpoint_transport.py', 'hms/contracts.py',
    'protocol/serial/frame.py')


def require(value, code='INVALID'):
    if not value:
        raise JournalError('STANDING_' + code)


def exact(value, fields):
    require(type(value) is dict and set(value) == set(fields), 'FIELDS')


def uint(value, maximum=SAFE_INTEGER, minimum=0):
    require(type(value) is int and minimum <= value <= maximum, 'INTEGER')
    return value


def hex_bytes(value, count, *, nonzero=False):
    require(type(value) is str and re.fullmatch('[0-9a-f]{' + str(count * 2) + '}', value) is not None, 'HEX')
    data = bytes.fromhex(value)
    require(not nonzero or any(data), 'HEX')
    return data


def digest(value):
    require(type(value) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', value) is not None, 'DIGEST')
    return value


def sha(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def identity(domain, value):
    return sha(domain.encode('ascii') + b'\0' + canonical(value))


def document(value, maximum=65536):
    # Detach before encoding so bool/float cannot become valid integer inputs.
    result = parse_json(value) if type(value) is bytes else copy.deepcopy(value)
    encoded = canonical(result)
    require(len(encoded) <= maximum, 'RECORD_LIMIT')
    return result


def bounded_file(path, maximum):
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),'rb') as stream:
        before=os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size<=maximum,'SOURCE_LIMIT')
        body=stream.read(maximum+1);after=os.fstat(stream.fileno())
        signature=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
        require(len(body)==before.st_size and signature(before)==signature(after),'SOURCE_CHANGED')
        return body


def _source_pins():
    result = {}
    for name in SOURCE_NAMES:
        body = bounded_file(ROOT / name,1024*1024)
        require(len(body) <= 1024 * 1024, 'SOURCE_LIMIT')
        result[name] = sha(body)
    return result


# Import-time image identity; fresh admission must still verify original bytes.
# Python stdlib, loader and already installed validation packages remain trusted
# runtime dependencies. This is deliberately not a full runtime-closure claim.
_IMPORTED_SOURCES = _source_pins()
_INTERPRETER = Path(sys.executable).resolve()
_INTERPRETER_SHA = sha(bounded_file(_INTERPRETER,64*1024*1024))


def implementation_identity(*, fresh=True):
    if fresh:
        require(_source_pins() == _IMPORTED_SOURCES and
                sha(bounded_file(_INTERPRETER,64*1024*1024)) == _INTERPRETER_SHA, 'IMPLEMENTATION_CHANGED')
    return identity('HMS-STANDING-HOST-IMAGE-v0.1', {
        'sources': _IMPORTED_SOURCES, 'interpreter': _INTERPRETER_SHA,
        'dependencyScope': 'original-source-pins;trusted-python-stdlib-loader-validation-packages'})


def parse_request(value):
    request = document(value, 8192)
    exact(request, ('protocol', 'replayNamespace', 'deploymentKey', 'taskKind',
                    'inputProfile', 'parameters', 'evidenceMode', 'limits'))
    require(request['protocol'] == REQUEST and request['evidenceMode'] == 'simulation', 'PROFILE')
    for key in ('replayNamespace', 'deploymentKey', 'taskKind', 'inputProfile'):
        identifier(request[key])
    require(request['parameters'] == {} and type(request['parameters']) is dict, 'PARAMETERS_UNQUALIFIED')
    limits = request['limits']
    exact(limits, ('activationCap', 'commandedOnMs', 'mutationRecords', 'episodeRecords', 'leaseHorizonMs'))
    for key in limits:
        uint(limits[key], 60000, 1)
    # This initial artifact has one tested literal domain. No generic native
    # pass is promoted into an arbitrary hysteresis/feedback configuration.
    require(limits['activationCap'] == 100 and limits['commandedOnMs'] == 500 and
            limits['leaseHorizonMs'] == 1000, 'DOMAIN_UNQUALIFIED')
    require(16 <= limits['mutationRecords'] <= 128 and 9 <= limits['episodeRecords'] <= 32, 'CAPACITY')
    return request


def request_digest(request):
    return identity('HMS-STANDING-REQUEST-v0.1', parse_request(request))


def parse_installation(value):
    value = document(value)
    exact(value, ('profile', 'deployment', 'routeId', 'instanceId', 'finiteInstanceId',
                  'topology', 'generations', 'hardwareResources', 'slotResource',
                  'endpoint', 'driverImageDigest', 'qualificationImageDigest',
                  'driverSourceDigest', 'hostImplementationDigest', 'capacity'))
    require(value['profile'] == PROFILE and type(value['capacity']) is dict and
            canonical(value['capacity']) == canonical(CAPACITY), 'CAPACITY_UNQUALIFIED')
    # Check types as well as canonical bytes (which normalize 1.0).
    for name, expected in CAPACITY.items():
        require(type(value['capacity'][name]) is type(expected) and value['capacity'][name] == expected,
                'CAPACITY_UNQUALIFIED')
    for name in ('deployment', 'routeId', 'instanceId', 'finiteInstanceId', 'slotResource'):
        identifier(value[name])
    require(value['instanceId'] != value['finiteInstanceId'], 'INSTALLATION')
    for name in ('driverImageDigest', 'qualificationImageDigest', 'driverSourceDigest', 'hostImplementationDigest'):
        digest(value[name])
    topology = parse_topology(value['topology'])
    generations = parse_generations(topology, value['generations'])
    require(topology['deployment'] == value['deployment'], 'INSTALLATION')
    resources = value['hardwareResources']
    require(type(resources) is list and len(resources) == 2 and len(set(resources)) == 2, 'FOOTPRINT')
    for name in resources:
        identifier(name)
    require(value['slotResource'] not in resources, 'FOOTPRINT')
    for instance in (value['instanceId'], value['finiteInstanceId']):
        proof = binding_proof(topology, generations, instance)
        require(set(proof['expandedClaims']) == {'control'}, 'FOOTPRINT')
        require(set(proof['expandedClaims']['control']) == set(resources + [value['slotResource']]), 'FOOTPRINT')
    endpoint = value['endpoint']
    exact(endpoint, ('incarnationHex', 'firmwareHex', 'manifestHex', 'boot', 'kernel', 'mask', 'epochs'))
    hex_bytes(endpoint['incarnationHex'], 16, nonzero=True)
    hex_bytes(endpoint['firmwareHex'], 32, nonzero=True)
    hex_bytes(endpoint['manifestHex'], 32, nonzero=True)
    uint(endpoint['boot'], 2**64-2, 1)
    require(type(endpoint['kernel']) is int and endpoint['kernel'] == 1 and
            type(endpoint['mask']) is int and endpoint['mask'] == 3, 'INSTALLATION')
    require(type(endpoint['epochs']) is list and len(endpoint['epochs']) == 2, 'INSTALLATION')
    for epoch in endpoint['epochs']:
        uint(epoch, 2**32-1, 1)
    return value


class InstalledPolicy:
    """Trusted installed test policy, shared by finite Journal and standing host.

    Actor identity is supplied by the trusted caller/channel as in Journal.
    No request contains grants, descriptors, paths or a callable.
    """
    def __init__(self, owner, installation):
        require(type(owner) is Context, 'OWNER')
        self.owner = owner
        self.installation = parse_installation(installation)
        require(owner.deployment == self.installation['deployment'], 'OWNER')
        self.original = canonical(self.installation)
        self.enabled = True
        self.journal = None
        self._held_image = None

    @contextmanager
    def hold_image(self):
        """Source I/O happens before entering an authority transaction."""
        require(self.journal is None or not self.journal._db.in_transaction, 'TRANSACTION_REENTRY')
        require(self._held_image is None, 'IMAGE_REENTRY')
        expected = implementation_identity()
        lease = (threading.get_ident(), time.monotonic_ns() + 2_000_000_000, expected)
        self._held_image = lease
        try:
            yield self.check_image
        finally:
            self._held_image = None

    def check_image(self):
        lease = self._held_image
        require(lease is not None and lease[0] == threading.get_ident() and
                time.monotonic_ns() < lease[1] and
                lease[2] == self.installation['hostImplementationDigest'], 'IMAGE_LEASE_UNAVAILABLE')

    def authorize(self, context, verb, target):
        require(type(context) is Context and context == self.owner, 'ACCESS_DENIED')
        require(verb in {'namespace', 'admin', 'read', 'invoke', 'cancel'} or verb == 'invoke:control', 'ACCESS_DENIED')
        require(target in {'*', self.owner.deployment, self.installation['instanceId'],
                           self.installation['finiteInstanceId']}, 'ACCESS_DENIED')

    def fresh(self, context):
        self.authorize(context, 'invoke', self.installation['instanceId'])
        require(self.enabled, 'AUTHORITY_WITHDRAWN')
        self.check_image()
        current = parse_installation(self.installation)
        require(canonical(current) == self.original and
                current['hostImplementationDigest'] == implementation_identity(fresh=False), 'INSTALLATION_CHANGED')
        proof = binding_proof(current['topology'], current['generations'], current['instanceId'])
        return current, proof

    def affected_instances(self, instances):
        # Two explicit installed aliases share the endpoint footprint. Guard
        # both direct binding paths regardless of the acquiring capability.
        allowed = {self.installation['instanceId'], self.installation['finiteInstanceId']}
        require(set(instances) <= allowed, 'INSTANCE')
        return tuple(sorted(allowed))

    def resources(self, instance):
        require(instance in {self.installation['instanceId'], self.installation['finiteInstanceId']}, 'INSTANCE')
        proof = binding_proof(self.installation['topology'], self.installation['generations'], instance)
        return tuple(sorted(proof['expandedClaims']['control']))

    def admit(self, context, intent, now_ms):
        installation, proof = self.fresh(context)
        require(intent['instanceId'] == installation['finiteInstanceId'] and intent['actionId'] == 'control', 'FINITE_CAPABILITY')
        require(intent['arguments'] == {} and intent['requiredEffect'] == 'capability_completion', 'FINITE_CAPABILITY')
        expected={'endpointSession':'native-boot:1','controlGeneration':'native-control:2',
            'bindingGeneration':'native-binding:1','calibrationRevision':'native-calibration:1',
            'descriptionDigest':identity('HMS-STANDING-FINITE-CAPABILITY-v0.1',installation)}
        require(all(intent[key]==value for key,value in expected.items()),'FINITE_BINDING_CHANGED')
        self.journal._require_at_commit(self.check_image)
        return Admission(self.resources(intent['instanceId']), 'standing-test:1',
                         min(now_ms + 1000, intent['timing']['latestCompletionUnixMs']))

    def recheck(self, context, operation, now_ms):
        admission = self.admit(context, operation['intent'], now_ms)
        require(list(admission.resources) == operation['admission']['resources'], 'FOOTPRINT')

    def evidence(self, operation, evidence):
        require(evidence.kind == 'simulation' and evidence.source == self.installation['routeId'], 'EVIDENCE')

    def require_lifecycle_quiescent(self, context, target):
        self.authorize(context, 'admin', '*')
        require(self.journal is not None and self.journal._db.in_transaction, 'TRANSACTION_REQUIRED')
        scope = generation_change_claims(self.installation['topology'], target)
        for resource in scope['claims']:
            require(self.journal._db.execute('SELECT 1 FROM claims WHERE deployment=? AND resource=?',
                    (context.deployment, resource)).fetchone() is None, 'CLAIMS_UNRESOLVED')
        return scope
