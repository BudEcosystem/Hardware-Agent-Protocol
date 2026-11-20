"""Closed combined I/O qualification preflight, not an execution worker.

Candidate cases and fixed provider/authority challenges share the original
global ceilings. Construction reads trusted installation pins; planning thereafter
uses detached data. No partial matrix, callback or caller-selected fault list.
"""
from __future__ import annotations

import copy
import hashlib

from .contracts import canonical
from .pat_contracts import PatError, closed, integer, parse_pat, pat_digest, require, snapshot
from .pat_io_contracts import IoSequencePolicy, _errors, _same
from .synthetic_io_installation import handler_details, normalize_installation

PROFILE = 'hms.pat.io-combined-matrix/0.1'
POLICY = 'hms.pat.eval.sqlite-finite-io-combined/0.1'
CEILINGS = dict(maxCases=32, maxChildOperations=512, maxSchedulerTicks=2048,
    maxProducerBytes=16*1024*1024, maxRecords=4096, maxDocumentBytes=65536,
    maxDerivedBytes=20*1024*1024, maxWallMs=60000)
ROLES = ('gpio', 'pwm', 'alias', 'independent')

# Named fixed timing programs; these are not modifications of the candidate.
# n, latest-start, child-completion, run-budget, duration, parent-completion.
WINDOWS = {
    'ordinary': (0, 100, 1000, 100, 10, 1000),
    'not_before': (50, 100, 1000, 100, 10, 1000),
    'latest_start': (0, 50, 1000, 100, 1, 1000),
    'start_run': (0, 200, 1000, 100, 1, 1000),
    'run_finish': (0, 100, 1000, 100, 1, 1000),
    'wall_finish': (0, 10, 50, 50, 1, 1000),
    'lease_wait': (59998, 60001, 70000, 2, 1, 70000),
    'late_parent': (0, 100, 1000, 100, 1, 1000),
}


def _scenario(name, window, count, control, effects, outcome, checks):
    return dict(scenario=name, window=window, stepCount=count, control=control,
        expected=dict(activations=effects[0], completedCycles=effects[1], canceledActivations=effects[2],
            completionContract=outcome, settledAndQuiescent=True, unresolvedOperations=0,
            checks=checks.split(',')), schedulerTickCeiling=64)


