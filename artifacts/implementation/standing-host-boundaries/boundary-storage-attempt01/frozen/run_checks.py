"""Fixed review-gated owner for explicit standing-host boundary profiles.

No compiler, qualification rerun, device or caller executable selection.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import sys
import time

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
GUARDIAN_SHA='b9451d90c845f86b9e41cfc527c3fb7fa0ed8e7e58b65ab0cd5c0bc0d2a60792'
HELPER_SHA='a6ee94bcf3dc03df19f0dd07a81663badd4875ef1a6c429afbc55d7b2373b977'
ENV={'LANG':'C','LC_ALL':'C','PATH':'/usr/bin:/bin'}
FINAL_DESTINATION=None
FINAL_REPORT=None
PROFILES={
    'negative':['expired_qualification','driver_expiry_after_possible','installed_context_change',
        'boot_after_acceptance','retired_without_terminal_proof','refused_sequence_original_key',
        'automatic_ack_revision_refusal','dispute_retention'],
    'storage':['storage_'+phase+'_'+when for phase in ('prepare','open','collection','retire') for when in ('before','after')]+
        ['rollback_exception','sqlite_page_exhaustion'],
    'mutation':['mutation_capacity'],'episodes':['episode_capacity'],
    'activations':['activation_capacity'],'keys':['retained_keys'],'fixed':['fixed_writer_capacity'],
    'accounting':['accounting_model']}
CAPACITY_PROFILES=frozenset(('mutation','episodes','activations','keys','fixed'))


def require(value,message):
    if not value:raise RuntimeError(message)


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def save(path,value,*,replace=False):
    body=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
    require(len(body)<=1024*1024,'Receipt exceeds file bound')
    temporary=Path(str(path)+'.pending') if replace else Path(path)
    with temporary.open('wb' if replace else 'xb') as out:
        out.write(body);out.flush();os.fsync(out.fileno())
    if replace:os.replace(temporary,path)
    fd=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def fd_snapshot(fd):
    before=os.fstat(fd)
    require(stat.S_ISREG(before.st_mode) and before.st_size<=64*1024*1024,'Bounded regular executable required')
    hasher=hashlib.sha256();offset=0
    while offset<before.st_size:
        block=os.pread(fd,min(65536,before.st_size-offset),offset)
        require(bool(block),'Executable truncated');hasher.update(block);offset+=len(block)
    after=os.fstat(fd)
    signature=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
    require(signature(before)==signature(after),'Executable changed while held')
    return {'identity':list(signature(before)),'sha256':hasher.hexdigest()}


def main():
    global FINAL_DESTINATION,FINAL_REPORT
    require(not sys.flags.optimize and len(sys.argv) in (2,4) and sys.argv[1] in PROFILES,'Fixed profile invocation; assertions required')
    profile=sys.argv[1];expected_cases=PROFILES[profile]
    attempt_number=1
    if len(sys.argv)==4:
        require(sys.argv[2]=='--attempt' and sys.argv[3].isascii() and sys.argv[3].isdigit(),'Explicit bounded attempt required')
        attempt_number=int(sys.argv[3])
        require(1<=attempt_number<=16 and str(attempt_number)==sys.argv[3],'Attempt must be canonical1..16')
    expected_native=0 if profile=='accounting' else len(expected_cases)
    file_bytes=(32 if profile in CAPACITY_PROFILES else 1)*1024*1024
    def interrupted(signum,_):raise RuntimeError('Runner interrupted '+str(signum))
    signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGTERM,interrupted)
    os.umask(0o077)
    require(digest(HERE/'owner/guardian.py')==GUARDIAN_SHA and digest(HERE/'owner/libharness-owner.so')==HELPER_SHA,'Owner bytes changed')
    sys.path.insert(0,str(HERE/'owner'))
    from guardian import Guardian
    inputs=json.loads((HERE/'source-pins.json').read_bytes())
    parent=REPO/inputs['parentPacket']['path'];parent_index=parent/'index.json'
    public=REPO/inputs['publicReceipt']['path']
    interpreter=Path(sys.executable).resolve();runtime=digest(interpreter)
    require(digest('/proc/self/exe')==runtime,'Interpreter identity mismatch')
    reviewed=json.loads((HERE/'SOURCE-REVIEW.json').read_bytes())
    frozen_names=[row['path'] for row in reviewed['files']]+['SOURCE-REVIEW.json']
    require(len(frozen_names)==len(set(frozen_names)),'Duplicate input inventory')
    pins={name:digest(HERE/name) for name in frozen_names}
    for row in reviewed['files']:
        path=HERE/row['path']
        require(path.is_file() and not path.is_symlink() and path.stat().st_size==row['bytes'] and
                pins[row['path']]==row['sha256'],'Reviewed source changed')
    prior_results=[]
    for number in range(1,attempt_number):
        path=HERE/('boundary-'+profile+'-attempt'+str(number).zfill(2))/'RESULTS.json'
        require(path.is_file() and not path.is_symlink(),'Prior explicit attempt receipt missing')
        prior_results.append({'path':str(path.relative_to(HERE)),'sha256':digest(path)})
    def stable():
        require(digest(parent_index)==inputs['parentPacket']['indexSha256'],'Parent packet index changed')
        parent_rows=json.loads(parent_index.read_bytes())['files']
        require({str(f.relative_to(parent)) for f in parent.rglob('*') if f.is_file()}=={r['path'] for r in parent_rows}|{'index.json'},'Parent inventory changed')
        for row in parent_rows:require(digest(parent/row['path'])==row['sha256'],'Parent bytes changed: '+row['path'])
        second=REPO/inputs['secondParentPacket']['path']
        require(digest(second/'index.json')==inputs['secondParentPacket']['indexSha256'],'Owner-death index changed')
        second_rows=json.loads((second/'index.json').read_bytes())['files']
        require({str(f.relative_to(second)) for f in second.rglob('*') if f.is_file()}=={r['path'] for r in second_rows}|{'index.json'},'Owner-death inventory changed')
        for row in second_rows:require(digest(second/row['path'])==row['sha256'],'Owner-death bytes changed: '+row['path'])
        require(digest(public)==inputs['publicReceipt']['sha256'],'Public receipt changed')
        public_rows=json.loads(public.read_bytes())['files'];require(len(public_rows)==244,'Public inventory changed')
        for row in public_rows:require(digest(REPO/row['path'])==row['sha256'],'Public input changed')
        for row in inputs['copies']+inputs['originalProvenance']:
            require(digest(REPO/row['source'])==digest(HERE/row['copy'])==row['sha256'],'Original input changed')
        for row in reviewed['files']:
            path=HERE/row['path']
            require(path.is_file() and not path.is_symlink() and path.stat().st_size==row['bytes'],'Reviewed input type/length changed')
        for name,pin in pins.items():require(not (HERE/name).is_symlink() and digest(HERE/name)==pin,'Prepared input changed: '+name)
        for row in prior_results:require(digest(HERE/row['path'])==row['sha256'],'Earlier attempt result changed')
        require(digest(interpreter)==digest('/proc/self/exe')==runtime,'Interpreter changed')
    stable()
    attempt=HERE/('boundary-'+profile+'-attempt'+str(attempt_number).zfill(2));attempt.mkdir(mode=0o700)
    FINAL_DESTINATION=attempt/'RESULTS.json';FINAL_REPORT={'passed':False,'phase':'preparation'}
    save(FINAL_DESTINATION,FINAL_REPORT,replace=True)
    frozen=attempt/'frozen';frozen.mkdir()
    for name in frozen_names:
        target=frozen/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(HERE/name,target)
        require(digest(target)==pins[name],'Frozen copy changed')
    native=Path(inputs['nativeImage']);evidence=Path(inputs['qualificationRoot'])
    require(native==parent/'host-attempt04/standing-host-pipe' and evidence==parent/'host-attempt04/qualification','Original root required')
    original_manifest=json.loads((evidence/'manifest.json').read_bytes())
    require(original_manifest['argv']==[str(evidence/original_manifest['binaryPath'])],'Original qualifier argv changed')
    argv=[str(interpreter),'-I','-B',str(frozen/'boundary_controls.py'),profile,str(attempt/'state'),str(native),str(evidence),str(evidence/'manifest.json'),str(frozen/'owner/libharness-owner.so')]
    save(attempt/'intent.json',{'profile':'hms.standing-host-boundary-attempt/0.1','controlProfile':profile,
        'attemptNumber':attempt_number,'priorProfileAttemptResults':prior_results,'sourcePins':pins,
        'parentPacket':inputs['parentPacket'],'secondParentPacket':inputs['secondParentPacket'],
        'publicReceipt':inputs['publicReceipt'],'interpreter':str(interpreter),
        'interpreterSha256':runtime,'argv':argv,'nativeImageSha256':digest(native),'originalQualificationRoot':str(evidence),
        'originalQualificationRunId':original_manifest['runId'],'qualificationRerun':False,'cases':expected_cases,
        'expectedInnerReaps':expected_native,'expectedOuterReaps':1,'wallSeconds':30,'cpuSeconds':30,
        'addressBytes':512*1024*1024,'childCpuSeconds':5,'childAddressBytes':256*1024*1024,
        'fileBytes':file_bytes,'nativeChildFileBytes':1024*1024,'stateDiskBytes':96*1024*1024,'openFiles':64,'cleanupSeconds':8,'termGraceSeconds':3,
        'dependencyScope':'Exact copied host sources/native images/helper and held interpreter; trusted Python stdlib/loader/validation packages, no complete runtime closure',
        'processScope':'Per-process rlimits and observed wall bounds; living sole-thread Guardian, no kernel aggregate quota or universal containment',
        'physicalEligible':False,'protectedCapacity':False,'publicMountEligible':False,'controlProfilePreviouslyExecuted':bool(prior_results)})
    guardian=Guardian(frozen/'owner/libharness-owner.so');held=None;child=None;record=None;inner=None
    reason=None;began=time.monotonic_ns();held_before=held_after=None
    control_started=control_terminal=None
    observed_state_bytes=observed_state_files=0
    def observe_disk():
        nonlocal observed_state_bytes,observed_state_files
        files=[]
        if (attempt/'state').exists():
            for path in (attempt/'state').rglob('*'):
                try:
                    info=path.stat()
                    if stat.S_ISREG(info.st_mode):files.append(info.st_size)
                except FileNotFoundError:
                    pass  # DELETE-mode journals may disappear between samples.
        observed_state_bytes=max(observed_state_bytes,sum(files))
        observed_state_files=max(observed_state_files,len(files))
        require(len(files)<=256 and sum(files)<=96*1024*1024,'CONTROL_DISK_LIMIT')
    try:
        held=os.open(interpreter,os.O_RDONLY|os.O_CLOEXEC);fcntl.flock(held,fcntl.LOCK_SH|fcntl.LOCK_NB)
        held_before=fd_snapshot(held);require(held_before['sha256']==runtime,'Held interpreter differs')
        with (attempt/'control.stdout').open('xb') as out,(attempt/'control.stderr').open('xb') as err:
            def fixed_child():
                os.dup2(out.fileno(),1);os.dup2(err.fileno(),2)
                null=os.open('/dev/null',os.O_RDONLY);os.dup2(null,0);os.close(null)
                for fd in range(3,64):
                    if fd!=held:
                        try:os.close(fd)
                        except OSError:pass
                os.chdir(frozen)
                os.execve('/proc/self/fd/'+str(held),argv,ENV)
            control_started=time.monotonic_ns()
            child=guardian.fork(fixed_child,cpu_seconds=30,address_bytes=512*1024*1024,file_bytes=file_bytes)
            save(attempt/'control.started.json',guardian.handles[child]['identity'])
            while guardian.status(child) is None:
                require(time.monotonic_ns()-control_started<30_000_000_000,'CONTROL_WALL_LIMIT')
                observe_disk()
                time.sleep(.005)
            control_terminal=time.monotonic_ns()
            require(control_terminal-control_started<=30_000_000_000,'CONTROL_TERMINAL_OBSERVED_AFTER_WALL_LIMIT')
            record=guardian.reap(child)
            out.flush();err.flush();os.fsync(out.fileno());os.fsync(err.fileno())
        require(record['exitCode']==0,'Control process failed')
        observe_disk()
        inner=json.loads((attempt/'state/CONTROL-RESULTS.json').read_bytes())
        require(inner['passed'] and inner['profile']==profile and [case['case'] for case in inner['cases']]==expected_cases,'Inner exact case matrix failed')
        require(inner['ownerEmpty'] and inner['ownerClosed'] and not inner['cleanupErrors'] and not inner['interruptsPending'],'Inner cleanup failed')
        records=inner['nativeChildrenReaped']
        require(len(records)==expected_native and len({(r['pid'],r['startTicks']) for r in records})==len(records),'Exact distinct native ownership required')
        require(all(r['parent']==child and r['reaped'] and r['exitCode']==0 for r in records),'Native clean EOF exit required')
        require(inner['actualOwnerDeath'] is False,'This profile injects living-owner exceptions only')
        joined_reaps=[]
        for case in inner['cases']:
            require(case['passed'],'Case failed')
            directory=attempt/'state'/case['case']
            require(digest(directory/'evidence.json')==case['evidenceSha256'],'Case evidence changed')
            evidence_row=json.loads((directory/'evidence.json').read_bytes())
            require(evidence_row['case']==case['case'],'Case evidence name mismatch')
            if profile!='accounting':
                require(digest(directory/'authority.db')==case['databaseSha256'],'Case database changed')
                require(evidence_row['publicWriterRecords'] is True and evidence_row['directSQLPopulation'] is False,'Real public-writer scope mismatch')
                require(set(evidence_row['native'])=={str(n) for n in range(28)},'Native snapshot scope mismatch')
                require(evidence_row['nativeStartIdentity']==case['nativeStartIdentity'] and evidence_row['nativeReap']==case['nativeReap'],'Case native evidence mismatch')
                require(all(case['nativeReap'][key]==value for key,value in case['nativeStartIdentity'].items()),'Case native identity/exit join failed')
                joined_reaps.append(case['nativeReap'])
            else:
                require(case['databaseSha256'] is None and not (directory/'authority.db').exists(),'Accounting must remain non-durable model')
                require(evidence_row['publicWriterRecords'] is False and evidence_row['directSQLPopulation'] is True and
                        evidence_row['durableCapacityEstablished'] is False,'Accounting evidence scope mismatch')
        require(joined_reaps==records,'Native reaps must match every ordered named case exactly')
        for owned in records:
            require(not Path('/proc',str(owned['pid'])).exists(),'Previously owned PID still exists; no signal authority inferred')
        require(not (attempt/'control.stderr').read_bytes(),'Unexpected control stderr')
    except BaseException as error:reason=type(error).__name__+': '+str(error)
    finally:
        previous=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        cleanup_errors=[];empty=closed=False;adopted=[]
        def cleanup(label,action):
            try:return action()
            except BaseException as error:cleanup_errors.append(label+': '+type(error).__name__+': '+str(error));return None
        def finish_leader():
            nonlocal record
            if child is not None and child in guardian.handles and guardian.status(child) is None:
                guardian.send(child,signal.SIGTERM);end=time.monotonic()+3
                while guardian.status(child) is None and time.monotonic()<end:time.sleep(.005)
            if child is not None and child in guardian.handles and guardian.status(child) is not None:record=guardian.reap(child)
        cleanup('leader',finish_leader);cleanup('refresh',guardian.refresh);adopted=list(guardian.handles)
        cleanup('settle',guardian.settle);empty=cleanup('empty',guardian.empty) is True
        if held is not None:
            held_after=cleanup('heldSnapshot',lambda:fd_snapshot(held));cleanup('heldClose',lambda:os.close(held))
        cleanup('heldStable',lambda:require(held_before==held_after and held_before is not None,'Held interpreter changed'))
        cleanup('stable',stable)
        cleanup('frozenStable',lambda:require(all(digest(frozen/name)==pin for name,pin in pins.items()),'Frozen inputs changed'))
        cleanup('close',guardian.close);closed=guardian.closed
        pending=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
        passed=reason is None and inner is not None and not cleanup_errors and not pending and not adopted and empty and closed and len(guardian.records)==1
        FINAL_REPORT={'passed':passed,'reason':reason,'cleanupErrors':cleanup_errors,'interruptsPending':pending,
            'ownerEmpty':empty,'ownerClosed':closed,'outerChildrenReaped':guardian.records,'unexpectedChildrenObserved':adopted,
            'controlExit':record,'heldInterpreterBefore':held_before,'heldInterpreterAfter':held_after,
            'elapsedMonotonicNs':str(time.monotonic_ns()-began),
            'controlStartedMonotonicNs':None if control_started is None else str(control_started),
            'controlTerminalObservedMonotonicNs':None if control_terminal is None else str(control_terminal),
            'controlObservedElapsedMonotonicNs':None if control_terminal is None else str(control_terminal-control_started),
            'innerCases':0 if inner is None else len(inner['cases']),
            'innerReaps':0 if inner is None else len(inner['nativeChildrenReaped']),
            'actualOwnerDeath':False,'controlProfile':profile,'attemptNumber':attempt_number,
            'priorProfileAttemptResults':prior_results,'historicalPossibleEffectsResent':False if passed else None,
            'fullSimultaneousCapacityEstablished':False,'logicalCeilingBytes':16*1024*1024,'fileBytes':file_bytes,
            'observedStateHighBytes':observed_state_bytes,'observedStateHighFiles':observed_state_files,
            'diskMonitorIsObservedNotKernelQuota':True,
            'publicInputsExact':244,'parentPacketStable':not any(e.startswith('stable:') for e in cleanup_errors),
            'qualificationRerun':False,'physicalEligible':False,'publicMountEligible':False,'protectedCapacity':False,'universalContainment':False}
        try:
            save(FINAL_DESTINATION,FINAL_REPORT,replace=True)
            print(json.dumps(FINAL_REPORT,sort_keys=True))
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)
    require(FINAL_REPORT['passed'],'Boundary run failed; preserve original attempt')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        if FINAL_DESTINATION is not None:
            FINAL_REPORT['passed']=False;FINAL_REPORT['actualOwnerDeath']=False
            FINAL_REPORT['terminalFailure']=type(error).__name__+': '+str(error)
            FINAL_REPORT['terminalPendingSignals']=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
            save(FINAL_DESTINATION,FINAL_REPORT,replace=True)
        raise
