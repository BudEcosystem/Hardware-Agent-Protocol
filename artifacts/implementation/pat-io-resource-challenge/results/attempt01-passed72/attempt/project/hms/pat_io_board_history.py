"""Independent finite GPIO/PWM model-history checks over acquired transcripts.

No provider/worker imports and no I/O. This is one semantic component, not the
authority/procedure/event oracle or a qualification/promotion decision.
"""
from __future__ import annotations

import hashlib

from .contracts import ContractError, SAFE_INTEGER, canonical, identifier, intent_digest, parse_invoke, parse_json
from .pat_io_transcript import IoTranscriptError, SCHEMAS, _read
from .resource_topology import ResourceTopologyError, binding_proof, parse_generations, parse_topology


class IoHistoryError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(condition, code):
    if not condition:
        raise IoHistoryError(code)


def closed(value, fields, code='PAT_IO_HISTORY_SHAPE'):
    require(type(value) is dict and set(value) == set(fields), code)


def integer(value, low=0, high=SAFE_INTEGER):
    require(type(value) is int and low <= value <= high, 'PAT_IO_HISTORY_INTEGER')
    return value


def same(left, right):
    return canonical(left) == canonical(right)


def digest(domain, value):
    return 'sha256:' + hashlib.sha256(domain + b'\0' + canonical(value)).hexdigest()


