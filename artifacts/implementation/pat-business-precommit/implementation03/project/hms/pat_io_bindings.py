"""Trusted, read-only PAT descriptors for the explicitly installed finite I/O profile.

This joins authority rows and fixed primitive semantics. It does not inspect a
board, refresh presence, grant authority or qualify execution/physical behavior.
Construction is trusted setup; selection uses only the caller's existing
Journal transaction. Legacy RegistryPatBindings is intentionally unchanged.
"""
from __future__ import annotations

import copy
from functools import wraps
import hashlib
import itertools
import re
import sqlite3

from .contracts import ContractError, MAX_BYTES, SAFE_INTEGER, canonical, identifier, parse_json
from .journal import JournalError
from .pat_compiler import _binding
from .pat_contracts import PatError, parse_pat
from .registry import _parse_binding, _resource_stored_row, validate_type_bundle
from .resource_catalog import control_generation
from .resource_topology import binding_proof
from .synthetic_io_catalog import IoAdapterCatalog
from .synthetic_io_installation import DRIVER, definitions, installation_digest, normalize_installation

PROFILE = 'hms.pat.bindings.sqlite-finite-io/0.1'
FIXED_UNIT_PROFILE = 'hms.pat.argument.fixed-schema-unit/0.1'
MAX_INSTANCES = 128
MAX_ASSIGNMENTS = 16
MAX_DESCRIPTOR_BYTES = MAX_BYTES
MAX_CACHE_BYTES = MAX_INSTANCES * MAX_DESCRIPTOR_BYTES
MAX_ASSIGNMENT_BYTES = MAX_BYTES
MAX_OUTPUT_BYTES = MAX_ASSIGNMENTS * MAX_ASSIGNMENT_BYTES
_REGISTRATION_FIELDS = {'instanceId', 'typeDigest', 'driverProfile', 'driverDigest',
                        'installationDigest', 'argumentMetadata'}
_UNITS = {'gpio_pulse': {'level': '1', 'durationMs': 'ms'},
          'pwm_burst': {'frequencyHz': 'Hz', 'dutyPermille': 'permille',
                        'resolutionBits': 'bit', 'durationMs': 'ms'}}


def _require(condition, code):
    if not condition:
        raise PatError(code)


