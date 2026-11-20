"""Retain copied-current-source resource admission tests, including failing proof."""
from datetime import datetime, timezone
import argparse
import hashlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import traceback
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BEFORE_METHODS = (
    'test_stored_resource_documents_are_bounded_before_materialization',
    'test_stored_resource_metadata_is_typed_and_bounded_before_materialization',
    'test_catalog_history_bounds_its_retained_binding_reads',
    'test_resource_requirements_are_bounded_in_catalog_and_policy',
    'test_resource_requirement_inventory_has_exact_bounded_cardinality',
)


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('before', 'after'))
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('resource_admission_input_inventory', ROOT / 'scripts/check_runtime.py')
    inventory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inventory)
    def paths():
        return sorted(set(inventory.input_paths(ROOT)) | {Path(__file__).resolve()} |
                      set(ROOT.glob('tests/fixtures/**/*.json')))
    started = datetime.now(timezone.utc)
    attempt = HERE / 'attempts' / (started.strftime('%Y%m%dT%H%M%S.%fZ') + '-' + args.phase + '-' + uuid.uuid4().hex[:12])
    attempt.mkdir(parents=True)
    def capture(phase):
        records = []
        for path in paths():
            relative = path.relative_to(ROOT)
            data = path.read_bytes()
            target = attempt / phase / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data)
            records.append({'path': str(relative), 'bytes': len(data),
                'sha256': hashlib.sha256(data).hexdigest(), 'snapshot': str(target.relative_to(attempt))})
        write(attempt / (phase + '-inputs.json'), records)
        return records
    before = capture('before')
    copied = attempt / 'before'
    # No installed HMS package or current working directory may supply the SUT.
    sys.path[:] = [str(copied), str(copied / 'tests'), *[item for item in sys.path
        if item and Path(item).resolve() not in {ROOT, ROOT / 'tests'}]]
    stream = io.StringIO()
    result = module = compiler_before = compiler_after = None
    failure = None
    clock = time.monotonic()
    try:
        from hms.pat_compiler import compiler_digest, compiler_manifest, _identity
        compiler_before = {'digest': compiler_digest(), 'manifest': compiler_manifest(), 'current': _identity()}
        write(attempt / 'compiler-before.json', compiler_before)
        module = importlib.import_module('test_io_resource_admission')
        if Path(module.__file__).resolve() != copied / 'tests/test_io_resource_admission.py':
            raise AssertionError('test module imported outside retained current-source copy')
        module.EVIDENCE_DIRECTORY = attempt / 'evidence'
        module.EVIDENCE_DIRECTORY.mkdir()
        if args.phase == 'before':
            suite = unittest.TestSuite(module.IoResourceAdmissionTests(name) for name in BEFORE_METHODS)
        else:
            suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        compiler_after = {'digest': compiler_digest(), 'manifest': compiler_manifest(), 'current': _identity()}
        write(attempt / 'compiler-after.json', compiler_after)
    except BaseException:
        failure = traceback.format_exc()
        stream.write(failure)
    finally:
        (attempt / 'tests.txt').write_text(stream.getvalue())
        if module is not None:
            write(attempt / 'storage-probes.json', module.STORAGE_PROBES)
        after = capture('after')
        imports = {name: str(Path(value.__file__).resolve()) for name, value in sys.modules.items()
            if (name == 'hms' or name.startswith('hms.')) and getattr(value, '__file__', None)}
        historical = copied / 'tests/fixtures/registry-before-resource-roots/hms/registry.py'
        scoped = bool(imports) and all(Path(path).is_relative_to(copied / 'hms') or
            (name == 'hms.retained_original_registry' and Path(path) == historical) for name, path in imports.items())
        write(attempt / 'imports.json', imports)
        def comparable(records):
            return [{key: value for key, value in row.items() if key != 'snapshot'} for row in records]
        stable = comparable(before) == comparable(after)
        compiler_stable = (compiler_before is not None and compiler_before == compiler_after and
                           compiler_before['manifest'] == compiler_before['current'])
        forbidden = sorted(set(imports) & {'hms.runtime', 'hms.endpoint_binding', 'hms.pat_simulation_worker'})
        report = {'schema': 'hms-resource-admission-live-focused/1', 'phase': args.phase,
            'startedUtc': started.isoformat(), 'seconds': time.monotonic() - clock,
            'tests': result.testsRun if result else 0, 'failures': len(result.failures) if result else 0,
            'errors': len(result.errors) if result else 0, 'skips': len(result.skipped) if result else 0,
            'expectedFailures': len(result.expectedFailures) if result else 0,
            'unexpectedSuccesses': len(result.unexpectedSuccesses) if result else 0,
            'inputCount': len(before), 'inputsUnchanged': stable, 'compilerStable': compiler_stable,
            'importsScoped': scoped, 'forbiddenImports': forbidden, 'runnerError': failure,
            'passed': bool(result and result.wasSuccessful() and not result.skipped and not result.expectedFailures
                and stable and compiler_stable and scoped and not forbidden and failure is None),
            'limits': ['Original Journal/Registry admission and synthetic contracts only; no provider or Runtime mounting.',
                'Before-phase failures are retained as failures, not relabelled passing qualification.',
                'Historical fixture executes exact pinned original Registry source with current Python dependencies.',
                'Fixed-clock transitions do not establish native-clock latency or physical behavior.']}
        write(attempt / 'result.json', report)
    print(stream.getvalue())
    print(json.dumps({'attempt': str(attempt.relative_to(ROOT)), **report}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
