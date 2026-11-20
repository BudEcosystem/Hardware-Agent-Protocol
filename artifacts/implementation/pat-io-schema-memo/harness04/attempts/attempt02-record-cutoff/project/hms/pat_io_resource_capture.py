"""Closed shared-board challenge; direct compiled invokes, no qualification."""
import copy

from .contracts import canonical
from .journal import JournalError
from .pat_compiler import compile_pat, evaluation_environment
from .pat_contracts import require, snapshot
from .pat_io_bindings import IoRegistryPatBindings
from .pat_io_combined_matrix import IoCombinedMatrixPolicy, ROLES
from .pat_io_configuration_capture import ConfiguredIoTrialEngine
from .pat_io_contracts import IoSequencePolicy
from .pat_io_trials import ORIGIN, MAX_RECORDS, MAX_OUTPUT_BYTES
from .synthetic_io_runtime import IoRuntime


class ResourceIoTrialEngine(ConfiguredIoTrialEngine):
    _record_profile = 'hms.pat.io-trial-record/0.4'

    def __init__(self, directory, installation, *, case, actors, group_budget=None):
        self.case, self.actors = snapshot(case), snapshot(actors)
        self.requests, self.operation_ids = {}, {}
        base = self.actors['gpio']
        super().__init__(directory, base['artifact'], installation, base['original_descriptor'], group_budget=group_budget)

    def _open(self, *, create):
        require(create and self.runtime is None, 'PAT_IO_RESOURCE_REOPEN_UNSUPPORTED')
        self._check_budget()
        self.runtime = IoRuntime(self.directory/'state', create=True, owner=self.owner,
            installation=self.document, wall_clock_ms=self.clock, monotonic_ms=self.clock)
        require(not self.runtime.route_errors and not self.runtime._threads and
                set(self.runtime.adapters)==set(self.document['routes']['adapters']), 'PAT_IO_TRIAL_RECONSTRUCTION')
        original = self.runtime.journal.submission_guard
        def bounded_admission(context, request, intent, digest, managed, now):
            count = self.runtime.journal._db.execute('SELECT count(*) FROM operations').fetchone()[0]
            if self._group_budget is not None:
                self._group_budget.admission(count)
            require(self.plan is not None and managed is None and count < 5 and
                    canonical(request) in self.requests.values(), 'PAT_IO_TRIAL_OPERATION_LIMIT')
            return original(context, request, intent, digest, managed, now)
        self.runtime.journal.submission_guard = bounded_admission
        records = []
        for role in ROLES:
            d = self.actors[role]['original_descriptor']
            record = {k:d[k] for k in ('driverProfile','driverDigest','installationDigest','argumentMetadata')}
            record.update(instanceId=d['binding']['instanceId'],typeDigest=d['binding']['typeDigest'])
            records.append(record)
        records.sort(key=lambda r:r['instanceId'])
        provider = IoRegistryPatBindings(self.runtime, records)
        self._resolver_configuration = dict(profile='hms.pat.io-resolver-configuration/0.1',
            resolverProfile='hms.pat.bindings.sqlite-finite-io/0.1',registrations=copy.deepcopy(records),
            registrationIdentity=provider.registration_identity)
        wanted, actual, self.actor_bindings = {}, {}, {}
        for role in ROLES:
            a, d = self.actors[role]['artifact'], self.actors[role]['original_descriptor']
            with self.runtime.journal._transaction():
                current = provider.for_roles(self.owner,a,{'io':d['binding']['instanceId']})
            wanted[role] = evaluation_environment(a,{'io':d},deployment=self.owner.deployment)
            actual[role] = evaluation_environment(a,current,deployment=self.owner.deployment)
            require(actual[role]['evaluationEnvironment']==wanted[role]['evaluationEnvironment'] and
                    actual[role]['environmentDigest']==wanted[role]['environmentDigest'], 'PAT_IO_TRIAL_ENVIRONMENT_CHANGED')
            self.actor_bindings[role] = current
        self._write('runtime_opened',dict(create=True,wallMs=self.clock.value,
            ownerEpoch=self.runtime.journal.owner_epoch,authorityId=self.runtime.journal.authority_id,
            session=self.runtime.io_board.session,originalEnvironment=wanted,workerEnvironment=actual))

    def operations(self):
        rows = self.runtime.journal._db.execute('SELECT id FROM operations ORDER BY rowid LIMIT 6').fetchall()
        require(len(rows)<=5,'PAT_IO_TRIAL_OPERATION_LIMIT')
        return [self.runtime.journal._operation(r[0]) for r in rows]

    def lower_actors(self):
        require(not self._lower_attempted,'PAT_IO_TRIAL_ALREADY_COMPILED')
        self._lower_attempted=True
        self._write('resource_input',dict(case=self.case,actors=self.actors))
        def compile_all():
            namespace=self.runtime.journal.issue_namespace(self.owner,ORIGIN+1001)['token']
            plans={}
            for role in ROLES:
                a=self.actors[role]['artifact']
                plans[role]=compile_pat(a,{},self.actor_bindings[role],origin_ms=ORIGIN,
                    replay_namespace=namespace,procedure_key='trial:parent:'+role,
                    operation_keys={'step:0':'trial:actor:'+role},caller_deadline_ms=ORIGIN+1000,
                    context=dict(taskKind=a['taskKind'],inputProfile=a['inputProfile'],
                                 evidenceMode='simulation',deployment=self.owner.deployment))
            probe=copy.deepcopy(plans['gpio']['request']['procedure']['steps'][0]['request'])
            probe['operationKey']='trial:probe:gpio_busy'
            return dict(actors=plans,probes={'gpio_while_pwm':probe})
        self.plan=self._call('lower',compile_all)
        self._write('compiled_plan',self.plan)
        self.requests={role:canonical(plan['request']['procedure']['steps'][0]['request'])
                       for role,plan in self.plan['actors'].items()}
        self.requests['gpio_while_pwm']=canonical(self.plan['probes']['gpio_while_pwm'])
        require(len(set(self.requests.values()))==5,'PAT_IO_RESOURCE_REQUEST_INVENTORY')

    def invoke_actor(self, name):
        require(name in ROLES,'PAT_IO_RESOURCE_ACTOR')
        op=self._call('invoke:'+name,lambda:self.runtime.journal.submit(self.owner,self.requests[name]))
        require(name not in self.operation_ids or self.operation_ids[name]==op['id'],'PAT_IO_TRIAL_REPLAY_CHANGED')
        self.operation_ids[name]=op['id']
        return op

    def probe_gpio(self):
        return self._call('probe:gpio_while_pwm',
            lambda:self.runtime.journal.submit(self.owner,self.requests['gpio_while_pwm']))

    def read_gpio(self):
        return self._call('read:gpio',lambda:self.runtime.operation(self.owner,self.operation_ids['gpio']))