# Each item is one fresh trial; controls name fixed worker behavior, not code.
SCENARIOS = [
    _scenario('cancel_accepted', 'ordinary', 2, {'at':'accepted','action':'cancel_parent'}, (0,0,0), 'failed', 'no_handoff,claims_released,floor_retained,no_suffix'),
    _scenario('cancel_pending', 'ordinary', 2, {'at':'pending','action':'cancel_parent'}, (1,0,1), 'failed', 'one_activation,idle_before_release,no_suffix'),
    _scenario('reopen_accepted', 'ordinary', 2, {'at':'accepted','action':'reopen','recovery':'resume_refuses_then_cancel'}, (0,0,0), 'failed', 'new_session,old_request_preserved,no_rebinding,no_suffix'),
    _scenario('reopen_pending', 'ordinary', 2, {'at':'pending','action':'reopen','recovery':'reconcile_then_cancel'}, (1,0,1), 'failed', 'owner_reopen_stop,old_request_preserved,no_rebinding,no_suffix'),
    _scenario('completion_reply_lost', 'ordinary', 2, {'at':'first_board_completion','action':'lose_completion_record','recovery':'reopen_resume_refuses_then_cancel'}, (1,1,0), 'failed', 'historical_completion,no_reactivation,stale_suffix_refused'),
    _scenario('pending_reply_lost', 'ordinary', 2, {'at':'first_board_activation','action':'lose_begin_reply','recovery':'reconcile_stop'}, (1,0,1), 'failed', 'unknown_holds_claims,exact_reconciliation_stop,no_suffix'),
    _scenario('not_before_boundary', 'not_before', 1, {'advanceOffsetsMs':[49,50,60]}, (1,1,0), 'satisfied', 'no_early_handoff,start_at_lower_bound,due_equality_completes'),
    _scenario('latest_start_before', 'latest_start', 1, {'advanceOffsetsMs':[49,50]}, (1,1,0), 'satisfied', 'start_before_upper_bound,started_work_can_finish_at_start_deadline'),
    _scenario('latest_start_equal', 'latest_start', 1, {'advanceOffsetsMs':[50]}, (0,0,0), 'failed', 'no_start_at_upper_bound,claims_released,floor_retained'),
    _scenario('start_run_equal', 'start_run', 1, {'at':'reserved_before_begin','guardDelayMs':99}, (0,0,0), 'failed', 'due_equals_reserved_run_limit,start_excluded_receipt,no_board_fence'),
    _scenario('run_completion_equal', 'run_finish', 1, {'at':'pending','advanceOffsetsMs':[100]}, (1,0,1), 'failed', 'execution_deadline_precedes_due,activation_not_completion'),
    _scenario('wall_completion_equal', 'wall_finish', 1, {'dispatchOffsetMs':5,'finishOffsetMs':50}, (1,0,1), 'failed', 'wall_deadline_precedes_due,wall_deadline_precedes_equal_lease,run_budget_not_expired'),
    _scenario('lease_wait_before', 'lease_wait', 1, {'advanceOffsetsMs':[59997,59998,59999]}, (1,1,0), 'satisfied', 'lease_starts_at_admission,no_early_handoff,finish_before_lease'),
    _scenario('lease_wait_equal', 'lease_wait', 1, {'advanceOffsetsMs':[60000]}, (0,0,0), 'failed', 'accepted_wait_consumes_lease,lease_precedes_latest_start,no_activation'),
    _scenario('late_parent_reporting', 'late_parent', 1, {'boardFinishOffsetMs':1,'parentReportOffsetMs':1000}, (1,1,0), 'satisfied', 'historical_completion,parent_completion_at_deadline,nominal_timing_false'),
    _scenario('wall_clock_regression', 'ordinary', 2, {'at':'pending','action':'regress_wall_by_one','recovery':'new_epoch_reopen_and_reconcile'}, (1,0,1), 'failed', 'invalid_clock_no_continuation,new_epoch_retained,no_reset,no_suffix'),
    _scenario('clock_epoch_mismatch', 'ordinary', 2, {'at':'pending','action':'invalidate_clock_mapping','recovery':'new_epoch_reopen_and_reconcile'}, (1,0,1), 'failed', 'invalid_mapping_no_continuation,new_epoch_retained,no_rebinding,no_suffix'),
    _scenario('permission_before_parent', 'ordinary', 1, {'at':'before_submit','action':'withdraw_invoke_keep_read'}, (0,0,0), 'failed', 'no_parent,no_child,no_claim,no_floor'),
    _scenario('permission_before_dispatch', 'ordinary', 2, {'at':'accepted','action':'withdraw_invoke_keep_read'}, (0,0,0), 'failed', 'no_handoff,claims_released,floor_retained,no_suffix'),
    _scenario('permission_pending', 'ordinary', 2, {'at':'pending','action':'withdraw_invoke_keep_read'}, (1,0,1), 'failed', 'authority_loss_stop,idle_before_release,no_suffix'),
    _scenario('permission_after_completion', 'ordinary', 1, {'at':'board_completed_before_settlement','action':'withdraw_invoke_keep_read'}, (1,1,0), 'satisfied', 'historical_completion,retained_read,no_reactivation'),
    _scenario('full_authority_withdrawal', 'ordinary', 2, {'at':'pending','action':'withdraw_all','recovery':'privileged_capture_reopen_and_reconcile'}, (1,0,1), 'failed', 'public_read_denied,internal_recovery_retained,no_namespace_bypass,no_suffix'),
    _scenario('binding_before_dispatch', 'ordinary', 2, {'at':'accepted','action':'invalidate_binding'}, (0,0,0), 'failed', 'no_handoff,no_rebinding,claims_released,no_suffix'),
    _scenario('binding_pending', 'ordinary', 2, {'at':'pending','action':'invalidate_binding','recovery':'reopen_and_reconcile'}, (1,0,1), 'failed', 'historical_stop,new_admission_refused,no_rebinding,no_suffix'),
]
RESOURCE_SCENARIO = dict(scenario='shared_resources', schedulerTickCeiling=128,
    actorOrder=['gpio','independent','alias','pwm'],
    control=['start_gpio','pwm_busy','alias_busy','start_independent','finish_gpio_and_independent',
             'replay_original_gpio','start_alias','read_historical_gpio_while_alias_active','finish_alias',
             'start_pwm','gpio_busy','finish_pwm','replay_all_original_requests'],
    expected=dict(activations=4,completedCycles=4,canceledActivations=0,completionContract='provider_challenge',
        settledAndQuiescent=True,unresolvedOperations=0,
        checks=['both_primitives_execute','gpio_pwm_mutual_exclusion','cross_route_alias_exclusion',
                'independent_pad_progress','same_key_replay_no_activation','one_shared_fence_history',
                'historical_idle_not_current_idle','no_hidden_actor']))


def _hash(domain, value):
    return 'sha256:' + hashlib.sha256(domain + b'\0' + canonical(value)).hexdigest()


