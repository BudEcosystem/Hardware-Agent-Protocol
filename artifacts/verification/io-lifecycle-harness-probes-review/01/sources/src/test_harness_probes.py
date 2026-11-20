"""Original bookkeeping probes. These do not qualify lifecycle effects."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import py_compile
import shutil
import signal
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

BASE=Path(os.environ['PROBE_INPUT_ROOT']).resolve()
OUT=Path(os.environ['PROBE_CASE_ROOT']).resolve()
FROZEN=BASE/'retained05'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(path):
    return [{'path':str(p.relative_to(path)),'sha256':sha(p),'bytes':p.stat().st_size}
            for p in sorted(path.rglob('*')) if p.is_file()]


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class HarnessProbes(unittest.TestCase):
    def setUp(self):
        self.case=OUT/self._testMethodName;self.case.mkdir(parents=True,exist_ok=False)
        self.source_before=None
        self.stage=self.case/'stage';self.stage.mkdir()
        for name in ('run_attempt.py','attempt_child.py'):shutil.copyfile(FROZEN/name,self.stage/name)
        shutil.copytree(FROZEN/'project',self.stage/'project')
        self.addCleanup(self.retain)

    def retain(self):
        # Never delete a probe case, even if its assertion or cleanup fails.
        state={'scope':'Bookkeeping only; all injected sources explicit; not lifecycle qualification.',
               'sourcesUnchanged':None,'sourceBefore':self.source_before}
        if self.source_before is not None:
            state['sourcesUnchanged']=all((self.stage/r['path']).is_file() and sha(self.stage/r['path'])==r['sha256'] for r in self.source_before)
        (self.case/'case-state.json').write_text(json.dumps(state,indent=2)+'\n')
        (self.case/'retention.json').write_text(json.dumps({'files':inventory(self.case)},indent=2)+'\n')

    def basic_fixture(self,kind='pass'):
        body={'pass':'self.assertEqual(2+2,4)','skip':'self.skipTest("controlled skip")',
              'expected_failure':'self.fail("controlled expected failure")','unexpected_success':'self.assertTrue(True)'}
        if kind=='empty':text='import unittest\n'
        else:
            decorator='    @unittest.expectedFailure\n' if kind in {'expected_failure','unexpected_success'} else ''
            text='import unittest\nclass Probe(unittest.TestCase):\n'+decorator+'    def test_original_bookkeeping_fixture(self):\n        '+body[kind]+'\n'
        (self.stage/'project/tests/test_io_lifecycle.py').write_text(text)
        (self.stage/'project/tests/test_io_synthetic_provider.py').write_text('"""Explicit empty original ordinary-provider import fixture; no provider test executed."""\n')
        (self.case/'fixture-description.json').write_text(json.dumps({'replacedTestModules':['test_io_lifecycle','test_io_synthetic_provider'],
            'kind':kind,'lifecycleQualified':False},indent=2)+'\n')

    def run_runner(self,mode='normal',targets=None):
        config={'case':str(self.case),'mode':mode,'targets':targets or ['test_io_lifecycle'],
                'childFixture':str(BASE/'src/owned_child_fixture.py')}
        path=self.case/'wrapper-config.json';path.write_text(json.dumps(config,indent=2)+'\n')
        self.source_before=inventory(self.stage)
        (self.case/'case-inputs-before.json').write_text(json.dumps(self.source_before,indent=2)+'\n')
        environment={'PATH':os.pathsep.join((str(Path(sys.executable).parent),'/usr/bin','/bin')),
                     'TMPDIR':str(self.case),'LC_ALL':'C.UTF-8','TZ':'UTC'}
        command=[sys.executable,'-I','-B',str(BASE/'src/runner_wrapper.py'),str(path)]
        (self.case/'wrapper-command.json').write_text(json.dumps({'argv':command,'environment':environment},indent=2)+'\n')
        with (self.case/'wrapper.log').open('xb') as log:
            process=subprocess.Popen(command,cwd=self.stage,env=environment,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:returncode=process.wait(timeout=90)
            except BaseException:
                process.terminate()
                try:process.wait(timeout=20)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
                raise
        wrapper=json.loads((self.case/'wrapper-return.json').read_text())
        self.assertTrue(all(not row['emergencyCleanupNeeded'] and row['finalReturnCode'] is not None for row in wrapper['ownedChildren']),wrapper)
        self.assertTrue(all(sha(self.stage/r['path'])==r['sha256'] for r in self.source_before))
        attempt=self.stage/'attempts/probe'
        result=json.loads((attempt/'result.json').read_text()) if (attempt/'result.json').exists() else None
        return returncode,result,wrapper,attempt

    def assert_failed(self,result):
        self.assertIsNotNone(result);self.assertIs(result['currentPass'],False)
        self.assertNotEqual(result['status'],'passed')

    def test_actual_launch_failure_finalizes_without_child(self):
        self.basic_fixture();code,result,wrapper,attempt=self.run_runner('launch_failure')
        self.assertNotEqual(code,0);self.assert_failed(result)
        self.assertEqual(wrapper['ownedChildren'],[]);self.assertEqual(result['childState'],'not_started')
        self.assertIsNone(result['exitCode']);self.assertIsNone(result['counts'])
        self.assertTrue((attempt/'inputs-before.json').exists());self.assertTrue((attempt/'inputs-after.json').exists())
        self.assertTrue(any(e['type']=='OSError' for e in result['errors']))

    def test_actual_owned_timeout_terminates_and_reaps(self):
        self.basic_fixture();code,result,wrapper,attempt=self.run_runner('timeout')
        self.assertNotEqual(code,0);self.assert_failed(result)
        self.assertEqual(result['status'],'timed_out');self.assertEqual(result['childState'],'exited')
        self.assertEqual(result['signalsAttempted'],['terminate'])
        self.assertEqual(result['exitCode'],-signal.SIGTERM)
        self.assertEqual(json.loads((self.case/'child-ready.json').read_text())['pid'],result['pid'])
        self.assertIn('ORIGINAL_OWNED_CHILD_READY',(attempt/'output.log').read_text())

    def test_actual_owned_timeout_escalates_to_kill(self):
        self.basic_fixture();code,result,wrapper,attempt=self.run_runner('kill_required')
        self.assertNotEqual(code,0);self.assert_failed(result)
        self.assertEqual(result['signalsAttempted'],['terminate','kill']);self.assertEqual(result['exitCode'],-signal.SIGKILL)
        self.assertEqual(result['childState'],'exited');self.assertEqual(len(wrapper['ownedChildren']),1)

    def test_interrupted_owned_wait_finalizes_and_reaps(self):
        self.basic_fixture();code,result,wrapper,attempt=self.run_runner('interrupt_wait')
        self.assertNotEqual(code,0);self.assert_failed(result)
        self.assertEqual(result['status'],'interrupted');self.assertEqual(result['childState'],'exited')
        self.assertTrue(any(e['type']=='KeyboardInterrupt' for e in result['errors']))
        self.assertTrue((attempt/'external-after.json').exists());self.assertTrue((attempt/'scratch-index.json').exists())

    def test_after_manifest_failure_does_not_block_other_finalizers(self):
        self.basic_fixture();code,result,wrapper,attempt=self.run_runner('finalization_failure')
        self.assertNotEqual(code,0);self.assert_failed(result)
        self.assertEqual(result['exitCode'],0);self.assertIsNone(result['inputsUnchanged'])
        self.assertTrue(any(e['phase']=='inputs-after' for e in result['errors']))
        self.assertTrue((attempt/'external-after.json').exists());self.assertTrue((attempt/'evidence-index.json').exists())
        self.assertEqual(result['counts']['testsRun'],1)

    def test_missing_and_malformed_real_child_return_fail_closed(self):
        # Separate owned cases so the runner's immutable attempt directory is not reused.
        for mode in ('missing_return','malformed_return'):
            with self.subTest(mode=mode):
                nested=self.case/mode;nested.mkdir();saved_case,saved_stage=self.case,self.stage
                self.case=nested;self.stage=nested/'stage';self.stage.mkdir()
                for name in ('run_attempt.py','attempt_child.py'):shutil.copyfile(FROZEN/name,self.stage/name)
                shutil.copytree(FROZEN/'project',self.stage/'project')
                try:
                    self.basic_fixture();code,result,wrapper,attempt=self.run_runner(mode)
                    self.assertNotEqual(code,0);self.assert_failed(result);self.assertEqual(result['exitCode'],0)
                finally:
                    self.retain();self.case,self.stage=saved_case,saved_stage;self.source_before=None

    def test_actual_empty_skip_expected_failure_and_unexpected_success_never_pass(self):
        for kind in ('empty','skip','expected_failure','unexpected_success'):
            with self.subTest(kind=kind):
                nested=self.case/kind;nested.mkdir();saved_case,saved_stage=self.case,self.stage
                self.case=nested;self.stage=nested/'stage';self.stage.mkdir()
                for name in ('run_attempt.py','attempt_child.py'):shutil.copyfile(FROZEN/name,self.stage/name)
                shutil.copytree(FROZEN/'project',self.stage/'project')
                try:
                    self.basic_fixture(kind);code,result,wrapper,attempt=self.run_runner()
                    self.assertNotEqual(code,0);self.assert_failed(result)
                    field={'empty':'testsRun','skip':'skips','expected_failure':'expectedFailures','unexpected_success':'unexpectedSuccesses'}[kind]
                    self.assertEqual(result['counts'][field],0 if kind=='empty' else 1)
                finally:
                    self.retain();self.case,self.stage=saved_case,saved_stage;self.source_before=None

    def test_target_module_gate_refuses_before_attempt_or_child(self):
        self.basic_fixture();code,result,wrapper,attempt=self.run_runner(targets=['test_endpoint_cli'])
        self.assertNotEqual(code,0);self.assertIsNone(result);self.assertFalse(attempt.exists())
        self.assertEqual(wrapper['ownedChildren'],[]);self.assertEqual(wrapper['exception']['type'],'SystemExit')

    def test_original_closed_count_function_rejects_boolean_negative_extra_and_missing(self):
        runner=load(self.stage/'run_attempt.py','closed_counts_original')
        good={'testsRun':1,'failures':0,'errors':0,'skips':0,'expectedFailures':0,'unexpectedSuccesses':0}
        self.assertTrue(runner.valid_counts(good))
        bad=[good|{'testsRun':True},good|{'testsRun':0},good|{'errors':-1},good|{'unknown':0},[],None]
        bad.append({k:v for k,v in good.items() if k!='skips'})
        for value in bad:
            with self.subTest(value=value):self.assertFalse(runner.valid_counts(value))

    def test_source_fallback_dynamic_fixture_and_shared_helper_origins(self):
        self.basic_fixture()
        tests=self.stage/'project/tests';project=self.stage/'project'
        shutil.copyfile(BASE/'src/source_probe_module.py',tests/'test_io_lifecycle.py')
        (tests/'shared_probe.py').write_text("VALUE='shared-original'\n")
        (tests/'fixtures/dynamic_origin.py').write_text("VALUE='dynamic-original'\n")
        source=tests/'probe_source.py';source.write_text("VALUE = 'cached'\n")
        original_stat=source.stat();py_compile.compile(str(source),doraise=True)
        source.write_text("VALUE = 'source'\n");os.utime(source,ns=(original_stat.st_atime_ns,original_stat.st_mtime_ns))
        py_compile.compile(str(BASE/'src/sourceless_source.py'),cfile=str(tests/'fixtures/sourceless.pyc'),doraise=True)
        with (self.case/'cache-control.log').open('xb') as log:
            control=subprocess.run([sys.executable,'-I','-S','-B',str(BASE/'src/cache_control.py'),str(tests),str(self.case/'cache-control.json')],
                stdout=log,stderr=subprocess.STDOUT,timeout=15)
        self.assertEqual(control.returncode,0);self.assertEqual(json.loads((self.case/'cache-control.json').read_text())['value'],'cached')
        code,result,wrapper,attempt=self.run_runner()
        self.assertEqual(code,0,result);self.assertIs(result['currentPass'],True)
        self.assertEqual(result['counts']['testsRun'],1)
        origins=json.loads((attempt/'imports.json').read_text())
        copied=attempt/'project/tests'
        for name in ('shared_probe.py','probe_source.py','fixtures/dynamic_origin.py'):
            self.assertTrue(any(r.get('origin')==str((copied/name).resolve()) and r.get('kind')=='project' and r.get('matchesBefore') is True for r in origins['records']),name)
        self.assertTrue(any(r.get('source')=='executed_code' and r.get('origin')==str((copied/'fixtures/dynamic_origin.py').resolve()) for r in origins['records']))
        self.assertTrue(any('probe_source.' in p and p.endswith('.pyc') for p in origins['deniedBytecodeReads']))
        self.assertTrue(any(p.endswith('sourceless.pyc') for p in origins['deniedBytecodeReads']))
        self.assertEqual(origins['violations'],[])

    def test_unexpected_shared_origin_cannot_produce_current_pass(self):
        self.basic_fixture()
        foreign=self.case/'explicit-foreign-fixture.py'
        shutil.copyfile(BASE/'src/foreign_origin_fixture.py',foreign)
        text=('import unittest, importlib.util\nclass Probe(unittest.TestCase):\n'
              '    def test_controlled_foreign_origin(self):\n'
              '        spec=importlib.util.spec_from_file_location("shared_unpinned",'+repr(str(foreign))+')\n'
              '        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)\n'
              '        self.assertEqual(module.VALUE,"explicit-unpinned-origin")\n')
        (self.stage/'project/tests/test_io_lifecycle.py').write_text(text)
        (self.case/'foreign-fixture-input.json').write_text(json.dumps({'path':str(foreign),'sha256':sha(foreign),
            'intent':'Original harmless negative fixture outside tested copy; expected origin refusal.'},indent=2)+'\n')
        code,result,wrapper,attempt=self.run_runner()
        self.assertNotEqual(code,0);self.assert_failed(result)
        self.assertEqual(result['counts']['testsRun'],1);self.assertEqual(result['counts']['failures'],0)
        origins=json.loads((attempt/'imports.json').read_text())
        self.assertTrue(any(r.get('origin')==str(foreign.resolve()) and r.get('kind')=='unexpected_origin' for r in origins['violations']))

    def capture_parts(self):
        # Import exact original05 TestCase methods, but never run its setUp or Runtime.
        project=FROZEN/'project';sys.path[:0]=[str(project),str(project/'tests')]
        import test_io_lifecycle as lifecycle
        import io_evidence_capture as helper
        self.assertEqual(Path(lifecycle.__file__).resolve(),(project/'tests/test_io_lifecycle.py').resolve())
        self.assertEqual(Path(helper.__file__).resolve(),(project/'tests/io_evidence_capture.py').resolve())
        with patch.object(helper.tempfile,'tempdir',str(self.case)):
            workspace=helper.EvidenceWorkspace()
        directory=Path(workspace.name)/'runtime';directory.mkdir()
        with sqlite3.connect(directory/'authority.db') as db:
            db.execute('CREATE TABLE proof(value INTEGER)');db.execute('INSERT INTO proof VALUES(1)')
        case=lifecycle.LifecycleTests('test_exact_all_sibling_claims_and_no_admin_publication_shortcut')
        case.temp=workspace;case.directory=directory;case.wall=case.mono=1000;case.configuration={}
        case._capture_number=0;case._final_captured=False
        lifecycle.EVIDENCE_DIRECTORY=self.case/'captures';lifecycle.EVIDENCE_DIRECTORY.mkdir()
        return helper,case,workspace,directory

    def test_real_backup_failure_retains_raw_workspace_and_allows_retry(self):
        helper,case,workspace,directory=self.capture_parts();original=helper.sqlite3.connect
        class SourceProxy:
            def __init__(self,connection):self.connection=connection
            def backup(self,*args,**kwargs):raise sqlite3.OperationalError('controlled real-source backup failure')
            def __getattr__(self,name):return getattr(self.connection,name)
        def connect(database,*args,**kwargs):
            connection=original(database,*args,**kwargs)
            return SourceProxy(connection) if isinstance(database,str) and database.startswith('file:') else connection
        with patch.object(helper.sqlite3,'connect',side_effect=connect):
            with self.assertRaisesRegex(sqlite3.OperationalError,'controlled real-source'):case.capture()
        self.assertFalse(case._final_captured);workspace.cleanup()
        self.assertTrue((directory/'authority.db').exists());self.assertTrue(workspace.capture_failed)
        failures=json.loads((Path(workspace.name)/'retention-failures.json').read_text())
        self.assertEqual(failures['failures'][0]['phase'],'capture')
        case.capture();self.assertTrue(case._final_captured);workspace.cleanup()
        self.assertTrue((directory/'authority.db').exists())
        records=[json.loads(p.read_text()) for p in sorted((self.case/'captures').rglob('capture.json'))]
        self.assertEqual([r['status'] for r in records],['failed','captured'])

    def test_successful_capture_then_close_failure_preserves_changed_raw_state(self):
        helper,case,workspace,directory=self.capture_parts();case.capture()
        snapshots=list((self.case/'captures').rglob('authority.db'));self.assertEqual(len(snapshots),1)
        class CloseMutatesThenFails:
            def close(self):
                with sqlite3.connect(directory/'authority.db') as db:db.execute('UPDATE proof SET value=2')
                raise RuntimeError('controlled post-capture close failure')
        with self.assertRaisesRegex(RuntimeError,'controlled post-capture'):helper.close_retaining(workspace,CloseMutatesThenFails())
        case.capture();workspace.cleanup()
        self.assertTrue((directory/'authority.db').exists())
        with sqlite3.connect(directory/'authority.db') as db:self.assertEqual(db.execute('SELECT value FROM proof').fetchone()[0],2)
        with sqlite3.connect(snapshots[0]) as db:self.assertEqual(db.execute('SELECT value FROM proof').fetchone()[0],1)
        failure=json.loads((Path(workspace.name)/'retention-failures.json').read_text())
        self.assertEqual(failure['failures'][0]['phase'],'runtime-close')
