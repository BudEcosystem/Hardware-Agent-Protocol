"""Trusted installed management roots and exact generation publication plans."""
import hashlib

from .contracts import SAFE_INTEGER, canonical, identifier, parse_json
from .journal import Context
from .registry import exact
from .resource_catalog import control_generation
from .resource_topology import binding_proof, generation_change_claims
from .synthetic_io_catalog import IoAdapterCatalog
from .synthetic_io_installation import require, installation_digest as io_installation_digest
from .synthetic_io_storage import bounded_rows, document_row
from .synthetic_lifecycle_contracts import (DRIVER, ROOT_PROFILE, STORAGE_PROFILE, action_for,
    arguments, definitions, digest, installation_digest, normalize, root_id, snapshot)


def route_documents(document):
    adapters = sorted({entry['adapterId'] for entry in document['management']})
    return [{'profile': 'hms.synthetic-lifecycle-route/1', 'driver': DRIVER, 'adapterId': adapter,
        'installationDigest': io_installation_digest(document['io']), 'lifecycleInstallationDigest': installation_digest(document),
        'instances': sorted(entry['instanceId'] for entry in document['management'] if entry['adapterId'] == adapter)}
        for adapter in adapters]


class LifecycleCatalog:
    def __init__(self, journal, registry, *, create=False, owner=None, installation=None):
        self.journal, self.registry, self.db = journal, registry, journal._db
        if create:
            document = normalize(installation)
            self.io = IoAdapterCatalog(journal, registry, create=True, owner=owner, installation=document['io'])
            with journal._transaction():
                registry.authorize(owner, 'admin', '*')
                require(registry._storage_profile() == 'hms.registry/resource-roots/0.1', 'LIFECYCLE_STORAGE_PROFILE')
                journal._now()
                for statement in (
                    'CREATE TABLE lc_installation(singleton INTEGER PRIMARY KEY CHECK(singleton=1),document BLOB NOT NULL,digest TEXT NOT NULL)',
                    'CREATE TABLE lc_routes(adapter TEXT PRIMARY KEY,profile TEXT NOT NULL,document BLOB NOT NULL,digest TEXT NOT NULL,ready INTEGER NOT NULL)',
                    'CREATE TABLE lc_instances(instance TEXT PRIMARY KEY,adapter TEXT NOT NULL,profile TEXT NOT NULL,document BLOB NOT NULL,digest TEXT NOT NULL)',
                    'CREATE TABLE lc_dispatch(operation TEXT PRIMARY KEY,document BLOB NOT NULL,digest TEXT NOT NULL)',
                    'CREATE TABLE lc_receipts(operation TEXT PRIMARY KEY,document BLOB NOT NULL,digest TEXT NOT NULL)',
                    'CREATE TABLE lc_publications(operation TEXT PRIMARY KEY,document BLOB NOT NULL,digest TEXT NOT NULL)'):
                    self.db.execute(statement)
                self.db.execute('INSERT INTO lc_installation VALUES(1,?,?)', (canonical(document), installation_digest(document)))
                for route in route_documents(document):
                    self.db.execute('INSERT INTO lc_routes VALUES(?,?,?,?,0)', (route['adapterId'], ROOT_PROFILE,
                        canonical(route), digest('HMS-LIFECYCLE-ROUTE-v1', route)))
                for instance, definition in definitions(document).items():
                    binding = definition['binding']
                    self.db.execute('INSERT INTO lc_instances VALUES(?,?,?,?,?)', (instance, binding['adapterId'], ROOT_PROFILE,
                        canonical(binding), digest('HMS-LIFECYCLE-INSTALLED-BINDING-v1', binding)))
                self.db.execute("UPDATE reg_meta SET value=? WHERE key='version'", (STORAGE_PROFILE,))
        else:
            with journal._mutex:
                require(registry._storage_profile() == STORAGE_PROFILE, 'LIFECYCLE_STORAGE_PROFILE')
                row = document_row(self.db, 'lc_installation', {'singleton': 1})
                require(row is not None, 'LIFECYCLE_INSTALLATION_MISSING')
                document = normalize(bytes(row['document']))
                require(canonical(document) == bytes(row['document']) and installation_digest(document) == row['digest'],
                    'LIFECYCLE_INSTALLATION_CHANGED')
                if installation is not None:
                    require(canonical(normalize(installation)) == canonical(document), 'LIFECYCLE_INSTALLATION_CHANGED')
            self.io = IoAdapterCatalog(journal, registry, installation=document['io'])
        self.document = document
        self.resources = self.io.resources
        self.definitions = definitions(document)
        self.owner = self.io.owner
        self.installations = self.io.installations + route_documents(document)
        self.ready = dict(self.io.ready)
        with journal._mutex:
            self._load()
        for instance, definition in self.definitions.items():
            binding = definition['binding']; adapter = binding['adapterId']
            if self.ready[adapter]:
                self._historical_management(instance)
                continue
            # Incomplete provisioning remains fenced by the already activated
            # storage profile and exact persisted managed-instance inventory.
            registry.authorize(self.owner, 'admin', '*')
            type_digest = registry.publish_type(self.owner, canonical(definition['type']))
            identity = 'lifecycle-installation:' + hashlib.sha256((installation_digest(document)+'\0'+instance).encode()).hexdigest()
            enrolled = self.db.execute('SELECT id FROM reg_instances WHERE id=?', (instance,)).fetchone()
            if enrolled is None:
                registry.enroll(self.owner, instance, type_digest, identity_kind='simulation', identity_ref=identity)
            else:
                row = registry._instance(instance)
                require(row['type_digest'] == type_digest and row['identity_kind'] == 'simulation' and row['identity_ref'] == identity,
                    'LIFECYCLE_ENROLLMENT_CHANGED')
            existing = self.db.execute('SELECT 1 FROM reg_bindings WHERE instance=?', (instance,)).fetchone()
            if existing is None:
                registry.bind(self.owner, canonical(binding))
            else:
                actual, active = registry._binding(instance)
                require(active and canonical(actual) == canonical(binding), 'LIFECYCLE_BINDING_CHANGED')

    def _load(self):
        require(self.registry._storage_profile() == STORAGE_PROFILE, 'LIFECYCLE_STORAGE_PROFILE')
        rows = bounded_rows(self.db, 'lc_installation', ('singleton',), limit=1)
        require(len(rows) == 1 and rows[0]['singleton'] == 1, 'LIFECYCLE_INSTALLATION_INVENTORY')
        saved = document_row(self.db, 'lc_installation', {'singleton': 1})
        require(saved is not None and bytes(saved['document']) == canonical(self.document) and
            saved['digest'] == installation_digest(self.document), 'LIFECYCLE_INSTALLATION_CHANGED')
        expected_routes = route_documents(self.document)
        routes = sorted(bounded_rows(self.db, 'lc_routes', ('adapter','profile','document','digest','ready'),
            limit=16, blobs=('document',)), key=lambda row: row['adapter'])
        require(len(routes) == len(expected_routes), 'LIFECYCLE_ROUTE_INVENTORY')
        for row, expected in zip(routes, expected_routes):
            require(row['adapter'] == expected['adapterId'] and row['profile'] == ROOT_PROFILE and
                type(row['ready']) is int and row['ready'] in (0,1) and bytes(row['document']) == canonical(expected) and
                row['digest'] == digest('HMS-LIFECYCLE-ROUTE-v1', expected), 'LIFECYCLE_ROUTE_CHANGED')
            self.ready[row['adapter']] = bool(row['ready'])
        instances = sorted(bounded_rows(self.db, 'lc_instances', ('instance','adapter','profile','document','digest'),
            limit=128, blobs=('document',)), key=lambda row: row['instance'])
        require(len(instances) == len(self.definitions), 'LIFECYCLE_INSTANCE_INVENTORY')
        for row, instance in zip(instances, sorted(self.definitions)):
            binding = self.definitions[instance]['binding']
            require(row['instance'] == instance and row['adapter'] == binding['adapterId'] and row['profile'] == ROOT_PROFILE and
                bytes(row['document']) == canonical(binding) and row['digest'] == digest('HMS-LIFECYCLE-INSTALLED-BINDING-v1', binding),
                'LIFECYCLE_INSTANCE_CHANGED')
        saved = self.resources._load()
        require(canonical(saved['topology']) == canonical(self.document['io']['topology']) and
            canonical(saved['routes']) == canonical(self.document['io']['routes']), 'LIFECYCLE_TOPOLOGY_CHANGED')
        return saved

    def _historical_management(self, instance):
        expected = self.definitions[instance]['binding']
        row = document_row(self.db, 'reg_binding_history', {'instance': instance, 'generation': expected['generation']})
        require(row is not None and bytes(row['document']) == canonical(expected) and
            row['digest'] == hashlib.sha256(canonical(expected)).hexdigest(), 'LIFECYCLE_HISTORICAL_BINDING_CHANGED')
        return expected

    def mark_ready(self, adapter):
        if adapter in self.io.ready:
            self.io.mark_ready(adapter); self.ready[adapter] = True
        elif not self.ready[adapter]:
            with self.journal._transaction():
                self.journal._now()
                self.db.execute('UPDATE lc_routes SET ready=1 WHERE adapter=?', (adapter,))
            self.ready[adapter] = True

    def board_filename(self):
        return self.io.board_filename()

    def _target(self, intent, binding):
        entry, target = action_for(self.document, intent['instanceId'], intent['actionId'])
        expected = self.definitions[intent['instanceId']]['binding']
        require(canonical(binding) == canonical(expected), 'LIFECYCLE_BINDING_CHANGED')
        require(binding['resourceMap']['lifecycle:'+intent['actionId']] == root_id(intent['instanceId'], intent['actionId']),
            'LIFECYCLE_ROOT_CHANGED')
        return target, arguments(intent['arguments'])

    def resolve(self, context, intent, binding, action, *, live=True):
        with self.journal._mutex:
            saved = self._load()
            if intent['instanceId'] not in self.definitions:
                return self.resources.resolve(context, intent, binding, action, live=live)
            target, args = self._target(intent, binding)
            require(context.deployment == self.registry.deployment, 'ACCESS_DENIED')
            self.registry.authorize(context, 'read', intent['instanceId'])
            self.registry.authorize(context, 'invoke:'+intent['actionId'], intent['instanceId'])
            require(saved['revision'] == args['expectedRevision'] and saved['generations']['nodes'][target] == args['expectedGeneration'],
                'RESOURCE_GENERATION_CONFLICT')
            require(self.db.execute('SELECT 1 FROM rc_tokens WHERE node=? AND generation=?', (target,args['newGeneration'])).fetchone() is None,
                'RESOURCE_GENERATION_REUSED')
            return tuple(generation_change_claims(saved['topology'], target)['claims'])

    def reserve(self, operation, io_link):
        require(self.db.in_transaction, 'LIFECYCLE_TRANSACTION_REQUIRED')
        saved = self._load()
        binding = self._historical_management(operation['intent']['instanceId'])
        target, args = self._target(operation['intent'], binding)
        require(saved['revision'] == args['expectedRevision'] and saved['generations']['nodes'][target] == args['expectedGeneration'],
            'RESOURCE_GENERATION_CONFLICT')
        scope = generation_change_claims(saved['topology'], target)
        require([row['resource'] for row in operation['claims']] == scope['claims'], 'LIFECYCLE_CLAIM_CLOSURE')
        affected = {}
        for instance in sorted({row['instanceId'] for row in scope['affectedConsumers']}):
            current, _active = self.registry._binding(instance)
            proof, historical = self.resources._retained_proof(saved, instance, current['generation'])
            require(canonical(current) == canonical(historical) and canonical(proof) == canonical(binding_proof(saved['topology'],saved['generations'],instance)),
                'RESOURCE_DEPENDENCY_CHANGED')
            affected[instance] = {'binding': current, 'proof': proof}
        value = {'profile':'hms.synthetic-lifecycle-dispatch/1','operationId':operation['id'],
            'ioDispatchDigest':io_link, 'installationDigest':installation_digest(self.document),
            'target':target,'oldGeneration':args['expectedGeneration'],'newGeneration':args['newGeneration'],
            'dispatchRevision':saved['revision'],'scope':scope,'affected':affected}
        self.db.execute('INSERT INTO lc_dispatch VALUES(?,?,?)', (operation['id'],canonical(value),digest('HMS-LIFECYCLE-DISPATCH-v1',value)))
        return value

    def dispatch(self, operation, io_link):
        row = document_row(self.db, 'lc_dispatch', {'operation': operation['id']})
        require(row is not None, 'LIFECYCLE_DISPATCH_MISSING')
        value = snapshot(bytes(row['document']))
        exact(value, {'profile','operationId','ioDispatchDigest','installationDigest','target','oldGeneration','newGeneration',
            'dispatchRevision','scope','affected'})
        require(value['profile'] == 'hms.synthetic-lifecycle-dispatch/1' and value['operationId'] == operation['id'] and
            value['ioDispatchDigest'] == io_link and value['installationDigest'] == installation_digest(self.document) and
            canonical(value) == bytes(row['document']) and row['digest'] == digest('HMS-LIFECYCLE-DISPATCH-v1',value), 'LIFECYCLE_DISPATCH_CHANGED')
        binding = self._historical_management(operation['intent']['instanceId'])
        target, args = self._target(operation['intent'], binding)
        require(value['target'] == target and value['oldGeneration'] == args['expectedGeneration'] and
            value['newGeneration'] == args['newGeneration'] and type(value['dispatchRevision']) is int and
            value['dispatchRevision'] == args['expectedRevision'], 'LIFECYCLE_DISPATCH_CHANGED')
        saved = self._load()
        scope = generation_change_claims(saved['topology'], target)
        require(canonical(value['scope']) == canonical(scope) and operation['admission']['resources'] == scope['claims'],
            'LIFECYCLE_CLAIM_CLOSURE')
        require(type(value['affected']) is dict and set(value['affected']) == {entry['instanceId'] for entry in scope['affectedConsumers']},
            'LIFECYCLE_AFFECTED_CHANGED')
        old_generations = self.resources._generation_row(saved['topology'], value['dispatchRevision'])
        require(old_generations['nodes'][target] == value['oldGeneration'], 'LIFECYCLE_DISPATCH_CHANGED')
        for instance, previous in value['affected'].items():
            exact(previous, {'binding','proof'})
            proof, historical = self.resources._retained_proof(saved, instance, previous['binding']['generation'])
            require(canonical(previous['binding']) == canonical(historical) and canonical(previous['proof']) == canonical(proof) and
                canonical(proof) == canonical(binding_proof(saved['topology'],old_generations,instance)), 'LIFECYCLE_DISPATCH_CHANGED')
        return value

    def prepare_publication(self, operation, dispatch):
        """Called only by the installed receipt coordinator in its transaction."""
        require(self.db.in_transaction, 'LIFECYCLE_TRANSACTION_REQUIRED')
        saved = self._load(); target = dispatch['target']
        require(saved['revision'] < SAFE_INTEGER, 'LIFECYCLE_REVISION_LIMIT')
        require(saved['generations']['nodes'][target] == dispatch['oldGeneration'], 'RESOURCE_GENERATION_CONFLICT')
        require(self.db.execute('SELECT 1 FROM rc_tokens WHERE node=? AND generation=?', (target,dispatch['newGeneration'])).fetchone() is None,
            'RESOURCE_GENERATION_REUSED')
        require(operation['intent']['instanceId'] not in dispatch['affected'], 'LIFECYCLE_MANAGEMENT_SEPARATION')
        value = snapshot(saved['generations']); value['revision'] += 1; value['nodes'][target] = dispatch['newGeneration']
        next_saved = saved | {'generations':value,'revision':value['revision']}
        updates = []
        for instance, previous in dispatch['affected'].items():
            current, _active = self.registry._binding(instance)
            proof, _historical = self.resources._retained_proof(saved, instance, current['generation'])
            require(canonical(current) == canonical(previous['binding']) and canonical(proof) == canonical(previous['proof']) and
                canonical(proof) == canonical(binding_proof(saved['topology'],saved['generations'],instance)), 'RESOURCE_DEPENDENCY_CHANGED')
            require(all(saved['generations']['nodes'][node] == token for node,token in previous['proof']['dependencies'].items()),
                'RESOURCE_DEPENDENCY_CHANGED')
            next_proof = binding_proof(saved['topology'],value,instance)
            binding = current | {'generation':next_proof['bindingGeneration'],'controlGeneration':control_generation(next_proof)}
            self.resources._validate_binding(next_saved,binding,next_proof)
            updates.append((binding,next_proof))
        return {'base':saved,'next':next_saved,'updates':updates}

    def apply_publication(self, plan, dispatch):
        require(self.db.in_transaction, 'LIFECYCLE_TRANSACTION_REQUIRED')
        next_saved = plan['next']; value = next_saved['generations']
        self.resources._insert_generations(value)
        self.db.execute('INSERT INTO rc_tokens VALUES(?,?,?)', (dispatch['target'],dispatch['newGeneration'],value['revision']))
        self.db.execute('UPDATE rc_catalog SET current_revision=? WHERE singleton=1', (value['revision'],))
        for binding, proof in plan['updates']:
            self.registry._bind_recorded_effect_in_tx(binding)
            self.resources._insert_proof(next_saved,binding,proof)
        return {'dispatchRevision':dispatch['dispatchRevision'],'baseRevision':plan['base']['revision'],'revision':value['revision'],
            'target':dispatch['target'],'generation':dispatch['newGeneration'],
            'bindings':{binding['instanceId']:{'generation':binding['generation'],'proofDigest':digest('HMS-LIFECYCLE-PUBLISHED-PROOF-v1',proof)}
                for binding,proof in plan['updates']}}
