"""Retain provider tests on the prepared current baseline; run only after root release."""
from datetime import datetime, timezone
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import time
import traceback
import unittest
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TREE = HERE / 'tree'


def pin(path, base):
    data = path.read_bytes()
    return {'path': str(path.relative_to(base)), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    sys.dont_write_bytecode = True
    started = datetime.now(timezone.utc)
    attempt = HERE / 'attempts' / (started.strftime('%Y%m%dT%H%M%S.%fZ') + '-' + uuid.uuid4().hex[:12])
    attempt.mkdir(parents=True)
    sources = sorted(path for path in TREE.rglob('*') if path.is_file() and '__pycache__' not in path.parts)
    before = [pin(path, TREE) for path in sources]
    assert before == json.loads((HERE / 'prepared-inputs.json').read_text()), 'prepared source closure changed'
    project = attempt / 'inputs/project'
    for path in sources:
        target = project / path.relative_to(TREE)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(path.read_bytes())
    controller = Path(__file__).resolve()
    controller_before = pin(controller, HERE)
    (attempt / 'inputs/run.py').write_bytes(controller.read_bytes())
    write(attempt / 'inputs-before.json', before)
    sys.path[:] = [str(project), str(project / 'tests'), *[item for item in sys.path
        if item and Path(item).resolve() not in {ROOT, ROOT / 'tests', TREE, TREE / 'tests'}]]
    result = compiler_before = compiler_after = provider_before = provider_after = None
    failure = None
    stream = io.StringIO()
    clock = time.monotonic()
    try:
        from hms.pat_compiler import compiler_digest, compiler_manifest, _identity
        from hms.synthetic_io_installation import implementation_digest
        compiler_before = {'digest': compiler_digest(), 'manifest': compiler_manifest(), 'current': _identity()}
        provider_before = implementation_digest()
        write(attempt / 'compiler-before.json', compiler_before)
        write(attempt / 'provider-identity-before.json', {'digest': provider_before,
            'scope': 'Prepared provider project-source closure; no physical, binary or live-config attestation.'})
        module = importlib.import_module('test_io_synthetic_provider')
        assert Path(module.__file__).resolve() == project / 'tests/test_io_synthetic_provider.py'
        module.EVIDENCE_DIRECTORY = attempt / 'evidence'
        module.EVIDENCE_DIRECTORY.mkdir()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromModule(module))
        compiler_after = {'digest': compiler_digest(), 'manifest': compiler_manifest(), 'current': _identity()}
        provider_after = implementation_digest()
        write(attempt / 'compiler-after.json', compiler_after)
        write(attempt / 'provider-identity-after.json', {'digest': provider_after,
            'scope': 'Prepared provider project-source closure; no physical, binary or live-config attestation.'})
    except BaseException:
        failure = traceback.format_exc()
        stream.write(failure)
    finally:
        (attempt / 'tests.txt').write_text(stream.getvalue())
        after = [pin(path, TREE) for path in sorted(TREE.rglob('*'))
                 if path.is_file() and '__pycache__' not in path.parts]
        write(attempt / 'inputs-after.json', after)
        copied = [pin(path, project) for path in sorted(project.rglob('*'))
                  if path.is_file() and '__pycache__' not in path.parts]
        write(attempt / 'copied-inputs-after.json', copied)
        imports = {name: str(Path(value.__file__).resolve()) for name, value in sys.modules.items()
            if (name == 'hms' or name.startswith('hms.')) and getattr(value, '__file__', None)}
        scoped = bool(imports) and all(Path(path).is_relative_to(project / 'hms') for path in imports.values())
        forbidden = sorted(set(imports) & {'hms.endpoint_binding', 'hms.pat_simulation_worker'})
        write(attempt / 'imports.json', imports)
        evidence = [pin(path, attempt) for path in sorted((attempt / 'evidence').rglob('*')) if path.is_file()]
        stable = before == after == copied
        compiler_stable = compiler_before is not None and compiler_before == compiler_after and compiler_before['manifest'] == compiler_before['current']
        provider_stable = provider_before is not None and provider_before == provider_after
        controller_after = pin(controller, HERE)
        controller_stable = (controller_before == controller_after and
            hashlib.sha256((attempt / 'inputs/run.py').read_bytes()).hexdigest() == controller_before['sha256'])
        report = {'schema': 'hms-provider-current-baseline-tests/1', 'startedUtc': started.isoformat(),
            'seconds': time.monotonic() - clock, 'tests': result.testsRun if result else 0,
            'failures': len(result.failures) if result else 0, 'errors': len(result.errors) if result else 0,
            'skips': len(result.skipped) if result else 0, 'expectedFailures': len(result.expectedFailures) if result else 0,
            'unexpectedSuccesses': len(result.unexpectedSuccesses) if result else 0,
            'inputCount': len(before), 'inputsUnchanged': stable, 'compilerStable': compiler_stable,
            'providerIdentityStable': provider_stable, 'importsScoped': scoped, 'forbiddenImports': forbidden,
            'runnerError': failure, 'runner': controller_before, 'runnerAfter': controller_after,
            'runnerUnchanged': controller_stable, 'evidence': evidence,
            'passed': bool(result and result.wasSuccessful() and not result.skipped and not result.expectedFailures
                and stable and compiler_stable and provider_stable and controller_stable and scoped and not forbidden and failure is None),
            'limits': ['Prepared copy of current139-input baseline plus six reviewed provider modules; live sources unchanged.',
                'Original SQLite I/O model and controlled clocks only; no native endpoint, physical I/O or model execution.',
                'No stock Runtime/daemon/IPC/CLI/MCP mounting, PAT qualification or lifecycle-effect settlement.',
                'Host-fetch bounds do not establish SQLite internal memory/time or physical pulse timing.']}
        write(attempt / 'result.json', report)
    print(stream.getvalue())
    print(json.dumps({'attempt': str(attempt.relative_to(ROOT)), **{key: report[key] for key in
        ('tests','failures','errors','inputCount','inputsUnchanged','compilerStable','providerIdentityStable','passed')}}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
