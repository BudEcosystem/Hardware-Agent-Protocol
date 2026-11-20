"""I/O-specific control failures, real bounded workers and hard owner loss."""
import copy
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import selectors
import sqlite3
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

from hms.contracts import canonical
from hms.journal import JournalError
from hms.pat_io_run_bundle import prepare_io_run_bundle, bundle_digest
from hms.pat_io_group_history import inspect_io_group, IoGroupHistoryError
from test_io_supervisor_contracts import IoSupervisorContractsTests, contracts, supervision, bundle_io, program
from test_io_supervisor_process import IoSupervisorProcessTests


class Fixture(IoSupervisorContractsTests):
    def workspace(self):
        p=Path(os.environ['TMPDIR'])/self._testMethodName
        if not p.exists():p.mkdir(mode=0o700)
        self.assertEqual(p.stat().st_mode&0o777,0o700)
        return p

    def new_root(self,label='supervisor'):
        p=self.workspace()/label;p.mkdir(mode=0o700);return p

    def emit(self,name,value):
        p=self.workspace()/(name+'.json')
        fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:contracts.write_file(fd,p.name,canonical(value))
        finally:os.close(fd)

    def case(self,name,group_limits=None):
        context=self.context|dict(runId='run:'+name)
        if group_limits is None:
            request=copy.deepcopy(self.request);bundle=copy.deepcopy(self.bundle)
            request['context']=context;request['bundleHeader']['context']=copy.deepcopy(context)
            bundle['header']=canonical(request['bundleHeader']);bundle['bundleDigest']=bundle_digest(bundle['header'])
            request['bundleDigest']=bundle['bundleDigest']
            return contracts.parse_request(request),bundle
        bundle=prepare_io_run_bundle(context=context,**self.options,limits=group_limits)
        return contracts.prepare_request(bundle,context=context),bundle

    def service(self,label='supervisor'):
        service=supervision.QualificationSupervisor(self.new_root(label),create=True)
        def close():
            if service.ledger.db is not None:
                for identifier in list(service._owned):service.stop_owned(identifier)
                service.close()
        self.addCleanup(close);return service

    def code(self,expected,call,*args,**kwargs):
        with self.assertRaises(JournalError) as caught:call(*args,**kwargs)
        self.assertEqual(caught.exception.code,expected)

    def arm(self,service,request,*,running=False):
        row,_=service.ledger.admit(request);identifier=row['record']['attemptId']
        directory=supervision._directory(service.ledger.fd,identifier,create=True)
        contracts.write_file(directory,'writer.lease',b'')
        fd=os.open('writer.lease',os.O_RDWR|os.O_NOFOLLOW,dir_fd=directory);info=os.fstat(fd)
        service.ledger.change(identifier,'launching',lease=dict(device=str(info.st_dev),inode=str(info.st_ino)))
        if running:service.ledger.change(identifier,'running',pid=12345)  # Diagnostic fixture only, never signal authority.
        return identifier,directory,fd


