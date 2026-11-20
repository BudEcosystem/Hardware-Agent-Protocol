"""Trusted persistent installation branch for one explicitly shared I/O board."""
import hashlib

from .contracts import canonical, parse_json
from .journal import Context, JournalError
from .resource_catalog import ResourceCatalog
from .synthetic_io_installation import definitions, installation_digest, normalize_installation, require
from .synthetic_io_storage import bounded_rows, document_row


class IoAdapterCatalog:
    def __init__(self, journal, registry, *, create=False, owner=None, installation=None):
        self.journal, self.registry = journal, registry
        db = journal._db
        if create:
            document = normalize_installation(installation)
            require(owner is not None and owner.deployment == document['topology']['deployment'] == registry.deployment,
                    'IO_INSTALLATION_DEPLOYMENT')
            with journal._transaction():
                registry.authorize(owner, 'admin', '*')
                require(db.execute("SELECT 1 FROM sqlite_master WHERE name IN ('rt_catalog','rt_adapters','rt_io_installation')").fetchone() is None,
                        'IO_CATALOG_ALREADY_EXISTS')
                journal._now()
                db.execute('CREATE TABLE rt_catalog(singleton INTEGER PRIMARY KEY CHECK(singleton=1),profile TEXT NOT NULL,legacy INTEGER NOT NULL,owner TEXT NOT NULL)')
                db.execute('CREATE TABLE rt_adapters(adapter TEXT PRIMARY KEY,document BLOB NOT NULL,digest TEXT NOT NULL,ready INTEGER NOT NULL)')
                db.execute('CREATE TABLE rt_io_installation(singleton INTEGER PRIMARY KEY CHECK(singleton=1),document BLOB NOT NULL,digest TEXT NOT NULL)')
                db.execute('CREATE TABLE io_dispatch_links(operation TEXT PRIMARY KEY,document BLOB NOT NULL,digest TEXT NOT NULL)')
                db.execute('CREATE TABLE io_authority_receipts(operation TEXT NOT NULL,sequence INTEGER NOT NULL,document BLOB NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(operation,sequence))')
                db.execute('INSERT INTO rt_catalog VALUES (1,?,0,?)', ('hms.adapter-catalog/io/1',owner.principal))
                db.execute('INSERT INTO rt_io_installation VALUES (1,?,?)', (canonical(document),installation_digest(document)))
                for route in self.route_documents(document):
                    data = canonical(route)
                    db.execute('INSERT INTO rt_adapters VALUES (?,?,?,0)', (route['adapterId'],data,hashlib.sha256(data).hexdigest()))
        with journal._mutex:
            meta_rows = bounded_rows(db,'rt_catalog',('profile','legacy','owner'),limit=1,keys={'singleton':1})
            meta = meta_rows[0] if meta_rows else None
            require(meta is not None and meta['profile'] == 'hms.adapter-catalog/io/1' and meta['legacy'] == 0, 'IO_CATALOG_PROFILE')
            row = document_row(db,'rt_io_installation',{'singleton':1})
            require(row is not None, 'IO_INSTALLATION_MISSING')
            self.document = normalize_installation(bytes(row['document']))
            require(canonical(self.document) == bytes(row['document']) and installation_digest(self.document) == row['digest'], 'IO_INSTALLATION_CHANGED')
            if installation is not None:
                require(canonical(normalize_installation(installation)) == canonical(self.document), 'IO_INSTALLATION_CHANGED')
            require(self.document['topology']['deployment'] == registry.deployment, 'IO_INSTALLATION_DEPLOYMENT')
            self.owner = Context(meta['owner'],registry.deployment)
            self.installations = self.route_documents(self.document)
            rows = sorted(bounded_rows(db,'rt_adapters',('adapter','document','digest','ready'),limit=16,blobs=('document',)),key=lambda row:row['adapter'])
            require(len(rows) == len(self.installations), 'IO_ROUTE_INVENTORY')
            self.ready = {}
            for saved,expected in zip(rows,self.installations):
                data = canonical(expected)
                require(saved['adapter'] == expected['adapterId'] and bytes(saved['document']) == data and
                        saved['digest'] == hashlib.sha256(data).hexdigest() and saved['ready'] in {0,1}, 'IO_ROUTE_CHANGED')
                self.ready[saved['adapter']] = bool(saved['ready'])
        # Activation is explicit. A completed catalog is never silently rebuilt.
        resource_exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='rc_catalog'").fetchone() is not None
        require(resource_exists or not any(self.ready.values()), 'IO_RESOURCE_CATALOG_MISSING')
        self.resources = ResourceCatalog(journal,registry,create=not resource_exists,
            **({'owner':self.owner,'topology':self.document['topology'],'generations':self.document['initialGenerations'],
                'routes':self.document['routes']} if not resource_exists else {}))
        # Trusted recovery must not depend on current administrator grants.
        # This is the same validated retained state, with no authority mutation.
        with journal._mutex:
            saved = self.resources._load()
        require(canonical(saved['topology']) == canonical(self.document['topology']) and
                canonical(saved['routes']) == canonical(self.document['routes']), 'IO_RESOURCE_INSTALLATION_CHANGED')
        # Generation changes without the future receipt-gated provider bridge
        # deliberately make this first immutable installation unavailable.
        self.current_generations_supported = canonical(saved['generations']) == canonical(self.document['initialGenerations'])
        self.definitions = definitions(self.document)
        for instance,definition in self.definitions.items():
            binding = definition['binding']; adapter = binding['adapterId']
            if self.ready[adapter]:
                # Current invalidation/rebinding denies fresh policy checks but
                # must not prevent stopping/reconciling installed historical work.
                with journal._mutex:
                    _proof,historical = self.resources._retained_proof(saved,instance,binding['generation'])
                require(canonical(historical) == canonical(binding), 'IO_HISTORICAL_BINDING_CHANGED')
                continue
            digest = registry.publish_type(self.owner,canonical(definition['type']))
            enrolled = db.execute('SELECT * FROM reg_instances WHERE id=?',(instance,)).fetchone()
            identity = 'io-installation:' + hashlib.sha256((installation_digest(self.document)+'\0'+instance).encode()).hexdigest()
            if enrolled is None:
                registry.enroll(self.owner,instance,digest,identity_kind='simulation',identity_ref=identity)
            else:
                require(enrolled['type_digest'] == digest and enrolled['identity_kind'] == 'simulation' and enrolled['identity_ref'] == identity,
                        'IO_ENROLLMENT_CHANGED')
            old = db.execute('SELECT document,active FROM reg_bindings WHERE instance=?',(instance,)).fetchone()
            if old is None:
                self.resources.bind(self.owner,binding)
            else:
                require(old['active'] == 1 and bytes(old['document']) == canonical(binding), 'IO_BINDING_CHANGED')
                self.resources.history(self.owner,instance,binding['generation'])

    @staticmethod
    def route_documents(document):
        digest = installation_digest(document)
        return [{'profile':'hms.synthetic-io-route/1','driver':'sqlite-finite-io/1','adapterId':adapter,
                 'boardId':document['boardId'],'installationDigest':digest,'instances':instances}
                for adapter,instances in sorted(document['routes']['adapters'].items())]

    def mark_ready(self, adapter):
        require(adapter in self.ready, 'IO_ROUTE_UNINSTALLED')
        if not self.ready[adapter]:
            with self.journal._transaction():
                self.journal._now()
                self.journal._db.execute('UPDATE rt_adapters SET ready=1 WHERE adapter=?',(adapter,))
            self.ready[adapter] = True

    def board_filename(self):
        return 'synthetic-io-board-' + hashlib.sha256(self.document['boardId'].encode()).hexdigest() + '.db'
