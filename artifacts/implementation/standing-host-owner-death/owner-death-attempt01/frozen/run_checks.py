"""Fixed review-gated outer owner for thirteen actual host process deaths.

No compiler, qualifier rerun, device, service or caller executable selection.
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
GUARDIAN_SHA='cf682bcfae001f5e1d33cad603ec4a7e3911dc4eab8557714b6973deec7bb206'
HELPER_SHA='a6ee94bcf3dc03df19f0dd07a81663badd4875ef1a6c429afbc55d7b2373b977'
ENV={'LANG':'C','LC_ALL':'C','PATH':'/usr/bin:/bin'}
FINAL_DESTINATION=None
FINAL_REPORT=None
EXPECTED_CASES=[('open-prepared','OPEN','prepared'),('open-possible','OPEN','possible'),('open-reply','OPEN','reply'),
    ('start-prepared','START','prepared'),('start-possible','START','possible'),('start-reply','START','reply'),
    ('collection-before-ack','COLLECTION','collection'),('ack-prepared','ACK','prepared'),
    ('ack-possible','ACK','possible'),('ack-reply','ACK','reply'),('retire-prepared','RETIRE','prepared'),
    ('retire-possible','RETIRE','possible'),('retire-reply','RETIRE','reply')]


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
    require(not sys.flags.optimize and len(sys.argv)==1,'Fixed invocation; assertions required')
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
    for row in reviewed['files']:require(pins[row['path']]==row['sha256'],'Reviewed source changed')
    def stable():
        require(digest(parent_index)==inputs['parentPacket']['indexSha256'],'Parent packet index changed')
        parent_rows=json.loads(parent_index.read_bytes())['files']
        require({str(f.relative_to(parent)) for f in parent.rglob('*') if f.is_file()}=={r['path'] for r in parent_rows}|{'index.json'},'Parent inventory changed')
        for row in parent_rows:require(digest(parent/row['path'])==row['sha256'],'Parent bytes changed: '+row['path'])
        require(digest(public)==inputs['publicReceipt']['sha256'],'Public receipt changed')
        public_rows=json.loads(public.read_bytes())['files'];require(len(public_rows)==244,'Public inventory changed')
        for row in public_rows:require(digest(REPO/row['path'])==row['sha256'],'Public input changed')
        for row in inputs['copies']+inputs['originalProvenance']:
            require(digest(REPO/row['source'])==digest(HERE/row['copy'])==row['sha256'],'Original input changed')
        for name,pin in pins.items():require(digest(HERE/name)==pin,'Prepared input changed: '+name)
        require(digest(interpreter)==digest('/proc/self/exe')==runtime,'Interpreter changed')
    stable()
    attempt=HERE/'owner-death-attempt01';attempt.mkdir(mode=0o700)
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
    argv=[str(interpreter),'-I','-B',str(frozen/'owner_death_controls.py'),str(attempt/'state'),str(native),str(evidence),str(frozen/'owner/libharness-owner.so')]
    save(attempt/'intent.json',{'profile':'hms.standing-host-owner-death-attempt/0.1','sourcePins':pins,
        'parentPacket':inputs['parentPacket'],'publicReceipt':inputs['publicReceipt'],'interpreter':str(interpreter),
        'interpreterSha256':runtime,'argv':argv,'nativeImageSha256':digest(native),'originalQualificationRoot':str(evidence),
        'originalQualificationRunId':original_manifest['runId'],'qualificationRerun':False,'cases':13,
        'expectedInnerReaps':39,'expectedOuterReaps':1,'wallSeconds':30,'cpuSeconds':30,
        'addressBytes':512*1024*1024,'childCpuSeconds':5,'childAddressBytes':256*1024*1024,
        'fileBytes':1024*1024,'openFiles':64,'cleanupSeconds':8,'termGraceSeconds':3,
        'dependencyScope':'Exact copied host sources/native images/helper and held interpreter; trusted Python stdlib/loader/validation packages, no complete runtime closure',
        'processScope':'Per-process rlimits and observed wall bounds; living sole-thread Guardian, no kernel aggregate quota or universal containment',
        'physicalEligible':False,'protectedCapacity':False,'publicMountEligible':False,'candidatePreviouslyExecuted':False})
    guardian=Guardian(frozen/'owner/libharness-owner.so');held=None;child=None;record=None;inner=None
    reason=None;began=time.monotonic_ns();held_before=held_after=None
    control_started=control_terminal=None
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
            child=guardian.fork(fixed_child,cpu_seconds=30,address_bytes=512*1024*1024)
            save(attempt/'control.started.json',guardian.handles[child]['identity'])
            while guardian.status(child) is None:
                require(time.monotonic_ns()-control_started<30_000_000_000,'CONTROL_WALL_LIMIT')
                time.sleep(.005)
            control_terminal=time.monotonic_ns()
            require(control_terminal-control_started<=30_000_000_000,'CONTROL_TERMINAL_OBSERVED_AFTER_WALL_LIMIT')
            record=guardian.reap(child)
            out.flush();err.flush();os.fsync(out.fileno());os.fsync(err.fileno())
        require(record['exitCode']==0,'Control process failed')
        inner=json.loads((attempt/'state/CONTROL-RESULTS.json').read_bytes())
        require(inner['passed'] and len(inner['cases'])==13 and len(inner['childrenReaped'])==39,'Inner result failed')
        require(inner['ownerEmpty'] and inner['ownerClosed'] and not inner['cleanupErrors'] and not inner['interruptsPending'],'Inner cleanup failed')
        require(inner['actualOwnerDeath'] and inner['nativePeerSurvivedOwner'] and inner['historicalPossibleEffectsResent'] is False,'Inner effect classification failed')
        expected=[]
        require([(case['case'],case['operation'],case['cut']) for case in inner['cases']]==EXPECTED_CASES,'Exact ordered thirteen-cut matrix required')
        require(len({(r['pid'],r['startTicks']) for r in inner['childrenReaped']})==39 and
                all(r['parent']==child for r in inner['childrenReaped']),'Inner children must be distinct direct owned children')
        for case in inner['cases']:
            require(case['passed'] and case['actualOwnerDeath'] and case['nativePeerSurvivedOwner'] and case['historicalPossibleEffectsResent'] is False,'Case failed')
            for role,exit_code in [('native',0),('owner',-signal.SIGKILL),('recovery',0)]:
                result=case['reaps'][role];identity=case['identities'][role]
                require(result['reaped'] and result['exitCode']==exit_code and all(result[k]==v for k,v in identity.items()),'Case identity/exit join failed')
                expected.append(result)
            for name,pin in case['evidence'].items():require(digest(attempt/'state'/case['case']/name)==pin,'Case evidence changed')
        require(sorted(expected,key=lambda r:(r['pid'],r['startTicks']))==sorted(inner['childrenReaped'],key=lambda r:(r['pid'],r['startTicks'])),'Inner reaps not exact joined family')
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
            'innerReaps':0 if inner is None else len(inner['childrenReaped']),
            'actualOwnerDeath':passed,'nativePeerSurvivedOwner':passed,'historicalPossibleEffectsResent':False if passed else None,
            'publicInputsExact':244,'parentPacketStable':not any(e.startswith('stable:') for e in cleanup_errors),
            'qualificationRerun':False,'physicalEligible':False,'publicMountEligible':False,'protectedCapacity':False,'universalContainment':False}
        try:
            save(FINAL_DESTINATION,FINAL_REPORT,replace=True)
            print(json.dumps(FINAL_REPORT,sort_keys=True))
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)
    require(FINAL_REPORT['passed'],'Owner-death run failed; preserve original attempt')


if __name__=='__main__':
    try:main()
    except BaseException as error:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        if FINAL_DESTINATION is not None:
            FINAL_REPORT['passed']=False;FINAL_REPORT['actualOwnerDeath']=False;FINAL_REPORT['nativePeerSurvivedOwner']=False
            FINAL_REPORT['terminalFailure']=type(error).__name__+': '+str(error)
            FINAL_REPORT['terminalPendingSignals']=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
            save(FINAL_DESTINATION,FINAL_REPORT,replace=True)
        raise