class IoControlRecoveryTests(Fixture):
    def setUp(self):
        guard=patch.object(supervision.subprocess,'Popen',side_effect=AssertionError('control fixture must not spawn'))
        guard.start();self.addCleanup(guard.stop)

    def test_admission_replay_conflict_and_detachment(self):
        service=self.service();request,_=self.case('admission');saved=copy.deepcopy(request)
        first,created=service.ledger.admit(request);self.assertTrue(created)
        request['context']['runId']='changed';replay,created=service.ledger.admit(saved)
        self.assertFalse(created);self.assertEqual(first,replay)
        changed=copy.deepcopy(saved);changed['limits']['maxStreamBytes']-=1
        self.code('KEY_CONFLICT',service.ledger.admit,changed)
        self.assertEqual(service.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(),(1,))
        self.emit('checks',dict(first=first['record'],replayMatched=True,conflictRefused=True,workerExecuted=False))

    def test_one_active_attempt_and_owner_are_preserved(self):
        service=self.service();first,_=self.case('one');second,_=self.case('two')
        service.ledger.admit(first)
        self.code('QUALIFICATION_BUSY',service.ledger.admit,second)
        self.code('QUALIFICATION_OWNER_BUSY',supervision.QualificationSupervisor,service.ledger.root)
        self.emit('checks',dict(singleActive=True,exclusiveOwner=True,workerExecuted=False))

    def test_concurrent_replay_and_conflict_do_not_launch_twice(self):
        service=self.service();request,bundle=self.case('concurrent');admitted=threading.Event();release=threading.Event();errors=[]
        def checkpoint(phase,row):
            if phase=='admitted':admitted.set();release.wait(10);raise RuntimeError('controlled stop before launch')
        service._checkpoint=checkpoint
        def execute():
            try:service.execute(request,bundle)
            except Exception as error:errors.append(str(error))
        thread=threading.Thread(target=execute);thread.start()
        try:
            self.assertTrue(admitted.wait(10));row=service.execute(request)
            self.assertEqual(row['record']['state'],'admitted')
            changed=copy.deepcopy(request);changed['limits']['maxStreamBytes']-=1
            self.code('KEY_CONFLICT',service.execute,changed)
            other,other_bundle=self.case('other');self.code('QUALIFICATION_BUSY',service.execute,other,other_bundle)
        finally:release.set();thread.join(10)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,['controlled stop before launch'])
        archived=service.recover(row['record']['attemptId']);self.assertFalse(archived['record']['archive']['transportComplete'])
        self.emit('checks',dict(archive=archived['record'],concurrentReplayMatched=True,workerExecuted=False))

    def test_retention_and_image_reservation_refuse_before_admission(self):
        for number in (0,1):
            service=self.service('case-%02d'%number);request,bundle=self.case('capacity-'+str(number))
            if number==0:
                request['limits']['maxRetainedBytes']=request['limits']['attemptReservationBytes']
                self.code('QUALIFICATION_RETENTION_FULL',service.ledger.admit,request)
            else:
                usage=supervision.tree_usage(service.ledger.root,max_files=8192,max_bytes=256*1024*1024)
                image=supervision._image_charge(service.ledger,request)
                request['limits']['maxRetainedBytes']=usage['logicalBytes']+request['limits']['attemptReservationBytes']+image['logicalBytes']-1
                self.code('QUALIFICATION_RETENTION_FULL',service.execute,request,bundle)
            self.assertEqual(service.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(),(0,))
            self.assertEqual(list(service.ledger.root.glob('code-*')),[])
        self.emit('checks',dict(noAdmission=True,noImageWritten=True,workerExecuted=False,hardQuotaProved=False))

    def test_unarmed_owner_loss_is_terminal_and_replays_without_fresh_setup(self):
        service=self.service();request,_=self.case('unarmed');row,_=service.ledger.admit(request)
        root=service.ledger.root;identifier=row['record']['attemptId'];service.close()
        reopened=supervision.QualificationSupervisor(root);self.addCleanup(reopened.close)
        self.assertEqual(reopened.status(identifier)['state'],'interrupted')
        with patch.object(supervision.signal,'pidfd_send_signal',side_effect=AssertionError('stored PID signal')):
            archived=reopened.recover(identifier);self.code('QUALIFICATION_NO_OWNED_PROCESS',reopened.stop_owned,identifier)
        self.assertIsNone(archived['returnBytes']);self.assertFalse(archived['record']['archive']['transportComplete'])
        with patch.object(supervision,'validate_fresh',side_effect=AssertionError('replan')):
            self.assertEqual(reopened.execute(request),archived)
        self.emit('checks',dict(record=archived['record'],exactReplay=True,noStoredPidSignal=True,workerExecuted=False))

    def test_held_missing_and_replaced_leases_remain_unknown(self):
        for kind in ('held','missing','replaced'):
            service=self.service(kind);request,_=self.case('lease-'+kind)
            identifier,directory,lease=self.arm(service,request,running=True)
            try:
                fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
                if kind!='held':
                    os.rename('writer.lease','retained-writer.lease',src_dir_fd=directory,dst_dir_fd=directory)
                    if kind=='replaced':contracts.write_file(directory,'writer.lease',b'')
                    os.fsync(directory)
                with patch.object(supervision.signal,'pidfd_send_signal',side_effect=AssertionError('stored PID signal')):
                    self.code('QUALIFICATION_PRODUCER_ACTIVE' if kind=='held' else 'QUALIFICATION_OWNERSHIP_UNKNOWN',service.recover,identifier)
                    self.code('QUALIFICATION_NO_OWNED_PROCESS',service.stop_owned,identifier)
                self.assertEqual(service.status(identifier)['state'],'running')
                self.emit(kind,dict(record=service.status(identifier),workerExecuted=False,diagnosticPidOnly=True,originalLeaseRetained=True))
            finally:os.close(lease);os.close(directory)

    def test_malformed_return_bytes_are_preserved_without_success(self):
        for index,raw in enumerate((b'',b'not canonical JSON',b'{}')):
            service=self.service('case-%02d'%index);request,_=self.case('malformed-'+str(index))
            identifier,directory,lease=self.arm(service,request)
            try:contracts.write_file(directory,'worker-return.json',raw)
            finally:os.close(lease);os.close(directory)
            archived=service.recover(identifier);self.assertEqual(archived['returnBytes'],raw)
            self.assertFalse(archived['record']['archive']['transportComplete']);self.assertIsNone(archived['record']['archive']['unresolvedEffects'])
            self.assertIsNotNone(archived['record']['archive']['returnValidationFailure'])
            self.assertEqual(service.execute(request),archived)
            self.emit('case-%02d'%index,dict(record=archived['record'],returnSha256=hashlib.sha256(raw).hexdigest(),workerExecuted=False))

    def test_each_corrupt_control_record_is_refused_and_left_unrestored(self):
        mutations=[lambda r:r['archive'].update(transportComplete=True),lambda r:r['archive'].update(semanticQualificationVerified=True),
            lambda r:r['archive'].update(unresolvedEffects=0),lambda r:r.update(unrecognized=True),
            lambda r:r.update(history=['admitted','running','archived']),lambda r:r.update(pid=True),
            lambda r:r['archive'].update(totalDiskQuotaEnforced=True),lambda r:r.update(archive=None),
            lambda r:r.update(state='unknown'),lambda r:r.update(state='interrupted'),lambda r:r.update(lease=[])]
        for index,mutate in enumerate(mutations):
            service=self.service('case-%02d'%index);request,_=self.case('corrupt-'+str(index))
            row,_=service.ledger.admit(request);identifier=row['record']['attemptId'];saved=service.recover(identifier)['record']
            invalid=copy.deepcopy(saved);mutate(invalid)
            service.ledger.db.execute('UPDATE qs_attempts SET record=?,active=? WHERE id=?',
                (canonical(invalid),0 if invalid['state']=='archived' else 1,identifier))
            self.code('QUALIFICATION_LEDGER_INVALID',service.execute,request)
            self.assertEqual(service.ledger.db.execute('SELECT record FROM qs_attempts').fetchone()[0],canonical(invalid))
            self.emit('case-%02d'%index,dict(originalRecord=saved,retainedCorruptRecord=invalid,restored=False,workerExecuted=False))

    def test_partial_schema_refuses_without_reinitialization(self):
        root=self.new_root();path=root/'attempts.db';fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600);os.close(fd)
        db=sqlite3.connect(path)
        try:db.execute('CREATE TABLE qs_meta(version)');db.commit()
        finally:db.close()
        before=path.read_bytes();self.code('QUALIFICATION_SCHEMA_INVALID',supervision.QualificationSupervisor,root,create=True)
        self.assertEqual(path.read_bytes(),before)
        self.emit('checks',dict(databaseUnchanged=True,schemaReinitialized=False,workerExecuted=False))

    def test_exit_eof_after_selector_wait_still_fails_parent_deadline(self):
        service=self.service();request,_=self.case('late-eof');identifier,directory,lease=self.arm(service,request,running=True);os.close(lease)
        readers=[]
        for _ in range(2):
            reader,writer=os.pipe();os.close(writer);readers.append(os.fdopen(reader,'rb'))
        process=SimpleNamespace(stdout=readers[0],stderr=readers[1],poll=lambda:0)
        service._owned[identifier]=(process,os.open('/dev/null',os.O_RDONLY));clock=[.9]
        class Selector:
            def __init__(self):self.items={}
            def register(self,stream,event,name):self.items[stream]=name
            def unregister(self,stream):self.items.pop(stream)
            def select(self,timeout):
                clock[0]=1.1;return [(SimpleNamespace(fileobj=stream,data=name),1) for stream,name in list(self.items.items())]
            def get_map(self):return self.items
            def close(self):pass
        try:
            with patch.object(supervision.selectors,'DefaultSelector',Selector), \
                 patch.object(supervision.time,'monotonic',side_effect=lambda:clock[0]), \
                 patch.object(supervision.signal,'pidfd_send_signal',side_effect=AssertionError('already exited')):
                row=service._collect(service.ledger.get(identifier),directory,-59)
            self.assertEqual(row['record']['archive']['supervisorReason'],'SUPERVISOR_DEADLINE')
            self.assertFalse(row['record']['archive']['transportComplete']);self.assertFalse(service._owned)
            self.emit('checks',dict(record=row['record'],workerExecuted=False,clockAndProcessSimulated=True))
        finally:
            os.close(directory)
            for stream in readers:
                if not stream.closed:stream.close()
            if identifier in service._owned:os.close(service._owned.pop(identifier)[1])

    def test_caller_mapping_mutation_cannot_change_retained_launch_input(self):
        service=self.service();request,bundle=self.case('detachment');original=copy.deepcopy(bundle)
        def checkpoint(phase,row):
            if phase=='admitted':bundle['documents']['cases/00.json']=b'{}'
            if phase=='launching':
                fd=supervision._directory(service.ledger.fd,row['record']['attemptId'])
                try:self.assertEqual(bundle_io.load_bundle(fd,request),original)
                finally:os.close(fd)
                raise RuntimeError('controlled stop after durable inputs')
        service._checkpoint=checkpoint
        with self.assertRaisesRegex(RuntimeError,'controlled stop'):service.execute(request,bundle)
        row=service.lookup(*contracts.run_key(request));self.assertEqual(row['record']['state'],'interrupted')
        archived=service.recover(row['record']['attemptId']);self.assertFalse(archived['record']['archive']['transportComplete'])
        self.emit('checks',dict(record=archived['record'],callerMutationExcluded=True,workerExecuted=False))