def _refusals(method):
    @wraps(method)
    def checked(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except JournalError:
            raise
        except sqlite3.Error as error:
            raise PatError('PAT_BINDING_STORAGE') from error
        except (ContractError, TypeError, KeyError, ValueError, RecursionError) as error:
            raise PatError('PAT_BINDING_INVALID_INPUT') from error
    return checked


def _same(left, right):
    """Type-sensitive equality for already bounded built-in JSON trees."""
    pending = [(left, right)]
    while pending:
        left, right = pending.pop()
        if type(left) is not type(right):
            return False
        if type(left) is dict:
            if set(left) != set(right):
                return False
            pending.extend((left[key], right[key]) for key in left)
        elif type(left) is list:
            if len(left) != len(right):
                return False
            pending.extend(zip(left, right))
        elif left != right:
            return False
    return True


def _digest(value, *, prefixed=True):
    pattern = r'sha256:[0-9a-f]{64}' if prefixed else r'[0-9a-f]{64}'
    _require(type(value) is str and re.fullmatch(pattern, value) is not None,
             'PAT_BINDING_DIGEST_INVALID')
    return value


def _point(db, table, keys, fields):
    # Specifications are source constants; callers supply only validated keys.
    try:
        return _resource_stored_row(db, table, keys, fields)
    except JournalError as error:
        if error.code.startswith('RESOURCE_STORAGE_'):
            raise PatError('PAT_BINDING_STORAGE', error.code) from error
        raise


def _document(raw):
    value = parse_json(raw)
    _require(canonical(value) == raw, 'PAT_BINDING_NONCANONICAL')
    return value


def _output_wire(value, limit):
    # Only validated private JSON reaches this output-size boundary.
    try:
        wire = canonical(value)
    except ContractError as error:
        raise PatError('PAT_BINDING_OUTPUT_LIMIT') from error
    _require(len(wire) <= limit, 'PAT_BINDING_OUTPUT_LIMIT')
    return wire


class IoRegistryPatBindings:
    """Complete bounded static enumeration; trusted setup, never caller metadata."""

    @_refusals
    def __init__(self, runtime, registrations):
        self.journal, self.registry = runtime.journal, runtime.registry
        catalog = runtime.catalog
        self.resources = catalog.resources
        _require(self.registry.journal is self.journal and catalog.journal is self.journal and
                 self.resources.journal is self.journal and self.resources.registry is self.registry,
                 'PAT_AUTHORITY_MISMATCH')
        self._db = self.journal._db
        # Filesystem/source-identity work is confined to trusted construction.
        self._installation = normalize_installation(catalog.document)
        _require(self._installation['topology']['deployment'] == self.registry.deployment,
                 'PAT_BINDING_INSTALLATION_CHANGED')
        self._installation_wire = canonical(self._installation)
        self._installation_digest = installation_digest(self._installation)
        self._driver_digest = _digest(self._installation['driverDigest'])
        self._owner = identifier(catalog.owner.principal)
        self._routes = {row['adapterId']: row for row in IoAdapterCatalog.route_documents(self._installation)}
        self._definitions = definitions(self._installation)
        _require(1 <= len(self._definitions) <= MAX_INSTANCES, 'PAT_BINDING_ENUMERATION_LIMIT')
        self._semantics = {instance: {} for instance in self._definitions}
        for handler in self._installation['handlers']:
            units = _UNITS[handler['primitive']]
            self._semantics[handler['instanceId']][handler['actionId']] = {
                argument: {'profile': FIXED_UNIT_PROFILE, 'unit': unit, 'frame': None,
                           'unitArgument': None, 'frameArgument': None}
                for argument, unit in units.items()}
        _require(type(registrations) in {list, tuple} and 1 <= len(registrations) <= MAX_INSTANCES,
                 'PAT_INVALID_BINDING_REGISTRATION')
        # Bound/check original built-in values before copying; do not run caller hooks.
        values = list(registrations)
        canonical(values)
        values = copy.deepcopy(values)
        records = {}
        for value in values:
            _require(type(value) is dict and set(value) == _REGISTRATION_FIELDS,
                     'PAT_INVALID_BINDING_REGISTRATION')
            instance = identifier(value['instanceId'])
            _require(instance in self._definitions and instance not in records,
                     'PAT_INVALID_BINDING_REGISTRATION')
            identifier(value['driverProfile'])
            for field in ('typeDigest', 'driverDigest', 'installationDigest'):
                _digest(value[field])
            metadata = value['argumentMetadata']
            _require(type(metadata) is dict and 1 <= len(metadata) <= 32 and
                     len(canonical(metadata)) <= 16384 and
                     set(metadata) <= set(self._semantics[instance]), 'PAT_INVALID_BINDING_REGISTRATION')
            for action in metadata:
                identifier(action)
            records[instance] = value
        self._registrations = records
        identity = {'profile': PROFILE, 'installationDigest': self._installation_digest,
                    'driverDigest': self._driver_digest,
                    'registrations': [records[key] for key in sorted(records)]}
        self.registration_identity = 'sha256:' + hashlib.sha256(
            b'HMS-PAT-IO-BINDING-REGISTRATIONS-v1\0' + canonical(identity)).hexdigest()

    def _context(self, context):
        # Called only after acquiring the same Journal RLock. A different
        # thread's transaction has ended by the time its mutex can be acquired.
        _require(self._db.in_transaction, 'PAT_BINDING_TRANSACTION_REQUIRED')
        _require(context.deployment == self.registry.deployment, 'ACCESS_DENIED')

    def _exact_count(self, table, expected):
        count = len(self._db.execute('SELECT 1 FROM ' + table + ' LIMIT ?', (expected + 1,)).fetchall())
        _require(count == expected, 'PAT_BINDING_INVENTORY_INVALID')

    def _inventory(self):
        for key, expected in [('version', 'hms.registry/resource-roots/0.1'),
                              ('deployment', self.registry.deployment)]:
            saved = _point(self._db, 'reg_meta', {'key': key}, {'value': ('text', 128)})
            _require(saved is not None and saved['value'] == expected, 'PAT_BINDING_STORAGE_PROFILE')
        self._exact_count('rt_catalog', 1)
        row = _point(self._db, 'rt_catalog', {'singleton': 1}, {
            'profile': ('text', 128), 'legacy': ('integer', 1), 'owner': ('text', 128)})
        _require(row is not None and row['profile'] == 'hms.adapter-catalog/io/1' and
                 row['legacy'] == 0 and row['owner'] == self._owner, 'PAT_BINDING_STORAGE_PROFILE')
        self._exact_count('rt_io_installation', 1)
        row = _point(self._db, 'rt_io_installation', {'singleton': 1}, {
            'document': ('blob', MAX_BYTES), 'digest': ('text', 71)})
        _require(row is not None and _digest(row['digest']) == self._installation_digest and
                 row['document'] == self._installation_wire, 'PAT_BINDING_INSTALLATION_CHANGED')
        self._exact_count('rt_adapters', len(self._routes))
        ready = {}
        for adapter, expected in self._routes.items():
            row = _point(self._db, 'rt_adapters', {'adapter': adapter}, {
                'adapter': ('text', 128), 'document': ('blob', MAX_BYTES),
                'digest': ('text', 64), 'ready': ('integer', 1)})
            wire = canonical(expected)
            _require(row is not None and row['adapter'] == adapter and row['document'] == wire and
                     _digest(row['digest'], prefixed=False) == hashlib.sha256(wire).hexdigest(),
                     'PAT_BINDING_INSTALLATION_CHANGED')
            ready[adapter] = row['ready']
        # _load reads only the version metadata preflighted above, plus its own
        # bounded resource rows. It neither initializes nor publishes a catalog.
        saved = self.resources._load()
        _require(_same(saved['topology'], self._installation['topology']) and
                 _same(saved['routes'], self._installation['routes']), 'PAT_BINDING_INSTALLATION_CHANGED')
        return saved, ready

    def _minimal(self, context, instance, actions):
        row = _point(self._db, 'reg_instances', {'id': instance}, {
            'id': ('text', 128), 'deployment': ('text', 128), 'type_digest': ('text', 71),
            'identity_kind': ('text', 128), 'identity_ref': ('text', 128), 'retired': ('integer', 1)})
        authorized = self.registry.allowed(context, 'read', instance) and all(
            self.registry.allowed(context, 'invoke:' + action, instance) for action in actions)
        if row is None:
            _require(not authorized, 'PAT_BINDING_INSTANCE_MISSING')
            return None
        expected = self._definitions[instance]['binding']
        identity = 'io-installation:' + hashlib.sha256(
            (self._installation_digest + '\0' + instance).encode()).hexdigest()
        _require(row['id'] == instance and row['deployment'] == context.deployment and
                 _digest(row['type_digest']) == expected['typeDigest'] and
                 row['identity_kind'] == 'simulation' and row['identity_ref'] == identity,
                 'PAT_BINDING_INSTANCE_CHANGED')
        if row['retired'] == 1:
            return None
        binding = _point(self._db, 'reg_bindings', {'instance': instance}, {
            'generation': ('text', 128), 'active': ('integer', 1)})
        if binding is None:
            _require(not authorized, 'PAT_BINDING_CURRENT_MISSING')
            return None
        identifier(binding['generation'])
        if binding['active'] == 0 or not authorized:
            return None
        return binding['generation']

    def _descriptor(self, instance, generation, saved, ready):
        expected = self._definitions[instance]
        registered = self._registrations.get(instance)
        _require(registered is not None, 'PAT_BINDING_METADATA_MISSING')
        _require(registered['typeDigest'] == expected['binding']['typeDigest'] and
                 registered['driverProfile'] == DRIVER and registered['driverDigest'] == self._driver_digest and
                 registered['installationDigest'] == self._installation_digest, 'PAT_BINDING_REGISTRATION_CHANGED')
        row = _point(self._db, 'reg_types', {'digest': expected['binding']['typeDigest']}, {
            'digest': ('text', 71), 'document': ('blob', MAX_BYTES)})
        _require(row is not None, 'PAT_BINDING_TYPE_MISSING')
        bundle = _document(row['document'])
        _require(row['digest'] == expected['binding']['typeDigest'] == validate_type_bundle(bundle) and
                 _same(bundle, expected['type']), 'PAT_BINDING_TYPE_CHANGED')
        row = _point(self._db, 'reg_bindings', {'instance': instance}, {
            'generation': ('text', 128), 'active': ('integer', 1), 'document': ('blob', MAX_BYTES)})
        _require(row is not None and row['active'] == 1 and row['generation'] == generation,
                 'PAT_BINDING_CURRENT_CHANGED')
        binding = _parse_binding(row['document'])
        _require(canonical(binding) == row['document'] and binding['instanceId'] == instance and
                 binding['generation'] == generation and binding['typeDigest'] == expected['binding']['typeDigest'],
                 'PAT_BINDING_CURRENT_CHANGED')
        historical_row = _point(self._db, 'reg_binding_history', {'instance': instance, 'generation': generation}, {
            'document': ('blob', MAX_BYTES), 'digest': ('text', 64)})
        _require(historical_row is not None, 'PAT_BINDING_HISTORY_MISSING')
        historical = _parse_binding(historical_row['document'])
        _require(canonical(historical) == historical_row['document'] and _same(historical, binding) and
                 _digest(historical_row['digest'], prefixed=False) == hashlib.sha256(canonical(binding)).hexdigest(),
                 'PAT_BINDING_HISTORY_CHANGED')
        proof_row = _point(self._db, 'rc_proofs', {'instance': instance, 'generation': generation}, {
            'revision': ('integer', SAFE_INTEGER), 'document': ('blob', MAX_BYTES),
            'digest': ('text', 71), 'binding_digest': ('text', 64)})
        _require(proof_row is not None and 1 <= proof_row['revision'] <= saved['revision'],
                 'PAT_BINDING_PROOF_CHANGED')
        # Only now may the existing helper follow the history's type pointer:
        # it is proven equal to the exact bounded type already checked above.
        proof, retained = self.resources._retained_proof(saved, instance, generation)
        _require(_same(retained, binding) and _same(proof, binding_proof(saved['topology'], saved['generations'], instance)) and
                 binding['controlGeneration'] == control_generation(proof), 'PAT_BINDING_PROOF_CHANGED')
        _require(_same(binding, expected['binding']), 'PAT_BINDING_INSTALLATION_UNSUPPORTED')
        _require(ready[binding['adapterId']] == 1, 'PAT_BINDING_INSTALLATION_UNAVAILABLE')
        presence = _point(self._db, 'reg_presence', {'instance': instance}, {
            'session': ('text', 128), 'adapter': ('text', 128), 'expires_ms': ('integer', SAFE_INTEGER)})
        _require(presence is not None, 'PAT_BINDING_SESSION_UNKNOWN')
        identifier(presence['session'])
        current = _point(self._db, 'reg_endpoint_sessions', {'instance': instance}, {'session': ('text', 128)})
        _require(presence['adapter'] == binding['adapterId'] and current is not None and
                 current['session'] == presence['session'] and
                 self._db.execute('SELECT 1 FROM reg_session_history WHERE instance=? AND session=? LIMIT 1',
                                  (instance, presence['session'])).fetchone() is not None,
                 'PAT_BINDING_SESSION_CHANGED')
        # Expiry is retained, typed provenance, not a freshness predicate.
        descriptor = {'type': bundle, 'binding': binding, 'endpointSession': presence['session'],
            'driverProfile': DRIVER, 'driverDigest': self._driver_digest,
            'installationDigest': self._installation_digest,
            'argumentMetadata': registered['argumentMetadata']}
        _output_wire(descriptor, MAX_DESCRIPTOR_BYTES)
        return descriptor

    def _choices(self, context, artifact, *, explicit=None):
        saved, ready = self._inventory()  # Global closure before role/caller filters.
        cache, cache_bytes, choices = {}, 0, {}
        for role in sorted(artifact['roles']):
            requirement = artifact['roles'][role]
            candidates = []
            instances = [explicit[role]] if explicit is not None else sorted(self._definitions)
            for instance in instances:
                _require(instance in self._definitions, 'PAT_BINDING_NOT_REGISTERED')
                definition = self._definitions[instance]['type']['execution']
                if (DRIVER not in requirement['driverProfiles'] or
                        requirement['capabilityFamily'] not in definition['capabilities'] or
                        not set(requirement['actions']) <= set(definition['actions'])):
                    continue
                generation = self._minimal(context, instance, requirement['actions'])
                if generation is None:
                    continue
                if instance not in cache:
                    descriptor = self._descriptor(instance, generation, saved, ready)
                    cache_bytes += len(canonical(descriptor))
                    _require(len(cache) < MAX_INSTANCES and cache_bytes <= MAX_CACHE_BYTES,
                             'PAT_BINDING_OUTPUT_LIMIT')
                    cache[instance] = descriptor
                descriptor = cache[instance]
                _require(set(requirement['actions']) <= set(descriptor['argumentMetadata']),
                         'PAT_BINDING_METADATA_MISSING')
                metadata = {action: descriptor['argumentMetadata'][action] for action in requirement['actions']}
                _require(all(_same(metadata[action], self._semantics[instance][action])
                             for action in requirement['actions']), 'PAT_BINDING_METADATA_CHANGED')
                # A role view shares only call-local, non-exposed immutable data.
                # There is one cached base descriptor per installed instance.
                view = descriptor | {'argumentMetadata': metadata}
                _binding(view, requirement)
                candidates.append(instance)
            choices[role] = candidates
        return cache, choices

    @staticmethod
    def _assignment(artifact, cache, roles, instances):
        result = {}
        for role, instance in zip(roles, instances):
            base = cache[instance]
            result[role] = base | {'argumentMetadata': {
                action: base['argumentMetadata'][action] for action in artifact['roles'][role]['actions']}}
        wire = _output_wire(result, MAX_ASSIGNMENT_BYTES)
        # deepcopy of the whole mapping would preserve shared base-object
        # aliases between roles. Each emitted role owns an independent tree.
        return {role: copy.deepcopy(value) for role, value in result.items()}, len(wire)

    def _resolve(self, context, artifact, explicit=None):
        self._context(context)
        program = parse_pat(artifact)
        if explicit is not None:
            _require(type(explicit) is dict and len(explicit) == len(program['roles']) and
                     all(type(role) is str for role in explicit) and set(explicit) == set(program['roles']),
                     'PAT_INVALID_BINDING_REGISTRATION')
            for instance in explicit.values():
                identifier(instance)
        before = self._db.total_changes
        cache, choices = self._choices(context, program, explicit=explicit)
        _require(self._db.in_transaction and self._db.total_changes == before, 'PAT_RESOLVER_IMPURE')
        roles = sorted(program['roles'])
        total = 1
        for role in roles:
            total *= len(choices[role])
        _require(total <= MAX_ASSIGNMENTS, 'PAT_BINDING_ENUMERATION_LIMIT')
        assignments, output_bytes = [], 0
        for instances in itertools.product(*(choices[role] for role in roles)):
            value, size = self._assignment(program, cache, roles, instances)
            output_bytes += size
            _require(output_bytes <= MAX_OUTPUT_BYTES, 'PAT_BINDING_OUTPUT_LIMIT')
            assignments.append(value)
        if explicit is not None:
            _require(len(assignments) == 1, 'PAT_BINDING_NOT_APPLICABLE')
            return assignments[0]
        return {'complete': True, 'assignments': assignments}

    @_refusals
    def __call__(self, context, artifact, request):
        # Request values deliberately cannot narrow the trusted inventory.
        with self.journal._mutex:
            return self._resolve(context, artifact)

    @_refusals
    def for_roles(self, context, artifact, role_instances):
        with self.journal._mutex:
            return self._resolve(context, artifact, explicit=role_instances)

    @_refusals
    def configured_snapshot(self, context):
        """Read every explicitly registered instance in the owning transaction.

        This is a complete configured inventory, not a routing/uniqueness query.
        Every instance needs read and invoke permission for all installed actions.
        Unavailable or missing entries refuse the entire snapshot. Presence is
        typed session provenance; effect admission still checks actual freshness.
        """
        with self.journal._mutex:
            self._context(context)
            before = self._db.total_changes
            saved, ready = self._inventory()
            result = {}; size = 0
            for instance in sorted(self._registrations):
                expected = self._semantics[instance]
                generation = self._minimal(context, instance, sorted(expected))
                _require(generation is not None, 'PAT_BINDING_UNAVAILABLE')
                descriptor = self._descriptor(instance, generation, saved, ready)
                _require(_same(descriptor['argumentMetadata'], expected), 'PAT_BINDING_METADATA_CHANGED')
                size += len(_output_wire(descriptor, MAX_DESCRIPTOR_BYTES))
                _require(size <= MAX_CACHE_BYTES, 'PAT_BINDING_OUTPUT_LIMIT')
                result[instance] = copy.deepcopy(descriptor)
            _require(self._db.in_transaction and self._db.total_changes == before, 'PAT_RESOLVER_IMPURE')
            return result
