"""Original reviewed-only controls for the private pure compilation change."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'project'),str(HERE/'project/tests'),str(HERE/'owner')]
from guardian import Guardian
from standing_host_fixture import Fixture,OWNER,installation
import standing_host_controls as legacy
from hms import standing_pat as pat
from hms import standing_contracts as c
from hms import resource_topology as graph
from hms.contracts import canonical
from hms.journal import JournalError
from hms.standing_capacity import check as capacity_check

BASELINE_SHA='b1734acbe443501124b2a6965aa9768abd1eb3c3966e57f4945ebc10f801d726'
checks=0
FINAL_DESTINATION=None
FINAL_REPORT=None


def require(value,message='selection reuse assertion'):
    global checks
    checks+=1
    if not value:raise AssertionError(str(message)+' #'+str(checks))


def save(path,value):
    body=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
    if len(body)>1024*1024:raise RuntimeError('Bounded evidence exceeded')
    temporary=Path(str(path)+'.pending')
    with temporary.open('wb') as out:out.write(body);out.flush();os.fsync(out.fileno())
    os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def refuse(code,action,*args,**kwargs):
    try:action(*args,**kwargs)
    except JournalError as error:require(error.code==code,(code,error.code))
    else:raise AssertionError('Expected '+code)


def baseline():
    source=HERE/'originals/standing_pat.py'
    require(hashlib.sha256(source.read_bytes()).hexdigest()==BASELINE_SHA,'Exact old compiler oracle')
    name='hms._selection_reuse_original'
    spec=importlib.util.spec_from_file_location(name,source);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module)
    return module


def outcome(action):
    try:
        value=action();return ('ok',value._wire,value.configuration.payload())
    except Exception as error:return ('error',type(error).__name__,getattr(error,'code',None),str(error))


def compilation_count(action):
    # Control-only observational Python call hook; no candidate/global parser
    # replacement, no timing claim and no application callback is installed.
    require(sys.getprofile() is None)
    code=c.parse_installation.__code__;calls=0
    def observe(frame,event,arg):
        nonlocal calls
        if event=='call' and frame.f_code is code:calls+=1
    sys.setprofile(observe)
    try:value=action()
    finally:sys.setprofile(None)
    return value,calls


def compiler_equivalence(directory,pipe,evidence,manifest):
    original=baseline();installed=installation(pipe,evidence/manifest['binaryPath'])
    artifact=pat.installed_artifact(installed);records=[]
    def check(name,value,config,success=False):
        expected=outcome(lambda:original.compile_artifact(copy.deepcopy(value),copy.deepcopy(config)))
        public=outcome(lambda:pat.compile_artifact(copy.deepcopy(value),copy.deepcopy(config)))
        private=outcome(lambda:pat._compile_catalog_artifact(copy.deepcopy(value),copy.deepcopy(config)))
        require(expected==public==private,name)
        require((expected[0]=='ok')==success,name+' classification')
        records.append({'case':name,'outcome':expected[0],'error':None if success else list(expected[1:]),
            'compiledSha256':hashlib.sha256(expected[1]).hexdigest() if success else None})
    check('literal',artifact,installed,True)
    check('canonical_bytes',canonical(artifact),installed,True)
    for field in ('id','taskKind','inputProfile'):
        value=copy.deepcopy(artifact);value[field]='other:valid-label';check('label_'+field,value,installed,True)
    reordered=copy.deepcopy(installed);reordered['hardwareResources'].reverse()
    check('resource_order',pat.installed_artifact(reordered),reordered,True)
    deep=None
    for _ in range(40):deep=[deep]
    invalid=[('bad_json',b'{'),('duplicate_key',b'{"id":1,"id":2}'),('oversize',{'x':'x'*65537}),
        ('excess_depth',deep),('negative_zero',b'{"x":-0}'),
        ('missing_fields',{}),('unexpected_fields',{**artifact,'unexpected':1})]
    for name,value in invalid:
        check(name,value,installed);check(name+'_and_bad_installation',value,{})
    for name,path,value in [('bool_kernel',('kernel',),True),('float_kernel',('kernel',),1.0),
            ('bool_lower',('configuration','lowerDemand'),False),('float_lower',('configuration','lowerDemand'),20000.0),
            ('invalid_label',('id',),'bad label'),('wrong_domain',('qualificationDomainDigest',),'sha256:'+'0'*64)]:
        altered=copy.deepcopy(artifact);target=altered
        for part in path[:-1]:target=target[part]
        target[path[-1]]=value;check(name,altered,installed)
    for name,mutate in [('slot_service',lambda x:x.update(slotResource='atom:service')),
            ('capacity_bool',lambda x:x['capacity'].update(maxDeployments=True)),
            ('driver_digest',lambda x:x.update(driverSourceDigest='sha256:'+'0'*64)),
            ('missing_driver_dependency',lambda x:x['topology']['nodes']['demand-access'].update(requires=[])),
            ('alias_extra_slot',lambda x:x['topology']['aliases']['alias:demand']['includes'].append('atom:slot')),
            ('epoch_bool',lambda x:x['endpoint']['epochs'].__setitem__(0,True))]:
        altered=copy.deepcopy(installed);mutate(altered)
        if name=='missing_driver_dependency':
            altered['generations']['topologyDigest']=graph.topology_digest(altered['topology'])
        check(name,artifact,altered)
    for name,mutate in [('different_boot',lambda x:x['endpoint'].update(boot=2)),
            ('different_incarnation',lambda x:x['endpoint'].update(incarnationHex='11'*16))]:
        altered=copy.deepcopy(installed);mutate(altered)
        check(name,pat.installed_artifact(altered),altered)
    expected=original.compile_artifact(artifact,installed)
    public,count=compilation_count(lambda:pat.compile_artifact(artifact,installed));require(count==5)
    row={'document':canonical(artifact),'digest':pat.artifact_digest(artifact)}
    private,count_private=compilation_count(lambda:pat.StandingCatalog._compiled(None,row,installed));require(count_private==1)
    require(public._wire==private[1]._wire==expected._wire and private[0]==artifact)
    returned=private[1].document;returned['limits']['activationCap']=1
    private[0]['configuration']['lowerDemand']=0
    require(private[1].document==expected.document and artifact['configuration']['lowerDemand']==20000)
    again=pat.StandingCatalog._compiled(None,row,installed)[1];require(again._wire==expected._wire)
    wrong={'document':row['document'],'digest':'sha256:'+'0'*64}
    refuse('STANDING_ARTIFACT_CHANGED',pat.StandingCatalog._compiled,None,wrong,{})
    changed=copy.deepcopy(installed);changed['capacity']['maxDeployments']=True
    refuse('STANDING_CAPACITY_UNQUALIFIED',pat.StandingCatalog._compiled,None,row,changed)
    # Current pure helpers/constants are read anew on the next independent call.
    saved=pat.CONFIGURATION['lowerDemand'];pat.CONFIGURATION['lowerDemand']=19999
    try:refuse('STANDING_PAT_DOMAIN_UNQUALIFIED',pat.StandingCatalog._compiled,None,row,installed)
    finally:pat.CONFIGURATION['lowerDemand']=saved
    require(pat.StandingCatalog._compiled(None,row,installed)[1]._wire==expected._wire)
    validator=pat.parse_installation
    def changed_validator(_):raise JournalError('CONTROL_CHANGED_INSTALLATION_VALIDATOR')
    pat.parse_installation=changed_validator
    try:
        refuse('CONTROL_CHANGED_INSTALLATION_VALIDATOR',pat.compile_artifact,artifact,installed)
        refuse('CONTROL_CHANGED_INSTALLATION_VALIDATOR',pat.StandingCatalog._compiled,None,row,installed)
    finally:pat.parse_installation=validator
    require(pat.StandingCatalog._compiled(None,row,installed)[1]._wire==expected._wire)
    save(directory/'evidence.json',{'case':'compiler_equivalence','vectors':records,'publicParseCalls':count,
        'privateParseCalls':count_private,'oldOracleSha256':BASELINE_SHA,'compiledSha256':hashlib.sha256(expected._wire).hexdigest(),
        'observationalProfileHook':True,'timingMeasured':False,'physicalEligible':False,'protectedCapacity':False})


class ProbeHost(legacy.LostReplyHost):
    trace=None
    def _checkpoint(self,phase,value=None):
        if self.trace is None:self.trace=[]
        require(len(self.trace)<2048,'Bounded trace')
        if phase=='before_exchange':self.trace.append({'direction':'request','session':value.frame.session,'sequence':value.frame.sequence,'raw':value.frame.payload.hex()})
        elif phase=='after_exchange':self.trace.append({'direction':'response','session':value['session'],'sequence':value['response_sequence'],'raw':value['raw'].hex()})
        super()._checkpoint(phase,value)


class ProbeFixture(Fixture):
    def __init__(self,*args,**kwargs):self.retained_trace=[];super().__init__(*args,**kwargs)
    def attach(self,*,create):
        super().attach(create=create);self.host.trace=self.retained_trace


def management_replays(f):
    with f.policy.hold_image():
        with f.catalog.hold_selection(OWNER,f.request()):
            with f.journal._transaction():
                selected,count=compilation_count(lambda:f.catalog._selected(OWNER,f.request()))
                require(count==3);f.selection_parse_calls=count
                f.catalog.check_selection(selected,OWNER)
    row=f.journal._db.execute('SELECT digest,evaluation,decision FROM sp_artifacts').fetchone();digest=row['digest']
    require(f.catalog.record_evaluation(OWNER,digest,pat.EVALUATOR,f.manifest['runId'])==row['evaluation'])
    require(f.catalog.promote(OWNER,digest)==row['decision'])
    artifact=pat.installed_artifact(f.installation);artifact['id']='other:label'
    other=f.catalog.publish(OWNER,artifact)
    refuse('STANDING_ORIGINAL_RUN_CONFLICT',f.catalog.record_evaluation,OWNER,other,pat.EVALUATOR,f.manifest['runId'])
    f.catalog.suspend(OWNER,digest)
    refuse('STANDING_NO_ELIGIBLE_ARTIFACT',f.host.prepare,OWNER,f.request())
    require(not f.journal._db.execute('SELECT 1 FROM claims').fetchone())
    f.catalog.promote(OWNER,digest);legacy.opened(f)


def final_evidence_withdrawal(f):
    f.store.fault='before_deployment_commit';f.store.hook=lambda:setattr(f.producer,'enabled',False)
    refuse('STANDING_QUALIFICATION_LEASE_UNAVAILABLE',f.host.prepare,OWNER,f.request())
    require(not f.journal._db.execute('SELECT 1 FROM claims').fetchone())
    f.producer.enabled=True;f.store.hook=None;legacy.opened(f)


def final_artifact_change(f):
    def change():
        row=f.journal._db.execute('SELECT digest,document FROM sp_artifacts').fetchone()
        artifact=c.document(bytes(row['document']));artifact['id']='changed:at-final-boundary'
        # Deliberate stored-record corruption; not capacity prefill/public work.
        f.journal._db.execute('UPDATE sp_artifacts SET document=? WHERE digest=?',(canonical(artifact),row['digest']))
    f.store.fault='before_deployment_commit';f.store.hook=change
    refuse('STANDING_ARTIFACT_CHANGED',f.host.prepare,OWNER,f.request())
    require(not f.journal._db.execute('SELECT 1 FROM claims').fetchone())
    f.store.hook=None;legacy.opened(f)


LIVE=(management_replays,final_evidence_withdrawal,final_artifact_change,
      legacy.renewal_withdrawal,legacy.expiry_after_commit,legacy.shared_authority,
      legacy.finite_policy_replacement,legacy.prepared_mutation_recovery,legacy.common_revoke_remains_unresolved)
PROFILES={'pure':['compiler_equivalence'],'live':[f.__name__ for f in LIVE]}


def main():
    global FINAL_DESTINATION,FINAL_REPORT
    require(not sys.flags.optimize and len(sys.argv)==7 and sys.argv[1] in PROFILES,'Fixed invocation')
    profile=sys.argv[1];state,pipe,evidence,manifest_path,helper=map(Path,sys.argv[2:])
    def interrupted(signum,_):raise RuntimeError('Control interrupted '+str(signum))
    signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGTERM,interrupted)
    state.mkdir();FINAL_DESTINATION=state/'CONTROL-RESULTS.json';FINAL_REPORT={'passed':False,'phase':'preparation'};save(FINAL_DESTINATION,FINAL_REPORT)
    guardian=Guardian(helper);manifest=json.loads(manifest_path.read_bytes());results=[];failure=None
    try:
        for name in PROFILES[profile]:
            began=time.monotonic_ns();prior=checks;old_legacy=legacy.checks;directory=state/name
            if profile=='pure':directory.mkdir();compiler_equivalence(directory,pipe,evidence,manifest);identity=reap=None
            else:
                with ProbeFixture(guardian,directory,pipe,evidence,manifest,host_class=ProbeHost,store_class=legacy.FaultStore) as f:
                    identity=copy.deepcopy(guardian.handles[f.pid]['identity']);count=len(guardian.records)
                    next(action for action in LIVE if action.__name__==name)(f)
                    record={'case':name,'native':{str(n):f.snapshot(n) for n in range(28)},'trace':f.retained_trace,
                        'route':f.store.route(),'capacity':capacity_check(f.journal._db,JournalError),'nativeStartIdentity':identity,
                        'hostImplementationDigest':f.installation['hostImplementationDigest'],'legacyChecks':legacy.checks-old_legacy,
                        'selectionParseCalls':getattr(f,'selection_parse_calls',None),
                        'physicalEligible':False,'protectedCapacity':False}
                    require(f.policy._held_image is None and f.driver._lease is None and f.catalog._selection is None and f.producer._held is None)
                require(len(guardian.records)==count+1);reap=copy.deepcopy(guardian.records[-1])
                require(reap['reaped'] and reap['exitCode']==0 and all(reap[k]==v for k,v in identity.items()))
                record['nativeReap']=reap;save(directory/'evidence.json',record)
            results.append({'case':name,'passed':True,'checks':checks-prior,'legacyChecks':legacy.checks-old_legacy,
                'elapsedMonotonicNs':str(time.monotonic_ns()-began),'nativeStartIdentity':identity,'nativeReap':reap,
                'evidenceSha256':hashlib.sha256((directory/'evidence.json').read_bytes()).hexdigest(),
                'databaseSha256':None if profile=='pure' else hashlib.sha256((directory/'authority.db').read_bytes()).hexdigest()})
    except BaseException as error:failure=type(error).__name__+': '+str(error);traceback.print_exc();raise
    finally:
        previous=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        try:
            errors=[];empty=closed=False
            for label,action in [('settle',guardian.settle),('empty',guardian.empty),('close',guardian.close)]:
                try:
                    value=action()
                    if label=='empty':empty=value is True
                    if label=='close':closed=True
                except BaseException as error:errors.append(label+': '+type(error).__name__+': '+str(error))
            pending=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
            FINAL_REPORT={'passed':failure is None and not errors and empty and closed and not pending and all(r['reaped'] and r['exitCode']==0 for r in guardian.records),
                'profile':profile,'cases':results,'checks':checks,'legacyChecks':legacy.checks,'failure':failure,'cleanupErrors':errors,
                'ownerEmpty':empty,'ownerClosed':closed,'interruptsPending':pending,'nativeChildrenReaped':guardian.records,
                'actualOwnerDeath':False,'productionChanged':True,'full128RecordQualification':False,'qualificationRerun':False,
                'physicalEligible':False,'protectedCapacity':False,'publicMountEligible':False}
            save(FINAL_DESTINATION,FINAL_REPORT);print(json.dumps(FINAL_REPORT,sort_keys=True))
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        if FINAL_DESTINATION is not None:
            FINAL_REPORT['passed']=False;FINAL_REPORT['terminalFailure']=type(error).__name__+': '+str(error)
            FINAL_REPORT['terminalPendingSignals']=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM});save(FINAL_DESTINATION,FINAL_REPORT)
        raise
