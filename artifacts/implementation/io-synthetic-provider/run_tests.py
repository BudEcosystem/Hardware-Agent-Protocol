"""Retain and run only copied original I/O provider tests after the root hold."""
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True

def pin(path,root):
    data = path.read_bytes()
    return {'path':str(path.relative_to(root)),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}

def packages():
    result = []
    for name in ('jsonschema','attrs','referencing','rpds-py','jsonschema-specifications'):
        distribution = importlib.metadata.distribution(name)
        files = []
        for item in sorted(distribution.files or [],key=str):
            path = Path(distribution.locate_file(item)).resolve()
            if path.is_file() and path.suffix != '.pyc':
                data = path.read_bytes(); files.append({'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        result.append({'name':name,'version':distribution.version,'files':files})
    return result

if __name__ == '__main__':
    attempts = HERE/'attempts'; attempts.mkdir(exist_ok=True)
    attempt = attempts/('%02d'%(len(list(attempts.iterdir()))+1)); attempt.mkdir()
    paths = sorted([*HERE.glob('staged/**/*.py'),*HERE.glob('staged/**/*.json'),
                    HERE/'test_io_synthetic_provider.py',HERE/'io_fixtures.py',Path(__file__)])
    before = [pin(path,HERE) for path in paths]
    for path in paths:
        target = attempt/'inputs'/path.relative_to(HERE); target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(path.read_bytes())
    (attempt/'before.json').write_text(json.dumps(before,indent=2)+'\n')
    before_packages = packages(); (attempt/'packages-before.json').write_text(json.dumps(before_packages,indent=2)+'\n')
    sys.path[:0] = [str(attempt/'inputs/staged'),str(attempt/'inputs')]
    stream = io.StringIO(); result = None; failure = None
    started,clock = datetime.now(timezone.utc).isoformat(),time.monotonic()
    try:
        spec = importlib.util.spec_from_file_location('test_io_synthetic_provider',attempt/'inputs/test_io_synthetic_provider.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        module.EVIDENCE_DIRECTORY = attempt/'evidence'; module.EVIDENCE_DIRECTORY.mkdir()
        result = unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
    except BaseException:
        import traceback
        failure = traceback.format_exc(); stream.write(failure)
    (attempt/'tests.txt').write_text(stream.getvalue())
    after = [pin(path,HERE) for path in paths]; after_packages = packages()
    (attempt/'after.json').write_text(json.dumps(after,indent=2)+'\n')
    (attempt/'packages-after.json').write_text(json.dumps(after_packages,indent=2)+'\n')
    imports = {name:str(Path(value.__file__).resolve()) for name,value in sys.modules.items()
               if name.startswith('hms') and getattr(value,'__file__',None)}
    scoped = bool(imports) and all(path.startswith(str(attempt/'inputs/staged')+'/') for path in imports.values())
    forbidden = sorted(name for name in imports if name in {'hms.endpoint_binding','hms.pat_simulation_worker'})
    passed = bool(result is not None and result.wasSuccessful() and not result.skipped and not result.expectedFailures
        and before == after and before_packages == after_packages and scoped and not forbidden and failure is None)
    evidence = [pin(path,attempt) for path in sorted((attempt/'evidence').rglob('*')) if path.is_file()] if (attempt/'evidence').exists() else []
    receipt = {'schema':'hms-staged-synthetic-io-tests/1','startedUtc':started,'seconds':time.monotonic()-clock,
        'tests':result.testsRun if result else 0,'failures':len(result.failures) if result else 0,'errors':len(result.errors) if result else 0,
        'skips':len(result.skipped) if result else 0,'expectedFailures':len(result.expectedFailures) if result else 0,
        'unexpectedSuccesses':len(result.unexpectedSuccesses) if result else 0,'loaderError':failure,
        'inputCount':len(before),'inputsUnchanged':before == after,'packagesUnchanged':before_packages == after_packages,
        'importsScopedToSnapshots':scoped,'imports':imports,'forbiddenImports':forbidden,'passed':passed,'evidence':evidence,
        'limits':['Original staged IoRuntime with copied Journal/Registry/Runtime scheduler and shared SQLite board only.',
                  'Controlled wall/monotonic clocks; no native-clock availability or physical/electrical timing evidence.',
                  'No physical hardware, OS driver, model, acquired controller or subprocess execution.',
                  'Service/driver lifecycle execution and receipt-gated generation publication remain unsupported.']}
    (attempt/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(stream.getvalue())
    print(json.dumps({key:receipt[key] for key in ('tests','failures','errors','inputCount','inputsUnchanged','passed')}))
    raise SystemExit(0 if passed else 1)