class _Model:
    def __init__(self, setup):
        self.installation = setup['installation']
        value = self.installation
        closed(value, {'profile', 'driver', 'driverDigest', 'boardId', 'topology', 'initialGenerations', 'routes', 'handlers'})
        require(value['profile'] == 'hms.synthetic-io-installation/1' and value['driver'] == 'sqlite-finite-io/1', 'PAT_IO_HISTORY_INSTALLATION')
        self.installation_digest = digest(b'HMS-SYNTHETIC-IO-INSTALLATION-v1', value)
        topology = parse_topology(value['topology'])
        require(same(topology, value['topology']), 'PAT_IO_HISTORY_TOPOLOGY')
        generations = parse_generations(topology, value['initialGenerations'])
        require(generations['revision'] == 1, 'PAT_IO_HISTORY_GENERATIONS')
        self.deployment = topology['deployment']
        require(self.deployment.startswith('simulation:'), 'PAT_IO_HISTORY_INSTALLATION')
        nodes, aliases, atoms = topology['nodes'], topology['aliases'], topology['atoms']
        require([n for n in nodes if nodes[n]['kind'] == 'board'] == [value['boardId']], 'PAT_IO_HISTORY_INSTALLATION')
        atom_by_node = {a['node']: key for key, a in atoms.items() if a['purpose'] == 'exclusive_hardware'}
        consumers = {(c['instanceId'], c['actionId']): c for c in topology['consumers']}
        routes = value['routes']; closed(routes, {'profile', 'adapters'})
        require(routes['profile'] == 'hms.resource-route-inventory/0.1' and type(routes['adapters']) is dict and
                1 <= len(routes['adapters']) <= 16, 'PAT_IO_HISTORY_ROUTES')
        self.routes = {}
        for adapter, instances in routes['adapters'].items():
            identifier(adapter)
            require(type(instances) is list and 1 <= len(instances) <= 128, 'PAT_IO_HISTORY_ROUTES')
            for instance in instances:
                identifier(instance)
                require(instance not in self.routes, 'PAT_IO_HISTORY_ROUTES')
                self.routes[instance] = adapter
        self.details, self.idle = {}, {}
        handlers = value['handlers']
        require(type(handlers) is list and 1 <= len(handlers) <= 128, 'PAT_IO_HISTORY_HANDLERS')
        # Alias expansion is independently compared with the typed physical nodes.
        # Shared topology parsing bounds and validates the graph before this walk.
        cache = {}
        def expand(root):
            if root not in cache:
                found = set()
                for item in aliases[root]['includes']:
                    found.update(expand(item) if item in aliases else {item})
                cache[root] = found
            return cache[root]
        for handler in handlers:
            closed(handler, {'instanceId', 'actionId', 'primitive'})
            key = (handler['instanceId'], handler['actionId'])
            require(key in consumers and key not in self.details, 'PAT_IO_HISTORY_HANDLERS')
            roots = consumers[key]['rootAliases']
            require(len(roots) == 1, 'PAT_IO_HISTORY_FOOTPRINT')
            access = nodes[aliases[roots[0]]['node']]
            primitive = handler['primitive']
            if primitive == 'gpio_pulse':
                require(access['kind'] == 'gpio_access', 'PAT_IO_HISTORY_FOOTPRINT')
                touched = {access['properties']['pin']}
                envelope = None
            else:
                require(primitive == 'pwm_burst' and access['kind'] == 'pwm_access', 'PAT_IO_HISTORY_FOOTPRINT')
                channel = access['properties']['channel']
                fields = nodes[channel]['properties']
                require(nodes[channel]['kind'] == 'timer_channel', 'PAT_IO_HISTORY_FOOTPRINT')
                touched = {channel, fields['timer'], fields['pin']}
                envelope = nodes[fields['timer']]['properties']
                require(nodes[fields['timer']]['kind'] == 'timer' and envelope['resolutionBits'] == 8 and
                        100 <= envelope['minFrequencyHz'] <= envelope['maxFrequencyHz'] <= 10000, 'PAT_IO_HISTORY_PWM_ENVELOPE')
            claims = sorted(atom_by_node[n] for n in touched)
            require(set(claims) == expand(roots[0]), 'PAT_IO_HISTORY_FOOTPRINT')
            for atom in claims:
                node = nodes[atoms[atom]['node']]
                kind = node['kind']
                if kind == 'pin':
                    electrical = node['properties']['electrical']
                    mode = 'push_pull_output' if primitive == 'gpio_pulse' else 'pwm_output'
                    require(electrical['evidenceMode'] == 'simulation' and electrical['idleMode'] == 'high_impedance' and
                            mode in electrical['modes'], 'PAT_IO_HISTORY_ELECTRICAL')
                    state = {'kind': 'pin', 'mode': 'high_impedance', 'level': None}
                elif kind == 'timer':
                    state = {'kind': 'timer', 'enabled': False, 'frequencyHz': 0, 'resolutionBits': 0}
                else:
                    require(kind == 'timer_channel', 'PAT_IO_HISTORY_FOOTPRINT')
                    state = {'kind': 'timer_channel', 'enabled': False, 'dutyPermille': 0}
                self.idle[atom] = state
            self.details[key] = {'primitive': primitive, 'claims': claims, 'envelope': envelope}
        require(set(self.details) == set(consumers) and set(self.routes) == {k[0] for k in consumers}, 'PAT_IO_HISTORY_HANDLERS')
        self.proofs = {instance: binding_proof(topology, generations, instance) for instance in self.routes}
        for key, detail in self.details.items():
            require(self.proofs[key[0]]['expandedClaims'][key[1]] == detail['claims'], 'PAT_IO_HISTORY_FOOTPRINT')
        descriptor = setup['original_descriptor']
        self.binding = descriptor['binding']
        self.target = (self.binding['instanceId'], setup['static_contract']['actionId'])
        require(self.target in self.details and self.binding['mode'] == 'simulation' and
                self.binding['adapterId'] == self.routes[self.target[0]] and
                self.binding['generation'] == self.proofs[self.target[0]]['bindingGeneration'] and
                self.binding['controlGeneration'] == 'resource-control:' + self.proofs[self.target[0]]['closureDigest'].removeprefix('sha256:') and
                descriptor['driverProfile'] == value['driver'] and descriptor['driverDigest'] == value['driverDigest'] and
                descriptor['installationDigest'] == self.installation_digest, 'PAT_IO_HISTORY_BINDING')

    def intent(self, value):
        parse_invoke(canonical({'protocol': 'hms.invoke/0.1', 'replayNamespace': 'history:validation',
                                'operationKey': 'history:validation', 'intent': value}))
        key = (value['instanceId'], value['actionId'])
        # The current trial profile has one PAT actor. Auxiliary actors require
        # an explicit future trusted manifest; they cannot be inferred from rows.
        require(key == self.target and value['requiredEffect'] == 'capability_completion', 'PAT_IO_HISTORY_ACTOR')
        for left, right in [('descriptionDigest', 'typeDigest'), ('bindingGeneration', 'generation'),
                            ('controlGeneration', 'controlGeneration'), ('calibrationRevision', 'calibrationRevision')]:
            require(value[left] == self.binding[right], 'PAT_IO_HISTORY_BINDING')
        integer(value['timing']['maxRunMs'], 1, 5000)
        detail, args = self.details[key], value['arguments']
        expected = {'durationMs', 'level'} if detail['primitive'] == 'gpio_pulse' else {'durationMs', 'frequencyHz', 'dutyPermille', 'resolutionBits'}
        closed(args, expected, 'PAT_IO_HISTORY_ARGUMENTS')
        integer(args['durationMs'], 1, 5000)
        if detail['primitive'] == 'gpio_pulse':
            integer(args['level'], 0, 1)
        else:
            env = detail['envelope']
            integer(args['frequencyHz'], env['minFrequencyHz'], env['maxFrequencyHz'])
            integer(args['dutyPermille'], 0, 1000)
            integer(args['resolutionBits'], env['resolutionBits'], env['resolutionBits'])
        active = {}
        for atom in detail['claims']:
            kind = self.idle[atom]['kind']
            if kind == 'pin':
                active[atom] = {'kind': kind, 'mode': 'push_pull_output' if detail['primitive'] == 'gpio_pulse' else 'pwm_output',
                                'level': args['level'] if detail['primitive'] == 'gpio_pulse' else None}
            elif kind == 'timer':
                active[atom] = {'kind': kind, 'enabled': True, 'frequencyHz': args['frequencyHz'], 'resolutionBits': args['resolutionBits']}
            else:
                active[atom] = {'kind': kind, 'enabled': True, 'dutyPermille': args['dutyPermille']}
        return detail, active


