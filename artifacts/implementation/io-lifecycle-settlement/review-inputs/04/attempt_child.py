"""Original test child; isolated startup, scoped origin receipts, no child processes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import sysconfig
import traceback

config=json.loads(Path(sys.argv[1]).read_text())
root=Path(config['project']).resolve(); out=Path(config['attempt']).resolve()
# -I -S excludes environment-driven Python path, site hooks and user customization.
# These explicit selected package roots are not an OS sandbox.
sys.path[:0]=[str(root),str(root/'tests')]+config['externalRoots']
sys.dont_write_bytecode=True
executed=set(); resource_reads=set(); errors=[]; counts=None


def audit(event,args):
    if event.startswith('socket.') or event in {'subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn'}:
        raise RuntimeError('Staged lifecycle test forbids network and child-process use')
    if event=='exec':executed.add(args[0].co_filename)
    if event=='open' and isinstance(args[0],str):
        path=Path(args[0])
        if path.is_absolute() and any(path.is_relative_to(Path(base)) for base in config['externalRoots']):
            resource_reads.add(str(path))


sys.addaudithook(audit)


def write(name,value):
    (out/name).write_text(json.dumps(value,indent=2)+'\n')


def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def actual_origins():
    acquired={str((root/row['path']).resolve()):row['sha256'] for row in config['expectedInputs'] if row['kind']=='file'}
    external={row['resolvedPath']:row['sha256'] for row in config['expectedExternalInputs']}
    stdlib=Path(sysconfig.get_path('stdlib')).resolve()
    rows=[]; violations=[]; seen=set()
    def add(label,origin):
        if not isinstance(origin,str) or origin.startswith('<') or origin in {'built-in','frozen'}:
            rows.append({'source':label,'origin':str(origin),'kind':'interpreter_or_synthetic'});return
        path=Path(origin).resolve()
        if path.suffix=='.pyc':
            try:path=Path(importlib.util.source_from_cache(str(path))).resolve()
            except ValueError:pass
        key=(label,str(path))
        if key in seen:return
        seen.add(key)
        value={'source':label,'origin':str(path)}
        if not path.is_file():
            value['kind']='missing';violations.append(value.copy());rows.append(value);return
        value['sha256']=sha(path)
        if path.is_relative_to(root):
            value['kind']='project';value['matchesBefore']=acquired.get(str(path))==value['sha256']
            if not value['matchesBefore']:violations.append(value.copy())
        elif str(path) in external:
            value['kind']='selected_external';value['matchesBefore']=external[str(path)]==value['sha256']
            if not value['matchesBefore']:violations.append(value.copy())
        elif path==Path(__file__).resolve():value['kind']='retained_child_harness'
        elif path.is_relative_to(stdlib) and 'site-packages' not in path.parts and 'dist-packages' not in path.parts:
            value['kind']='stdlib_actual_file';value['preExecutionPin']=False
        else:
            value['kind']='unexpected_origin';violations.append(value.copy())
        rows.append(value)
    for name,module in sorted(sys.modules.items()):
        origin=getattr(module,'__file__',None)
        if origin is None:origin=getattr(getattr(module,'__spec__',None),'origin',None)
        if origin is not None:add('module:'+name,origin)
        if (name=='hms' or name.startswith('hms.') or name.startswith('test_') or name in {'io_evidence_capture','journal_support','sqlite_observer'}) and origin:
            if not Path(origin).resolve().is_relative_to(root):violations.append({'module':name,'origin':str(origin),'reason':'project_name_outside_copy'})
    for origin in sorted(executed):add('executed_code',origin)
    for origin in sorted(resource_reads):add('selected_external_read',origin)
    return {'profile':'hms.lifecycle-actual-origins/1','complete':True,'allProjectOriginsMatched':not violations,
            'records':rows,'violations':violations,'limits':'Actual file hashes are not a pre-execution pin of all stdlib/shared libraries; synthetic/frozen origins remain explicitly distinct.'}


try:
    write('child-runtime.json',{'executable':sys.executable,'version':sys.version,'flags':repr(sys.flags),
        'path':sys.path,'cwd':str(Path.cwd()),'environment':dict(os.environ),'stdlib':sysconfig.get_path('stdlib')})
    import unittest
    import test_io_lifecycle as lifecycle
    import test_io_synthetic_provider as ordinary
    import hms.journal
    if not Path(hms.journal.__file__).resolve().is_relative_to(root):raise RuntimeError('Journal origin outside copy')
    lifecycle.EVIDENCE_DIRECTORY=out/'evidence/lifecycle';lifecycle.EVIDENCE_DIRECTORY.mkdir()
    ordinary.EVIDENCE_DIRECTORY=out/'evidence/ordinary';ordinary.EVIDENCE_DIRECTORY.mkdir()
    tests=unittest.defaultTestLoader.loadTestsFromNames(config['targets'])
    result=unittest.TextTestRunner(verbosity=2).run(tests)
    counts={'testsRun':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'skips':len(result.skipped),'expectedFailures':len(result.expectedFailures),'unexpectedSuccesses':len(result.unexpectedSuccesses)}
except BaseException as exc:
    errors.append({'type':type(exc).__name__,'message':str(exc)[:4096]})
    traceback.print_exc()
finally:
    origins=None
    try:
        origins=actual_origins();write('imports.json',origins)
    except BaseException as exc:
        errors.append({'phase':'actual-origins','type':type(exc).__name__,'message':str(exc)[:4096]})
    if counts is not None:
        try:write('test-return.json',counts)
        except BaseException as exc:errors.append({'phase':'test-return','type':type(exc).__name__,'message':str(exc)[:4096]})
    try:write('child-errors.json',errors)
    except BaseException:pass
passed=(not errors and counts is not None and counts['testsRun']>0 and all(counts[k]==0 for k in counts if k!='testsRun')
        and origins is not None and origins['allProjectOriginsMatched'])
raise SystemExit(0 if passed else 1)
