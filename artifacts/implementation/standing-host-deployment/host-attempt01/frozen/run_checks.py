"""Original bounded review-gated build/evaluator/vertical-test launcher.

Source only until root approval. No caller executable, device, service, network,
or GPU argument. Every child is original fixed code or the installed C compiler.
"""
import hashlib
import fcntl
import stat
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import sys
import time

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
sys.path.insert(0,str(HERE/'owner'))
BASELINE=REPO/'artifacts/verification/runtime-attempts/20261109T013550.239422Z-7faa2ecb4078/receipt.json'
BASELINE_SHA='dba009874d97e14a9d0bc7b39cbc144e7361218866bca41f6857c933dedddd4e'
GUARDIAN_SHA='cf682bcfae001f5e1d33cad603ec4a7e3911dc4eab8557714b6973deec7bb206'
HELPER_SHA='a6ee94bcf3dc03df19f0dd07a81663badd4875ef1a6c429afbc55d7b2373b977'
ENV={'LANG':'C','LC_ALL':'C','PATH':'/usr/bin:/bin'}
FINAL_DESTINATION=None
FINAL_REPORT=None
BACKEND=Path('/usr/libexec/gcc/x86_64-linux-gnu/13')
COMMON=['-B'+str(BACKEND)+'/','-std=c11','-g','-Wall','-Wextra','-Wconversion','-Werror','-Wvla','-fno-common','-O1']
CORE=['protocol/serial/frame.c','protocol/endpoint/endpoint.c','protocol/endpoint/link.c',
      'protocol/endpoint/standing.c','tests/standing_fixture.c']
NEW=['hms/standing_contracts.py','hms/standing_capacity.py','hms/standing_wire.py','hms/standing_store.py',
     'hms/standing_pat.py','hms/standing_endpoint.py','tests/standing_host_pipe.c',
     'tests/standing_host_fixture.py','tests/standing_host_controls.py']


def require(value,message):
    if not value:raise RuntimeError(message)


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def save(path,value,*,canonical=False):
    body=json.dumps(value,sort_keys=True,separators=(',',':') if canonical else None,ensure_ascii=False).encode()
    with Path(path).open('xb') as target:
        target.write(body);target.flush();os.fsync(target.fileno())
    fd=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def baseline():
    require(digest(BASELINE)==BASELINE_SHA,'Baseline receipt changed')
    rows=json.loads(BASELINE.read_bytes())['files'];require(len(rows)==244,'Baseline inventory changed')
    for row in rows:require(digest(REPO/row['path'])==row['sha256'],'Public source changed: '+row['path'])