def _tables(transcript, cp):
    return {table: [dict(zip(SCHEMAS[store][table][0].split(','), row))
                    for ref in names for row in transcript['pages'][ref]['rows']]
            for (store, table), names in cp['tables'].items()}


def _claims(value, expected):
    require(type(value) is list and len(value) == len(expected), 'PAT_IO_HISTORY_CLAIMS')
    result = {}
    for row, atom in zip(value, expected):
        closed(row, {'resource', 'fence'}, 'PAT_IO_HISTORY_CLAIMS')
        require(row['resource'] == atom, 'PAT_IO_HISTORY_CLAIMS')
        result[atom] = integer(row['fence'], 1)
    return result


def _cause(reason, receipt, operation, now, label, opened):
    timing = receipt['intent']['timing']
    if reason == 'board_owner_reopened':
        valid = label == 'after_reopen' and opened['ownerEpoch'] > receipt['ownerEpoch']
    elif reason == 'client_cancel':
        valid = operation['cancel_state'] in {'requested', 'acknowledged', 'confirmed'}
    elif reason == 'execution_deadline':
        valid = now >= timing['latestCompletionUnixMs'] or now - receipt['budgetOriginMonoMs'] >= timing['maxRunMs']
    elif reason == 'lease_expired':
        valid = now >= operation['admission_value']['lease_expires_ms'] and now < timing['latestCompletionUnixMs'] and now - receipt['budgetOriginMonoMs'] < timing['maxRunMs']
    else:
        raise IoHistoryError('PAT_IO_HISTORY_CAUSE_UNSUPPORTED')
    require(valid, 'PAT_IO_HISTORY_CANCEL_CAUSE')


