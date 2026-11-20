"""Durable host binding for the original three-scenario compact C simulator.

This installed binding deliberately has no arbitrary-port or raw-command API.
Its clock assumption is the supplied same-host CLOCK_MONOTONIC fixture profile.
All command reservations, local fences and evidence share authority.db. The
endpoint process lifetime is owned by a separate trusted launcher.
"""
import copy
import hashlib
import json
from pathlib import Path
import struct
import uuid

from protocol.serial.frame import Frame, encode
from .contracts import canonical, SAFE_INTEGER
from .installations import definitions_for, legacy_installation, manifest_for, resource_map
from .endpoint_transport import LocalEndpointStream
from .endpoint_wire import (Control, Execution, Hello, Opcode, Operation, Reference,
                            Request, Receipt, Refusal, Retired, Status, WireError,
                            arm, bind, decode_response, hello)
from .journal import Context, Evidence, JournalError, TERMINAL
from .registry import validate_type_bundle

ADAPTER = 'endpoint:compact-simulation'
DEPLOYMENT = 'simulation:compact'
MANIFEST_DIGEST = 'f82db3e3066e987b7dbb702396a434d00cd1a7cec5af29f25a17791fc2219c4e'
MANIFEST_PATH = Path(__file__).resolve().parents[1] / 'protocol/endpoint/scenario-manifest.json'
_TERMINAL = {Execution.COMPLETED, Execution.FAILED, Execution.CANCELED, Execution.REJECTED_BEFORE_START}


def _require(value, code):
    if not value:
        raise JournalError(code)


def ensure_endpoint_schema(journal):
    """Atomically preserve legacy retained state while adding route keys."""
    db = journal._db
    with journal._transaction():
        present = [bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())
                   for name in ('ep_state', 'ep_commands', 'ep_packets')]
        _require(all(present) or not any(present), 'ENDPOINT_SCHEMA_INCOMPLETE')
        if all(present):
            routed = ['adapter' in {row['name'] for row in db.execute('PRAGMA table_info(' + name + ')')}
                      for name in ('ep_state', 'ep_commands', 'ep_packets')]
            _require(all(routed) or not any(routed), 'ENDPOINT_SCHEMA_INCOMPLETE')
            if all(routed):
                return
            rows = db.execute('SELECT singleton,document FROM ep_state').fetchall()
            _require(len(rows) == 1 and rows[0][0] == 1 and
                     db.execute('SELECT 1 FROM rt_adapters WHERE adapter=?', (ADAPTER,)).fetchone(),
                     'AMBIGUOUS_LEGACY_ENDPOINT')
            for name in ('ep_state', 'ep_commands', 'ep_packets'):
                db.execute('ALTER TABLE ' + name + ' RENAME TO ' + name + '_before_routes')
        db.execute('CREATE TABLE ep_state (adapter TEXT NOT NULL REFERENCES rt_adapters(adapter), singleton INTEGER NOT NULL CHECK(singleton=1), document BLOB NOT NULL, PRIMARY KEY(adapter,singleton))')
        db.execute('CREATE TABLE ep_commands (operation_id TEXT PRIMARY KEY REFERENCES operations(id), payload BLOB NOT NULL, tx_sequence INTEGER NOT NULL, mapping BLOB NOT NULL, receipt BLOB, retired INTEGER NOT NULL DEFAULT 0, retire_intent INTEGER NOT NULL DEFAULT 0, result BLOB, adapter TEXT NOT NULL REFERENCES rt_adapters(adapter))')
        db.execute('CREATE TABLE ep_packets (id INTEGER PRIMARY KEY, direction TEXT NOT NULL, boot TEXT NOT NULL, sequence INTEGER NOT NULL, wire BLOB NOT NULL, adapter TEXT NOT NULL REFERENCES rt_adapters(adapter))')
        db.execute('CREATE INDEX ep_commands_route ON ep_commands(adapter,retired)')
        db.execute('CREATE INDEX ep_packets_route ON ep_packets(adapter,id)')
        if all(present):
            db.execute('INSERT INTO ep_state SELECT ?,singleton,document FROM ep_state_before_routes', (ADAPTER,))
            db.execute('INSERT INTO ep_commands(rowid,operation_id,payload,tx_sequence,mapping,receipt,retired,retire_intent,result,adapter) SELECT rowid,operation_id,payload,tx_sequence,mapping,receipt,retired,retire_intent,result,? FROM ep_commands_before_routes', (ADAPTER,))
            db.execute('INSERT INTO ep_packets SELECT id,direction,boot,sequence,wire,? FROM ep_packets_before_routes', (ADAPTER,))
            for name in ('ep_state', 'ep_commands', 'ep_packets'):
                db.execute('DROP TABLE ' + name + '_before_routes')


