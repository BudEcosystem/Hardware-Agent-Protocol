"""Retain focused live I/O integration evidence without changing full-suite pointers."""
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time
import traceback
import unittest
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]


def write(path, value):
    with path.open('x') as output:
        output.write(json.dumps(value, indent=2) + '\n')


def pin(path):
    data = path.read_bytes()
    return {'path': str(path.relative_to(ROOT)), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    started = datetime.now(timezone.utc)
    attempt = HERE / 'attempts' / (started.strftime('%Y%m%dT%H%M%S.%fZ') + '-' + uuid.uuid4().hex[:12])
    attempt.mkdir(parents=True)
    write(attempt / 'started.json', {'startedUtc': started.isoformat(), 'command': 'python3 -B ' + str(Path(__file__).relative_to(ROOT)),
          'scope': '37 selected live-source tests: 24 synthetic provider, 9 runtime profile, 4 actual CLI/UDS/MCP transport; not a full-suite result.'})
    from scripts.check_runtime import capture_inputs, input_paths, compiler_identity, environment, retained_failures
    paths = lambda root: [*input_paths(root), Path(__file__).resolve()]
    before, before_errors = capture_inputs(ROOT, attempt, 'inputs-before', paths)
    write(attempt / 'inputs-before.json', before)
    result = None
    compiler_before = compiler_after = provider_before = provider_after = None
    runner_errors = []
    clock = time.monotonic()
    modules = []
    reports = {}
    log = (attempt / 'tests.txt').open('x')
    class Tee:
        def write(self, data):
            log.write(data); log.flush(); sys.stdout.write(data); sys.stdout.flush()
        def flush(self):
            log.flush(); sys.stdout.flush()
    try:
        if before_errors:
            raise RuntimeError(repr(before_errors))
        compiler_before = compiler_identity()
        from hms.synthetic_io_installation import implementation_digest
        provider_before = implementation_digest()
        write(attempt / 'compiler-before.json', compiler_before)
        write(attempt / 'provider-before.json', {'digest': provider_before})
        modules = [importlib.import_module(name) for name in
                   ('test_io_synthetic_provider', 'test_runtime_profiles', 'test_io_transport')]
        modules[0].EVIDENCE_DIRECTORY = attempt / 'provider-evidence'
        modules[0].EVIDENCE_DIRECTORY.mkdir()
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(module) for module in modules)
        assert suite.countTestCases() == 37
        result = unittest.TextTestRunner(stream=Tee(), verbosity=2).run(suite)
    except BaseException:
        runner_errors.append(traceback.format_exc())
        Tee().write(runner_errors[-1])
    finally:
        try:
            compiler_after = compiler_identity()
            from hms.synthetic_io_installation import implementation_digest
            provider_after = implementation_digest()
            write(attempt / 'compiler-after.json', compiler_after)
            write(attempt / 'provider-after.json', {'digest': provider_after})
            for module in modules:
                if hasattr(module, 'LAST_REPORT'):
                    name = module.__name__ + '-report.json'
                    reports[name] = {'module_loaded': True, 'report': module.LAST_REPORT}
                    write(attempt / name, module.LAST_REPORT)
            retained_failures(ROOT, attempt, reports)
        except BaseException:
            runner_errors.append(traceback.format_exc())
            Tee().write(runner_errors[-1])
        log.close()
    after, after_errors = capture_inputs(ROOT, attempt, 'inputs-after', paths)
    write(attempt / 'inputs-after.json', after)
    before_map = {item['path']: item['sha256'] for item in before}
    after_map = {item['path']: item['sha256'] for item in after}
    stable = before_map == after_map and not before_errors and not after_errors
    compiler_stable = compiler_before is not None and compiler_before == compiler_after and compiler_before['import_matches_current']
    provider_stable = provider_before is not None and provider_before == provider_after
    outputs = [pin(path) for path in sorted(attempt.rglob('*')) if path.is_file() and
               not path.is_relative_to(attempt / 'inputs-before') and not path.is_relative_to(attempt / 'inputs-after')]
    report = {'schema': 'hms-live-io-integration-tests/1', 'startedUtc': started.isoformat(),
        'seconds': time.monotonic() - clock, 'environment': environment(),
        'tests': result.testsRun if result else 0, 'failures': len(result.failures) if result else 0,
        'errors': len(result.errors) if result else 0, 'skips': len(result.skipped) if result else 0,
        'expectedFailures': len(result.expectedFailures) if result else 0,
        'unexpectedSuccesses': len(result.unexpectedSuccesses) if result else 0,
        'failureDetails': [{'test': str(test), 'detail': detail} for test, detail in result.failures] if result else [],
        'errorDetails': [{'test': str(test), 'detail': detail} for test, detail in result.errors] if result else [],
        'inputs': len(before), 'inputsUnchanged': stable, 'inputCaptureErrors': before_errors + after_errors,
        'compilerStable': compiler_stable, 'providerStable': provider_stable, 'providerDigest': provider_before,
        'runnerErrors': runner_errors, 'outputs': outputs,
        'passed': bool(result and result.testsRun == 37 and result.wasSuccessful() and not result.skipped and
                       not result.expectedFailures and stable and compiler_stable and provider_stable and not runner_errors),
        'scope': 'Live source with original SQLite synthetic I/O and controlled virtual-clock unit cases plus real CLI/UDS/modern+legacy MCP processes.',
        'limitations': ['No physical port, target MCU/emulator, neural inference or acquired controller execution.',
                       'Host-driven simulated pulse state; no autonomous pulse, watchdog, stop-latency or physical timing guarantee.',
                       'No installed PAT I/O qualification or public driver/hub lifecycle implementation.',
                       'Before/after source hashes do not detect a transient change and restore; compiler closure is not whole-host attestation.']}
    write(attempt / 'result.json', report)
    print(json.dumps({'attempt': str(attempt.relative_to(ROOT)), **{key: report[key] for key in
          ('tests', 'failures', 'errors', 'skips', 'inputs', 'inputsUnchanged', 'compilerStable', 'providerStable', 'passed')}}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