def _reduce(transcript, setup, *, checked_causes=None, checked_no_starts=None):
    model = _Model(setup)
    checked_causes = {} if checked_causes is None else checked_causes
    consumed_causes = set()
    checked_no_starts = {} if checked_no_starts is None else checked_no_starts
    consumed_no_starts = set()
    openings = [(i, d['value']) for i, d in enumerate(transcript['records']) if d['kind'] == 'runtime_opened']
    by_epoch = {value['ownerEpoch']: value for _, value in openings}
    previous_versions, previous_operations, previous_links, previous_authority = {}, {}, {}, {}
    seen_fences = {}
    observed_transitions = []
    final = None
    for cp_index, cp in enumerate(transcript['checkpoints']):
        now, label = cp['value']['wallMs'], cp['value']['label']
        opened = next(value for pos, value in reversed(openings) if pos < cp['record'])
        tables = _tables(transcript, cp)
        meta = {r['key']: r['value'] for r in tables['io_meta']}
        expected_meta = {'profile': 'hms.synthetic-io-board/1', 'authority': opened['authorityId'],
            'deployment': model.deployment, 'board': model.installation['boardId'],
            'installation': canonical(model.installation).decode(), 'installationDigest': model.installation_digest,
            'ownerEpoch': str(opened['ownerEpoch']), 'clockEpoch': cp['value']['clockEpoch'], 'session': opened['session']}
        require(meta == expected_meta, 'PAT_IO_HISTORY_META')
        proofs = {row['instance']: row for row in tables['rc_proofs']}
        require(len(proofs) == len(tables['rc_proofs']) and set(proofs) == set(model.proofs), 'PAT_IO_HISTORY_PROOF')
        for instance, proof in model.proofs.items():
            row = proofs[instance]
            require(row['document'] == canonical(proof) and row['generation'] == proof['bindingGeneration'] and row['revision'] == 1 and
                    row['digest'] == digest(b'HMS-RESOURCE-BINDING-PROOF-v0.1', proof), 'PAT_IO_HISTORY_PROOF')
            if instance == model.binding['instanceId']:
                require(row['binding_digest'] == hashlib.sha256(canonical(model.binding)).hexdigest(), 'PAT_IO_HISTORY_BINDING')
        operations = {}
        for row in tables['operations']:
            value = dict(row)
            value['intent_value'], value['admission_value'] = parse_json(row['intent']), parse_json(row['admission'])
            detail, _ = model.intent(value['intent_value'])
            require(row['digest'] == intent_digest(value['intent_value']) and row['deployment'] == model.deployment,
                    'PAT_IO_HISTORY_OPERATION')
            admission = value['admission_value']
            closed(admission, {'resources', 'lease_expires_ms', 'policy_revision'}, 'PAT_IO_HISTORY_ADMISSION')
            integer(admission['lease_expires_ms']); identifier(admission['policy_revision'])
            require(admission['resources'] == detail['claims'], 'PAT_IO_HISTORY_ADMISSION')
            operations[row['id']] = value
        immutable_operations = {k: tuple(v[f] for f in ('id', 'principal', 'deployment', 'digest', 'intent', 'admission')) for k, v in operations.items()}
        require(all(immutable_operations.get(k) == v for k, v in previous_operations.items()), 'PAT_IO_HISTORY_OPERATION_CHANGED')
        previous_operations = immutable_operations
        links = {}
        for row in tables['io_dispatch_links']:
            value = parse_json(row['document']); op = operations.get(row['operation'])
            require(op is not None, 'PAT_IO_HISTORY_DISPATCH')
            closed(value, {'profile', 'operationId', 'digest', 'intent', 'claims', 'adapterId', 'authorityId', 'attemptId',
                           'ownerEpoch', 'checkpoint', 'budgetOriginMonoMs', 'clockEpoch', 'installationDigest'})
            require(row['digest'] == digest(b'HMS-SYNTHETIC-IO-DISPATCH-v1', value) and
                    value['profile'] == 'hms.synthetic-io-dispatch/1' and value['operationId'] == row['operation'] and
                    value['digest'] == op['digest'] and canonical(value['intent']) == op['intent'] and
                    value['authorityId'] == opened['authorityId'] and value['installationDigest'] == model.installation_digest and
                    value['adapterId'] == model.routes[value['intent']['instanceId']] and value['attemptId'] == op['attempt_id'],
                    'PAT_IO_HISTORY_DISPATCH')
            integer(value['ownerEpoch'], 1, opened['ownerEpoch']); integer(value['checkpoint']); integer(value['budgetOriginMonoMs'])
            require(value['clockEpoch'] == opened['authorityId'] + ':' + str(value['ownerEpoch']), 'PAT_IO_HISTORY_DISPATCH')
            _claims(value['claims'], model.details[model.target]['claims'])
            events = [e for e in tables['events'] if e['operation_id'] == row['operation'] and e['kind'] == 'dispatch_claimed']
            require(len(events) == 1 and events[0]['time_ms'] == value['checkpoint'] and
                    events[0]['payload'] == canonical({'attemptId': value['attemptId'], 'ownerEpoch': value['ownerEpoch']}), 'PAT_IO_HISTORY_DISPATCH_EVENT')
            links[row['operation']] = value
        raw_links = {r['operation']: r['document'] for r in tables['io_dispatch_links']}
        require(all(raw_links.get(k) == v for k, v in previous_links.items()), 'PAT_IO_HISTORY_DISPATCH_CHANGED')
        previous_links = raw_links
        versions = {(r['operation'], r['sequence']): r for r in tables['io_receipt_versions']}
        require(all(k in versions and versions[k] == v for k, v in previous_versions.items()), 'PAT_IO_HISTORY_VERSION_CHANGED')
        receipts = {}
        for key, row in versions.items():
            value = parse_json(row['document']); operation_id, sequence = key
            closed(value, {'profile', 'operationId', 'sequence', 'authorityId', 'boardId', 'installationDigest', 'adapterId', 'digest',
                           'intent', 'claims', 'ownerEpoch', 'clockEpoch', 'providerSession', 'state', 'startedMonoMs',
                           'budgetOriginMonoMs', 'dueMonoMs', 'activeState', 'idleState', 'result'})
            integer(sequence, 1, 2)
            require(value['sequence'] == sequence and type(value['sequence']) is int and value['operationId'] == operation_id and
                    value['profile'] == 'hms.synthetic-io-receipt/1' and row['digest'] == digest(b'HMS-SYNTHETIC-IO-RECEIPT-v1', value), 'PAT_IO_HISTORY_RECEIPT_DIGEST')
            require(operation_id in operations and operation_id in links, 'PAT_IO_HISTORY_RECEIPT_LINK')
            op, link = operations[operation_id], links[operation_id]
            detail, active = model.intent(value['intent'])
            epoch = integer(value['ownerEpoch'], 1, opened['ownerEpoch'])
            require(epoch in by_epoch and value['providerSession'] == by_epoch[epoch]['session'] == value['intent']['endpointSession'] and
                    value['clockEpoch'] == by_epoch[epoch]['authorityId'] + ':' + str(epoch), 'PAT_IO_HISTORY_RECEIPT_SESSION')
            require(value['authorityId'] == opened['authorityId'] and value['boardId'] == model.installation['boardId'] and
                    value['installationDigest'] == model.installation_digest, 'PAT_IO_HISTORY_RECEIPT_IDENTITY')
            for field in ('digest', 'intent', 'claims', 'adapterId', 'ownerEpoch', 'clockEpoch'):
                require(same(value[field], link[field]), 'PAT_IO_HISTORY_RECEIPT_LINK')
            claims = _claims(value['claims'], detail['claims'])
            held = {r['resource']: r['fence'] for r in tables['claims'] if r['operation_id'] == operation_id}
            require(not held or held == claims, 'PAT_IO_HISTORY_AUTHORITY_CLAIMS')
            require(same(value['activeState'], active) and
                    same(value['idleState'], {atom: model.idle[atom] for atom in detail['claims']}), 'PAT_IO_HISTORY_DERIVED_STATE')
            result = value['result']; closed(result, {'activationCommitted', 'cycleCompleted', 'safeIdle', 'reason'})
            require(all(type(result[k]) is bool for k in ('activationCommitted', 'cycleCompleted', 'safeIdle')), 'PAT_IO_HISTORY_FLAGS')
            state = value['state']
            require(state in {'pending', 'completed', 'canceled', 'rejected_before_start'}, 'PAT_IO_HISTORY_RECEIPT_STATE')
            # Historical pending versions do not imply current authority claims.
            # The latest pending receipt is checked after version reduction.
            times = ('startedMonoMs', 'budgetOriginMonoMs', 'dueMonoMs')
            if state == 'rejected_before_start':
                require(sequence == 1 and all(value[k] is None for k in times) and
                        same(result, {'activationCommitted': False, 'cycleCompleted': False, 'safeIdle': True, 'reason': result['reason']}), 'PAT_IO_HISTORY_FLAGS')
                identifier(result['reason'])
            else:
                for field in times:
                    integer(value[field])
                require(value['budgetOriginMonoMs'] == link['budgetOriginMonoMs'] <= value['startedMonoMs'] and
                        value['dueMonoMs'] == value['startedMonoMs'] + value['intent']['arguments']['durationMs'] and
                        value['dueMonoMs'] < value['budgetOriginMonoMs'] + value['intent']['timing']['maxRunMs'], 'PAT_IO_HISTORY_TIME')
                require(sequence == (1 if state == 'pending' else 2) and
                        same(result, {'activationCommitted': True, 'cycleCompleted': state == 'completed',
                                      'safeIdle': state != 'pending', 'reason': result['reason']}), 'PAT_IO_HISTORY_FLAGS')
                if state == 'canceled':
                    identifier(result['reason'])
                else:
                    require(result['reason'] is None, 'PAT_IO_HISTORY_FLAGS')
            if sequence == 2:
                require((operation_id, 1) in versions, 'PAT_IO_HISTORY_PREDECESSOR')
                prior = parse_json(versions[(operation_id, 1)]['document'])
                require(prior['state'] == 'pending' and
                        same({k: v for k, v in value.items() if k not in {'state', 'sequence', 'result'}},
                             {k: v for k, v in prior.items() if k not in {'state', 'sequence', 'result'}}), 'PAT_IO_HISTORY_IMMUTABLE_RECEIPT')
            if key not in previous_versions:
                allowed = label in {'drive:cycle:after', 'drive:cycle:after_error', 'drive:adapters:after', 'drive:adapters:after_error'}
                require(allowed or sequence == 2 and state == 'canceled' and label == 'after_reopen', 'PAT_IO_HISTORY_EFFECT_PHASE')
                timing = value['intent']['timing']; lease = op['admission_value']['lease_expires_ms']
                if sequence == 1:
                    require(epoch == opened['ownerEpoch'], 'PAT_IO_HISTORY_RECEIPT_SESSION')
                    if state == 'pending':
                        require(value['startedMonoMs'] == now and timing['notBeforeUnixMs'] <= now < timing['latestStartUnixMs'] and
                                now < timing['latestCompletionUnixMs'] and now < lease, 'PAT_IO_HISTORY_START_TIME')
                        for atom, fence in claims.items():
                            require(atom not in seen_fences or fence > seen_fences[atom][0], 'PAT_IO_HISTORY_FENCE_REUSE')
                            seen_fences[atom] = (fence, operation_id)
                    else:
                        cause_key = (cp['record'], operation_id)
                        require(cause_key in checked_no_starts, 'PAT_IO_HISTORY_NO_START_CAUSE_UNIMPLEMENTED')
                        require(checked_no_starts[cause_key] == result['reason'] == 'duration_budget_excluded',
                                'PAT_IO_HISTORY_NO_START_CAUSE')
                        consumed_no_starts.add(cause_key)
                elif state == 'completed':
                    require(epoch == opened['ownerEpoch'] and value['dueMonoMs'] <= now < timing['latestCompletionUnixMs'] and
                            now < value['budgetOriginMonoMs'] + timing['maxRunMs'] and now < lease, 'PAT_IO_HISTORY_COMPLETION_TIME')
                else:
                    cause_key = (cp['record'], operation_id)
                    if result['reason'] in {'authority_or_binding_lost','reconciliation_stop'} and cause_key in checked_causes:
                        # Only the composed checker supplies this private handoff,
                        # after deriving the cause from trusted grants/faults and prior state.
                        require(checked_causes[cause_key] == result['reason'], 'PAT_IO_HISTORY_CANCEL_CAUSE')
                        consumed_causes.add(cause_key)
                    else:
                        _cause(result['reason'], value, op, now, label, opened)
                observed_transitions.append({'operationId': operation_id, 'sequence': sequence, 'state': state,
                                             'clock': now, 'phase': cp['value']['phase'],
                                             'authorityStateAtCapture': op['state'], 'authorityClaimsAtCapture': len(held)})
            receipts[key] = value
        latest = {op: receipts[(op, max(s for o, s in receipts if o == op))] for op, _ in receipts}
        current = {row['operation']: row for row in tables['io_receipts']}
        require(set(current) == set(latest), 'PAT_IO_HISTORY_RECEIPT_INVENTORY')
        for op, value in latest.items():
            row, version = current[op], versions[(op, value['sequence'])]
            require(row['state'] == value['state'] and row['sequence'] == value['sequence'] and
                    row['document'] == version['document'] and row['digest'] == version['digest'], 'PAT_IO_HISTORY_CURRENT_RECEIPT')
            if value['state'] == 'pending':
                held = {r['resource']: r['fence'] for r in tables['claims'] if r['operation_id'] == op}
                require(held == _claims(value['claims'], model.details[model.target]['claims']), 'PAT_IO_HISTORY_AUTHORITY_CLAIMS')
        authority = {(r['operation'], r['sequence']): r for r in tables['io_authority_receipts']}
        require(all(k in authority and authority[k] == v for k, v in previous_authority.items()), 'PAT_IO_HISTORY_AUTHORITY_RECEIPT')
        for key, row in authority.items():
            require(key in versions and row['document'] == versions[key]['document'] and row['digest'] == versions[key]['digest'], 'PAT_IO_HISTORY_AUTHORITY_RECEIPT')
        previous_authority = authority
        counts = {instance: [0, 0, 0] for instance in model.routes}
        owners, floors, resources = {}, {}, dict(model.idle)
        for op, value in latest.items():
            if value['state'] == 'rejected_before_start':
                continue
            count = counts[value['intent']['instanceId']]; count[0] += 1
            count[1] += value['state'] == 'completed'; count[2] += value['state'] == 'canceled'
            for claim in value['claims']:
                atom, fence = claim['resource'], claim['fence']
                if atom in floors:
                    require(floors[atom][0] != fence, 'PAT_IO_HISTORY_FENCE_REUSE')
                if atom not in floors or fence > floors[atom][0]:
                    floors[atom] = (fence, op)
                if value['state'] == 'pending':
                    require(atom not in owners, 'PAT_IO_HISTORY_OWNER_OVERLAP')
                    owners[atom] = (op, fence); resources[atom] = value['activeState'][atom]
        require({r['instance']: [r['activations'], r['completed'], r['canceled']] for r in tables['io_effects']} == counts,
                'PAT_IO_HISTORY_COUNTERS')
        require({r['resource']: (r['operation'], r['fence']) for r in tables['io_owners']} == owners, 'PAT_IO_HISTORY_OWNERS')
        require({r['resource']: (r['fence'], r['operation']) for r in tables['io_fences']} == floors, 'PAT_IO_HISTORY_FENCES')
        require(floors == seen_fences, 'PAT_IO_HISTORY_FENCES')
        actual_resources = {r['resource']: parse_json(r['state']) for r in tables['io_resources']}
        require(same(actual_resources, resources), 'PAT_IO_HISTORY_RESOURCES')
        for atom, (op, fence) in owners.items():
            require(floors[atom] == (fence, op), 'PAT_IO_HISTORY_FENCES')
        if cp_index == 0:
            require(not versions and not operations and not links and not authority and not tables['claims'] and not tables['resource_floors'],
                    'PAT_IO_HISTORY_BASELINE')
        previous_versions = versions
        final = {'instances': [{'instanceId': instance, 'activations': c[0], 'completedCycles': c[1], 'canceledActivations': c[2]}
                               for instance, c in sorted(counts.items())],
                 'modeledBoardIdle': not owners, 'pendingOperationIds': sorted(op for op, r in latest.items() if r['state'] == 'pending')}
    require(consumed_causes == set(checked_causes), 'PAT_IO_HISTORY_UNUSED_CAUSE')
    require(consumed_no_starts == set(checked_no_starts), 'PAT_IO_HISTORY_UNUSED_NO_START')
    return {'profile': 'hms.pat.io-board-history-inspection/0.1', 'checkpointsChecked': len(transcript['checkpoints']),
            'receiptVersionsChecked': len(previous_versions), 'transitions': observed_transitions,
            'boardHistoryChecked': True, **final, 'authoritySemanticsChecked': False,
            'independentOutcomeChecked': False, 'qualificationPassed': False}


def inspect_board_history(references, files, *, expected_setup):
    """Validate a complete trusted-source transcript, never open or repair state."""
    try:
        result = _reduce(_read(references, files, expected_setup), expected_setup)
        canonical(result)
        return result
    except (IoHistoryError, IoTranscriptError):
        raise
    except (ContractError, ResourceTopologyError, KeyError, TypeError, ValueError, IndexError, RecursionError) as error:
        raise IoHistoryError('PAT_IO_HISTORY_SHAPE') from error