def replace_result(path,value):
    temporary=Path(str(path)+'.pending')
    if temporary.exists():temporary.unlink()
    save(temporary,value)
    os.replace(temporary,path)
    fd=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def fd_snapshot(fd):
    before=os.fstat(fd)
    require(stat.S_ISREG(before.st_mode) and before.st_size<=64*1024*1024,'Executable exceeds bounded regular image')
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
    def interrupt(signum,_):raise RuntimeError('Runner interrupted '+str(signum))
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    os.umask(0o077);baseline()
    require(digest(HERE/'owner/guardian.py')==GUARDIAN_SHA and digest(HERE/'owner/libharness-owner.so')==HELPER_SHA,'Owner source changed')
    from guardian import Guardian
    attempt=HERE/'host-attempt01';attempt.mkdir(mode=0o700)
    FINAL_DESTINATION=attempt/'RESULTS.json'
    FINAL_REPORT={'passed':False,'phase':'preparation','reason':None}
    replace_result(FINAL_DESTINATION,FINAL_REPORT)
    frozen=attempt/'frozen';frozen.mkdir()
    origin=json.loads((HERE/'source-pins.json').read_bytes())
    names=sorted({row['project'] for row in origin['files'] if row['project'] is not None}|set(NEW))
    files=['project/'+name for name in names]+['owner/guardian.py','owner/libharness-owner.so',
        'run_checks.py','PLAN.md','README.md','CAPACITY-REVIEW.md','source-pins.json','SOURCE-REVIEW.json','source-diff.patch','REVISION-02.md','revision-02.patch','REVISION-03.md','revision-03.patch','REVISION-04.md','revision-04.patch']
    reviewed=json.loads((HERE/'SOURCE-REVIEW.json').read_bytes())
    require(all(digest(HERE/row['path'])==row['sha256'] for row in reviewed['files']),'Reviewed source bytes changed')
    pins={}
    for name in files:
        source=HERE/name;target=frozen/name;target.parent.mkdir(parents=True,exist_ok=True)
        pins[name]=digest(source);shutil.copyfile(source,target)
        require(digest(target)==pins[name],'Frozen copy changed')
    interpreter=Path(sys.executable).resolve();runtime=digest(interpreter)
    require(digest('/proc/self/exe')==runtime,'Interpreter identity mismatch')
    gcc=Path(shutil.which('gcc',path=ENV['PATH']) or '/missing').resolve(strict=True)
    require(gcc==Path('/usr/bin/x86_64-linux-gnu-gcc-13'),'Unsupported installed compiler')
    compiler=digest(gcc)
    tools={str(path.resolve(strict=True)):digest(path) for path in [gcc,BACKEND/'cc1',BACKEND/'collect2',Path('/usr/bin/as'),Path('/usr/bin/ld')]}
    aliases={str(path):str(path.resolve(strict=True)) for path in [Path('/usr/bin/gcc'),Path('/usr/bin/as'),Path('/usr/bin/ld')]}

    save(attempt/'intent.json',{'profile':'hms.standing-host-attempt/0.1','sourcePins':pins,
        'publicReceiptSha256':BASELINE_SHA,'interpreter':str(interpreter),'interpreterSha256':runtime,
        'compiler':str(gcc),'compilerSha256':compiler,'installedToolPins':tools,'toolAliases':aliases,
        'dependencyScope':'Pinned GCC13/cc1/collect2/as/ld and interpreter ELF; native headers/specs/start objects/libraries, loader and Python packages remain trusted unpinned dependencies; no complete toolchain closure claim',
        'processScope':'Per-process rlimits and observed wall bound; original qualification image has no fork; spawnCount is an association, not a kernel process quota',
        'fixedCommands':4,'commandWallSeconds':30,
        'cleanupSeconds':8,'cpuSeconds':30,'addressBytes':512*1024*1024,'fileBytes':1024*1024,
        'openFiles':64,'physicalEligible':False,'protectedCapacity':False,'candidatePreviouslyExecuted':False})
    project=frozen/'project';evidence=attempt/'qualification';evidence.mkdir()
    # This authorized runner imports only after freezing its complete candidate.
    # Qualification bytes are then produced by the actual original child below.
    sys.path.insert(0,str(project))
    from hms.standing_pat import SOURCE_PINS,DOMAIN_DIGEST,EVALUATOR,EXPECTED_STDOUT,RUN_LIMITS
    from hms.contracts import canonical
    runner_digest='sha256:'+pins['run_checks.py']
    guardian=Guardian(frozen/'owner/libharness-owner.so')
    commands=[];reason=None;began=time.monotonic_ns();control=None

    def stable():
        baseline()
        for row in origin['files']:
            require(digest(HERE/row['copy'])==digest(REPO/row['source'])==row['sha256'],'Original source preservation changed')
        require(digest(interpreter)==digest('/proc/self/exe')==runtime,'Interpreter changed')
        require(digest(gcc)==compiler,'Compiler changed')
        require(all(digest(path)==pin for path,pin in tools.items()),'Installed backend changed')
        require(all(str(Path(path).resolve(strict=True))==target for path,target in aliases.items()),'Tool alias changed')
        for name,pin in pins.items():
            require(digest(HERE/name)==digest(frozen/name)==pin,'Source changed: '+name)

    def run(argv,label,*,cpu=30,stdout=None,stderr=None):
        stable();argv=[str(x) for x in argv]
        output=stdout or attempt/(label+'.stdout');errors=stderr or attempt/(label+'.stderr')
        executable=Path(argv[0]).resolve(strict=True);held=os.open(executable,os.O_RDONLY|os.O_CLOEXEC)
        fcntl.flock(held,fcntl.LOCK_SH|fcntl.LOCK_NB)
        image=digest(executable);held_before=fd_snapshot(held)
        require(held_before['sha256']==image,'Held executable differs from pinned path')
        start=time.monotonic_ns();child=None;record=None;failed=None
        before=len(guardian.records)
        with output.open('xb') as out,errors.open('xb') as err:
            try:
                def fixed_child():
                    os.dup2(out.fileno(),1);os.dup2(err.fileno(),2)
                    null=os.open('/dev/null',os.O_RDONLY);os.dup2(null,0);os.close(null)
                    os.chdir(project)
                    resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu))
                    os.execve('/proc/self/fd/'+str(held),argv,ENV)
                child=guardian.fork(fixed_child,cpu_seconds=30,address_bytes=512*1024*1024)
                save(attempt/(label+'.started.json'),guardian.stat(child))
                while guardian.status(child) is None:
                    require(time.monotonic_ns()-start<30_000_000_000,'COMMAND_WALL_LIMIT')
                    time.sleep(.005)
                record=guardian.reap(child)
            except BaseException as error:
                failed=type(error).__name__+': '+str(error)
            finally:
                previous=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
                try:
                    cleanup_errors=[];adopted=[];empty=False;held_after=None
                    def cleanup(action):
                        try:return action()
                        except BaseException as error:
                            cleanup_errors.append(type(error).__name__+': '+str(error));return None
                    def finish_leader():
                        nonlocal record
                        if child is not None and child in guardian.handles and guardian.status(child) is None:
                            guardian.send(child,signal.SIGTERM)
                            grace=time.monotonic()+3
                            while guardian.status(child) is None and time.monotonic()<grace:time.sleep(.005)
                        if child is not None and child in guardian.handles and guardian.status(child) is not None:
                            record=guardian.reap(child)
                    cleanup(finish_leader)
                    cleanup(guardian.refresh);adopted=list(guardian.handles)
                    cleanup(guardian.settle);empty=cleanup(guardian.empty) is True
                    held_after=cleanup(lambda:fd_snapshot(held));cleanup(lambda:os.close(held))
                    cleanup(out.flush);cleanup(err.flush)
                    cleanup(lambda:os.fsync(out.fileno()));cleanup(lambda:os.fsync(err.fileno()))
                    cleanup(stable)
                    cleanup(lambda:require(digest(executable)==image and held_after==held_before,'Executable changed'))
                    receipt={'label':label,'argv':argv,'executableSha256':image,'heldImageBefore':held_before,
                        'heldImageAfter':held_after,'startedMonotonicNs':str(start),
                        'finishedMonotonicNs':str(time.monotonic_ns()),'exit':record,'failure':failed,
                        'adoptedAfterLeaderExit':adopted,'childrenReaped':guardian.records[before:],
                        'stdoutSha256':digest(output),'stderrSha256':digest(errors),'cleanupComplete':empty,
                        'cleanupErrors':cleanup_errors,
                        'interruptsPending':sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})}
                    save(attempt/(label+'.receipt.json'),receipt);commands.append(receipt)
                finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)
        require(failed is None and record is not None and record['exitCode']==0 and not adopted and
                not receipt['interruptsPending'] and receipt['cleanupComplete'] and not receipt['cleanupErrors'],'COMMAND_FAILED: '+label)
        return receipt

    try:
        qualification=evidence/'standing-controls'
        run([gcc,*COMMON,*CORE,'tests/standing_controls.c','-o',qualification],'compile-qualification')
        common={'evaluatorId':EVALUATOR,'runId':'native-standing-original:1','attemptId':'native-standing-attempt:1',
            'runnerDigest':runner_digest,'domainDigest':DOMAIN_DIGEST,'sourcePins':SOURCE_PINS,
            'binaryPath':'standing-controls','binaryDigest':'sha256:'+digest(qualification),'argv':[str(qualification)]}
        reservation={'profile':'hms.standing-native-reservation/0.1',**common,'limits':RUN_LIMITS,'state':'reserved'}
        save(evidence/'reservation.json',reservation,canonical=True)
        require((evidence/'reservation.json').read_bytes()==canonical(reservation),'Reservation noncanonical')
        original=run([qualification],'original-qualification',cpu=10,stdout=evidence/'stdout',stderr=evidence/'stderr')
        require((evidence/'stdout').read_bytes()==EXPECTED_STDOUT and not (evidence/'stderr').read_bytes(),'Original native result changed')
        require(len(original['childrenReaped'])==1,'Unexpected qualification child family')
        require(original['executableSha256']==common['binaryDigest'][7:] and original['argv']==common['argv'],
                'Original launch differs from committed qualification reservation')
        pid=original['exit']['pid']
        result={'profile':'hms.standing-native-attempt/0.1',**common,
            'reservationDigest':'sha256:'+digest(evidence/'reservation.json'),
            'stdoutDigest':'sha256:'+digest(evidence/'stdout'),'stderrDigest':'sha256:'+digest(evidence/'stderr'),
            'exitCode':0,'terminationSignal':0,'startedMonotonicNs':original['startedMonotonicNs'],
            'finishedMonotonicNs':original['finishedMonotonicNs'],
            'ownership':{'pid':pid,'waitedPid':pid,'spawnCount':1,'reaped':True,'cleanupComplete':True,'openChildHandles':0},
            'physicalQualification':False,'protectedCapacity':False}
        save(evidence/'receipt.json',result,canonical=True)
        manifest={'profile':'hms.standing-native-producer/0.1',**{k:v for k,v in common.items() if k!='attemptId'},
            'reservationPath':'reservation.json','reservationDigest':'sha256:'+digest(evidence/'reservation.json'),
            'receiptPath':'receipt.json','receiptDigest':'sha256:'+digest(evidence/'receipt.json'),
            'stdoutPath':'stdout','stdoutDigest':'sha256:'+digest(evidence/'stdout'),
            'stderrPath':'stderr','stderrDigest':'sha256:'+digest(evidence/'stderr')}
        save(evidence/'manifest.json',manifest,canonical=True)
        pipe=attempt/'standing-host-pipe'
        run([gcc,*COMMON,*CORE,'tests/standing_host_pipe.c','-o',pipe],'compile-pipe')
        control=run([interpreter,'-I','-B',project/'tests/standing_host_controls.py',attempt/'state',pipe,evidence,
                     evidence/'manifest.json',frozen/'owner/libharness-owner.so'],'host-controls')
        output=json.loads((attempt/'host-controls.stdout').read_bytes())
        require(output['passed'] and len(output['cases'])==20 and len(output['nativeChildrenReaped'])==20 and
                output['nativeExpectedCleanExits'] and all(r['reaped'] and r['exitCode']==0 for r in output['nativeChildrenReaped']) and
                not (attempt/'host-controls.stderr').read_bytes(),'HOST_CONTROL_RESULT')
    except BaseException as error:
        reason=type(error).__name__+': '+str(error)
    finally:
        previous=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        try:
            cleanup_errors=[];empty=False;closed=False
            for label,action in [('settle',guardian.settle),('empty',guardian.empty),('close',guardian.close),('stable',stable)]:
                try:
                    value=action()
                    if label=='empty':empty=value is True
                    if label=='close':closed=True
                except BaseException as error:cleanup_errors.append(label+': '+type(error).__name__+': '+str(error))
            pending=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
            final={'passed':reason is None and len(commands)==4 and not pending and not cleanup_errors and empty and closed,
                'reason':reason,'cleanupErrors':cleanup_errors,'ownerEmpty':empty,'ownerClosed':closed,
                'commands':commands,'outerChildrenReaped':guardian.records,'publicInputsExact':244,
                'sourceStable':not any(s.startswith('stable:') for s in cleanup_errors),'interruptsPending':pending,
                'elapsedMonotonicNs':str(time.monotonic_ns()-began),
                'physicalEligible':False,'publicMountEligible':False,'protectedCapacity':False,
                'universalContainment':False,'priorTestsRerun':False,'candidateNativeQualificationOnly':True}
            FINAL_REPORT=final;replace_result(FINAL_DESTINATION,final)
            print(json.dumps(final,sort_keys=True))
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)
    require(final['passed'],'Standing host controls failed; retained attempt must be reviewed')

if __name__=='__main__':
    try:main()
    except BaseException as error:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
        if FINAL_DESTINATION is not None:
            FINAL_REPORT['passed']=False
            FINAL_REPORT['terminalFailure']=type(error).__name__+': '+str(error)
            FINAL_REPORT['terminalPendingSignals']=sorted(int(s) for s in signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
            replace_result(FINAL_DESTINATION,FINAL_REPORT)
        raise
