"""Original bounded method probe against an exact pre-change Registry snapshot."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
SOURCE = Path(__file__).parent / 'sources/hms/registry.py'
EXPECTED = 'beda13e1ced09099f1d0f58f332ba088cbf0d18f13f64faa6a8520aa3393c11e'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == EXPECTED
spec = importlib.util.spec_from_file_location('hms._multi_route_registry_review', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

sampled = threading.Event()
release = threading.Event()
second_done = threading.Event()
results = {}

def clock():
    if threading.current_thread().name == 'older-sample':
        sampled.set()
        assert release.wait(3), 'bounded gate timed out'
        return 1000
    return 1100

registry = module.Registry.__new__(module.Registry)
registry.monotonic_ms = clock
registry._last_monotonic = 0
registry._monotonic_invalid = False
registry.journal = SimpleNamespace(_mutex=threading.RLock())

def worker(name):
    try:
        results[name] = {'value': registry._monotonic()}
    except Exception as error:
        results[name] = {'error': type(error).__name__, 'code': getattr(error, 'code', str(error))}
    finally:
        if name == 'newer':
            second_done.set()

older = threading.Thread(target=worker, args=('older',), name='older-sample')
newer = threading.Thread(target=worker, args=('newer',), name='newer-sample')
older.start()
assert sampled.wait(2), 'first sample never started'
newer.start()
newer_finished_before_older_release = second_done.wait(1)
release.set()
older.join(2)
newer.join(2)
assert not older.is_alive() and not newer.is_alive()
assert newer_finished_before_older_release
assert results['newer'] == {'value': 1100}
assert results['older']['code'] == 'CLOCK_MAPPING_INVALID'
assert registry._monotonic_invalid
print(json.dumps({
    'baselineSourceSha256': EXPECTED,
    'newerFinishedBeforeOlderRelease': newer_finished_before_older_release,
    'results': results,
    'stickyInvalidAfterReorderedCalls': registry._monotonic_invalid,
    'reproduced': True,
    'scope': 'Exact frozen Registry._monotonic method with bounded synthetic callback scheduling; no DB, device or full-runtime test.'
}, sort_keys=True))
