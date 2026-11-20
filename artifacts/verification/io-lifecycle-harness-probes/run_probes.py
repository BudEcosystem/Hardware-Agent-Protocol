"""Outer source-copy/retention harness. Do not invoke before parent release."""
import sys
sys.dont_write_bytecode=True
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import traceback


def sha(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):result.update(chunk)
    return result.hexdigest()


def rows(root):
    return [{'path':str(p.relative_to(root)),'sha256':sha(p),'bytes':p.stat().st_size}
        for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]


def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('attempt');parser.add_argument('--parent-released',action='store_true')
    args=parser.parse_args()
    if not args.parent_released:raise SystemExit('No execution without explicit parent shared-freeze release')
    if not args.attempt.replace('-','').replace('_','').isalnum():raise SystemExit('Invalid unique attempt name')
    lane=Path(__file__).resolve().parent;out=lane/'attempts'/args.attempt;out.mkdir(parents=True,exist_ok=False)
    report={'profile':'hms.lifecycle-harness-probes-attempt/1','attempt':args.attempt,'status':'preparing',
        'passed':False,'counts':None,'inputsUnchanged':None,'externalInputsUnchanged':None,'exitCode':None,
        'childState':'not_started','errors':[],'scope':'Original controlled bookkeeping probes only; no lifecycle or public-I/O qualification.',
        'limits':['No OS sandbox or hard aggregate quota.','Controlled process and SQLite fixtures execute only after explicit release.',
            'Selected validation/Python/SQLite pins and actual origins are not full host/cache/shared-library closure.',
            'SIGKILL, host loss, storage failure or OS-uninterruptible cleanup can prevent final receipts.']}
    save(out/'started.json',report);process=None;before=external_before=None;runner=None;started=time.monotonic()
    source=out/'source'
    try:
        shutil.copyfile(Path(__file__),out/'run_probes.py')
        source.mkdir();shutil.copytree(lane/'src',source/'src');shutil.copytree(lane/'retained05',source/'retained05')
        for name in ('README.md','source-preparation.json','manifest.json'):shutil.copyfile(lane/name,source/name)
        retained=json.loads((source/'retained05/manifest.json').read_text())
        for item in retained['files']:
            path=source/'retained05'/item['path']
            if sha(path)!=item['sha256']:raise ValueError('Retained05 input changed: '+item['path'])
        before=rows(source);save(out/'inputs-before.json',before)
        spec=importlib.util.spec_from_file_location('original05_metadata_functions',source/'retained05/run_attempt.py')
        runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        external_before,roots=runner.external_inputs();save(out/'external-before.json',external_before)
        (out/'scratch').mkdir()
        config={'source':str(source),'attempt':str(out),'externalRoots':roots};save(out/'child-config.json',config)
        environment={'PATH':os.pathsep.join((str(Path(sys.executable).parent),'/usr/bin','/bin')),
            'TMPDIR':str(out/'scratch'),'LC_ALL':'C.UTF-8','TZ':'UTC'}
        command=[sys.executable,'-I','-S','-B',str(source/'src/probe_entry.py'),str(out/'child-config.json')]
        save(out/'command.json',{'argv':command,'cwd':str(source),'environment':environment})
        report['status']='running'
        with (out/'output.log').open('xb') as log:
            process=subprocess.Popen(command,cwd=source,env=environment,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            report['pid']=process.pid;save(out/'owned-child.json',{'pid':process.pid,'scope':'Only retained direct probe-entry process'})
            report['exitCode']=process.wait(timeout=600)
    except BaseException as exc:
        report['status']='interrupted' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'failed'
        report['errors'].append({'type':type(exc).__name__,'message':str(exc)[:4096]})
        try:(out/'runner-error.txt').write_text(traceback.format_exc())
        except BaseException:pass
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=30)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
                report['exitCode']=process.poll();report['childState']='exited' if process.returncode is not None else 'termination_unconfirmed'
            except BaseException as exc:
                report['childState']='termination_unconfirmed';report['errors'].append({'phase':'cleanup','type':type(exc).__name__,'message':str(exc)[:4096]})
        def finalize(label,fn):
            try:fn()
            except BaseException as exc:report['errors'].append({'phase':label,'type':type(exc).__name__,'message':str(exc)[:4096]})
        def inputs_after():
            if before is None:return
            after=rows(source);save(out/'inputs-after.json',after);report['inputsUnchanged']=before==after
        def external_after():
            if external_before is None:return
            after,_=runner.external_inputs();save(out/'external-after.json',after);report['externalInputsUnchanged']=external_before==after
        def collect():
            if (out/'test-return.json').exists():report['counts']=json.loads((out/'test-return.json').read_text())
            if (out/'cases').exists():save(out/'case-index.json',{'files':rows(out/'cases'),'rawCaseTreesRetained':True})
            if (out/'scratch').exists():save(out/'scratch-index.json',{'files':rows(out/'scratch')})
        for label,fn in [('inputs-after',inputs_after),('external-after',external_after),('results-and-cases',collect)]:finalize(label,fn)
        counts=report['counts'];report['elapsedSeconds']=time.monotonic()-started
        report['passed']=(report['exitCode']==0 and report['childState']=='exited' and not report['errors'] and
            report['inputsUnchanged'] is True and report['externalInputsUnchanged'] is True and type(counts) is dict and
            type(counts.get('testsRun')) is int and counts['testsRun']>0 and all(type(counts.get(k)) is int and counts[k]==0 for k in
                ('failures','errors','skips','expectedFailures','unexpectedSuccesses')) and counts.get('entryErrors')==[])
        if report['passed']:report['status']='passed'
        elif report['status']=='running':report['status']='failed'
        try:save(out/'result.json',report)
        except BaseException as exc:
            report['passed']=False;print('Could not retain final result:',type(exc).__name__,str(exc),file=sys.stderr)
        print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