def _program(action, primitive, arguments, window, count):
    n,s,c,r,d,p = WINDOWS[window]
    args = dict(arguments, durationMs=d)
    steps = [dict(stepId='step:'+str(i), role='io', actionId=action,
        arguments={k:{'literal':v} for k,v in sorted(args.items())},
        timing=dict(notBeforeOffsetMs=n if i==0 else 0, latestStartOffsetMs=s if i==0 else p-1,
                    latestCompletionOffsetMs=c, maxRunMs=r)) for i in range(count)]
    return dict(protocol='hms.pat/0.1', profile='hms.pat.bound-sequence/0.1',
        name='io-policy-'+primitive, version='1', taskKind='sim.io.qualification.challenge',
        inputProfile='hms.sim.io.challenge/0.1', parameters={},
        roles={'io':dict(capabilityFamily='sim:finite-gpio-pwm',actions=[action],driverProfiles=['sqlite-finite-io/1'])},
        applicability={'phase':'selection','all':[dict(field='context.evidenceMode',op='equals',literal='simulation')]},
        targetProfile='hms.bound-sequence/0.1',executionPlacement='hms-host-orchestration',
        timingBudget=dict(latestStartOffsetMs=s,latestCompletionOffsetMs=p,maxRunSumMs=count*r),steps=steps,
        effectBudget=dict(maxInvocations=count,scope='simulation_only'),
        outcomeContract=dict(requiredEffect='capability_completion',requiredCompletedSteps=[row['stepId'] for row in steps],
                             evidenceMode='simulation',physicalObjectiveVerified=False),
        runtimeGuardProfile='installed_primitive_guards_only')