class CompactSimulation:
    def __init__(self, runtime, fd, *, create=False, owner=None, installation=None, allow_offline=False):
        self.runtime, self.journal, self.registry = runtime, runtime.journal, runtime.registry
        self.db = self.journal._db
        self.installation = copy.deepcopy(installation or legacy_installation(True))
        self.adapter_id = self.installation['adapterId']
        self.definitions = definitions_for(self.installation)
        self.startup_error = None
        self.witness = None
        self.control = None
        self.last_refresh = None
        self.streams = {}
        data, self.manifest_digest = manifest_for(self.installation)
        self.manifest = json.loads(data)
        self.primitives = {p['instanceId']: p for p in self.manifest['primitives']}
        existing = self._one('SELECT 1 FROM ep_state WHERE adapter=?', (self.adapter_id,))
        if create and not existing:
            with self.journal._transaction():
                _require(owner is not None, 'INSTALLATION_OWNER_MISSING')
                state = dict(profile='hms.compact-simulation/1', manifest=self.manifest_digest, owner=owner.principal,
                             boot=None, tx=0, rx=0, call=0, fences=[0]*8, seenCall=0, seenFences=[0]*8,
                             lastTick='0', clockAnchor=None, desired=None, armPending=None, installed=False, fault=None)
                self.db.execute('INSERT INTO ep_state VALUES (?,1,?)', (self.adapter_id, canonical(state)))
        _require(create or existing, 'ENDPOINT_INSTALLATION_REQUIRED')
        _require(self._state()['manifest'] == self.manifest_digest and self.registry.deployment in {DEPLOYMENT, 'simulation:multi'},
                 'ENDPOINT_INSTALLATION_MISMATCH')
        self.stream = LocalEndpointStream(fd) if fd is not None else None
        try:
            self._enroll()
            self.refresh(force=True, initialize=True)
        except (JournalError, WireError) as error:
            self.startup_error = getattr(error, 'code', 'ENDPOINT_RESPONSE_INVALID')
            if not self._state()['installed'] and not allow_offline:
                self.close()
                raise
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None

    def _one(self, query, parameters=()):
        with self.journal._mutex:
            return self.db.execute(query, parameters).fetchone()

    def _all(self, query, parameters=()):
        with self.journal._mutex:
            return self.db.execute(query, parameters).fetchall()

    def _operation(self, operation_id):
        with self.journal._mutex:
            return self.journal._operation(operation_id)

    def _state(self):
        row = self._one('SELECT document FROM ep_state WHERE adapter=? AND singleton=1', (self.adapter_id,))
        _require(row is not None, 'ENDPOINT_INSTALLATION_REQUIRED')
        return json.loads(row[0])

    def _save(self, state):
        self.db.execute('UPDATE ep_state SET document=? WHERE adapter=? AND singleton=1', (canonical(state), self.adapter_id))

    def _fault(self, code):
        with self.journal._transaction():
            state = self._state()
            state['fault'] = state['fault'] or code
            self._save(state)
            self.db.execute("DELETE FROM reg_presence WHERE instance IN (SELECT instance FROM reg_bindings WHERE json_extract(CAST(document AS TEXT),'$.adapterId')=?)", (self.adapter_id,))
            for op in self.runtime.work_items(self.adapter_id, ('dispatching', 'running')):
                self._unknown(op, code)
        self.witness = None

    def _unknown(self, op, reason):
        if op['state'] in {'dispatching', 'running'}:
            self.db.execute("UPDATE operations SET state='outcome_unknown' WHERE id=?", (op['id'],))
            self.journal._event(op['id'], self.journal._record_now(), 'outcome_unknown', {'reason': reason})

    def _request(self, payload, *, state=None):
        # Caller holds the authority transaction; this only reserves bytes.
        state = state if state is not None else self._state()
        _require(state['tx'] < 2**32-1, 'ENDPOINT_COUNTER_EXHAUSTED')
        state['tx'] += 1
        boot = 0 if payload[1] == Opcode.HELLO else int(state['boot'])
        request = Request(Frame(1, 0, boot, state['tx'], payload))
        self.db.execute('INSERT INTO ep_packets(direction,boot,sequence,wire,adapter) VALUES (?,?,?,?,?)',
                        ('tx', str(boot), state['tx'], encode(request.frame), self.adapter_id))
        self._save(state)
        return request

    def _receive(self, frame):
        _require(frame.kind == 2 and frame.channel == 0 and frame.sequence > 0, 'ENDPOINT_FRAME_INVALID')
        with self.journal._transaction():
            state = self._state()
            _require(state['boot'] is None or frame.session == int(state['boot']), 'ENDPOINT_BOOT_CHANGED')
            _require(frame.sequence > state['rx'], 'ENDPOINT_RESPONSE_REPLAY')
            state['rx'] = frame.sequence
            self.db.execute('INSERT INTO ep_packets(direction,boot,sequence,wire,adapter) VALUES (?,?,?,?,?)',
                            ('rx', str(frame.session), frame.sequence, encode(frame), self.adapter_id))
            self._save(state)

    def _exchange(self, request, operation=None):
        try:
            _require(self.stream is not None, 'ENDPOINT_DISCONNECTED')
            frame = self.stream.exchange(request, self._receive)
            response = decode_response(frame, request, operation=operation, simulator_only=True)
            return response, frame
        except WireError as error:
            self._fault('ENDPOINT_RESPONSE_INVALID')
            raise JournalError('ENDPOINT_RESPONSE_INVALID') from error
        except JournalError as error:
            if error.code not in {'ENDPOINT_IO_TIMEOUT', 'ENDPOINT_IO_FAILURE', 'ENDPOINT_DISCONNECTED'}:
                self._fault(error.code)
            raise

    def _send(self, payload, operation=None):
        with self.journal._transaction():
            request = self._request(payload)
        return self._exchange(request, operation)

    def _context(self, boot, control):
        bindings = []
        for instance, action, document in self.definitions:
            digest = validate_type_bundle(document)
            schema = copy.deepcopy(document['execution']['actions'][action]['inputSchema'])
            if action == 'inspect':
                schema['properties']['partId']['maxLength'] = 16
            else:
                field = 'level' if action == 'set_level' else 'position'
                schema['properties'][field]['type'] = 'integer'
            roles = document['execution']['actions'][action]['resources']
            bindings.append(dict(profile='hms.binding/0.1', instanceId=instance,
                generation=f'compact-binding:{boot}:{control}', typeDigest=digest,
                calibrationRevision='synthetic:compact:1', controlGeneration=f'compact-control:{boot}:{control}',
                mode='simulation', adapterId=self.adapter_id, resourceMap=resource_map(self.installation, instance),
                argumentSchemas={action: schema}))
        document = dict(profile='hms.compact-context/1', manifest=self.manifest_digest,
                        incarnation=self.manifest['incarnationHex'], firmware=self.manifest['firmwareDigest'],
                        boot=str(boot), control=control, handle=1, bindings=bindings,
                        resourcePositions=self.manifest['resources'], clockProfile=self.manifest['clockProfile'])
        return document, hashlib.sha256(canonical(document)).hexdigest()

    def _enroll(self):
        state = self._state()
        owner = Context(state['owner'], self.registry.deployment)
        for instance, _action, document in self.definitions:
            digest = validate_type_bundle(document)
            if self._one('SELECT 1 FROM reg_types WHERE digest=?', (digest,)) is None:
                self.registry.publish_type(owner, canonical(document))
            row = self._one('SELECT * FROM reg_instances WHERE id=?', (instance,))
            identity = ('compact:' + instance if self.installation == legacy_installation(True) else
                        'compact:' + hashlib.sha256((self.adapter_id + '\0' + instance).encode()).hexdigest())
            if row is None:
                self.registry.enroll(owner, instance, digest, identity_kind='simulation', identity_ref=identity)
            else:
                _require(row['type_digest'] == digest and row['identity_kind'] == 'simulation' and
                         row['identity_ref'] == identity, 'INSTALLATION_ENROLLMENT_MISMATCH')

    def _install(self, state):
        owner = Context(state['owner'], self.registry.deployment)
        for (instance, _action, document), binding in zip(self.definitions, state['desired']['document']['bindings']):
            digest = self.registry.publish_type(owner, canonical(document))
            _require(digest == binding['typeDigest'], 'ENDPOINT_TYPE_DIGEST_MISMATCH')
            row = self._one('SELECT 1 FROM reg_instances WHERE id=?', (instance,))
            _require(row is not None, 'INSTALLATION_ENROLLMENT_MISMATCH')
            row = self._one('SELECT document FROM reg_bindings WHERE instance=?', (instance,))
            if row is None:
                self.registry.bind(owner, canonical(binding))
            else:
                _require(json.loads(row[0]) == binding, 'ENDPOINT_BINDING_CHANGED')
        with self.journal._transaction():
            state = self._state()
            state['installed'] = True
            self._save(state)

    def refresh(self, *, force=False, initialize=False):
        _require(self.stream is not None, 'ENDPOINT_DISCONNECTED')
        mono_before = self.registry._monotonic()
        if not force and self.last_refresh is not None and 0 <= mono_before-self.last_refresh < 200:
            return
        state = self._state()
        _require(state['fault'] is None, state['fault'] or 'ENDPOINT_INHIBITED')
        wall_before = self.journal.authority_time()
        response, _ = self._send(hello())
        mono_after, wall_after = self.registry._monotonic(), self.journal.authority_time()
        try:
            _require(isinstance(response, Hello), 'ENDPOINT_HELLO_REQUIRED')
            c = response.control
            _require(response.incarnation.hex() == self.manifest['incarnationHex'] and
                     response.firmware_digest.hex() == self.manifest['firmwareDigest'] and
                     response.manifest_digest.hex() == self.manifest_digest, 'ENDPOINT_IDENTITY_MISMATCH')
            _require(response.resource_count == 3 and response.max_arguments == 72 and response.max_result == 32,
                     'ENDPOINT_LIMIT_MISMATCH')
            _require(c.flags & 9 == 9 and not c.flags & 4, 'ENDPOINT_UNQUALIFIED')
            # Each clock brackets the endpoint sample independently. Database
            # synchronization and scheduling between the clock reads are part
            # of the uncertainty, not evidence of a rate fault. Persistent
            # interval intersection below detects incompatible clock mappings.
            _require(0 <= mono_after-mono_before <= 1000 and 0 <= wall_after-wall_before <= 1000,
                     'ENDPOINT_CLOCK_UNQUALIFIED')
            _require(c.now <= SAFE_INTEGER, 'ENDPOINT_CLOCK_RANGE')
            state = self._state()
            if state['boot'] is None:
                _require(initialize and c.context_handle == 0 and c.call_high_water == 0 and c.held_resources == 0 and
                         not any(response.fence_floors) and c.flags & 16 and not c.flags & 2, 'ENDPOINT_NOT_PRISTINE')
                document, digest = self._context(response.boot_epoch, c.control_generation+1)
                with self.journal._transaction():
                    state = self._state()
                    state['boot'] = str(response.boot_epoch)
                    state['desired'] = dict(document=document, digest=digest)
                    request = self._request(bind(c.control_generation, 1, bytes.fromhex(self.manifest_digest), bytes.fromhex(digest)), state=state)
                bound, _ = self._exchange(request)
                _require(isinstance(bound, Control), 'ENDPOINT_BIND_UNRESOLVED')
                c = bound
                state = self._state()
            desired = state['desired']
            _require(c.control_generation == desired['document']['control'] and c.context_handle == 1 and
                     c.context_digest.hex() == desired['digest'], 'ENDPOINT_CONTEXT_CHANGED')
            _require(c.call_high_water <= state['call'] and c.call_high_water >= state['seenCall'] and
                     all(old <= observed <= allocated for old, observed, allocated in
                         zip(state['seenFences'], response.fence_floors, state['fences'])) and
                     c.now >= int(state['lastTick']), 'ENDPOINT_COUNTER_DRIFT')
            # The HELLO sample precedes optional BIND; use its original timestamp
            # and bracket for the clock witness, never BIND's later clock value.
            sample_tick = response.control.now
            anchor = {'monoLo':sample_tick-mono_after-2, 'monoHi':sample_tick-mono_before+2,
                      'wallLo':wall_before-mono_after-2, 'wallHi':wall_after-mono_before+2}
            if c.flags & 16 and state['clockAnchor'] is not None:
                old = state['clockAnchor']
                for low, high in (('monoLo','monoHi'),('wallLo','wallHi')):
                    anchor[low] = max(anchor[low], old[low])
                    anchor[high] = min(anchor[high], old[high])
                    _require(anchor[low] <= anchor[high], 'ENDPOINT_CLOCK_RATE_LOST')
            self.witness = dict(profile=self.manifest['clockProfile'], ownerEpoch=self.journal.owner_epoch,
                boot=state['boot'], monoBefore=mono_before, monoAfter=mono_after,
                wallBefore=wall_before, wallAfter=wall_after, sampleTick=str(sample_tick),
                offsetLo=sample_tick-wall_after-2, offsetHi=sample_tick-wall_before+2,
                monoOffsetLo=sample_tick-mono_after-2, monoOffsetHi=sample_tick-mono_before+2,
                validUntilMono=mono_after+59000, wallMonoLo=wall_before-mono_after-2, wallMonoHi=wall_after-mono_before+2)
            with self.journal._transaction():
                state = self._state()
                if c.flags & 16:
                    state['clockAnchor'] = anchor
                state['seenCall'], state['seenFences'], state['lastTick'] = c.call_high_water, list(response.fence_floors), str(c.now)
                if state['armPending'] is not None:
                    _require(c.armed_until >= int(state['armPending']), 'ENDPOINT_ARM_UNRESOLVED')
                    state['armPending'] = None
                self._save(state)
            self.control = c
            if not c.flags & 16:
                self.witness = None
            if not state['installed']:
                self._install(state)
            self.last_refresh = mono_after
            self._publish_ready(sample_tick)
            self._restore_samples()
        except (JournalError, WireError) as error:
            code = getattr(error, 'code', 'ENDPOINT_RESPONSE_INVALID')
            if code not in {'ENDPOINT_IO_TIMEOUT','ENDPOINT_IO_FAILURE','ENDPOINT_DISCONNECTED'}:
                self._fault(code)
            else:
                self.witness = None
            raise

    def _publish(self, instance, property_id, value, sample_tick):
        self._publish_many([(instance, property_id, value, sample_tick)])

    def _publish_many(self, samples, *, presences=None):
        with self.journal._mutex:
            state = self._state()
            session = 'compact-boot:' + state['boot']
            streams = copy.deepcopy(self.streams)
            starts, observations = [], []
            for instance, property_id, value, sample_tick in samples:
                binding, active = self.registry._binding(instance)
                expected = next(b for b in state['desired']['document']['bindings'] if b['instanceId'] == instance)
                _require(active and binding == expected, 'ENDPOINT_BINDING_CHANGED')
                key = (instance, property_id)
                if key not in streams:
                    epoch = 'compact-stream:' + uuid.uuid4().hex
                    starts.append(dict(instance_id=instance, property_id=property_id, adapter_id=self.adapter_id,
                        endpoint_session=session, binding_generation=binding['generation'], stream_epoch=epoch))
                    streams[key] = [epoch, 0]
                stream = streams[key]
                stream[1] += 1
                _require(sample_tick <= SAFE_INTEGER, 'ENDPOINT_CLOCK_RANGE')
                earliest = sample_tick-self.witness['monoOffsetHi'] if self.witness is not None else None
                prop = self.registry._type(binding['typeDigest'])['execution']['properties'][property_id]
                observations.append(dict(instance_id=instance, property_id=property_id, adapter_id=self.adapter_id,
                    endpoint_session=session, binding_generation=binding['generation'], value=value,
                    evidence_kind='simulation', quality='valid', stream_epoch=stream[0], sequence=stream[1],
                    acquisition={'clockDomain':'compact-boot-monotonic','clockEpoch':session,'ticksMs':sample_tick},
                    acquisition_latency_bound_ms=None, clock_uncertainty_ms=0,
                    acquisition_host_earliest_ms=earliest,
                    measurement_uncertainty={'absolute':0,'unit':prop['unit'],'method':'synthetic_exact_commit'}))
            self.registry.report_adapter_snapshot(self.adapter_id, presences=presences or [],
                                                  streams=starts, observations=observations)
            self.streams = streams

    def _publish_ready(self, sample_tick):
        state = self._state()
        ready = (self.control.state in {1,2} and self.control.flags & 16 != 0 and
                 not self.control.flags & 2 and state['fault'] is None)
        presences = [dict(instance_id=instance, adapter_id=self.adapter_id,
            endpoint_session='compact-boot:'+state['boot'], ttl_ms=1000) for instance in self.primitives]
        self._publish_many([(instance, 'ready', ready, sample_tick) for instance in self.primitives],
                           presences=presences)

    def _restore_samples(self):
        # Rebuild this projection after a crash between receipt commit and
        # observation publication. Original acquisition ticks remain unchanged.
        if self.witness is None or self._state()['fault'] is not None:
            return
        samples = []
        for instance in self.primitives:
            row = self._one("SELECT result,o.verification FROM ep_commands c JOIN operations o ON o.id=c.operation_id WHERE c.adapter=? AND c.result IS NOT NULL AND json_extract(CAST(o.intent AS TEXT),'$.instanceId')=? ORDER BY c.rowid DESC LIMIT 1", (self.adapter_id, instance))
            if row is not None:
                if row['verification'] == 'disputed':
                    with self.journal._transaction():
                        self._invalidate_sample(instance)
                    self._fault('ENDPOINT_EVIDENCE_DISPUTED')
                    return
                output = json.loads(row[0])['output']
                samples.append((instance, 'value', output['value'], output['sampleTick']))
        if samples:
            self._publish_many(samples)

    def _invalidate_sample(self, instance):
        # Caller holds the receipt/projection transaction. Preserve the old
        # sample for audit, but it can no longer satisfy a valid/fresh read.
        for row in self.db.execute('SELECT property,document FROM reg_observations WHERE instance=?', (instance,)).fetchall():
            document = json.loads(row['document'])
            document['quality'] = 'invalid'
            self.db.execute('UPDATE reg_observations SET document=? WHERE instance=? AND property=?',
                            (canonical(document), instance, row['property']))

    def _clock(self, now):
        mono = self.registry._monotonic()
        w = self.witness
        _require(w is not None and w['ownerEpoch'] == self.journal.owner_epoch and
                 w['monoAfter'] <= mono < w['validUntilMono'] and
                 w['wallMonoLo'] <= now-mono <= w['wallMonoHi'], 'ENDPOINT_CLOCK_UNQUALIFIED')
        return w

    def _arguments(self, intent):
        p = self.primitives[intent['instanceId']]
        args = intent['arguments']
        if p['primitiveId'] == 0x1003:
            part = args['partId'].encode('utf-8')
            _require(type(args['recipe']) is int and args['recipe'] in (1, 2) and
                     1 <= len(part) <= 64, 'ENDPOINT_ARGUMENT_RANGE')
            return bytes((args['recipe'], len(part))) + part
        value = args[p['arguments']['field']]
        _require(type(value) is int and 0 <= value <= 100, 'ENDPOINT_ARGUMENT_RANGE')
        return bytes((value,))

    def validate_admission(self, intent, binding, resources):
        """Check the installed context without reserving counters or sending."""
        _require(self.stream is not None, 'ADAPTER_OFFLINE')
        state = self._state()
        p = self.primitives.get(intent['instanceId'])
        desired = state['desired']
        expected = next((b for b in desired['document']['bindings']
                         if b['instanceId'] == intent['instanceId']), None) if desired else None
        _require(p is not None and expected is not None and binding == expected and
                 intent['actionId'] == p['actionId'], 'ADAPTER_INSTALLATION_UNSUPPORTED')
        installed_resources = tuple(sorted(expected['resourceMap'][r['role']]
            for r in self.manifest['resources'] if p['resourceMask'] & (1 << r['position'])))
        _require(tuple(resources) == installed_resources and
                 intent['requiredEffect'] == 'capability_completion' and
                 intent['timing']['maxRunMs'] <= p['maxRunMs'], 'ADAPTER_INSTALLATION_UNSUPPORTED')
        self._arguments(intent)

    def _reserve(self, op, ticket, now):
        state = self._state()
        _require(state['fault'] is None and self.control is not None, 'ENDPOINT_INHIBITED')
        _require(not self._one('SELECT 1 FROM ep_commands WHERE adapter=? AND retired=0 LIMIT 1', (self.adapter_id,)), 'ENDPOINT_SLOT_BUSY')
        intent = op['intent']
        binding, active = self.registry._binding(intent['instanceId'])
        self.validate_admission(intent, binding, op['admission']['resources'])
        p = self.primitives[intent['instanceId']]
        expected = next(b for b in state['desired']['document']['bindings'] if b['instanceId'] == intent['instanceId'])
        _require(active and binding == expected and intent['actionId'] == p['actionId'], 'ENDPOINT_BINDING_CHANGED')
        arguments = self._arguments(intent)
        w = self._clock(now)
        t = intent['timing']
        _require(t['latestCompletionUnixMs']-now < w['validUntilMono']-self.registry._monotonic(), 'ENDPOINT_CLOCK_HORIZON')
        _require(state['call'] < 2**32-1, 'ENDPOINT_COUNTER_EXHAUSTED')
        state['call'] += 1
        local_fences = []
        fence_map = []
        claims = {c['resource']:c['fence'] for c in op['claims']}
        for resource in self.manifest['resources']:
            pos = resource['position']
            if p['resourceMask'] & (1 << pos):
                host_resource = expected['resourceMap'][resource['role']]
                _require(host_resource in claims and state['fences'][pos] < 2**32-1, 'ENDPOINT_FENCE_INVALID')
                state['fences'][pos] += 1
                local_fences.append(state['fences'][pos])
                fence_map.append(dict(position=pos, localFence=state['fences'][pos], resource=host_resource, hostFence=claims[host_resource]))
        reference = Reference(expected_control := state['desired']['document']['control'], 1, state['call'], bytes.fromhex(op['digest'].removeprefix('sha256:')))
        operation = Operation(reference, p['primitiveId'], p['resourceMask'], tuple(local_fences), arguments, 0,
            t['notBeforeUnixMs']+w['offsetHi'], t['latestStartUnixMs']+w['offsetLo'],
            t['latestCompletionUnixMs']+w['offsetLo'], t['maxRunMs'],
            min(op['admission']['lease_expires_ms']+w['offsetLo'], self.control.armed_until))
        _require(expected_control == self.control.control_generation and operation.lease_until <= self.control.armed_until,
                 'ENDPOINT_LEASE_INVALID')
        request = self._request(operation.payload(), state=state)
        mapping = dict(intentDigest=op['digest'], intent=op['intent'], admission=op['admission'], claims=op['claims'],
                       attemptId=ticket.attempt_id, ownerEpoch=ticket.owner_epoch, context=state['desired'],
                       boot=state['boot'], clockWitness=w, fences=fence_map)
        self.db.execute('INSERT INTO ep_commands(operation_id,payload,tx_sequence,mapping,adapter) VALUES (?,?,?,?,?)',
                        (op['id'], operation.payload(), request.frame.sequence, canonical(mapping), self.adapter_id))

    def _row(self, operation_id):
        return self._one('SELECT * FROM ep_commands WHERE operation_id=? AND adapter=?', (operation_id, self.adapter_id))

    def result(self, operation_id):
        row = self._row(operation_id)
        return json.loads(row['result']) if row and row['result'] is not None else None

    def _saved_receipt(self, row, operation):
        p = row['receipt']
        if p is None:
            return None
        opcode = Opcode(p[1] & 0x7f)
        payload = operation.payload() if opcode == Opcode.OP else operation.reference.payload(opcode)
        boot = int(json.loads(row['mapping'])['boot'])
        request = Request(Frame(1, 0, boot, int.from_bytes(p[2:6], 'big'), payload))
        return decode_response(Frame(2, 0, boot, 1, p), request, operation=operation, simulator_only=True)

    def _evidence(self, operation_id, revision, *assertions):
        return Evidence('simulation', self.adapter_id, f'compact-receipt:{operation_id}:{revision}', assertions)

    def _settle(self, operation_id, receipt, frame):
        _require(isinstance(receipt, Receipt), 'ENDPOINT_RECEIPT_REQUIRED')
        with self.journal._transaction():
            now = self.journal._record_now()
            row = self._row(operation_id)
            operation = Operation.parse(row['payload'])
            previous = self._saved_receipt(row, operation)
            mapping = json.loads(row['mapping'])
            op = self._operation(operation_id)
            _require(receipt.verification == 0 or receipt.execution in _TERMINAL, 'ENDPOINT_VERIFICATION_UNSUPPORTED')
            _require(mapping['intentDigest'] == op['digest'] and mapping['intent'] == op['intent'] and
                     mapping['admission'] == op['admission'], 'ENDPOINT_MAPPING_CONFLICT')
            if previous is not None:
                _require(receipt.revision >= previous.revision, 'ENDPOINT_RECEIPT_REPLAY')
                if receipt.revision == previous.revision:
                    _require(frame.payload[7:] == row['receipt'][7:], 'ENDPOINT_RECEIPT_CONFLICT')
                _require(not previous.may_have_acted or receipt.may_have_acted, 'ENDPOINT_START_CONTRADICTION')
                _require(receipt.held_resources & ~previous.held_resources == 0 and
                         receipt.queued_at == previous.queued_at and
                         (previous.started_at is None or receipt.started_at == previous.started_at),
                         'ENDPOINT_RECEIPT_CONFLICT')
                if previous.execution in _TERMINAL:
                    _require(receipt.execution == previous.execution and receipt.result == previous.result and
                             receipt.terminal_at == previous.terminal_at and receipt.evidence_kind == previous.evidence_kind and
                             receipt.cancellation == previous.cancellation and
                             (receipt.verification == previous.verification or receipt.verification == 3),
                             'ENDPOINT_TERMINAL_CONFLICT')
                elif previous.execution != Execution.QUEUED:
                    _require(receipt.execution not in {Execution.QUEUED, Execution.REJECTED_BEFORE_START},
                             'ENDPOINT_EXECUTION_REGRESSION')
                if previous.execution == Execution.OUTCOME_UNKNOWN:
                    _require(receipt.execution in {Execution.OUTCOME_UNKNOWN,Execution.FAILED,Execution.CANCELED},
                             'ENDPOINT_EXECUTION_REGRESSION')
                if previous.cancellation in {2,3}:
                    _require(receipt.cancellation in {2,3,4}, 'ENDPOINT_CANCELLATION_REGRESSION')
            output = None
            if receipt.execution == Execution.COMPLETED:
                _require(receipt.evidence_kind == 5 and len(receipt.result) == 12, 'ENDPOINT_RESULT_INVALID')
                sample, value = struct.unpack('>QI', receipt.result)
                p = self.primitives[op['intent']['instanceId']]
                _require(receipt.started_at <= sample <= receipt.terminal_at and sample <= SAFE_INTEGER and
                         0 <= value <= p['result']['maximum'], 'ENDPOINT_RESULT_INVALID')
                if p['primitiveId'] == 0x1003:
                    _require(value >= 1, 'ENDPOINT_RESULT_INVALID')
                else:
                    _require(value == op['intent']['arguments'][p['arguments']['field']], 'ENDPOINT_RESULT_CONFLICT')
                output = {'evidenceKind':'simulation', 'output':{'effectCommitted':True, 'value':value, 'sampleTick':sample}}
                _require(row['result'] is None or json.loads(row['result']) == output, 'ENDPOINT_RESULT_CONFLICT')
            else:
                _require(not receipt.result, 'ENDPOINT_RESULT_INVALID')
            state_assertion = {
                Execution.RUNNING: ('running', 'running'), Execution.COMPLETED: ('completed', 'completed'),
                Execution.FAILED: ('failed', 'failed'), Execution.CANCELED: ('canceled', 'terminated'),
                Execution.REJECTED_BEFORE_START: ('rejected_before_start', 'start_excluded')}
            if receipt.execution == Execution.OUTCOME_UNKNOWN:
                self._unknown(op, 'endpoint_outcome_unknown')
            elif receipt.execution in state_assertion:
                state, assertion = state_assertion[receipt.execution]
                assertions = [assertion]
                if not receipt.may_have_acted and assertion != 'start_excluded':
                    assertions.append('start_excluded')
                if receipt.verification == 3:
                    assertions.append('disputed')
                elif receipt.verification == 2:
                    assertions.append('verification_failed')
                evidence = self._evidence(operation_id, receipt.revision, *assertions)
                if op['state'] != state:
                    self.journal._execution(op, state, evidence, now)
                elif receipt.verification == 3 and op['verification'] != 'disputed':
                    self.journal.policy.evidence(op, evidence)
                    _require(op['may_have_acted'] and state in TERMINAL, 'ENDPOINT_INVALID_DISPUTE')
                    self.db.execute("UPDATE operations SET verification='disputed' WHERE id=?", (operation_id,))
                    self.journal._event(operation_id, now, 'evidence_dispute', {'evidence':evidence.payload()})
                elif receipt.verification == 2:
                    _require(op['verification'] == 'failed', 'ENDPOINT_VERIFICATION_CONFLICT')
            elif receipt.execution == Execution.QUEUED:
                _require(op['state'] in {'dispatching','outcome_unknown'}, 'ENDPOINT_EXECUTION_REGRESSION')
            op = self._operation(operation_id)
            if op['cancel_state'] == 'requested' and receipt.cancellation in {2,3}:
                accepted = receipt.cancellation == 2
                evidence = self._evidence(operation_id, receipt.revision, 'cancel_ack')
                self.journal.policy.evidence(op, evidence)
                self.db.execute('UPDATE operations SET cancel_state=? WHERE id=?',
                                ('acknowledged' if accepted else 'rejected', operation_id))
                self.journal._event(operation_id, now, 'cancel_ack', {'accepted':accepted,'evidence':evidence.payload()})
            if receipt.verification == 3:
                state = self._state()
                state['fault'] = state['fault'] or 'ENDPOINT_EVIDENCE_DISPUTED'
                self._save(state)
                self._invalidate_sample(op['intent']['instanceId'])
                self.db.execute("DELETE FROM reg_presence WHERE instance IN (SELECT instance FROM reg_bindings WHERE json_extract(CAST(document AS TEXT),'$.adapterId')=?)", (self.adapter_id,))
            elif receipt.execution in _TERMINAL and receipt.held_resources == 0 and op['claims']:
                _require(op['state'] in TERMINAL and op['verification'] != 'disputed', 'ENDPOINT_QUIESCENCE_INVALID')
                evidence = self._evidence(operation_id, receipt.revision, 'resources_quiescent')
                self.journal.policy.evidence(op, evidence)
                self.db.execute('DELETE FROM claims WHERE operation_id=?', (operation_id,))
                self.journal._event(operation_id, now, 'resources_released', {'evidence':evidence.payload()})
            self.db.execute('UPDATE ep_commands SET receipt=?, result=? WHERE operation_id=? AND adapter=?',
                            (frame.payload, canonical(output) if output is not None else None, operation_id, self.adapter_id))
        if output is not None and receipt.verification != 3 and (previous is None or previous.result != receipt.result):
            self._publish(op['intent']['instanceId'], 'value', output['output']['value'], output['output']['sampleTick'])

    def _retire(self, row, operation):
        with self.journal._transaction():
            row = self._row(row['operation_id'])
            receipt = self._saved_receipt(row, operation)
            op = self._operation(row['operation_id'])
            _require(receipt is not None and receipt.execution in _TERMINAL and receipt.held_resources == 0 and
                     receipt.verification != 3 and op['state'] in TERMINAL and not op['claims'] and
                     op['verification'] != 'disputed', 'ENDPOINT_RETIRE_FORBIDDEN')
            self.db.execute('UPDATE ep_commands SET retire_intent=1 WHERE operation_id=? AND adapter=?', (op['id'], self.adapter_id))
            request = self._request(operation.reference.payload(Opcode.RETIRE))
        response, _ = self._exchange(request)
        if isinstance(response, Retired):
            with self.journal._transaction():
                self.db.execute('UPDATE ep_commands SET retired=1 WHERE operation_id=? AND adapter=?', (op['id'], self.adapter_id))
        else:
            raise JournalError('ENDPOINT_RETIRE_UNRESOLVED')

    def _reconcile_row(self, row):
        # Read cancellation and reserve the exact control command in one TX.
        # Another thread's uncommitted cancellation must not select an opcode.
        with self.journal._transaction():
            row = self._row(row['operation_id'])
            _require(row is not None, 'ENDPOINT_MAPPING_MISSING')
            operation = Operation.parse(row['payload'])
            op = self._operation(row['operation_id'])
            opcode = Opcode.CANCEL if op['cancel_state'] == 'requested' and not row['retire_intent'] else Opcode.QUERY
            request = self._request(operation.reference.payload(opcode))
        response, frame = self._exchange(request, operation)
        if isinstance(response, Refusal):
            if row['retire_intent'] and response.status == Status.OLD_OR_FORGOTTEN:
                with self.journal._transaction():
                    row = self._row(op['id'])
                    op = self._operation(op['id'])
                    previous = self._saved_receipt(row, operation)
                    _require(row['retire_intent'] and previous is not None and
                             previous.execution in _TERMINAL and previous.held_resources == 0 and
                             previous.verification != 3 and op['state'] in TERMINAL and not op['claims'] and
                             op['verification'] != 'disputed', 'ENDPOINT_RETIRE_FORBIDDEN')
                    self.db.execute('UPDATE ep_commands SET retired=1 WHERE operation_id=? AND adapter=?', (op['id'], self.adapter_id))
                return
            with self.journal._transaction():
                self._unknown(self._operation(op['id']), 'endpoint_receipt_unavailable')
            # Refusal/forgotten/NOT_SEEN cannot prove exclusion after handoff.
            return
        self._settle(op['id'], response, frame)
        if response.execution in _TERMINAL and response.held_resources == 0 and response.verification != 3:
            self._retire(self._row(op['id']), operation)

    def _arm_for(self, op):
        # Serialize authority/state checks through the controller handoff. A
        # caller may have canceled the accepted item since tick selected it.
        with self.journal._mutex:
            current = self._operation(op['id'])
            _require(current['state'] == 'accepted', 'NOT_DISPATCHABLE')
            now = self.journal.authority_time()
            timing = current['intent']['timing']
            if now >= min(timing['latestStartUnixMs'], current['admission']['lease_expires_ms']):
                self.journal.reject_before_dispatch(current['id'], 'start_or_lease_expired')
                raise JournalError('NOT_DISPATCHABLE')
            _require(now >= timing['notBeforeUnixMs'], 'NOT_YET_STARTABLE')
            context = Context(current['principal'], current['deployment'])
            self.runtime.policy.authorize(context, 'invoke', current['intent']['instanceId'])
            self.runtime.policy.recheck(context, current, now)
            self._arm_installed(current, now)

    def _arm_installed(self, op, now):
        # Caller holds the authority mutex. claim_dispatch repeats admission
        # inside its reservation transaction before any OP can be handed off.
        w = self._clock(now)
        _require(self.control.state in {1,2} and self.control.flags & 16 and not self.control.flags & 2,
                 'ENDPOINT_NOT_ELIGIBLE')
        until = op['admission']['lease_expires_ms']+w['offsetLo']
        _require(until > self.control.now and until-self.control.now <= 59000, 'ENDPOINT_LEASE_HORIZON')
        if self.control.state == 2 and self.control.armed_until >= until:
            return
        with self.journal._transaction():
            state = self._state()
            _require(state['armPending'] is None, 'ENDPOINT_ARM_UNRESOLVED')
            state['armPending'] = str(until)
            request = self._request(arm(state['desired']['document']['control'], 1,
                bytes.fromhex(state['desired']['digest']), until), state=state)
        response, _ = self._exchange(request)
        _require(isinstance(response, Control), 'ENDPOINT_ARM_UNRESOLVED')
        with self.journal._transaction():
            state = self._state()
            state['armPending'] = None
            self._save(state)
        self.control = response

    def tick(self):
        try:
            try:
                now = self.journal.authority_time()
            except JournalError:
                now = None
            if now is not None:
                for op in self.runtime.work_items(self.adapter_id, ('accepted',)):
                    if now >= min(op['intent']['timing']['latestStartUnixMs'], op['admission']['lease_expires_ms']):
                        self.journal.reject_before_dispatch(op['id'], 'start_or_lease_expired')
            _require(self.stream is not None, 'ENDPOINT_DISCONNECTED')
            # Queries/cancellation remain useful if current host clock qualification
            # is lost. A clock failure must not authorize a new command.
            refresh_error = None
            fault = self._state()['fault']
            if fault is None:
                try:
                    self.refresh()
                except JournalError as error:
                    refresh_error = error
            fault = self._state()['fault']
            # Keep exact-reference recovery available after evidence disputes or
            # loss of execution eligibility, but never follow a changed route,
            # boot, context or corrupt/replayed stream as a trusted endpoint.
            if fault is not None and fault not in {'ENDPOINT_EVIDENCE_DISPUTED','ENDPOINT_UNQUALIFIED','ENDPOINT_CLOCK_UNQUALIFIED','ENDPOINT_CONTEXT_CHANGED'}:
                raise JournalError(fault)
            rows = self._all('SELECT * FROM ep_commands WHERE adapter=? AND retired=0 ORDER BY rowid LIMIT 2', (self.adapter_id,))
            _require(len(rows) <= 1, 'ENDPOINT_SLOT_CONFLICT')
            for row in rows:
                self._reconcile_row(row)
            for op in self.runtime.work_items(self.adapter_id, ('dispatching','running','outcome_unknown')):
                _require(self._row(op['id']) is not None, 'ENDPOINT_MAPPING_MISSING')
            if refresh_error is not None:
                raise refresh_error
            if fault is not None:
                raise JournalError(fault)
            if self._one('SELECT 1 FROM ep_commands WHERE adapter=? AND retired=0 LIMIT 1', (self.adapter_id,)):
                return
            for op in self.runtime.work_items(self.adapter_id, ('accepted',), limit=1,
                                              startable_ms=self.journal.authority_time()):
                # Obtain fresh endpoint identity, counters, clock and eligibility
                # before installing this admission's bounded control lease.
                try:
                    self.refresh(force=True)
                    self._arm_for(op)
                    ticket = self.journal.claim_dispatch(op['id'], _reserve=self._reserve)
                except (JournalError, WireError) as error:
                    code = getattr(error, 'code', 'ENDPOINT_ENVELOPE_INVALID')
                    if code in {'NOT_YET_STARTABLE','NOT_DISPATCHABLE','ENDPOINT_SLOT_BUSY'}:
                        return
                    if self._operation(op['id'])['state'] == 'accepted':
                        self.journal.reject_before_dispatch(op['id'], code)
                    raise
                if ticket is None:
                    return
                row = self._row(op['id'])
                operation = Operation.parse(row['payload'])
                request = Request(Frame(1,0,int(json.loads(row['mapping'])['boot']),row['tx_sequence'],row['payload']))
                try:
                    response, frame = self._exchange(request, operation)
                    if isinstance(response, Receipt):
                        self._settle(op['id'], response, frame)
                    else:
                        with self.journal._transaction():
                            self._unknown(self._operation(op['id']), 'endpoint_handoff_unresolved')
                except (JournalError, WireError):
                    with self.journal._transaction():
                        self._unknown(self._operation(op['id']), 'endpoint_handoff_unresolved')
                    raise
        except JournalError as error:
            transient = {'ENDPOINT_IO_TIMEOUT','ENDPOINT_IO_FAILURE','ENDPOINT_DISCONNECTED',
                         'CLOCK_REGRESSION','CLOCK_UNAVAILABLE','ENDPOINT_CLOCK_UNQUALIFIED',
                         'ENDPOINT_LEASE_HORIZON','ENDPOINT_CLOCK_HORIZON','ENDPOINT_ENVELOPE_INVALID',
                         'ADAPTER_INSTALLATION_UNSUPPORTED','ADAPTER_OFFLINE',
                         'NOT_YET_STARTABLE','NOT_DISPATCHABLE','ENDPOINT_SLOT_BUSY'}
            if error.code not in transient and self._state()['fault'] is None:
                self._fault(error.code)
            raise