def _busy(function):
    try: function()
    except JournalError as error:
        require(error.code=='RESOURCE_BUSY','PAT_IO_RESOURCE_UNEXPECTED_FAILURE')
        return
    require(False,'PAT_IO_RESOURCE_BUSY_MISSING')


def run_resource_challenge(directory, *, matrix, candidate, installation, descriptor, challenge_bindings, case_id, group_budget=None):
    if group_budget is not None: group_budget.assert_case(case_id)
    matrix=snapshot(matrix,'PAT_IO_RESOURCE_MATRIX')
    policy=IoCombinedMatrixPolicy(installation)
    matrix_digest=policy.validate(matrix,candidate,descriptor,challenge_bindings,limits=matrix.get('limits'))
    require(type(case_id) is str,'PAT_IO_RESOURCE_CASE')
    cases=[c for c in matrix['cases'] if c['caseId']==case_id]
    require(len(cases)==1,'PAT_IO_RESOURCE_CASE');case=cases[0]
    require(case['kind']=='resource_challenge','PAT_IO_RESOURCE_UNSUPPORTED_CASE')
    programs={p['digest']:p['artifact'] for p in matrix['programs']};actors={}
    qualifier=IoSequencePolicy(installation)
    for role in ROLES:
        artifact=programs[case['actors'][role]['programDigest']];chosen=challenge_bindings[role]['descriptor']
        actors[role]=dict(artifact=artifact,original_descriptor=chosen,static_contract=qualifier.qualify(artifact,chosen))
    engine=ResourceIoTrialEngine(directory,installation,case=case,actors=actors,group_budget=group_budget)
    try:
        engine.lower_actors()
        engine.invoke_actor('gpio');engine.drive('adapters')
        _busy(lambda:engine.invoke_actor('pwm'));_busy(lambda:engine.invoke_actor('alias'))
        engine.invoke_actor('independent');engine.drive('adapters')
        engine.advance_to(ORIGIN+10);engine.drive('adapters')
        engine.invoke_actor('gpio')
        engine.invoke_actor('alias');engine.drive('adapters');engine.read_gpio()
        engine.advance_to(ORIGIN+20);engine.drive('adapters')
        engine.invoke_actor('pwm');engine.drive('adapters');_busy(engine.probe_gpio)
        engine.advance_to(ORIGIN+30);engine.drive('adapters')
        for role in ROLES:engine.invoke_actor(role)
        engine.capture('test_final');report=engine.report()
        require(report['schedulerTicks']<=case['schedulerTickCeiling'],'PAT_IO_RESOURCE_TICK_RESERVATION')
        manifest=dict(profile='hms.pat.io-resource-trial/0.1',caseId=case_id,matrixDigest=matrix_digest,
            records=copy.deepcopy(engine.records),configuration=engine.configuration_manifest(),report=report,
            operationIds=copy.deepcopy(engine.operation_ids),closed=False,executionPerformed=True,
            childOperationReservation=5,schedulerTickReservation=case['schedulerTickCeiling'],
            requiredMatrixCoverageChecked=False,independentOutcomeChecked=False,qualificationPassed=False,
            actualAggregateStorageEnforced=False)
    finally:engine.close()
    manifest['closed']=True;encoded=canonical(manifest)
    require(len(encoded)<=65536 and manifest['configuration']['combinedRecords']+1<=MAX_RECORDS and
            manifest['configuration']['combinedBytes']+len(encoded)<=MAX_OUTPUT_BYTES,'PAT_IO_RESOURCE_MANIFEST_LIMIT')
    return manifest
