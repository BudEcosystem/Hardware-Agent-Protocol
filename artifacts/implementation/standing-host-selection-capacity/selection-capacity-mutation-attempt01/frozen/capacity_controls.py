"""Single original mutation-capacity scenario against byte-exact validated host.

Source-only until root review. No reduced/staged workload or SQL prefill.
The original function is imported from a fixed exact copied source; only the
outer receipt/trace/ownership assembly is new. No production entry is replaced.
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

HERE=Path(__file__).resolve().parent
BASELINE_SHA='01e91d85d9da351af7f1c8dc8cd42bf375898959ff1264754408311042517e5d'
if hashlib.sha256((HERE/'boundary_controls.py').read_bytes()).hexdigest()!=BASELINE_SHA:
    raise RuntimeError('Original workload source changed')
sys.path.insert(0,str(HERE))
import boundary_controls as original
from guardian import Guardian
from hms.journal import JournalError
from hms.standing_capacity import check as capacity_check

checks=0
FINAL_DESTINATION=None
FINAL_REPORT=None


def require(value,message='capacity assembly assertion'):
    global checks
    checks+=1
    if not value:raise AssertionError(str(message)+' #'+str(checks))


def save(path,value):
    # Receipts are not application documents. The original application canonical
    # helper's64KiB cap cannot encode the complete original full-capacity trace.
    body=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
    if len(body)>1024*1024:raise RuntimeError('Bounded evidence exceeded')
    temporary=Path(str(path)+'.pending')
    with temporary.open('wb') as out:out.write(body);out.flush();os.fsync(out.fileno())
    os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


class BoundedHost(original.ProbeHost):
    def _checkpoint(self,phase,value=None):
        if phase in ('before_exchange','after_exchange') and self.trace is not None and len(self.trace)>=2048:
            raise RuntimeError('Bounded original trace exceeded')
        super()._checkpoint(phase,value)


def main():
    global FINAL_DESTINATION,FINAL_REPORT
    require(not sys.flags.optimize and len(sys.argv)==7 and sys.argv[1]=='mutation','Fixed original mutation invocation')
    state,pipe,evidence,manifest_path,helper=map(Path,sys.argv[2:])
    def interrupted(signum,_):raise RuntimeError('Control interrupted '+str(signum))
    signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGTERM,interrupted)
    state.mkdir();FINAL_DESTINATION=state/'CONTROL-RESULTS.json';FINAL_REPORT={'passed':False,'phase':'preparation'};save(FINAL_DESTINATION,FINAL_REPORT)
    manifest=json.loads(manifest_path.read_bytes());guardian=Guardian(helper)
    results=[];failure=None;fixture=None;native_identity=None;partial_file=None
    try:
        began=time.monotonic_ns();before=checks;legacy_before=original.checks
        with original.TraceFixture(guardian,state/'mutation_capacity',pipe,evidence,manifest,
                host_class=BoundedHost,store_class=original.ProbeStore) as f:
            fixture=f;native_identity=copy.deepcopy(guardian.handles[f.pid]['identity']);reap_count=len(guardian.records)
            original.mutation_capacity(f)
            tables=[r[0] for r in f.journal._db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            record={'case':'mutation_capacity','native':original.snapshot(f),'route':f.store.route(),
                'tableCounts':{t:f.journal._db.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0] for t in tables},
                'capacity':capacity_check(f.journal._db,JournalError),'trace':f.retained_trace,
                'boundaryNotes':f.boundary_notes,'nativeStartIdentity':native_identity,
                'ownerEpoch':f.journal.owner_epoch,'authority':f.journal.authority_id,
                'hostImplementationDigest':f.installation['hostImplementationDigest'],
                'publicWriterRecords':True,'directSQLPopulation':False,'originalWorkloadSha256':BASELINE_SHA,
                'physicalEligible':False,'protectedCapacity':False}
            require(f.policy._held_image is None and f.driver._lease is None and f.catalog._selection is None and f.producer._held is None)
            require(record['tableCounts']['sd_mutations']==128 and record['tableCounts']['claims']==0 and
                record['boundaryNotes']['ordinaryFull']['retainedMutations']==120 and
                record['boundaryNotes']['commonRevoke']['retainedMutations']==126 and
                record['boundaryNotes']['terminal']['retainedMutations']==128,'Complete original public-writer capacity path')
        require(len(guardian.records)==reap_count+1)
        reap=copy.deepcopy(guardian.records[-1]);require(reap['reaped'] and reap['exitCode']==0 and all(reap[k]==v for k,v in native_identity.items()))
        record['nativeReap']=reap;record['originalChecks']=original.checks-legacy_before
        save(state/'mutation_capacity/evidence.json',record)
        results.append({'case':'mutation_capacity','passed':True,'checks':checks-before,'originalChecks':original.checks-legacy_before,
            'elapsedMonotonicNs':str(time.monotonic_ns()-began),'nativeStartIdentity':native_identity,'nativeReap':reap,
            'evidenceSha256':hashlib.sha256((state/'mutation_capacity/evidence.json').read_bytes()).hexdigest(),
            'databaseSha256':hashlib.sha256((state/'mutation_capacity/authority.db').read_bytes()).hexdigest()})
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
            if failure is not None and fixture is not None:
                # Memory retained before interruption only: no late DB or native
                # query, no claim to have captured a final complete snapshot.
                try:
                    partial_file='PARTIAL-EVIDENCE.json'
                    save(state/partial_file,{'case':'mutation_capacity','completed':False,'failure':failure,
                        'trace':fixture.retained_trace,'boundaryNotes':fixture.boundary_notes,'nativeStartIdentity':native_identity,
                        'nativeChildrenReaped':guardian.records,'originalChecks':original.checks,'fullFinalSnapshot':False})
                except BaseException as error:errors.append('partialEvidence: '+type(error).__name__+': '+str(error))
            pending=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
            passed=failure is None and len(results)==1 and not errors and empty and closed and not pending and all(r['reaped'] and r['exitCode']==0 for r in guardian.records)
            FINAL_REPORT={'passed':passed,'profile':'mutation','cases':results,'checks':checks,'originalChecks':original.checks,
                'failure':failure,'cleanupErrors':errors,'ownerEmpty':empty,'ownerClosed':closed,'interruptsPending':pending,
                'nativeChildrenReaped':guardian.records,'partialEvidenceFile':partial_file,'actualOwnerDeath':False,
                'productionChangedFromSelectionReuse':False,'originalWorkloadSha256':BASELINE_SHA,
                'full128RecordWorkloadCompleted':passed,'fullSimultaneousCapacityEstablished':False,
                'qualificationRerun':False,'physicalEligible':False,'protectedCapacity':False,'publicMountEligible':False}
            save(FINAL_DESTINATION,FINAL_REPORT);print(json.dumps(FINAL_REPORT,sort_keys=True))
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)


if __name__=='__main__':
    try:main()
    except BaseException as error:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        if FINAL_DESTINATION is not None:
            FINAL_REPORT['passed']=False;FINAL_REPORT['full128RecordWorkloadCompleted']=False
            FINAL_REPORT['terminalFailure']=type(error).__name__+': '+str(error)
            FINAL_REPORT['terminalPendingSignals']=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM});save(FINAL_DESTINATION,FINAL_REPORT)
        raise
