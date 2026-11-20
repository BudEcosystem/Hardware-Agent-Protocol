"""Prepared isolated runner. Do not execute until the source review is complete."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

LIMITS = {'cpuSeconds': 30, 'addressSpaceBytes': 512 * 1024 * 1024,
          'fileBytes': 1024 * 1024, 'openFiles': 64, 'coreBytes': 0}
APPLIED_LIMITS = {}
for name, kind in (('cpuSeconds', resource.RLIMIT_CPU), ('addressSpaceBytes', resource.RLIMIT_AS),
                   ('fileBytes', resource.RLIMIT_FSIZE), ('openFiles', resource.RLIMIT_NOFILE),
                   ('coreBytes', resource.RLIMIT_CORE)):
    ceiling = LIMITS[name]
    _soft, hard = resource.getrlimit(kind)
    selected = ceiling if hard == resource.RLIM_INFINITY else min(ceiling, hard)
    resource.setrlimit(kind, (selected, selected))
    APPLIED_LIMITS[name] = list(resource.getrlimit(kind))

# The package initializer is inert. Verify file pins before importing any HMS code.
from intent_handoff.integrity import verify
verify()
sys.path.insert(0, str(ROOT / 'dependencies'))


def source_pins():
    paths = {ROOT / 'run_tests.py', ROOT / 'DEPENDENCIES.sha256'}
    for directory in ('intent_handoff', 'tests'):
        paths.update(path for path in (ROOT / directory).rglob('*')
                     if path.is_file() and '__pycache__' not in path.parts)
    for line in (ROOT / 'DEPENDENCIES.sha256').read_text().splitlines():
        paths.add(ROOT / line.split('  ', 1)[1])
    result = {}
    for path in sorted(paths):
        body = path.read_bytes()
        result[str(path.relative_to(ROOT))] = {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--reopen-child', type=Path)
    args = parser.parse_args()
    if args.reopen_child is not None:
        if args.output is not None:
            parser.error('child mode does not accept output')
        from intent_handoff.store import IntentStore
        store = IntentStore(args.reopen_child, owner='planning-owner', store_id='test-intent-store',
                            capacity={'maxRecords': 129, 'maxBytes': 8 * 1024 * 1024})
        try:
            print(json.dumps(store.request('planning-owner', 'intent_get', {'applicationId': 'application:fan'}), ensure_ascii=False))
        finally:
            store.close()
        return 0
    if args.output is None:
        parser.error('--output must name a new attempt directory')
    args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.environ['HMS_INTENT_TEST_ATTEMPT'] = str(args.output.resolve())
    sources = source_pins()
    (args.output / 'source-pins-before.json').write_text(json.dumps(sources, indent=2) + '\n')
    interpreter = Path(sys.executable).resolve()
    interpreter_hash = hashlib.sha256(interpreter.read_bytes()).hexdigest()
    start = time.monotonic()
    with (args.output / 'tests.log').open('x', encoding='utf-8') as log:
        suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern='test_*.py')
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    elapsed = time.monotonic() - start
    after = source_pins()
    (args.output / 'source-pins-after.json').write_text(json.dumps(after, indent=2) + '\n')
    stable = sources == after
    interpreter_after = hashlib.sha256(interpreter.read_bytes()).hexdigest()
    interpreter_stable = interpreter_hash == interpreter_after
    receipt = dict(profile='hms.intent-handoff-test-receipt/0.1', python=sys.version,
        platform=platform.platform(), testsRun=result.testsRun, failures=len(result.failures),
        errors=len(result.errors), successful=result.wasSuccessful() and stable and interpreter_stable,
        monotonicElapsedSeconds=elapsed, sourcePinsUnchanged=stable,
        requestedLimits=LIMITS, enforcedSoftHardLimits=APPLIED_LIMITS,
        interpreter=dict(path=str(interpreter), beforeSha256=interpreter_hash,
                         afterSha256=interpreter_after, unchanged=interpreter_stable),
        containment='finite per-process rlimits only; no hostile sandbox or aggregate child-tree claim',
        scope='isolated planning store and scripted-fixture tests; no learned or physical qualification',
        dependencyManifestSha256=hashlib.sha256((ROOT / 'DEPENDENCIES.sha256').read_bytes()).hexdigest())
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
    return 0 if result.wasSuccessful() and stable and interpreter_stable else 1


if __name__ == '__main__':
    raise SystemExit(main())
