"""Fixed binding/all-grant withdrawal captures; no installed qualification API."""
import copy

from .contracts import canonical
from .journal import JournalError, TERMINAL
from .pat_compiler import evaluation_environment
from .pat_contracts import PatError, require, snapshot
from .pat_io_bindings import IoRegistryPatBindings
from .pat_io_combined_matrix import IoCombinedMatrixPolicy
from .pat_io_configuration_capture import ConfiguredIoTrialEngine
from .pat_io_trials import ORIGIN, MAX_RECORDS, MAX_OUTPUT_BYTES
from .synthetic_io_runtime import IoRuntime


class AuthorityIoTrialEngine(ConfiguredIoTrialEngine):
    _record_profile = 'hms.pat.io-trial-record/0.5'

    def __init__(self, directory, artifact, installation, descriptor, *, case, group_budget=None):
        self.case = snapshot(case)
        self.probes = {}
        super().__init__(directory, artifact, installation, descriptor, group_budget=group_budget)

    def _open(self, *, create):
        self._check_budget()
        self.runtime = IoRuntime(self.directory/'state', create=create,
            owner=self.owner if create else None, installation=self.document,
            wall_clock_ms=self.clock, monotonic_ms=self.clock)
        require(not self.runtime.route_errors and not self.runtime._threads and
            set(self.runtime.adapters)==set(self.document['routes']['adapters']), 'PAT_IO_TRIAL_RECONSTRUCTION')
        original = self.runtime.journal.submission_guard
        def bounded_admission(context, request, intent, digest, managed, now):
            count = self.runtime.journal._db.execute('SELECT count(*) FROM operations').fetchone()[0]
            if self._group_budget is not None:
                self._group_budget.admission(count)
            require(self.plan is not None and count < self.case['plannedChildOperations'],
                'PAT_IO_TRIAL_OPERATION_LIMIT')
            allowed = ([s['request'] for s in self.plan['request']['procedure']['steps']]
                       if managed is not None else list(self.probes.values()))
            require(canonical(request) in [canonical(r) for r in allowed], 'PAT_IO_TRIAL_REQUEST_INVENTORY')
            return original(context, request, intent, digest, managed, now)
        self.runtime.journal.submission_guard = bounded_admission
        d = self.original_descriptor
        registration = {k:d[k] for k in ('driverProfile','driverDigest','installationDigest','argumentMetadata')}
        registration.update(instanceId=d['binding']['instanceId'],typeDigest=d['binding']['typeDigest'])
        provider = IoRegistryPatBindings(self.runtime,[registration])
        self._binding_configuration(copy.deepcopy(registration),provider.registration_identity)
        wanted = evaluation_environment(self.artifact,{self.role:d},deployment=self.owner.deployment)
        try:
            with self.runtime.journal._transaction():
                current = provider.for_roles(self.owner,self.artifact,{self.role:registration['instanceId']})
        except PatError as error:
            # This is the real resolver refusal. Historical bindings stay only
            # in the old compiled request; no fabricated current environment.
            require(not create and error.code=='PAT_BINDING_NOT_APPLICABLE', 'PAT_IO_AUTHORITY_RESOLUTION')
            actual = None
            resolution = dict(status='unavailable',exception=type(error).__name__,code=error.code)
        else:
            require(create,'PAT_IO_AUTHORITY_RESOLUTION')
            actual = evaluation_environment(self.artifact,current,deployment=self.owner.deployment)
            require(actual['evaluationEnvironment']==wanted['evaluationEnvironment'] and
                actual['environmentDigest']==wanted['environmentDigest'], 'PAT_IO_TRIAL_ENVIRONMENT_CHANGED')
            self.bindings = current
            resolution = dict(status='resolved',exception=None,code=None)
        self._write('runtime_opened',dict(create=create,wallMs=self.clock.value,
            ownerEpoch=self.runtime.journal.owner_epoch,authorityId=self.runtime.journal.authority_id,
            session=self.runtime.io_board.session,originalEnvironment=wanted,workerEnvironment=actual,
            bindingResolution=resolution))

    def operations(self):
        rows = self.runtime.journal._db.execute('SELECT id FROM operations ORDER BY rowid LIMIT 4').fetchall()
        require(len(rows)<=self.case['plannedChildOperations'],'PAT_IO_TRIAL_OPERATION_LIMIT')
        return [self.runtime.journal._operation(r[0]) for r in rows]

    def declare_probes(self):
        require(self.phase==1 and self.plan is not None,'PAT_IO_AUTHORITY_PROBE_PHASE')
        if self.case['definition']['scenario']=='binding_pending':
            original = self.plan['request']['procedure']['steps'][0]['request']
            self.probes['inactive_binding'] = copy.deepcopy(original) | {'operationKey':'trial:probe:inactive_binding'}
        self._write('authority_input',dict(case=self.case,probes=self.probes))

    def change(self):
        if self.case['definition']['scenario']=='full_authority_withdrawal':
            return self._call('change:authority',lambda:self.runtime.registry.grant(
                self.owner,self.owner.principal,'*','admin',enabled=False))
        return self._call('change:binding',lambda:self.runtime.registry.invalidate(
            self.owner,self.original_descriptor['binding']['instanceId']))

    def probe_binding(self):
        return self._call('probe:inactive_binding',lambda:self.runtime.journal.submit(
            self.owner,canonical(self.probes['inactive_binding'])))

    def read_operation(self):
        operation, = self.operations()
        return self._call('read:operation',lambda:self.runtime.operation(self.owner,operation['id']))

    def read_parent(self):
        return self._call('read:parent',self.status)

    def probe_namespace(self):
        return self._call('probe:namespace',lambda:self.runtime.journal.issue_namespace(self.owner,ORIGIN+1001))

    def report(self):
        # Internal observation is explicitly not a successful public status call.
        operations = self.operations()
        with self.runtime.journal._mutex:
            procedure = self.runtime.procedures._status(self.runtime.procedures._row(self.procedure_id))
        result = dict(profile='hms.pat.io-trial-observation/0.2',statusAccess='privileged_trial_observation',
            clock=self.clock.value,procedure=procedure,operationIds=[o['id'] for o in operations],
            unresolvedOperations=[o['id'] for o in operations if o['state'] not in TERMINAL or o['claims']],
            schedulerTicks=self.ticks,evidenceRecords=len(self.records),evidenceBytes=self.output_bytes,
            qualificationPassed=False,independentOutcomeChecked=False)
        self._write('trial_observation',result)
        return result


