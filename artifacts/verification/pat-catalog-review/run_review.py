"""Run original catalog review tests into a new, never-overwritten receipt lane."""
import datetime
import hashlib
import io
import json
from pathlib import Path
import platform
import re
import sys
import time
import unittest


ROOT = Path(__file__).resolve().parents[3]
LANE = Path(__file__).resolve().parent


def main():
    if len(sys.argv) != 2 or re.fullmatch(r'attempt-[0-9]{3}', sys.argv[1]) is None:
        raise SystemExit('usage: python3 -B run_review.py attempt-NNN (new directory only)')
    output = LANE / sys.argv[1]
    output.mkdir(exist_ok=False)
    sys.path[:0] = [str(ROOT / 'tests'), str(ROOT)]
    import test_pat_catalog_review as review
    paths = sorted({Path(module.__file__).resolve() for name, module in sys.modules.items()
        if (name.startswith('hms') or name == 'test_pat_catalog_review')
        and getattr(module, '__file__', None)})

    def pins():
        return {str(path.relative_to(ROOT)): {
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}
            for path in paths}

    before = pins()
    for path in paths:
        target = output / 'inputs' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    (output / 'source-before.json').write_text(json.dumps(before, indent=2, sort_keys=True) + '\n')
    stream = io.StringIO()
    started = time.monotonic()
    run = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(review))
    elapsed = time.monotonic() - started
    after = pins()
    (output / 'test.log').write_text(stream.getvalue())
    (output / 'source-after.json').write_text(json.dumps(after, indent=2, sort_keys=True) + '\n')
    report = {'schema': 'hms-pat-catalog-independent-run/1',
        'recordedAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'success': run.wasSuccessful(), 'tests': run.testsRun, 'failures': len(run.failures),
        'errors': len(run.errors), 'skipped': len(run.skipped), 'seconds': elapsed,
        'python': sys.version, 'platform': platform.platform(),
        'sourceUnchanged': before == after, 'trace': review.LAST_REPORT}
    (output / 'run.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(stream.getvalue())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if run.wasSuccessful() and before == after else 1


if __name__ == '__main__':
    raise SystemExit(main())
