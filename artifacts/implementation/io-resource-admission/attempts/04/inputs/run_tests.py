"""Freeze copied inputs before exercising original Journal/Registry with synthetic I/O contracts."""
from datetime import datetime, timezone
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

def record(path, root):
    value = path.read_bytes()
    return {'path': str(path.relative_to(root)), 'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}

def package_pins():
    pins = []
    for name in ('jsonschema', 'attrs', 'referencing', 'rpds-py', 'jsonschema-specifications'):
        distribution = importlib.metadata.distribution(name)
        files = []
        for item in sorted(distribution.files or [], key=str):
            path = Path(distribution.locate_file(item)).resolve()
            if path.is_file() and path.suffix != '.pyc':
                data = path.read_bytes()
                files.append({'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        pins.append({'name': name, 'version': distribution.version, 'files': files})
    return pins

if __name__ == '__main__':
    attempts = HERE / 'attempts'; attempts.mkdir(exist_ok=True)
    attempt = attempts / ('%02d' % (len(list(attempts.iterdir())) + 1)); attempt.mkdir()
    paths = sorted([*HERE.glob('staged/**/*.py'), *HERE.glob('staged/**/*.json'),
                    HERE / 'baseline/hms/registry.py', HERE / 'baseline/research/protocols/wot-artifacts/td-schema-1.1.json', HERE / 'io_fixtures.py',
                    HERE / 'test_io_resource_admission.py', Path(__file__)])
    before = [record(path, HERE) for path in paths]
    for path in paths:
        destination = attempt / 'inputs' / path.relative_to(HERE)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())
    (attempt / 'before.json').write_text(json.dumps(before, indent=2) + '\n')
    packages_before = package_pins()
    (attempt / 'packages-before.json').write_text(json.dumps(packages_before, indent=2) + '\n')
    sys.path[:0] = [str(attempt / 'inputs/staged'), str(attempt / 'inputs')]
    started, clock = datetime.now(timezone.utc).isoformat(), time.monotonic()
    stream = io.StringIO(); result = None; error = None
    try:
        spec = importlib.util.spec_from_file_location('test_io_resource_admission', attempt / 'inputs/test_io_resource_admission.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        module.EVIDENCE_DIRECTORY = attempt / 'evidence'; module.EVIDENCE_DIRECTORY.mkdir()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
    except BaseException:
        import traceback
        error = traceback.format_exc(); stream.write(error)
    (attempt / 'tests.txt').write_text(stream.getvalue())
    after = [record(path, HERE) for path in paths]
    packages_after = package_pins()
    (attempt / 'after.json').write_text(json.dumps(after, indent=2) + '\n')
    (attempt / 'packages-after.json').write_text(json.dumps(packages_after, indent=2) + '\n')
    imports = {name: str(Path(value.__file__).resolve()) for name, value in sys.modules.items()
               if name.startswith('hms') and getattr(value, '__file__', None)}
    scoped = bool(imports) and all(str(attempt / 'inputs/staged') + '/' in path or
        (name == 'hms.retained_original_registry' and path == str(attempt / 'inputs/baseline/hms/registry.py'))
        for name, path in imports.items())
    forbidden = sorted(name for name in imports if name in {'hms.runtime', 'hms.adapters', 'hms.endpoint_binding', 'hms.pat_simulation_worker'})
    passed = bool(result is not None and result.wasSuccessful() and not result.skipped and not result.expectedFailures
                  and before == after and packages_before == packages_after and scoped and not forbidden and error is None)
    evidence = [record(path, attempt) for path in sorted((attempt / 'evidence').rglob('*')) if path.is_file()] if (attempt / 'evidence').exists() else []
    receipt = {'schema': 'hms-staged-resource-admission-tests/1', 'startedUtc': started, 'seconds': time.monotonic() - clock,
        'tests': result.testsRun if result else 0, 'failures': len(result.failures) if result else 0,
        'errors': len(result.errors) if result else 0, 'skips': len(result.skipped) if result else 0,
        'expectedFailures': len(result.expectedFailures) if result else 0,
        'unexpectedSuccesses': len(result.unexpectedSuccesses) if result else 0, 'loaderError': error,
        'inputCount': len(before), 'inputsUnchanged': before == after, 'packagesUnchanged': packages_before == packages_after,
        'importsScopedToSnapshots': scoped, 'imports': imports, 'forbiddenImports': forbidden, 'passed': passed,
        'evidence': evidence,
        'limits': ['Original copied Journal/Registry SQLite admission/recheck with original synthetic I/O contracts.',
                   'Trusted installed-support fixture only; no executable provider or Runtime mounting.',
                   'No hardware, model, physical driver effect, acquired controller or public lifecycle execution.',
                   'Configuration publication is not an admitted physical lifecycle operation.']}
    (attempt / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(stream.getvalue())
    print(json.dumps({key: receipt[key] for key in ('tests', 'failures', 'errors', 'inputCount', 'inputsUnchanged', 'passed')}))
    raise SystemExit(0 if passed else 1)
