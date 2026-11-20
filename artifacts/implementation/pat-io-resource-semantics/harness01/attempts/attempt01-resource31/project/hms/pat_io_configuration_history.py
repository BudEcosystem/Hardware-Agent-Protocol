"""Independent configuration and permission checks over retained finite-I/O data.

No Registry, compiler, provider, worker, database or filesystem calls. A trusted
grant-change plan is required separately from the untrusted evidence. Snapshot
agreement is not current-source attestation or a full qualification decision.
"""
from __future__ import annotations

import hashlib
import re

from .contracts import ContractError, SAFE_INTEGER, canonical, identifier, intent_digest, parse_json
from .pat_io_correspondence import IoCorrespondenceError, _Program
from .pat_io_board_history import IoHistoryError, _tables, digest
from .pat_io_transcript import IoTranscriptError, _read
from .resource_topology import ResourceTopologyError

PROFILE = 'hms.pat.io-configuration-record/0.1'
# Independent closed wire/storage schema: columns, cell types, primary-key width,
# maximum rows. The producer module is deliberately not imported.
SCHEMA = {
    'reg_meta': ('key,value', 'text text', 1, 3),
    'reg_types': ('digest,document', 'text blob-utf8', 1, 128),
    'reg_instances': ('id,deployment,type_digest,identity_kind,identity_ref,retired', 'text text text text text integer', 1, 128),
    'reg_capabilities': ('instance,capability', 'text text', 2, 2048),
    'reg_bindings': ('instance,generation,document,active', 'text text blob-utf8 integer', 1, 128),
    'reg_binding_history': ('instance,generation,digest,document', 'text text text blob-utf8', 2, 128),
    'reg_presence': ('instance,session,expires_ms,adapter', 'text text integer text', 1, 128),
    'reg_endpoint_sessions': ('instance,session', 'text text', 1, 128),
    'reg_session_history': ('instance,session', 'text text', 2, 512),
    'reg_observations': ('instance,property,document', 'text text blob-utf8', 2, 256),
    'reg_streams': ('instance,property,epoch', 'text text text', 2, 256),
    'reg_stream_history': ('instance,property,epoch', 'text text text', 3, 1024),
    'reg_grants': ('principal,deployment,target,verb', 'text text text text', 4, 4096),
    'reg_resource_requirements': ('adapter,profile', 'text text', 1, 16),
    'reg_resource_instances': ('instance,adapter,profile', 'text text text', 1, 128),
}


class IoConfigurationError(ValueError):
    def __init__(self, code):
        self.code = 'PAT_IO_CONFIGURATION_' + code
        super().__init__(self.code)


def require(value, code):
    if not value: raise IoConfigurationError(code)


def closed(value, keys, code='SHAPE'):
    require(type(value) is dict and set(value) == set(keys), code)


def integer(value, low=0, high=SAFE_INTEGER):
    require(type(value) is int and low <= value <= high, 'INTEGER')
    return value


def same(left, right):
    return canonical(left) == canonical(right)


def one(rows, code):
    require(len(rows) == 1, code)
    return rows[0]