class IoPwmSupervisionTests(IoSupervisorProcessTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.context=cls.context|dict(runId='run:pwm')
        cls.options=cls.options|dict(candidate=program(pwm=True,literal=True),descriptor=cls.options['challenge_bindings']['pwm']['descriptor'])
        cls.bundle=prepare_io_run_bundle(context=cls.context,**cls.options)
        cls.request=contracts.prepare_request(cls.bundle,context=cls.context)

    def test_complete_owned_pwm_group_retains_inputs_before_launch_and_replays(self):
        self.test_complete_owned_gpio_group_retains_inputs_before_launch_and_replays()


class IoWorkerFailureTests(Fixture):
    def test_original_record_cutoff_retains_nonpassing_complete_transport(self):
        service=self.service();request,bundle=self.case('record-cutoff',self.request['groupLimits']|dict(maxRecords=500))
        row=service.execute(request,bundle);archive=row['record']['archive'];returned=contracts.document(row['returnBytes'])
        self.assertEqual(returned['status'],'failed');self.assertTrue(archive['transportComplete'],archive)
        self.assertFalse(archive['semanticQualificationVerified']);self.assertIsNone(archive['unresolvedEffects'])
        output=service.ledger.root/row['record']['attemptId']/'output'
        result=json.loads((output/'result.json').read_bytes());self.assertLess(len(result['cases']),30)
        parsed=bundle_io.check_bundle(request,bundle)
        files={p.relative_to(output).as_posix():p.read_bytes() for p in output.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(IoGroupHistoryError,'INCOMPLETE'):
            inspect_io_group(files,expected_inputs=parsed['expected_inputs'],expected_cases=parsed['expected_cases'])
        self.assertEqual(service.execute(request),row)
        self.emit('checks',dict(record=row['record'],returned=returned,groupError=result['error'],completedCases=len(result['cases']),independentQualificationRefused=True))

    def test_real_parent_deadline_stops_only_its_owned_child_and_keeps_unknown(self):
        service=self.service();request,bundle=self.case('deadline',self.request['groupLimits']|dict(maxWallMs=1))
        row=service.execute(request,bundle);archive=row['record']['archive']
        self.assertEqual(row['record']['state'],'archived');self.assertEqual(archive['supervisorReason'],'SUPERVISOR_DEADLINE')
        self.assertFalse(archive['transportComplete']);self.assertIsNone(archive['unresolvedEffects']);self.assertFalse(service._owned)
        self.assertEqual(service.execute(request),row)
        self.emit('checks',dict(record=row['record'],ownedHandlesSettled=True,exactReplay=True))

    def test_pidfd_failure_keeps_original_popen_for_bounded_settlement(self):
        service=self.service();request,bundle=self.case('pidfd-failure');captured=[];original=subprocess.Popen
        def spawn(*args,**kwargs):
            process=original(*args,**kwargs);captured.append(process);return process
        try:
            with patch.object(supervision.subprocess,'Popen',side_effect=spawn), \
                 patch.object(supervision.os,'pidfd_open',side_effect=OSError('controlled pidfd exhaustion')):
                with self.assertRaisesRegex(OSError,'controlled pidfd'):service.execute(request,bundle)
            row=service.lookup(*contracts.run_key(request));identifier=row['record']['attemptId']
            self.assertIs(service._owned[identifier][0],captured[0]);self.code('QUALIFICATION_PROCESS_UNSETTLED',service.close)
        finally:
            for identifier in list(service._owned):service.stop_owned(identifier)
        row=service.lookup(*contracts.run_key(request));self.assertEqual(row['record']['state'],'archived')
        self.assertFalse(row['record']['archive']['transportComplete']);self.assertIsNone(row['record']['archive']['unresolvedEffects'])
        self.assertEqual(service.execute(request),row)
        self.emit('checks',dict(record=row['record'],cleanupUsedOriginalPopen=True,childExitCode=captured[0].returncode,exactReplay=True))


class IoOwnerCrashTests(Fixture):
    def crash(self,phase):
        root=self.new_root();prepared=self.workspace()/'prepared';prepared.mkdir(mode=0o700)
        request,bundle=self.case('crash-'+phase);fd=os.open(prepared,os.O_RDONLY|os.O_DIRECTORY)
        try:
            bundle_io.retain_bundle(fd,request,bundle);contracts.write_file(fd,'request.json',canonical(request))
            roots=sorted({str(Path(importlib.metadata.distribution(p).locate_file('')).resolve()) for p in contracts.PACKAGES})
            contracts.write_file(fd,'driver-config.json',canonical(dict(root=str(root),phase=phase,externalRoots=roots)))
        finally:os.close(fd)
        driver=Path(__file__).with_name('io_supervisor_crash_driver.py')
        process=subprocess.Popen([sys.executable,'-I','-S','-B',str(driver),str(prepared)],
            cwd=Path(__file__).resolve().parents[1],env={'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'},stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        streams={'stdout':bytearray(),'stderr':bytearray()};deadline=time.monotonic()+90
        try:
            with selectors.DefaultSelector() as selector:
                for name in streams:
                    stream=getattr(process,name);os.set_blocking(stream.fileno(),False)
                    selector.register(stream,selectors.EVENT_READ,name)
                while selector.get_map():
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise TimeoutError('Original crash driver deadline')
                    for key,_ in selector.select(min(remaining,.1)):
                        chunk=os.read(key.fileobj.fileno(),4096)
                        if not chunk:selector.unregister(key.fileobj);continue
                        remaining_bytes=65536-len(streams[key.data])
                        streams[key.data].extend(chunk[:remaining_bytes])
                        if len(chunk)>remaining_bytes:raise ValueError('Original driver stream bound')
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Driver crossed deadline at EOF')
            process.wait(timeout=remaining)
            if time.monotonic()>=deadline:raise TimeoutError('Driver crossed deadline at exit')
        except BaseException:
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            raise
        finally:
            for name in streams:getattr(process,name).close()
            fd=os.open(self.workspace(),os.O_RDONLY|os.O_DIRECTORY)
            try:
                for name,value in streams.items():contracts.write_file(fd,'driver-'+name+'.log',bytes(value))
            finally:os.close(fd)
            self.emit('driver-exit',dict(exitCode=process.returncode,streams={name:dict(bytes=len(value),sha256=hashlib.sha256(value).hexdigest()) for name,value in streams.items()}))
        self.assertEqual(process.returncode,91,bytes(streams['stderr'][-4096:]))
        receipt=json.loads((prepared/'crash-receipt.json').read_bytes());self.assertEqual(receipt['phase'],phase)
        service=supervision.QualificationSupervisor(root);self.addCleanup(service.close)
        row=service.lookup(*contracts.run_key(request));identifier=row['record']['attemptId']
        with patch.object(supervision.signal,'pidfd_send_signal',side_effect=AssertionError('no inherited owned handle')):
            self.code('QUALIFICATION_NO_OWNED_PROCESS',service.stop_owned,identifier)
            if phase=='spawned':self.code('QUALIFICATION_PRODUCER_ACTIVE',service.recover,identifier)
            deadline=time.monotonic()+70
            while row['record']['state']!='archived':
                try:row=service.recover(identifier)
                except JournalError as error:
                    self.assertEqual(error.code,'QUALIFICATION_PRODUCER_ACTIVE');self.assertLess(time.monotonic(),deadline)
                    time.sleep(.05)
        archive=row['record']['archive']
        if phase=='archived':self.assertTrue(archive['transportComplete'])
        else:
            self.assertFalse(archive['transportComplete']);self.assertIsNone(archive['exitCode']);self.assertTrue(archive['ownerRecovered'])
        self.assertFalse(archive['semanticQualificationVerified']);self.assertIsNone(archive['unresolvedEffects'])
        if phase in ('spawned','producer_settled','archived'):
            returned=contracts.document(row['returnBytes']);self.assertEqual(returned['status'],'captured')
            output=root/identifier/'output';files={p.relative_to(output).as_posix():p.read_bytes() for p in output.rglob('*') if p.is_file()}
            parsed=bundle_io.check_bundle(request,bundle)
            checked=inspect_io_group(files,expected_inputs=parsed['expected_inputs'],expected_cases=parsed['expected_cases'])
            self.assertTrue(checked['summary']['independentOutcomeChecked'])
            self.emit('independent-summary',checked['summary'])
        else:self.assertIsNone(row['returnBytes'])
        with patch.object(supervision,'validate_fresh',side_effect=AssertionError('replan')):self.assertEqual(service.execute(request),row)
        self.assertEqual(service.ledger.db.execute('SELECT count(*) FROM qs_attempts').fetchone(),(1,))
        self.emit('checks',dict(phase=phase,record=row['record'],replayedWithoutRelaunch=True,noStoredPidSignal=True,crashExitCode=91))

    def test_owner_exit_after_admission(self):self.crash('admitted')
    def test_owner_exit_after_launch_intent(self):self.crash('launching')
    def test_owner_exit_after_spawn(self):self.crash('spawned')
    def test_owner_exit_after_producer_settlement(self):self.crash('producer_settled')
    def test_owner_exit_after_archive_commit(self):self.crash('archived')
