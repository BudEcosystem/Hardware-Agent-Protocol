"""Bounded read-only inspection of retained original AVR objects; never execute them."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNNER = None


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def main():
    global RUNNER
    if sys.flags.optimize != 0:
        raise RuntimeError('Assertions must remain enabled')
    os.umask(0o077);sys.dont_write_bytecode = True
    if any((HERE/name).exists() for name in ('attempt01','RESULTS.json','RESULTS.json.new')):
        raise RuntimeError('Preserve the existing inspection attempt or receipt')
    pins = json.loads((HERE/'input-pins.json').read_bytes())
    for row in pins['files']:
        assert digest(ROOT/row['source']) == digest(HERE/row['copy']) == row['sha256']
    assert digest(HERE/'runner.py') == 'a3d6317bb0a4fe39eb884c9654dc558505b61b99ddda57b9f2ced4faaa2d7099'
    spec = importlib.util.spec_from_file_location('reviewed_object_inspection_runner',HERE/'runner.py')
    runner = importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    RUNNER = runner
    build = HERE/'attempt01';build.mkdir(mode=0o700)
    source_names = ['run_analysis.py','PLAN.md','input-pins.json']+[row['copy'] for row in pins['files']]
    assert len(source_names) == len(set(source_names))
    runner.SOURCE_PINS = {name:digest(HERE/name) for name in source_names}
    runner.BUILD = build;runner.PROJECT = build;runner.FINAL_DESTINATION = HERE/'RESULTS.json'
    report = dict(status='started',requested_checks_completed=False,commands=[],
        sources=runner.SOURCE_PINS,objectsExecuted=False,targetExecuted=False,
        scope='Pinned AVR nm/objdump inspect retained original object files under the sealed live-owner runner; no compiling, linking or object execution.')
    runner.FINAL_REPORT = report
    def interrupted(signum,_):
        raise RuntimeError('Object inspection interrupted '+str(signum))
    signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGTERM,interrupted)
    try:
        for name,pin in runner.SOURCE_PINS.items():
            target = build/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with (HERE/name).open('rb') as source,target.open('xb') as copied:
                shutil.copyfileobj(source,copied)
            assert digest(target) == pin
        runner.write_json(runner.FINAL_DESTINATION,report)
        runner.prepare_owner()
        for name,pin in pins['tools'].items():runner.pin_installed(name,pin)
        nm = next(name for name in pins['tools'] if name.endswith('/avr-nm'))
        objdump = next(name for name in pins['tools'] if name.endswith('/avr-objdump'))
        for name in ('standing','standing-fixture','endpoint','baseline-endpoint'):
            obj = build/'objects'/(name+'.o')
            runner.run([nm,'-S','--size-sort',obj],name+'-symbols')
            runner.run([objdump,'-dr',obj],name+'-disassembly')
        runner.run([objdump,'-s','-j','.rodata',build/'objects/standing-fixture.o'],'fixture-constant-bytes')
        report['requested_checks_completed'] = True
    except BaseException as error:
        report['error'] = type(error).__name__+': '+str(error)
    finally:
        previous = signal.pthread_sigmask(signal.SIG_BLOCK,runner.BLOCKED)
        try:
            runner.final_audit(report)
            report['original_inputs_unchanged'] = all(digest(ROOT/row['source']) == row['sha256'] for row in pins['files'])
            if not report['original_inputs_unchanged']:report['requested_checks_completed'] = False
            report['status'] = 'passed' if report['requested_checks_completed'] else 'failed'
            runner.write_json(runner.FINAL_DESTINATION,report)
        finally:
            try:
                signal.pthread_sigmask(signal.SIG_SETMASK,previous)
            except BaseException as error:
                runner.publish_terminal_failure(error)
                raise
    if not report['requested_checks_completed']:
        raise RuntimeError('Inspection failed; preserve attempt01 and RESULTS.json')
    print(json.dumps(dict(status=report['status'],commands=len(runner.commands),objectsExecuted=False)))


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        if RUNNER is not None and RUNNER.FINAL_REPORT is not None:
            RUNNER.FINAL_REPORT['status'] = 'failed'
            RUNNER.publish_terminal_failure(error)
        raise
