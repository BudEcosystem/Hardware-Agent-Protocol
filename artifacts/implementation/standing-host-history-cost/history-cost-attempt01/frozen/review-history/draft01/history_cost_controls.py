"""Original intrusive timing diagnostic; source-only until root review.

The production classes and their canonical/parser helpers remain byte-exact.
Every measured method delegates once. Timings include wrapper overhead; nested
inclusive samples are not additive. Context held lifetimes overlap method spans.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time
import traceback

MODULE_STARTED=time.monotonic_ns()
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'project'),str(HERE/'project/tests'),str(HERE/'owner')]
from guardian import Guardian
from standing_host_fixture import Fixture,OWNER
from hms.journal import JournalError
from hms.standing_endpoint import StandingHost
from hms.standing_store import StandingStore
from hms.standing_wire import Opcode
from hms.standing_capacity import check as capacity_check
from hms.contracts import canonical
IMPORT_FINISHED=time.monotonic_ns()

checks=0
FINAL_DESTINATION=None
FINAL_REPORT=None
LOOPS=32
TABLES=('sd_meta','sd_route','sd_deployments','sd_mutations','sd_activations',
        'sd_episodes','sd_activation_versions','sd_conflicts')
BASE_LABELS=('store.mutation','store.pending','store.reserve_mutation',
             'store.abandon_prepared_mutation','policy.fresh','policy.check_image',
             'catalog._selected')
CONTEXT_LABELS=('policy.hold_image','driver.hold','catalog.hold_selection','producer.snapshot')
LABELS=set(BASE_LABELS)|{'store._read_locked:'+table for table in TABLES} | {
    name+suffix for name in CONTEXT_LABELS for suffix in ('.enter','.exit','.held')}
PHASES={'setup','final','cleanup'}|{str(n)+':'+part for n in range(LOOPS) for part in ('mutate','abandon','assert')}


def require(value,message='history-cost assertion'):
    global checks
    checks+=1
    if not value:raise AssertionError(str(message)+' #'+str(checks))


def save(path,value):
    data=canonical(value)
    if len(data)>1024*1024:raise RuntimeError('Bounded evidence exceeded')
    temporary=Path(str(path)+'.pending')
    with temporary.open('wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
    os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


class Meter:
    """Closed aggregate labels/phases; no per-call log or SQL callback."""
    def __init__(self):self.phase='setup';self.rows={};self.stack=[]
    def set_phase(self,phase):
        if phase not in PHASES or self.stack:raise RuntimeError('Invalid metric phase boundary')
        self.phase=phase
    def _row(self,label,phase):
        if label not in LABELS or phase not in PHASES:raise RuntimeError('Unbounded metric label')
        key=(phase,label)
        if key not in self.rows:self.rows[key]={'calls':0,'inclusiveNs':0,'exclusiveNs':0,'errors':0}
        return self.rows[key]
    def call(self,label,action,*args,**kwargs):
        row=self._row(label,self.phase);row['calls']+=1
        frame=[time.monotonic_ns(),0]
        try:
            self.stack.append(frame)
            return action(*args,**kwargs)
        except BaseException:
            row['errors']+=1;raise
        finally:
            elapsed=time.monotonic_ns()-frame[0]
            if self.stack and self.stack[-1] is frame:self.stack.pop()
            row['inclusiveNs']+=elapsed;row['exclusiveNs']+=elapsed-frame[1]
            if self.stack:self.stack[-1][1]+=elapsed
    def held(self,label,phase,began):
        row=self._row(label+'.held',phase);row['calls']+=1
        row['inclusiveNs']+=time.monotonic_ns()-began
        # Held lifetimes overlap arbitrary method scopes. No exclusive meaning.
    def count(self,label,phases):return sum(row['calls'] for (phase,name),row in self.rows.items() if name==label and phase in phases)
    def export(self,*,partial=False):
        if self.stack and not partial:raise RuntimeError('Unfinished timed method')
        return [{'phase':phase,'method':label,'calls':row['calls'],'errors':row['errors'],
                 'inclusiveNs':str(row['inclusiveNs']),
                 'exclusiveNs':None if label.endswith('.held') else str(row['exclusiveNs'])}
                for (phase,label),row in sorted(self.rows.items())]


METER=Meter()


class TimedContext:
    """Delegate each actual context enter/exit once, retaining suppression."""
    def __init__(self,label,context):self.label=label;self.context=context;self.began=None;self.phase=None
    def __enter__(self):
        value=METER.call(self.label+'.enter',self.context.__enter__)
        self.phase=METER.phase;self.began=time.monotonic_ns();return value
    def __exit__(self,*exception):
        if self.began is not None:METER.held(self.label,self.phase,self.began)
        return METER.call(self.label+'.exit',self.context.__exit__,*exception)


def context_probe(owner,name,label):
    original=getattr(owner,name)
    def wrapped(*args,**kwargs):return TimedContext(label,original(*args,**kwargs))
    setattr(owner,name,wrapped)


def method_probe(owner,name,label):
    original=getattr(owner,name)
    def wrapped(*args,**kwargs):return METER.call(label,original,*args,**kwargs)
    setattr(owner,name,wrapped)


class ProbeStore(StandingStore):
    def _read_locked(self,table,*args,**kwargs):
        return METER.call('store._read_locked:'+table,super()._read_locked,table,*args,**kwargs)
    def mutation(self,*args,**kwargs):return METER.call('store.mutation',super().mutation,*args,**kwargs)
    def pending(self,*args,**kwargs):return METER.call('store.pending',super().pending,*args,**kwargs)
    def reserve_mutation(self,*args,**kwargs):return METER.call('store.reserve_mutation',super().reserve_mutation,*args,**kwargs)
    def abandon_prepared_mutation(self,*args,**kwargs):
        return METER.call('store.abandon_prepared_mutation',super().abandon_prepared_mutation,*args,**kwargs)


class ProbeHost(StandingHost):
    hook=None
    trace=None
    def _checkpoint(self,phase,value=None):
        if self.trace is None:self.trace=[]
        if len(self.trace)>=2048:raise RuntimeError('Bounded trace exceeded')
        if phase=='before_exchange':
            self.trace.append({'direction':'request','session':value.frame.session,
                'sequence':value.frame.sequence,'raw':value.frame.payload.hex()})
        elif phase=='after_exchange':
            self.trace.append({'direction':'response','session':value['session'],
                'sequence':value['response_sequence'],'raw':value['raw'].hex()})
        if self.hook is not None:self.hook(phase,value)


class ProbeFixture(Fixture):
    def attach(self,*,create):
        # Publication/evaluation in super.attach remains outside these method
        # probes. Its wall span belongs to fixtureSetupElapsedNs, not the loop.
        super().attach(create=create)
        for owner,name,label in ((self.policy,'hold_image','policy.hold_image'),
                (self.driver,'hold','driver.hold'),(self.catalog,'hold_selection','catalog.hold_selection'),
                (self.producer,'snapshot','producer.snapshot')):context_probe(owner,name,label)
        for owner,name,label in ((self.policy,'fresh','policy.fresh'),(self.policy,'check_image','policy.check_image'),
                (self.catalog,'_selected','catalog._selected')):method_probe(owner,name,label)


def snapshot(f):return {str(n):f.snapshot(n) for n in range(28)}


def history_cost(f):
    application_setup_began=time.monotonic_ns()
    row=f.host.prepare(OWNER,f.request());require(row['openState']=='prepared')
    row=f.host.open(OWNER,row['id']);require(row['openState']=='accepted')
    identifier=row['id'];f.cycle(0);before=snapshot(f)
    iterations=[];loop_started=time.monotonic_ns()
    for number in range(LOOPS):
        parts={};phases={str(number)+':'+part for part in ('mutate','abandon','assert')}
        key='never-start:'+str(number)
        def hook(phase,value):
            if phase=='after_mutation_reservation_commit':
                f.host.hook=None;raise JournalError('CONTROL_PREPARED_BOUNDARY')
        METER.set_phase(str(number)+':mutate');began=time.monotonic_ns();f.host.hook=hook
        try:f.host.mutate(OWNER,identifier,key,Opcode.START)
        except JournalError as error:require(error.code=='CONTROL_PREPARED_BOUNDARY')
        else:raise AssertionError('Expected original prepared boundary')
        parts['mutateElapsedNs']=str(time.monotonic_ns()-began)
        METER.set_phase(str(number)+':abandon');began=time.monotonic_ns()
        item=f.host.abandon_prepared(OWNER,identifier,mutation_key=key)
        parts['abandonElapsedNs']=str(time.monotonic_ns()-began)
        METER.set_phase(str(number)+':assert');began=time.monotonic_ns()
        require(item['state']=='never_handed_off' and item['endpointSequence']==1)
        require(f.store.pending(identifier)==[] and f.snapshot(13)==0)
        parts['assertElapsedNs']=str(time.monotonic_ns()-began)
        validations=METER.count('store.mutation',phases)
        reads=METER.count('store._read_locked:sd_mutations',phases)
        require(validations==reads==4*number+6,'Exact per-iteration source count')
        iterations.append({'number':number,'key':key,'predictedMutationValidations':4*number+6,
            'mutationValidationCalls':validations,'mutationReadCalls':reads,**parts})
    loop_elapsed=time.monotonic_ns()-loop_started
    METER.set_phase('final')
    row=f.store.row(identifier)
    items=[f.store.mutation(identifier,n) for n in range(1,LOOPS+1)]
    require([item['hostKey'] for item in items]==['never-start:'+str(n) for n in range(LOOPS)])
    require(all(item['state']=='never_handed_off' and item['settlement']=='durable-prepared-never-possible' and
                item['endpointSequence']==1 and item['reply'] is not None for item in items))
    require(f.store.pending(identifier)==[])
    retained_claims=[r[0] for r in f.journal._db.execute('SELECT resource FROM claims WHERE operation_id=? ORDER BY resource',(identifier,))]
    require(retained_claims==['atom:demand','atom:output','atom:slot'])
    require(row['openState']=='accepted' and not row['retired'] and row['revoke'] is None)
    require(row['mutationSequence']==row['collected']==row['acknowledged']==row['highWater']==0)
    require(not any(row[key] for key in ('disputed','effectUnknown','recoveryRequired','sequenceUncertain','transportUncertain')))
    after=snapshot(f)
    require(all(before[key]==after[key] for key in before if key!='22'),'Read-only loop preserves native counters and virtual time')
    phases=PHASES-{'setup','final','cleanup'}
    count=METER.count('store.mutation',phases)
    require(count==METER.count('store._read_locked:sd_mutations',phases)==2176)
    return identifier,{'loopCount':LOOPS,'mutationValidationCalls':count,'mutationReadCalls':count,
        'predictedReadSelects':2*count,'selectCountIndependentlyObserved':False,
        'retainedMutations':len(items),'neverHandedOffRecords':sum(item['state']=='never_handed_off' for item in items),
        'retainedClaims':len(retained_claims),'mutationSequence':row['mutationSequence'],
        'collected':row['collected'],'acknowledged':row['acknowledged'],'highWater':row['highWater'],
        'loopElapsedNs':str(loop_elapsed),'iterations':iterations,'initialNative':before,
        'applicationSetupElapsedNs':str(loop_started-application_setup_began),
        'moduleToLoopsSetupNs':str(loop_started-MODULE_STARTED),
        'intrusiveInstrumentation':True,'instrumentationOverheadKnown':False,
        'exclusiveMeaning':'Inclusive method wall span minus directly nested measured method spans; includes unmeasured work and unknown probe overhead.',
        'heldMeaning':'Successful context enter return to exit invocation; overlapping lifetime, not additive CPU or exclusive time.',
        'full128RecordQualification':False,'timingExtrapolation':False}


def main():
    global FINAL_DESTINATION,FINAL_REPORT
    require(not sys.flags.optimize and len(sys.argv)==7 and sys.argv[1]=='history-cost','Fixed invocation')
    state,pipe,evidence,manifest_path,helper=map(Path,sys.argv[2:])
    def interrupted(signum,_):raise RuntimeError('Control interrupted '+str(signum))
    signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGTERM,interrupted)
    state.mkdir();FINAL_DESTINATION=state/'CONTROL-RESULTS.json'
    FINAL_REPORT={'passed':False,'phase':'preparation','profile':'history-cost'};save(FINAL_DESTINATION,FINAL_REPORT)
    manifest=json.loads(manifest_path.read_bytes());guardian=Guardian(helper)
    results=[];failure=None;diagnostic=None;began=time.monotonic_ns();previous_checks=checks
    try:
        with ProbeFixture(guardian,state/'history_cost',pipe,evidence,manifest,host_class=ProbeHost,store_class=ProbeStore) as f:
            fixture_elapsed=time.monotonic_ns()-began
            native_identity=copy.deepcopy(guardian.handles[f.pid]['identity']);reap_count=len(guardian.records)
            identifier,diagnostic=history_cost(f)
            diagnostic['candidateImportsElapsedNs']=str(IMPORT_FINISHED-MODULE_STARTED)
            diagnostic['fixtureSetupElapsedNs']=str(fixture_elapsed)
            tables=[r[0] for r in f.journal._db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            record={'case':'history_cost','native':snapshot(f),'route':f.store.route(),
                'tableCounts':{table:f.journal._db.execute('SELECT count(*) FROM "'+table+'"').fetchone()[0] for table in tables},
                'capacity':capacity_check(f.journal._db,JournalError),'trace':f.host.trace or [],
                'nativeStartIdentity':native_identity,'ownerEpoch':f.journal.owner_epoch,'authority':f.journal.authority_id,
                'deploymentId':identifier,'publicWriterRecords':True,'directSQLPopulation':False}
            require(f.policy._held_image is None and f.driver._lease is None and f.catalog._selection is None and f.producer._held is None)
            diagnostic['metrics']=METER.export();record['diagnostic']=diagnostic
            METER.set_phase('cleanup')
        require(len(guardian.records)==reap_count+1)
        native_reap=copy.deepcopy(guardian.records[-1])
        require(native_reap['reaped'] and native_reap['exitCode']==0 and all(native_reap[key]==value for key,value in native_identity.items()))
        record['nativeReap']=native_reap;save(state/'history_cost/evidence.json',record)
        results.append({'case':'history_cost','checks':checks-previous_checks,'passed':True,
            'nativeStartIdentity':native_identity,'nativeReap':native_reap,
            'elapsedMonotonicNs':str(time.monotonic_ns()-began),
            'evidenceSha256':hashlib.sha256((state/'history_cost/evidence.json').read_bytes()).hexdigest(),
            'databaseSha256':hashlib.sha256((state/'history_cost/authority.db').read_bytes()).hexdigest()})
    except BaseException as error:
        failure=type(error).__name__+': '+str(error);traceback.print_exc();raise
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
            clean=all(r['reaped'] and r['exitCode']==0 for r in guardian.records)
            FINAL_REPORT={'passed':failure is None and not errors and empty and closed and not pending and clean,
                'profile':'history-cost','cases':results,'checks':checks,'failure':failure,'cleanupErrors':errors,
                'ownerEmpty':empty,'ownerClosed':closed,'interruptsPending':pending,'nativeChildrenReaped':guardian.records,
                'diagnostic':diagnostic,'partialMetrics':METER.export(partial=True) if failure is not None else None,
                'interruptedMetricFrames':len(METER.stack),
                'actualOwnerDeath':False,'productionChanged':False,'full128RecordQualification':False,
                'physicalEligible':False,'protectedCapacity':False,'publicMountEligible':False}
            save(FINAL_DESTINATION,FINAL_REPORT);print(json.dumps(FINAL_REPORT,sort_keys=True))
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        if FINAL_DESTINATION is not None:
            FINAL_REPORT['passed']=False;FINAL_REPORT['terminalFailure']=type(error).__name__+': '+str(error)
            FINAL_REPORT['terminalPendingSignals']=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
            save(FINAL_DESTINATION,FINAL_REPORT)
        raise
