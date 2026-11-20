"""Explicit controlled injections around exact retained05 runner.main."""
import importlib.util
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

config=json.loads(Path(sys.argv[1]).read_text()); case=Path(config['case']); stage=case/'stage'
sys.path.extend(config['externalRoots'])
spec=importlib.util.spec_from_file_location('retained_runner_under_test',stage/'run_attempt.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
original_popen=runner.subprocess.Popen; original_write=runner.write
owned=[]; injections=[]
mode=config['mode']


def interrupt(_signal,_frame):raise KeyboardInterrupt('controlled wrapper termination')
signal.signal(signal.SIGTERM,interrupt)


class WaitProxy:
    def __init__(self, process):self.process=process;self.first=True
    def __getattr__(self,name):return getattr(self.process,name)
    def wait(self,*args,**kwargs):
        if self.first and mode=='interrupt_wait':
            self.first=False;injections.append('KeyboardInterrupt after retained spawn')
            raise KeyboardInterrupt('controlled owned wait interruption')
        self.first=False
        result=self.process.wait(*args,**kwargs)
        path=stage/'attempts/probe/test-return.json'
        if mode=='missing_return':
            path.unlink(missing_ok=True);injections.append('removed child return only after child exit')
        elif mode=='malformed_return':
            path.write_text('{"testsRun": true}\n');injections.append('replaced child return only after child exit')
        return result


def spawn(command,**kwargs):
    if mode=='launch_failure':
        injections.append('OSError before actual Popen');raise OSError('controlled launch failure')
    if mode in {'timeout','kill_required','interrupt_wait'}:
        childmode='ignore_term' if mode=='kill_required' else 'wait'
        command=[sys.executable,'-I','-S','-B',config['childFixture'],childmode,str(case/'child-ready.json')]
    (case/'actual-child-command.json').write_text(json.dumps({'argv':command,'cwd':str(kwargs['cwd']),
        'environment':kwargs['env'],'injectionMode':mode},indent=2)+'\n')
    process=original_popen(command,**kwargs);owned.append(process)
    # Wait only for the original tiny child's explicit ready marker so signal
    # tests cannot pass because TERM arrived before the ignore handler existed.
    if mode in {'timeout','kill_required','interrupt_wait'}:
        end=time.monotonic()+5
        while not (case/'child-ready.json').exists() and process.poll() is None and time.monotonic()<end:time.sleep(0.01)
        if not (case/'child-ready.json').exists():raise RuntimeError('owned fixture did not become ready')
    return WaitProxy(process) if mode in {'interrupt_wait','missing_return','malformed_return'} else process


def controlled_write(path,value):
    if mode=='finalization_failure' and path.name=='inputs-after.json':
        injections.append('OSError during after-manifest write');raise OSError('controlled after-manifest failure')
    return original_write(path,value)


runner.subprocess.Popen=spawn;runner.write=controlled_write
sys.argv=[str(stage/'run_attempt.py'),'probe']+config['targets']+['--parent-released','--timeout-seconds',
          '1' if mode in {'timeout','kill_required'} else '60']
result=None;failure=None
try:result=runner.main()
except BaseException as exc:
    failure={'type':type(exc).__name__,'message':str(exc)};traceback.print_exc()
finally:
    cleanup=[]
    for process in owned:
        state={'pid':process.pid,'returnCodeBeforeEmergencyCleanup':process.poll(),'emergencyCleanupNeeded':process.poll() is None}
        if process.poll() is None:
            # Only this wrapper's retained actual Popen; never a recovered PID.
            try:
                process.terminate();process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=5)
        state['finalReturnCode']=process.poll();cleanup.append(state)
    (case/'wrapper-return.json').write_text(json.dumps({'runnerReturn':result,'exception':failure,
        'injections':injections,'ownedChildren':cleanup,'mode':mode},indent=2)+'\n')
raise SystemExit(result if type(result) is int else 2)
