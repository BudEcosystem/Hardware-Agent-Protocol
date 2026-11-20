"""Immutable installed route identity with explicit initial provisioning state."""
import copy
import hashlib
import json

from .contracts import canonical
from .installations import (LEGACY_COMPACT, definitions_for, installation_digest,
                            legacy_installation, normalize_installations, resource_map)
from .journal import Context, JournalError


class AdapterCatalog:
    def __init__(self, journal, registry, *, create=False, owner=None,
                 installations=None, legacy_compact=False):
        self.journal, self.registry = journal, registry
        db = journal._db
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='rt_adapters' AND type='table'").fetchone()
        if not exists:
            legacy = installations is None
            if create:
                values = normalize_installations(installations if installations is not None else
                                                 [legacy_installation(legacy_compact)])
                principal = owner.principal
                ready = False
            else:
                if installations is not None:
                    raise JournalError('LEGACY_INSTALLATION_MIGRATION_REQUIRED')
                compact = db.execute("SELECT 1 FROM sqlite_master WHERE name='ep_state' AND type='table'").fetchone()
                required = 'simulation:compact' if compact else 'simulation:local'
                if registry.deployment != required:
                    raise JournalError('AMBIGUOUS_LEGACY_INSTALLATION')
                values = [legacy_installation(bool(compact))]
                principal, ready = '', True
                if compact:
                    rows = db.execute('SELECT singleton,document FROM ep_state').fetchall()
                    if len(rows) != 1 or rows[0][0] != 1:
                        raise JournalError('AMBIGUOUS_LEGACY_INSTALLATION')
                    state = json.loads(rows[0][1])
                    principal, ready = state['owner'], state['installed']
            with journal._transaction():
                db.execute('CREATE TABLE rt_catalog (singleton INTEGER PRIMARY KEY CHECK(singleton=1), profile TEXT NOT NULL, legacy INTEGER NOT NULL CHECK(legacy IN (0,1)), owner TEXT NOT NULL)')
                db.execute('CREATE TABLE rt_adapters (adapter TEXT PRIMARY KEY, document BLOB NOT NULL, digest TEXT NOT NULL, ready INTEGER NOT NULL CHECK(ready IN (0,1)))')
                db.execute('INSERT INTO rt_catalog VALUES (1,?,?,?)', ('hms.adapter-catalog/1', int(legacy), principal))
                for value in values:
                    db.execute('INSERT INTO rt_adapters VALUES (?,?,?,?)',
                               (value['adapterId'], canonical(value), installation_digest(value), int(ready)))
        metadata = db.execute('SELECT * FROM rt_catalog WHERE singleton=1').fetchone()
        if metadata is None or metadata['profile'] != 'hms.adapter-catalog/1':
            raise JournalError('INVALID_ADAPTER_CATALOG')
        self.legacy = bool(metadata['legacy'])
        self.owner = Context(metadata['owner'], registry.deployment) if metadata['owner'] else None
        rows = db.execute('SELECT * FROM rt_adapters ORDER BY adapter').fetchall()
        documents = [json.loads(row['document']) for row in rows]
        self.installations = normalize_installations(documents)
        if self.legacy and len(self.installations) != 1:
            raise JournalError('AMBIGUOUS_LEGACY_INSTALLATION')
        self.ready = {}
        for row, value in zip(rows, self.installations):
            if (row['adapter'] != value['adapterId'] or row['digest'] != installation_digest(value) or
                    bytes(row['document']) != canonical(value)):
                raise JournalError('INSTALLATION_DESCRIPTOR_MISMATCH')
            self.ready[row['adapter']] = bool(row['ready'])
        if installations is not None and normalize_installations(installations) != self.installations:
            raise JournalError('INSTALLATION_DESCRIPTOR_MISMATCH')

    def mark_ready(self, adapter):
        if not self.ready[adapter]:
            with self.journal._transaction():
                self.journal._db.execute('UPDATE rt_adapters SET ready=1 WHERE adapter=?', (adapter,))
            self.ready[adapter] = True

    def provision_local_registry(self, installation):
        """Resume only an unready, exact catalog installation; never overwrite.

        The separate plant database cannot share this transaction. Registry
        steps are individually durable/idempotent and `ready` is recorded only
        after the exact plant and all registry records have been checked.
        """
        if self.owner is None:
            raise JournalError('INSTALLATION_OWNER_MISSING')
        adapter = installation['adapterId']
        suffix = '1' if self.legacy else installation_digest(installation)[:32]
        for instance, _action, document in definitions_for(installation):
            digest = self.registry.publish_type(self.owner, canonical(document))
            row = self.journal._db.execute('SELECT * FROM reg_instances WHERE id=?', (instance,)).fetchone()
            identity_ref = instance if self.legacy else 'sim-installation:' + hashlib.sha256(
                (adapter + '\0' + instance).encode()).hexdigest()
            if row is None:
                self.registry.enroll(self.owner, instance, digest, identity_kind='simulation', identity_ref=identity_ref)
            elif (row['type_digest'] != digest or row['identity_kind'] != 'simulation' or row['identity_ref'] != identity_ref):
                raise JournalError('INSTALLATION_ENROLLMENT_MISMATCH')
            binding = {'profile': 'hms.binding/0.1', 'instanceId': instance,
                       'generation': 'sim-binding:' + suffix, 'typeDigest': digest,
                       'calibrationRevision': 'synthetic:1', 'controlGeneration': 'sim-control:' + suffix,
                       'mode': 'simulation', 'adapterId': adapter,
                       'resourceMap': resource_map(installation, instance),
                       'argumentSchemas': {name: copy.deepcopy(action['inputSchema'])
                           for name, action in document['execution']['actions'].items()}}
            old = self.journal._db.execute('SELECT document,active FROM reg_bindings WHERE instance=?', (instance,)).fetchone()
            if old is None:
                self.registry.bind(self.owner, canonical(binding))
            elif not old['active'] or json.loads(old['document']) != binding:
                raise JournalError('INSTALLATION_BINDING_MISMATCH')