def _denied(function, code):
    try: function()
    except JournalError as error:
        require(error.code==code,'PAT_IO_AUTHORITY_UNEXPECTED_FAILURE')
        return
    require(False,'PAT_IO_AUTHORITY_REFUSAL_MISSING')


def run_authority_challenge(directory, *, matrix, candidate, installation, descriptor, challenge_bindings, case_id, group_budget=None):
    if group_budget is not None: group_budget.assert_case(case_id)
    matrix = snapshot(matrix,'PAT_IO_AUTHORITY_MATRIX')
    policy = IoCombinedMatrixPolicy(installation)
    matrix_digest = policy.validate(matrix,candidate,descriptor,challenge_bindings,limits=matrix.get('limits'))
    require(type(case_id) is str,'PAT_IO_AUTHORITY_CASE')
    cases = [c for c in matrix['cases'] if c['caseId']==case_id]
    require(len(cases)==1,'PAT_IO_AUTHORITY_CASE');case=cases[0]
    require(case['kind']=='fixed_challenge' and case['definition']['scenario'] in {
        'binding_before_dispatch','binding_pending','full_authority_withdrawal'}, 'PAT_IO_AUTHORITY_UNSUPPORTED_CASE')
    artifact = next(p['artifact'] for p in matrix['programs'] if p['digest']==case['programDigest'])
    engine = AuthorityIoTrialEngine(directory,artifact,installation,descriptor,case=case,group_budget=group_budget)
    scenario = case['definition']['scenario']
    try:
        engine.lower({});engine.declare_probes();engine.submit();engine.drive('procedure')
        if scenario!='binding_before_dispatch':engine.drive('adapters')
        engine.change()
        if scenario=='binding_before_dispatch':
            engine.drive('adapters');engine.drive('procedure')
        else:
            if scenario=='full_authority_withdrawal':
                for call in (engine.read_operation,engine.read_parent,engine.submit,engine.probe_namespace):
                    _denied(call,'ACCESS_DENIED')
            engine.reopen();engine.drive('adapters')
            if scenario=='binding_pending':_denied(engine.resume,'PROCEDURE_DEPENDENCY_UNRESOLVED')
            engine.cancel()
            if scenario=='binding_pending':_denied(engine.probe_binding,'BINDING_INACTIVE')
            else:
                for call in (engine.read_operation,engine.read_parent,engine.submit,engine.probe_namespace):
                    _denied(call,'ACCESS_DENIED')
        engine.capture('test_final');report=engine.report()
        require(report['schedulerTicks']<=case['schedulerTickCeiling'],'PAT_IO_AUTHORITY_TICK_RESERVATION')
        manifest = dict(profile='hms.pat.io-authority-trial/0.1',caseId=case_id,matrixDigest=matrix_digest,
            records=copy.deepcopy(engine.records),configuration=engine.configuration_manifest(),report=report,
            closed=False,executionPerformed=True,childOperationReservation=case['plannedChildOperations'],
            schedulerTickReservation=case['schedulerTickCeiling'],requiredMatrixCoverageChecked=False,
            independentOutcomeChecked=False,qualificationPassed=False,actualAggregateStorageEnforced=False)
    finally:engine.close()
    manifest['closed']=True;encoded=canonical(manifest)
    require(len(encoded)<=65536 and manifest['configuration']['combinedRecords']+1<=MAX_RECORDS and
        manifest['configuration']['combinedBytes']+len(encoded)<=MAX_OUTPUT_BYTES,'PAT_IO_AUTHORITY_MANIFEST_LIMIT')
    return manifest
