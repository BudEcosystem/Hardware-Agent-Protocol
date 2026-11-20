"""Original copied-source harness; parent release is required before invocation."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import _sqlite3

PACKAGES = ('jsonschema','referencing','jsonschema-specifications','attrs','rpds-py','typing_extensions','idna')
ALLOWED_TARGETS = {'test_io_lifecycle','test_io_synthetic_provider','test_io_api_contracts',
                   'test_resource_topology','test_io_resource_admission','test_registry_review','test_journal'}


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            value.update(block)
    return value.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value,indent=2)+'\n')


def files(directory):
    rows = []
    for path in sorted(directory.rglob('*')):
        if '__pycache__' in path.parts:
            continue
        if path.is_symlink():
            rows.append({'path':str(path.relative_to(directory)),'kind':'symlink','target':os.readlink(path)})
        elif path.is_file():
            rows.append({'path':str(path.relative_to(directory)),'kind':'file','bytes':path.stat().st_size,'sha256':sha(path)})
    return rows


def external_inputs():
    rows, roots = [], set()
    for package in PACKAGES:
        distribution = importlib.metadata.distribution(package)
        roots.add(str(Path(distribution.locate_file('')).resolve()))
        for item in sorted(distribution.files or [],key=str):
            if item.is_absolute() or '..' in item.parts or '__pycache__' in item.parts:
                continue
            path = Path(distribution.locate_file(item)).resolve()
            if path.is_file():
                rows.append({'package':package,'version':distribution.version,'path':str(item),
                    'resolvedPath':str(path),'bytes':path.stat().st_size,'sha256':sha(path)})
    for label,path in [('python',Path(sys.executable)),('sqlite-extension',Path(_sqlite3.__file__))]:
        rows.append({'runtime':label,'path':str(path),'resolvedPath':str(path.resolve()),
                     'bytes':path.stat().st_size,'sha256':sha(path)})
    return rows, sorted(roots)


def stop_owned(process, record, grace=5):
    """Only the retained direct child; never discover or signal a PID by name."""
    if process is None:
        record['childState'] = 'not_started'; return
    record['pid'] = process.pid
    if process.poll() is None:
        for action in ('terminate','kill'):
            try:
                getattr(process,action)(); record.setdefault('signalsAttempted',[]).append(action)
                process.wait(timeout=grace)
                break
            except subprocess.TimeoutExpired:
                continue
            except ProcessLookupError:
                break
            except BaseException as exc:
                record.setdefault('cleanupErrors',[]).append({'type':type(exc).__name__,'message':str(exc)[:2048]})
    record['exitCode'] = process.poll()
    record['childState'] = 'exited' if process.returncode is not None else 'termination_unconfirmed'


def valid_counts(value):
    names = {'testsRun','failures','errors','skips','expectedFailures','unexpectedSuccesses'}
    return (type(value) is dict and set(value)==names and all(type(value[k]) is int and value[k]>=0 for k in names)
            and value['testsRun']>0 and all(value[k]==0 for k in names-{'testsRun'}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('attempt'); parser.add_argument('--parent-released',action='store_true')
    parser.add_argument('--source-snapshot',choices=['01','02'])
    parser.add_argument('--timeout-seconds',type=int,default=600)
    parser.add_argument('targets',nargs='*'); args=parser.parse_args()
    if not args.parent_released:
        raise SystemExit('No execution: parent shared-freeze release must be explicit.')
    if not args.attempt.replace('-','').replace('_','').isalnum() or not 1<=args.timeout_seconds<=1800:
        raise SystemExit('Invalid attempt name or harness timeout')
    targets=args.targets or ['test_io_lifecycle']
    if any(name.split('.')[0] not in ALLOWED_TARGETS for name in targets):
        raise SystemExit('Target outside approved pure/SQLite module inventory')
    stage=Path(__file__).resolve().parent; attempt=stage/'attempts'/args.attempt
    attempt.mkdir(parents=True,exist_ok=False)
    record={'profile':'hms.lifecycle-staged-attempt/2','attempt':args.attempt,'sourceSnapshot':args.source_snapshot,
        'targets':targets,'status':'preparing','currentPass':False,'counts':None,'exitCode':None,
        'inputsUnchanged':None,'externalInputsUnchanged':None,'runnerUnchanged':None,
        'timeoutSeconds':args.timeout_seconds,'childState':'not_started','errors':[],
        'scope':'Original controlled-clock SQLite lifecycle/ordinary-provider code in copies; no native endpoints, OS driver effects, models or hardware.',
        'limits':['Selected distribution/interpreter/extension inputs and actual imported origins are not a whole-host closure.',
                  'No physical/native-clock availability proof, hard SQLite bound, hard disk quota, or OS sandbox.',
                  'Catchable failures attempt finalization; SIGKILL/host loss/full storage can prevent receipts.',
                  'Lifecycle public result profile and mounting remain unsupported.']}
    process=None; before=external_before=None; started=time.monotonic(); tree=attempt/'project'
    write(attempt/'started.json',record)
    try:
        write(attempt/'parent-runtime.json',{'executable':sys.executable,'version':sys.version,
            'flags':repr(sys.flags),'path':sys.path,'cwd':str(Path.cwd()),'sqliteVersion':_sqlite3.sqlite_version,
            'scope':'Trusted launcher metadata; inherited environment values are not dumped.'})
        for name in ('run_attempt.py','attempt_child.py'):
            shutil.copyfile(stage/name,attempt/name)
        record['runnerSha256']=sha(attempt/'run_attempt.py'); record['childScriptSha256']=sha(attempt/'attempt_child.py')
        shutil.copytree(stage/'project',tree)
        if args.source_snapshot:
            frozen=stage/'review-inputs'/args.source_snapshot
            rows=json.loads((frozen/'manifest.json').read_text())['files']
            for row in rows:
                if row['path'].startswith('hms/'):
                    source=frozen/'project'/row['path']
                    if sha(source)!=row['sha256']:raise ValueError('Frozen source snapshot changed')
                    shutil.copyfile(source,tree/row['path'])
        before=files(tree); external_before,roots=external_inputs()
        if any(row['kind']!='file' for row in before):raise ValueError('Source symlinks are unsupported')
        write(attempt/'inputs-before.json',before); write(attempt/'external-before.json',external_before)
        for name in ('evidence','scratch'):(attempt/name).mkdir(mode=0o700,parents=True,exist_ok=True)
        environment={'PATH':os.pathsep.join((str(Path(sys.executable).parent),'/usr/bin','/bin')),
                     'TMPDIR':str(attempt/'scratch'),'LC_ALL':'C.UTF-8','TZ':'UTC'}
        config={'project':str(tree),'attempt':str(attempt),'targets':targets,'externalRoots':roots,
                'expectedInputs':before,'expectedExternalInputs':external_before}
        write(attempt/'child-config.json',config); write(attempt/'environment.json',environment)
        command=[sys.executable,'-I','-S','-B',str(attempt/'attempt_child.py'),str(attempt/'child-config.json')]
        write(attempt/'command.json',{'argv':command,'cwd':str(tree),'environment':environment})
        record['status']='launching'; write(attempt/'launch.json',record)
        with (attempt/'output.log').open('xb') as log:
            process=subprocess.Popen(command,cwd=tree,env=environment,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            # Retain ownership before any file write or later operation can fail.
            record['pid']=process.pid; record['childState']='running'; write(attempt/'owned-child.json',{'pid':process.pid,'ownedByThisAttempt':True})
            record['status']='running'
            try:record['exitCode']=process.wait(timeout=args.timeout_seconds)
            except subprocess.TimeoutExpired:
                record['status']='timed_out'; raise
    except BaseException as exc:
        if record['status']!='timed_out':record['status']='interrupted' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'failed'
        record['errors'].append({'phase':record['status'],'type':type(exc).__name__,'message':str(exc)[:4096]})
        try:(attempt/'runner-error.txt').write_text(traceback.format_exc())
        except BaseException:pass
    finally:
        try:stop_owned(process,record)
        except BaseException as exc:
            record['childState']='termination_unconfirmed' if process is not None else 'not_started'
            record['errors'].append({'phase':'owned-child-cleanup','type':type(exc).__name__,'message':str(exc)[:4096]})
        record['elapsedSeconds']=time.monotonic()-started
        def finalize(label,fn):
            try:fn()
            except BaseException as exc:record['errors'].append({'phase':label,'type':type(exc).__name__,'message':str(exc)[:4096]})
        def after_inputs():
            if before is None:return
            after=files(tree); write(attempt/'inputs-after.json',after)
            record.update(inputCount=len(before),inputsUnchanged=before==after)
        def after_external():
            if external_before is None:return
            after,_=external_inputs(); write(attempt/'external-after.json',after)
            record.update(externalInputCount=len(external_before),externalInputsUnchanged=external_before==after)
        def outputs():
            for name in ('evidence','scratch'):
                if (attempt/name).exists():
                    rows=files(attempt/name); write(attempt/(name+'-index.json'),rows); record[name+'Files']=len(rows)
        def counts():
            if (attempt/'test-return.json').exists():record['counts']=json.loads((attempt/'test-return.json').read_text())
            if (attempt/'imports.json').exists():record['importReceipt']=json.loads((attempt/'imports.json').read_text())
        def own_sources():
            record['runnerUnchanged']=(sha(Path(__file__))==sha(attempt/'run_attempt.py') and sha(stage/'attempt_child.py')==sha(attempt/'attempt_child.py'))
        for label,fn in [('inputs-after',after_inputs),('external-after',after_external),('retained-outputs',outputs),('child-receipts',counts),('runner-stability',own_sources)]:finalize(label,fn)
        imported=record.get('importReceipt',{})
        record['currentPass']=(record['exitCode']==0 and record['childState']=='exited' and not record['errors'] and
            valid_counts(record['counts']) and record['inputsUnchanged'] is True and record['externalInputsUnchanged'] is True and
            record['runnerUnchanged'] is True and imported.get('complete') is True and imported.get('allProjectOriginsMatched') is True)
        if record['currentPass']:record['status']='passed'
        elif record['status'] in {'running','launching','preparing'}:record['status']='failed'
        try:write(attempt/'result.json',record)
        except BaseException as exc:
            record['currentPass']=False;print('Final result write failed:',type(exc).__name__,str(exc),file=sys.stderr)
        print(json.dumps({k:record[k] for k in ('attempt','status','currentPass','counts','childState','errors')},indent=2))
    return 0 if record['currentPass'] else 1


if __name__=='__main__':raise SystemExit(main())