def _configuration(transcript, legacy_refs, legacy_files, manifest, files):
    closed(manifest, {'profile','records','snapshots','configurationBytes','combinedRecords','combinedBytes',
                     'configurationAttested','independentOutcomeChecked','qualificationPassed'})
    require(manifest['profile'] == 'hms.pat.io-configuration-manifest/0.1' and
            all(manifest[k] is False for k in ('configurationAttested','independentOutcomeChecked','qualificationPassed')), 'MANIFEST')
    refs = manifest['records']; require(type(refs) is list and 1 <= len(refs) <= 4096 and type(files) is dict, 'BOUNDS')
    require(len(legacy_refs)+len(refs) <= 4096 and len(files) == len(refs), 'BOUNDS')
    require(all(type(v) is bytes and len(v) <= 65536 for v in files.values()), 'BOUNDS')
    total = sum(map(len, files.values())); combined = total + sum(map(len, legacy_files.values()))
    require(combined <= 16*1024*1024 and manifest['configurationBytes'] == integer(total) and
            manifest['combinedRecords'] == len(legacy_refs)+len(refs) and manifest['combinedBytes'] == combined, 'BOUNDS')
    for key in ('configurationBytes','combinedRecords','combinedBytes'): integer(manifest[key])
    docs, pages, used, snapshots = {}, {}, {'000000.json'}, []
    for number, ref in enumerate(refs):
        closed(ref, {'path','bytes','sha256'}, 'REFERENCE')
        name = '%06d.json' % number; require(ref['path'] == name and name in files, 'REFERENCE')
        raw = files[name]; integer(ref['bytes'], 1, 65536)
        require(ref['bytes'] == len(raw) and ref['sha256'] == hashlib.sha256(raw).hexdigest(), 'REFERENCE')
        doc = parse_json(raw); require(canonical(doc) == raw, 'CANONICAL')
        closed(doc, {'profile','kind','value'}); require(doc['profile'] == PROFILE, 'PROFILE')
        docs[name] = doc; value = doc['value']
        if number == 0:
            require(doc['kind'] == 'header' and same(value, {
                'transcriptProfile':transcript['profile'],'setupRecords':legacy_refs[:4],
                'registryMetadataKeys':['deployment','revision','version'],
                'sharedLimits':{'records':4096,'bytes':16*1024*1024,'documentBytes':65536,'schedulerTicks':2048}}), 'HEADER')
        elif doc['kind'] == 'table_page':
            closed(value, {'table','projection','columns','first','totalRows','rows'}, 'PAGE')
            name_table = value['table']; require(type(name_table) is str and name_table in SCHEMA, 'TABLE')
            fields, kinds, _, limit = SCHEMA[name_table]; kinds = kinds.split()
            require(value['columns'] == fields.split(',') and value['projection'] == (
                'public_registry_metadata' if name_table == 'reg_meta' else 'complete'), 'PAGE')
            integer(value['totalRows'], 0, limit); integer(value['first'], 0, value['totalRows'])
            require(value['first'] % 8 == 0 and type(value['rows']) is list and
                    len(value['rows']) == min(8,value['totalRows']-value['first']), 'PAGE')
            rows = []
            for cells in value['rows']:
                require(type(cells) is list and len(cells) == len(kinds), 'CELL')
                row = []
                for cell, kind in zip(cells, kinds):
                    closed(cell, {'type','value'}, 'CELL'); raw_cell = cell['value']
                    require(cell['type'] == kind, 'CELL')
                    if kind == 'integer': integer(raw_cell)
                    else:
                        require(type(raw_cell) is str and len(raw_cell.encode()) <= 65536, 'CELL')
                        if kind == 'blob-utf8':
                            raw_cell = raw_cell.encode(); require(canonical(parse_json(raw_cell)) == raw_cell, 'BLOB')
                    row.append(raw_cell)
                rows.append(tuple(row))
            pages[name] = rows
        elif doc['kind'] == 'resolver_configuration':
            closed(value, {'profile','resolverProfile','registrations','registrationIdentity'}, 'RESOLVER')
        elif doc['kind'] == 'snapshot':
            closed(value, {'checkpoint','phase','label','wallMs','monotonicMs','clockEpoch',
                           'authorityId','ownerEpoch','session','resolver','tables'}, 'SNAPSHOT')
            position = len(snapshots); require(position < len(transcript['checkpoints']), 'PAIRING')
            cp = transcript['checkpoints'][position]
            require(value['checkpoint'] == legacy_refs[cp['record']] and
                    all(value[k] == cp['value'][k] for k in ('phase','label','wallMs','monotonicMs','clockEpoch')), 'PAIRING')
            for key in ('phase','wallMs','monotonicMs','ownerEpoch'): integer(value[key])
            opening = next(d['value'] for d in reversed(transcript['records'][:cp['record']]) if d['kind']=='runtime_opened')
            require(all(value[k] == opening[k] for k in ('authorityId','ownerEpoch','session')), 'SESSION')
            require(value['clockEpoch'] == value['authorityId']+':'+str(value['ownerEpoch']), 'SESSION')
            def reference(r, kind):
                closed(r, {'path','bytes','sha256'}, 'REFERENCE'); path = r['path']
                require(type(path) is str and re.fullmatch(r'[0-9]{6}\.json',path) is not None, 'REFERENCE')
                index = int(path[:6]); require(index < number and refs[index] == r and docs[path]['kind'] == kind, 'REFERENCE')
                used.add(path); return docs[path]['value']
            resolver = reference(value['resolver'],'resolver_configuration')
            require(type(value['tables']) is list and len(value['tables']) == len(SCHEMA), 'TABLE')
            tables = {}
            for table in value['tables']:
                closed(table, {'table','projection','rowCount','pages'}, 'TABLE'); key = table['table']
                require(type(key) is str and key in SCHEMA and key not in tables, 'TABLE')
                fields, _, pk, limit = SCHEMA[key]; count = integer(table['rowCount'],0,limit)
                require(table['projection'] == ('public_registry_metadata' if key == 'reg_meta' else 'complete') and
                        type(table['pages']) is list and len(table['pages']) == max(1,(count+7)//8), 'TABLE')
                rows = []
                for r in table['pages']:
                    page = reference(r,'table_page')
                    require(page['table'] == key and page['first'] == len(rows) and page['totalRows'] == count, 'PAGE')
                    rows.extend(pages[r['path']])
                require(len(rows) == count and rows == sorted(rows) and len({r[:pk] for r in rows}) == count, 'ROW_ORDER')
                tables[key] = [dict(zip(fields.split(','), r)) for r in rows]
            used.add(name); snapshots.append({'reference':ref,'value':value,'tables':tables,'resolver':resolver,'checkpoint':cp})
        else: raise IoConfigurationError('KIND')
    require(len(snapshots) == len(transcript['checkpoints']) and set(files) == set(docs) == used, 'INCOMPLETE')
    require(type(manifest['snapshots']) is list and len(manifest['snapshots']) == len(snapshots) and
            manifest['snapshots'] == [{'checkpoint':s['value']['checkpoint'],'configuration':s['reference']} for s in snapshots], 'PAIRING')
    return snapshots


class _Authority:
    def __init__(self, value, deployment):
        closed(value, {'profile','principal','deployment','initialGrants','initialRegistryRevision','grantChanges'}, 'TRUSTED_AUTHORITY')
        require(value['profile'] == 'hms.pat.io-trusted-authority/0.1' and value['deployment'] == deployment, 'TRUSTED_AUTHORITY')
        self.principal = identifier(value['principal']); self.deployment = deployment
        self.initial_revision = integer(value['initialRegistryRevision'],1)
        self.grants = self.parse(value['initialGrants']); self.changes = value['grantChanges']; self.index = 0
        require(type(self.changes) is list and len(self.changes) <= 16, 'TRUSTED_AUTHORITY')
        last = 0
        for change in self.changes:
            closed(change, {'phase','label','grants'}, 'TRUSTED_AUTHORITY')
            integer(change['phase'],last+1,2048); last = change['phase']
            require(change['label'] in {'submit:before','drive:cycle:before','drive:procedure:before','drive:adapters:before'}, 'TRUSTED_AUTHORITY')
            self.parse(change['grants'])

    def parse(self, rows):
        require(type(rows) is list and len(rows) <= 4096, 'TRUSTED_AUTHORITY')
        result = []
        for row in rows:
            closed(row, {'principal','deployment','target','verb'}, 'TRUSTED_AUTHORITY')
            for key in ('principal','deployment'): identifier(row[key])
            require(row['deployment'] == self.deployment, 'TRUSTED_AUTHORITY')
            if row['target'] != '*': identifier(row['target'])
            verb = row['verb']; require(type(verb) is str and (verb in {'admin','read','cancel','stop','namespace'} or verb.startswith('invoke:')), 'TRUSTED_AUTHORITY')
            if verb.startswith('invoke:'): identifier(verb[7:])
            result.append(tuple(row[k] for k in ('principal','deployment','target','verb')))
        require(len(set(result)) == len(result), 'TRUSTED_AUTHORITY')
        return set(result)

    def checkpoint(self, value, rows):
        delta = 0
        if self.index < len(self.changes):
            change = self.changes[self.index]
            if (value['phase'],value['label']) == (change['phase'],change['label']):
                require(self.allowed('admin','*'), 'GRANT_CHANGE_AUTHORIZATION')
                next_grants = self.parse(change['grants']); delta = len(self.grants ^ next_grants)
                require(delta > 0, 'TRUSTED_AUTHORITY'); self.grants = next_grants; self.index += 1
            else: require(value['phase'] <= change['phase'], 'GRANT_PLAN')
        require(self.parse(rows) == self.grants, 'GRANTS')
        return delta

    def allowed(self, verb, instance):
        return (self.principal,self.deployment,'*','admin') in self.grants or (self.principal,self.deployment,instance,verb) in self.grants

    def invokes(self, instance, action):
        return self.allowed('read',instance) and self.allowed('invoke:'+action,instance)


def _static(program, authority, config, execution, resolver, *, checked_registrations=None):
    model = program.model; installation = model.installation; instances = set(model.routes)
    types = {r['digest']:parse_json(r['document']) for r in config['reg_types']}
    rows = {r['id']:r for r in config['reg_instances']}
    require(set(rows) == instances and len(types) == len(instances), 'INSTANCE_INVENTORY')
    bindings = {}; used_types = set()
    consumers = {(r['instanceId'],r['actionId']):r for r in installation['topology']['consumers']}
    for instance,row in rows.items():
        require(row['deployment'] == model.deployment and row['identity_kind'] == 'simulation' and row['retired'] == 0 and
                row['identity_ref'] == 'io-installation:'+hashlib.sha256((model.installation_digest+'\0'+instance).encode()).hexdigest(), 'INSTANCE')
        sha = row['type_digest']; require(sha in types, 'TYPE'); bundle = types[sha]; used_types.add(sha)
        closed(bundle, {'profile','td','execution'}, 'TYPE')
        require(bundle['profile'] == 'hms.type-bundle/0.1' and digest(b'HMS-TYPE-BUNDLE-v0.1',bundle) == sha, 'TYPE')
        contract = bundle['execution']; closed(contract, {'profile','actions','properties','capabilities','requiredFeatures'}, 'TYPE')
        require(contract['profile'] == 'hms.execution-contract/0.1' and contract['capabilities'] == ['sim:finite-gpio-pwm'] and
                contract['requiredFeatures'] == ['binding-generations/1','durable-operations/1','host-invoke/0.1','physical-evidence/1'], 'TYPE')
        expected_properties = {'ready':{'schema':{'type':'boolean'},'unit':'1','frame':None},
            'value':{'schema':{'type':'integer','minimum':0,'maximum':SAFE_INTEGER},'unit':'1',
                     'frame':'sim:finite-io-'+hashlib.sha256(instance.encode()).hexdigest()[:16]}}
        require(same(contract['properties'],expected_properties), 'TYPE')
        actions = {key[1]:detail for key,detail in model.details.items() if key[0] == instance}
        require(type(contract['actions']) is dict and set(contract['actions']) == set(actions), 'TYPE')
        schemas, resources = {}, {}
        for action,detail in actions.items():
            properties = {'durationMs':{'type':'integer','minimum':1,'maximum':5000}}
            if detail['primitive'] == 'gpio_pulse': properties['level'] = {'type':'integer','minimum':0,'maximum':1}
            else:
                env = detail['envelope']; properties.update(frequencyHz={'type':'integer','minimum':env['minFrequencyHz'],'maximum':env['maxFrequencyHz']},
                    dutyPermille={'type':'integer','minimum':0,'maximum':1000},resolutionBits={'type':'integer','const':env['resolutionBits']})
            schema = {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
            schemas[action] = schema; resources['io-root:'+action] = consumers[instance,action]['rootAliases'][0]
            expected = {'inputSchema':schema,'maxRunMs':5000,'effect':detail['primitive'],'completionEvidence':['simulation'],
                        'preconditions':[],'resources':['io-root:'+action]}
            require(same(contract['actions'][action],expected), 'TYPE')
        proof = model.proofs[instance]
        bindings[instance] = {'profile':'hms.binding/0.1','instanceId':instance,'generation':proof['bindingGeneration'],
            'typeDigest':sha,'calibrationRevision':'synthetic:finite-io:1','controlGeneration':'resource-control:'+proof['closureDigest'].removeprefix('sha256:'),
            'mode':'simulation','adapterId':model.routes[instance],'resourceMap':resources,'argumentSchemas':schemas}
    require(used_types == set(types), 'TYPE')
    target = model.target[0]; require(same(types[rows[target]['type_digest']],program.descriptor['type']) and
                                     same(bindings[target],model.binding), 'TRUSTED_DESCRIPTOR')
    require(config['reg_bindings'] == sorted([{'instance':i,'generation':b['generation'],'document':canonical(b),'active':1}
            for i,b in bindings.items()],key=lambda r:r['instance']), 'BINDING')
    require(config['reg_binding_history'] == sorted([{'instance':i,'generation':b['generation'],
            'digest':hashlib.sha256(canonical(b)).hexdigest(),'document':canonical(b)} for i,b in bindings.items()],key=lambda r:r['instance']), 'BINDING_HISTORY')
    require(config['reg_capabilities'] == [{'instance':i,'capability':'sim:finite-gpio-pwm'} for i in sorted(instances)], 'CAPABILITIES')
    require(config['reg_resource_requirements'] == [{'adapter':a,'profile':'hms.resource-roots/0.1'} for a in sorted(installation['routes']['adapters'])] and
            config['reg_resource_instances'] == [{'instance':i,'adapter':model.routes[i],'profile':'hms.resource-roots/0.1'} for i in sorted(instances)], 'RESOURCE_REQUIREMENTS')
    require(execution['rt_catalog'] == [{'singleton':1,'profile':'hms.adapter-catalog/io/1','legacy':0,'owner':authority.principal}] and
            execution['rt_io_installation'] == [{'singleton':1,'document':canonical(installation),'digest':model.installation_digest}], 'INSTALLATION')
    routes = []
    for adapter, members in sorted(installation['routes']['adapters'].items()):
        route = {'profile':'hms.synthetic-io-route/1','driver':'sqlite-finite-io/1','adapterId':adapter,
                 'boardId':installation['boardId'],'installationDigest':model.installation_digest,'instances':members}
        routes.append({'adapter':adapter,'document':canonical(route),'digest':hashlib.sha256(canonical(route)).hexdigest(),'ready':1})
    require(execution['rt_adapters'] == routes, 'ROUTES')
    topology, generations, routing = installation['topology'],installation['initialGenerations'],installation['routes']
    require(execution['rc_catalog'] == [{'singleton':1,'profile':'hms.resource-catalog/0.1','topology':canonical(topology),
        'topology_digest':digest(b'HMS-RESOURCE-TOPOLOGY-v0.1',topology),'routes':canonical(routing),
        'routes_digest':digest(b'HMS-RESOURCE-ROUTES-v0.1',routing),'current_revision':1}], 'RESOURCE_CATALOG')
    require(execution['rc_generations'] == [{'revision':1,'document':canonical(generations),'digest':digest(b'HMS-RESOURCE-GENERATIONS-v0.1',generations)}] and
            execution['rc_tokens'] == [{'node':n,'generation':g,'revision':1} for n,g in sorted(generations['nodes'].items())], 'GENERATIONS')
    require(execution['rc_proofs'] == [{'instance':i,'generation':p['bindingGeneration'],'revision':1,'document':canonical(p),
        'digest':digest(b'HMS-RESOURCE-BINDING-PROOF-v0.1',p),'binding_digest':hashlib.sha256(canonical(bindings[i])).hexdigest()}
        for i,p in sorted(model.proofs.items())], 'PROOFS')
    registration = {k:program.descriptor[k] for k in ('driverProfile','driverDigest','installationDigest','argumentMetadata')}
    registration.update(instanceId=target,typeDigest=model.binding['typeDigest'])
    registrations = [registration] if checked_registrations is None else checked_registrations
    require(registration in registrations, 'RESOLVER')
    identity = {'profile':'hms.pat.bindings.sqlite-finite-io/0.1','installationDigest':model.installation_digest,
                'driverDigest':installation['driverDigest'],'registrations':registrations}
    require(same(resolver, {'profile':'hms.pat.io-resolver-configuration/0.1','resolverProfile':identity['profile'],
        'registrations':registrations,'registrationIdentity':'sha256:'+hashlib.sha256(b'HMS-PAT-IO-BINDING-REGISTRATIONS-v1\0'+canonical(identity)).hexdigest()}), 'RESOLVER')
    return bindings


class _Dynamic:
    def __init__(self, model, bindings, revision):
        self.model, self.bindings = model, bindings
        self.sessions, self.stream_history, self.previous = set(), set(), {}
        self.revision = revision

    def checkpoint(self, snapshot, authority, execution, *, sample_ceiling=None):
        value, tables = snapshot['value'],snapshot['tables']; now = value['monotonicMs']
        if sample_ceiling is None: sample_ceiling = now
        else: require(type(sample_ceiling) is int and sample_ceiling > now, 'SAMPLE_CLOCK_CONTEXT')
        self.revision += authority.checkpoint(value,tables['reg_grants'])
        require(tables['reg_meta'] == [{'key':'deployment','value':self.model.deployment},
            {'key':'revision','value':str(self.revision)},{'key':'version','value':'hms.registry/resource-roots/0.1'}], 'REGISTRY_META')
        instances = sorted(self.bindings); session = value['session']
        board = {r['key']:r['value'] for r in execution['io_meta']}
        require(all(board.get(k) == v for k,v in {'authority':value['authorityId'],'ownerEpoch':str(value['ownerEpoch']),
            'clockEpoch':value['clockEpoch'],'session':session,'deployment':self.model.deployment,
            'installationDigest':self.model.installation_digest}.items()), 'BOARD_IDENTITY')
        self.sessions.update((i,session) for i in instances)
        require(tables['reg_endpoint_sessions'] == [{'instance':i,'session':session} for i in instances] and
                tables['reg_session_history'] == [{'instance':i,'session':s} for i,s in sorted(self.sessions)], 'SESSION_HISTORY')
        presence = {r['instance']:r for r in tables['reg_presence']}
        require(set(presence) == set(instances), 'PRESENCE')
        for i,r in presence.items():
            require(r['session'] == session and r['adapter'] == self.model.routes[i], 'PRESENCE')
            integer(r['expires_ms'],3000)
        keys = {(i,p) for i in instances for p in ('ready','value')}
        streams = {(r['instance'],r['property']):r['epoch'] for r in tables['reg_streams']}
        observations = {(r['instance'],r['property']):parse_json(r['document']) for r in tables['reg_observations']}
        require(set(streams) == set(observations) == keys, 'OBSERVATION_INVENTORY')
        effects = {r['instance']:r['activations'] for r in execution['io_effects']}
        require(set(effects) == set(instances), 'OBSERVATION_COUNTER')
        for key, epoch in streams.items():
            identifier(epoch); instance, prop = key; binding = self.bindings[instance]
            observation = observations[key]; sequence = integer(observation['sequence'],1)
            tick = integer(observation['receipt']['ticksMs'],0,sample_ceiling)
            require(presence[instance]['expires_ms'] == tick+3000, 'PRESENCE')
            sampled = observation['value']
            if prop == 'ready': require(sampled is True, 'OBSERVATION_VALUE')
            else: integer(sampled,0,integer(effects[instance]))
            expected = {'protocol':'hms.observation/0.1','instanceId':instance,'propertyId':prop,'value':sampled,
                'unit':'1','frame':None if prop=='ready' else 'sim:finite-io-'+hashlib.sha256(instance.encode()).hexdigest()[:16],
                'evidenceKind':'simulation','source':self.model.routes[instance],'quality':'valid',
                'streamEpoch':epoch,'sequence':sequence,'endpointSession':session,
                'controlGeneration':binding['controlGeneration'],'bindingGeneration':binding['generation'],
                'calibrationRevision':binding['calibrationRevision'],
                'acquisition':{'clockDomain':'synthetic-io-monotonic','clockEpoch':value['clockEpoch'],'ticksMs':tick},
                'receipt':{'clockDomain':'host-monotonic','clockEpoch':value['clockEpoch'],'ticksMs':tick},
                'acquisitionLatencyBoundMs':0,'clockUncertaintyMs':0,
                'measurementUncertainty':{'absolute':0,'unit':'1','method':'synthetic_exact_counter'}}
            require(same(observation,expected), 'OBSERVATION_PROVENANCE')
            previous = self.previous.get(key)
            if previous is None or previous['streamEpoch'] != epoch:
                require(value['label'] in {'baseline','after_reopen'} and sequence == 1 and
                        (instance,prop,epoch) not in self.stream_history, 'STREAM_HISTORY')
            else:
                require(sequence >= previous['sequence'] and tick >= previous['receipt']['ticksMs'], 'OBSERVATION_ORDER')
                if sequence == previous['sequence']: require(same(observation,previous), 'OBSERVATION_REPLAY')
                if prop == 'value': require(sampled >= previous['value'], 'OBSERVATION_COUNTER')
            self.stream_history.add((instance,prop,epoch)); self.previous[key] = observation
        require(tables['reg_stream_history'] == [{'instance':i,'property':p,'epoch':e} for i,p,e in sorted(self.stream_history)], 'STREAM_HISTORY')
        return presence


def _decisions(program, authority, snapshot, execution, presence, previous, calls, counters):
    """Check new authorization decisions, separately from complete event folding."""
    value = snapshot['value']; model = program.model; now = value['wallMs']
    operations = {r['id']:r for r in execution['operations']}
    parents = {r['id']:r for r in execution['pr_procedures']}
    links = {r['operation']:r for r in execution['io_dispatch_links']}
    namespaces = {r['token']:r for r in execution['namespaces']}
    old_ops,old_parents,old_links,old_namespaces = ({},{},{},{}) if previous is None else previous
    require(set(old_ops) <= set(operations) and set(old_parents) <= set(parents) and set(old_links) <= set(links), 'DECISION_HISTORY')
    for identity,row in operations.items():
        intent = parse_json(row['intent']); require(row['digest'] == intent_digest(intent), 'INTENT_DIGEST')
        integer(row['may_have_acted'],0,1)
        if identity in old_ops:
            require(all(row[k] == old_ops[identity][k] for k in ('id','principal','deployment','digest','intent','admission')), 'DECISION_CHANGED')
        if row['state'] == 'rejected_before_dispatch': require(row['may_have_acted'] == 0, 'REFUSAL_EFFECT')
        if row['may_have_acted']:
            require(identity in links and row['attempt_id'] is not None, 'DISPATCH_LINK')
    for identity,row in old_links.items(): require(links[identity] == row, 'DECISION_CHANGED')
    require(set(links) <= set(operations), 'DISPATCH_LINK')
    for identity,row in old_parents.items():
        require(all(parents[identity][k] == row[k] for k in ('id','principal','deployment','digest','request')), 'DECISION_CHANGED')
    def permitted(intent, *, live):
        model.intent(intent)
        if not authority.invokes(intent['instanceId'],intent['actionId']): return False
        if live:
            row = presence[intent['instanceId']]
            require(row['session'] == intent['endpointSession'] and now < row['expires_ms'], 'LIVE_BINDING')
        return True
    for row in list(operations.values())+list(parents.values())+list(namespaces.values()):
        require(row['principal'] == authority.principal and row['deployment'] == authority.deployment, 'PRINCIPAL')
    new_ops = set(operations)-set(old_ops); new_parents = set(parents)-set(old_parents); new_links = set(links)-set(old_links)
    require(set(old_namespaces) <= set(namespaces), 'DECISION_HISTORY')
    for token in set(namespaces)-set(old_namespaces):
        require(value['label'] == 'lower:after' and authority.allowed('namespace','*'), 'NAMESPACE_AUTHORIZATION')
        counters['namespaces'] += 1
    if new_ops or new_parents or new_links:
        require(value['label'].endswith(':after') and value['phase'] in calls and calls[value['phase']]['returned'], 'DECISION_PHASE')
    for identity in new_parents:
        require(value['label'] == 'submit:after', 'DECISION_PHASE')
        counters['parents'] += 1
        for step in parse_json(parents[identity]['request'])['procedure']['steps']:
            require(permitted(step['request']['intent'],live=False), 'PARENT_AUTHORIZATION'); counters['parentSteps'] += 1
    for identity in new_ops:
        require(value['label'] in {'drive:procedure:after','drive:cycle:after'}, 'DECISION_PHASE')
        row = operations[identity]; require(permitted(parse_json(row['intent']),live=True), 'ADMISSION_AUTHORIZATION')
        require(parse_json(row['admission'])['policy_revision'] == 'registry:'+dict((r['key'],r['value']) for r in snapshot['tables']['reg_meta'])['revision'], 'ADMISSION_REVISION')
        counters['admissions'] += 1
    for identity in new_links:
        require(identity in operations and value['label'] in {'drive:adapters:after','drive:cycle:after'}, 'DECISION_PHASE')
        require(permitted(parse_json(operations[identity]['intent']),live=True), 'DISPATCH_AUTHORIZATION'); counters['dispatches'] += 1
    for identity,row in operations.items():
        if row['state'] == 'rejected_before_dispatch' and (identity not in old_ops or old_ops[identity]['state'] != row['state']):
            require(identity in old_ops and old_ops[identity]['state'] == 'accepted', 'REFUSAL_CAUSE')
            event = one([r for r in execution['events'] if r['operation_id']==identity and r['kind']=='rejected_before_dispatch'],'REFUSAL_CAUSE')
            reason = parse_json(event['payload'])
            if reason == {'reason':'start_or_lease_expired'}:
                timing = parse_json(row['intent'])['timing']; admission = parse_json(row['admission'])
                require(now >= timing['latestStartUnixMs'] or now >= admission['lease_expires_ms'], 'REFUSAL_CAUSE')
            else:
                require(reason == {'reason':'ACCESS_DENIED'} and not permitted(parse_json(row['intent']),live=False), 'REFUSAL_CAUSE')
            require(value['label'] in {'drive:adapters:after','drive:cycle:after'} and row['may_have_acted'] == 0 and
                    row['attempt_id'] is None and identity not in links and
                    all(r['operation_id'] != identity for r in execution['claims']) and
                    all(r['operation'] != identity for r in execution['io_receipt_versions']), 'REFUSAL_EFFECT')
            require(event['time_ms'] == now, 'REFUSAL_CAUSE')
            counters['dispatchRefusals'] += 1
    if value['label'] == 'submit:after_error':
        call = calls[value['phase']]
        require(not call['returned'] and call['outcome']['exception'] == 'JournalError' and call['outcome']['code'] == 'ACCESS_DENIED' and
                not authority.invokes(*model.target) and not new_ops and not new_parents and not new_links, 'PARENT_REFUSAL')
        counters['parentRefusals'] += 1
    return operations,parents,links,namespaces


def _validated_configuration_history(references, files, configuration, configuration_files, *, expected_setup, expected_authority,
                                     conflict_profile=False, clock_profile=False, checked_sample_ceilings=None):
    """Inspect bounded acquired data; expected setup and grants must be trusted.

No filesystem/clock/SQL/provider operation occurs here. Full source attestation,
intermediate observation sampling and complete outcomes remain separate checks.
"""
    try:
        transcript = _read(references,files,expected_setup,conflict_profile=conflict_profile,clock_profile=clock_profile)
        checked_sample_ceilings = {} if checked_sample_ceilings is None else checked_sample_ceilings
        consumed_ceilings = set()
        snapshots = _configuration(transcript,references,files,configuration,configuration_files)
        program = _Program(expected_setup); model = program.model
        authority = _Authority(expected_authority,model.deployment)
        calls = {c['phase']:c for c in transcript['calls']}
        counters = dict(namespaces=0,parents=0,parentSteps=0,admissions=0,dispatches=0,parentRefusals=0,dispatchRefusals=0)
        static_config = ('reg_types','reg_instances','reg_capabilities','reg_bindings','reg_binding_history','reg_resource_requirements','reg_resource_instances')
        static_execution = ('rt_catalog','rt_adapters','rt_io_installation','rc_catalog','rc_generations','rc_tokens','rc_proofs')
        fixed = None; dynamic = None; previous = previous_snapshot = None
        permissions, denied = {}, []
        for snapshot in snapshots:
            execution = _tables(transcript,snapshot['checkpoint']); config = snapshot['tables']
            current = ([config[k] for k in static_config],[execution[k] for k in static_execution],snapshot['resolver'])
            if fixed is None:
                bindings = _static(program,authority,config,execution,snapshot['resolver'])
                fixed = current; dynamic = _Dynamic(model,bindings,authority.initial_revision)
            else: require(current == fixed, 'IMMUTABLE_CONFIGURATION')
            if previous_snapshot is not None and snapshot['value']['label'] == previous_snapshot['value']['label'] == 'test_final':
                require(config == previous_snapshot['tables'] and snapshot['resolver'] == previous_snapshot['resolver'] and
                        {k:v for k,v in snapshot['value'].items() if k!='checkpoint'} ==
                        {k:v for k,v in previous_snapshot['value'].items() if k!='checkpoint'}, 'FINAL_CHANGED')
            key = snapshot['checkpoint']['record']
            ceiling = checked_sample_ceilings.get(key)
            if key in checked_sample_ceilings: consumed_ceilings.add(key)
            presence = dynamic.checkpoint(snapshot,authority,execution,sample_ceiling=ceiling)
            previous = _decisions(program,authority,snapshot,execution,presence,previous,calls,counters)
            permission = authority.invokes(*model.target)
            permissions[snapshot['checkpoint']['record']] = {
                'invokes':permission, 'read':authority.allowed('read',model.target[0])}
            for row in execution['operations']:
                if row['state'] in {'dispatching','running','outcome_unknown'} and not permission:
                    denied.append((snapshot['checkpoint']['record'],row['id']))
            previous_snapshot = snapshot
        require(authority.index == len(authority.changes), 'GRANT_PLAN')
        require(consumed_ceilings == set(checked_sample_ceilings), 'UNUSED_CLOCK_CONTEXT')
        result = {'profile':'hms.pat.io-configuration-inspection/0.1','configurationHistoryChecked':True,
            'trustedGrantPlanMatched':True,'authorizationDecisionsChecked':True,
            'configurationSnapshots':len(snapshots),'configurationRecords':len(configuration['records']),
            'decisions':counters,'configurationAttested':False,'compilerIdentityAttested':False,
            'observationSampleSemanticsChecked':False,'activeRevocationChecked':False,'operationHistoryChecked':False,'procedureHistoryChecked':False,
            'boardHistoryChecked':False,'independentOutcomeChecked':False,'qualificationPassed':False}
        return transcript, snapshots, permissions, denied, result
    except IoConfigurationError: raise
    except IoTranscriptError as error: raise IoConfigurationError('TRANSCRIPT') from error
    except (IoCorrespondenceError,IoHistoryError,ResourceTopologyError,ContractError,KeyError,TypeError,ValueError,IndexError,UnicodeError,RecursionError) as error:
        raise IoConfigurationError('SHAPE') from error


def inspect_configuration_history(references, files, configuration, configuration_files, *, expected_setup, expected_authority):
    """Validate configuration decisions; active withdrawal needs the composed checker.

The private validated-data handoff never turns denied invocation into approval.
This standalone API preserves its original active-revocation refusal.
"""
    _, _, _, denied, result = _validated_configuration_history(
        references,files,configuration,configuration_files,
        expected_setup=expected_setup,expected_authority=expected_authority)
    require(not denied, 'ACTIVE_REVOCATION_UNSUPPORTED')
    return result