class IoCombinedMatrixPolicy:
    """Trusted construction, then pure closed planning with global preflight."""
    @_errors
    def __init__(self, installation):
        self._installation = normalize_installation(installation)
        self._policy = IoSequencePolicy(self._installation)
        self._details = {(row['instanceId'],row['actionId']):handler_details(self._installation,row['instanceId'],row['actionId'])
                         for row in self._installation['handlers']}

    @_errors
    def generate(self, value, trusted_descriptor, challenge_bindings, *, limits=None):
        artifact = parse_pat(value); descriptor = snapshot(trusted_descriptor, 'PAT_IO_MATRIX_DESCRIPTOR')
        bindings = snapshot(challenge_bindings, 'PAT_IO_MATRIX_BINDINGS'); closed(bindings, ROLES, 'PAT_IO_MATRIX_BINDINGS')
        limits = snapshot(CEILINGS if limits is None else limits, 'PAT_IO_MATRIX_LIMITS'); closed(limits, CEILINGS, 'PAT_IO_MATRIX_LIMITS')
        for key,maximum in CEILINGS.items(): integer(limits[key],1,maximum,'PAT_IO_MATRIX_LIMITS')
        contract = self._policy.qualify(artifact, descriptor)
        domain = self._policy.generate_cases(artifact,descriptor)
        actors = {}; programs = {pat_digest(artifact):artifact}; requirements = {}; validated = set()
        sessions = set(); instances = set()
        for role in ROLES:
            entry = bindings[role]; closed(entry, {'actionId','descriptor'}, 'PAT_IO_MATRIX_BINDINGS')
            chosen = entry['descriptor']; instance = chosen['binding']['instanceId']; action = entry['actionId']
            detail = self._details.get((instance,action)); require(detail is not None, 'PAT_IO_MATRIX_BINDINGS')
            require(detail['primitive'] == ('pwm_burst' if role=='pwm' else 'gpio_pulse'), 'PAT_IO_MATRIX_PRIMITIVE')
            args = ({'level':1} if role!='pwm' else dict(frequencyHz=detail['timerEnvelope']['minFrequencyHz'],dutyPermille=500,resolutionBits=8))
            fixed = _program(action,detail['primitive'],args,'ordinary',1)
            self._policy.qualify(fixed,chosen)
            digest = pat_digest(fixed); programs[digest] = fixed
            actors[role] = dict(instanceId=instance,actionId=action,primitive=detail['primitive'],
                adapterId=chosen['binding']['adapterId'],claims=list(detail['claims']),programDigest=digest)
            requirements[role] = _hash(b'HMS-PAT-IO-DESCRIPTOR-v0.1', chosen)
            validated.add((digest,requirements[role]))
            sessions.add(chosen['endpointSession']); instances.add(instance)
        require(len(instances)==4 and len(sessions)==1, 'PAT_IO_MATRIX_BOARD_CONTEXT')
        gpio,pwm,alias,independent = (actors[key] for key in ROLES)
        require(gpio['claims']==alias['claims'] and gpio['adapterId']!=alias['adapterId'], 'PAT_IO_MATRIX_ALIAS')
        require(set(gpio['claims']) < set(pwm['claims']) and
                not set(independent['claims']) & (set(gpio['claims'])|set(pwm['claims'])), 'PAT_IO_MATRIX_RESOURCES')
        target_role = 'pwm' if contract['primitive']=='pwm_burst' else 'gpio'
        require(_same(bindings[target_role]['descriptor'], descriptor) and
                bindings[target_role]['actionId']==contract['actionId'], 'PAT_IO_MATRIX_TARGET')
        target = actors[target_role]; detail = self._details[target['instanceId'],target['actionId']]
        arguments = ({'level':1} if target_role=='gpio' else dict(frequencyHz=detail['timerEnvelope']['minFrequencyHz'],dutyPermille=500,resolutionBits=8))
        cases=[]
        def add(body):
            body['caseId'] = _hash(b'HMS-PAT-IO-COMBINED-CASE-v0.1', body)
            cases.append(body)
        for case in domain['cases']:
            applicable = case['expected']['staticOutcome']=='applicable'
            add(dict(kind='candidate',domainCase=case,programDigest=pat_digest(artifact),
                plannedChildOperations=case['expected']['plannedChildOperations'],
                schedulerTickCeiling=4*len(artifact['steps'])+8 if applicable else 0,
                terminalProbes=['exact_parent_replay','changed_same_key_conflict'] if applicable else [],
                unresolvedOperationsRequired=0))
        for definition in SCENARIOS:
            fixed = _program(target['actionId'],target['primitive'],arguments,definition['window'],definition['stepCount'])
            digest=pat_digest(fixed)
            if (digest,requirements[target_role]) not in validated:
                self._policy.qualify(fixed,descriptor); validated.add((digest,requirements[target_role]))
            programs[digest]=fixed
            add(dict(kind='fixed_challenge',definition=copy.deepcopy(definition),targetRole=target_role,
                programDigest=digest,plannedChildOperations=definition['stepCount'],
                schedulerTickCeiling=definition['schedulerTickCeiling']))
        add(dict(kind='resource_challenge',definition=copy.deepcopy(RESOURCE_SCENARIO),actors=actors,
                 plannedChildOperations=4,schedulerTickCeiling=RESOURCE_SCENARIO['schedulerTickCeiling']))
        totals=dict(cases=len(cases),childOperations=sum(c['plannedChildOperations'] for c in cases),
                    schedulerTicks=sum(c['schedulerTickCeiling'] for c in cases))
        for field,limit in [('cases','maxCases'),('childOperations','maxChildOperations'),('schedulerTicks','maxSchedulerTicks')]:
            require(totals[field]<=limits[limit], 'PAT_IO_MATRIX_COMBINED_LIMIT', dict(dimension=field,required=totals[field],limit=limits[limit]))
        spec=dict(policy=POLICY,windows={key:list(value) for key,value in WINDOWS.items()},scenarios=SCENARIOS,resourceScenario=RESOURCE_SCENARIO,ceilings=CEILINGS,
                  candidatePostCompletion=['exact_parent_replay','changed_same_key_conflict'],generationRevision=1)
        result=dict(profile=PROFILE,policy=POLICY,policyDigest=_hash(b'HMS-PAT-IO-COMBINED-POLICY-v0.1',spec),
            artifactDigest=pat_digest(artifact),candidateContract=contract,
            installationDigest=contract['installationDigest'],driverDigest=contract['driverDigest'],
            challengeBindingDigests=requirements,challengeInventoryDigest=_hash(b'HMS-PAT-IO-CHALLENGE-INVENTORY-v0.1',bindings),
            programs=[dict(digest=digest,artifact=programs[digest]) for digest in sorted(programs)],cases=cases,
            totals=totals,limits=limits,caseCountIncludesFixedChallenges=True,hiddenAuxiliaryActorsAllowed=False,
            requiredWorkerFeatures=['paired_configuration','complete_history','same_key_conflict','auxiliary_actor_inventory',
                'in_phase_guard_delay','clock_fault_and_new_epoch','binding_invalidation','full_read_withdrawal',
                'historical_reconciliation','group_budget_enforcement'],
            runtimeBudgetEnforcementRequired=['producer_and_configuration_bytes','combined_records','derived_closure_bytes',
                'all_child_admissions','all_scheduler_ticks','group_wall_deadline'],
            actualAggregateStorageEnforced=False,implementationIdentityAttested=False,
            executionPerformed=False,requiredOutcomesVerified=False,qualificationPassed=False)
        encoded=canonical(result)
        require(len(encoded)<=limits['maxDocumentBytes'], 'PAT_IO_MATRIX_DOCUMENT_LIMIT')
        require(len(encoded)<=limits['maxDerivedBytes'], 'PAT_IO_MATRIX_DERIVED_LIMIT')
        return result

    @_errors
    def validate(self, plan, value, trusted_descriptor, challenge_bindings, *, limits=None):
        supplied=snapshot(plan,'PAT_IO_MATRIX_INVALID_PLAN')
        expected=self.generate(value,trusted_descriptor,challenge_bindings,limits=limits)
        require(_same(supplied,expected),'PAT_IO_MATRIX_PLAN_MISMATCH')
        return _hash(b'HMS-PAT-IO-COMBINED-MATRIX-v0.1',expected)
