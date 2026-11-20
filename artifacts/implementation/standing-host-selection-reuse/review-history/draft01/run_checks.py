"""Fixed review-gated owner for pure equivalence and actual native freshness controls.

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
GUARDIAN_SHA='cf682bcfae001f5e1d33cad603ec4a7e3911dc4eab8557714b6973deec7bb206'
HELPER_SHA='a6ee94bcf3dc03df19f0dd07a81663badd4875ef1a6c429afbc55d7b2373b977'
ENV={'LANG':'C','LC_ALL':'C','PATH':'/usr/bin:/bin'}
FINAL_DESTINATION=None
FINAL_REPORT=None
PROFILES={'pure':['compiler_equivalence'],'live':['management_replays','final_evidence_withdrawal','final_artifact_change',
    'renewal_withdrawal','expiry_after_commit','shared_authority','finite_policy_replacement',
    'prepared_mutation_recovery','common_revoke_remains_unresolved']}


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
    expected_native=0 if profile=='pure' else len(expected_cases)
    file_bytes=1024*1024
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
        path=HERE/('selection-reuse-'+profile+'-attempt'+str(number).zfill(2))/'RESULTS.json'
        require(path.is_file() and not path.is_symlink(),'Prior explicit attempt receipt missing')
        prior_results.append({'path':str(path.relative_to(HERE)),'sha256':digest(path)})
    def stable():
        require(digest(parent_index)==inputs['parentPacket']['indexSha256'],'Parent packet index changed')
        parent_rows=json.loads(parent_index.read_bytes())['files']
        require({str(f.relative_to(parent)) for f in parent.rglob('*') if f.is_file()}=={r['path'] for r in parent_rows}|{'index.json'},'Parent inventory changed')
        for row in parent_rows:require(digest(parent/row['path'])==row['sha256'],'Parent bytes changed: '+row['path'])
        second=REPO/inputs['secondParentPacket']['path']
        require(digest(second/'index.json')==inputs['secondParentPacket']['indexSha256'],'Boundary evidence index changed')
        second_rows=json.loads((second/'index.json').read_bytes())['files']
        require({str(f.relative_to(second)) for f in second.rglob('*') if f.is_file()}=={r['path'] for r in second_rows}|{'index.json'},'Boundary evidence inventory changed')
        for row in second_rows:require(digest(second/row['path'])==row['sha256'],'Boundary evidence bytes changed: '+row['path'])
        proposal=REPO/inputs['proposalPacket']['path']
        require(digest(proposal/'index.json')==inputs['proposalPacket']['indexSha256'],'Reviewed proposal changed')
        proposal_rows=json.loads((proposal/'index.json').read_bytes())['files']
        require({str(f.relative_to(proposal)) for f in proposal.rglob('*') if f.is_file()}=={r['path'] for r in proposal_rows}|{'index.json'},'Proposal inventory changed')
        for row in proposal_rows:require(digest(proposal/row['path'])==row['sha256'],'Proposal source copy changed')
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
    attempt=HERE/('selection-reuse-'+profile+'-attempt'+str(attempt_number).zfill(2));attempt.mkdir(mode=0o700)
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
    argv=[str(interpreter),'-I','-B',str(frozen/'selection_reuse_controls.py'),profile,str(attempt/'state'),str(native),str(evidence),str(evidence/'manifest.json'),str(frozen/'owner/libharness-owner.so')]
    save(attempt/'intent.json',{'profile':'hms.standing-host-selection-reuse-attempt/0.1','controlProfile':profile,
        'attemptNumber':attempt_number,'priorProfileAttemptResults':prior_results,'sourcePins':pins,
        'parentPacket':inputs['parentPacket'],'secondParentPacket':inputs['secondParentPacket'],
        'proposalPacket':inputs['proposalPacket'],
        'publicReceipt':inputs['publicReceipt'],'interpreter':str(interpreter),
        'interpreterSha256':runtime,'argv':argv,'nativeImageSha256':digest(native),'originalQualificationRoot':str(evidence),
        'originalQualificationRunId':original_manifest['runId'],'qualificationRerun':False,'cases':expected_cases,
        'privateCompilationReuseCandidate':True,
        'productionChanged':True,'full128RecordQualification':False,
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
            child=guardian.fork(fixed_child,cpu_seconds=30,address_bytes=512*1024*1024)
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
            if profile=='pure':
                require(case['databaseSha256'] is None and case['nativeStartIdentity'] is None and case['nativeReap'] is None,'Pure case owns no native process or DB')
                require(evidence_row['publicParseCalls']==5 and evidence_row['privateParseCalls']==1 and
                    evidence_row['oldOracleSha256']=='b1734acbe443501124b2a6965aa9768abd1eb3c3966e57f4945ebc10f801d726','Exact old/new compilation count and oracle')
                vectors=evidence_row['vectors']
                require(len(vectors)==34 and len({r['case'] for r in vectors})==34 and
                    sum(r['outcome']=='ok' for r in vectors)==6 and sum(r['outcome']=='error' for r in vectors)==28,'Exact equivalence vector matrix')
                require(evidence_row['timingMeasured'] is False,'No pure timing claim')
                continue
            require(digest(directory/'authority.db')==case['databaseSha256'],'Case database changed')
            require(set(evidence_row['native'])=={str(n) for n in range(28)} and
                    all(type(value) is int and 0<=value<2**64 for value in evidence_row['native'].values()),'All28 bounded native selectors')
            require(evidence_row['nativeStartIdentity']==case['nativeStartIdentity'] and evidence_row['nativeReap']==case['nativeReap'],'Per-case native association')
            require(all(case['nativeReap'][key]==value for key,value in case['nativeStartIdentity'].items()),'Exact registered identity/reap')
            require(evidence_row['legacyChecks']==case['legacyChecks'],'Preserved legacy assertion count')
            if case['case']=='management_replays':require(evidence_row['selectionParseCalls']==3,'Complete fresh selection parse count')
            trace=evidence_row['trace'];require(type(trace) is list and 0<len(trace)<=2048,'Bounded actual trace')
            tx=rx=0;requests={};responses=set()
            for packet in trace:
                require(type(packet) is dict and set(packet)=={'direction','session','sequence','raw'},'Trace fields')
                body=bytes.fromhex(packet['raw']);require(body.hex()==packet['raw'] and 2<=len(body)<=192 and body[0]==2,'Canonical v2 payload')
                sequence=packet['sequence'];require(type(sequence) is int and 0<sequence<2**32,'Trace sequence')
                if packet['direction']=='request':
                    require(sequence>tx and body[1] in (1,16,18,64,65,66,67,68,69,70,71,72) and packet['session']==(0 if body[1]==1 else 1),'Original request sequence/session')
                    requests[sequence]=body;tx=sequence
                else:
                    request=int.from_bytes(body[2:6],'big')
                    require(packet['direction']=='response' and len(body)>=66 and sequence>rx and packet['session']==1 and
                        request in requests and request not in responses and body[1]==requests[request][1]|128,'Unique correlated reply')
                    responses.add(request);rx=sequence
            require(set(requests)==responses and tx<=evidence_row['route']['tx'] and rx<=evidence_row['route']['rx'],'Complete actual request/reply record')
            joined_reaps.append(case['nativeReap'])
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
            'privateCompilationReuseCandidate':True,'productionChanged':True,'full128RecordQualification':False,
            'legacyChecks':None if inner is None else inner.get('legacyChecks'),
            'fullSimultaneousCapacityEstablished':False,'logicalCeilingBytes':16*1024*1024,'fileBytes':file_bytes,
            'observedStateHighBytes':observed_state_bytes,'observedStateHighFiles':observed_state_files,
            'diskMonitorIsObservedNotKernelQuota':True,
            'publicInputsExact':244,'parentPacketStable':not any(e.startswith('stable:') for e in cleanup_errors),
            'qualificationRerun':False,'physicalEligible':False,'publicMountEligible':False,'protectedCapacity':False,'universalContainment':False}
        try:
            save(FINAL_DESTINATION,FINAL_REPORT,replace=True)
            print(json.dumps(FINAL_REPORT,sort_keys=True))
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)
    require(FINAL_REPORT['passed'],'Selection reuse controls failed; preserve original attempt')


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
