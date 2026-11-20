"""Compose the frozen native harness and unchanged accounting observer."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = ROOT / 'artifacts/implementation/pat-native-supervisor/implementation02'
TEMPLATE = ROOT / 'artifacts/implementation/pat-native-supervisor/harness02'
HARNESS = BASE / 'harness01'
SOURCE_PIN = '255b919194d150572c7b7876d941fb2e7d5866e36cdc119e91608da4b85ddc18'
TEMPLATE_PIN = '6fd4be31a43dca75bfcda3fdb9f9e75dba5c19f57b879ef1a271b5650aa10930'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):
    return json.loads(path.read_bytes())
def put(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(body if type(body) is bytes else body.encode())
def dump(path, value):
    put(path, json.dumps(value, indent=2) + '\n')
def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)
assert not HARNESS.exists()
for folder, pin, prefix in [(SOURCE, SOURCE_PIN, ROOT), (TEMPLATE, TEMPLATE_PIN, TEMPLATE)]:
    assert sha(folder / 'index.json') == pin
    for row in read(folder / 'index.json')['files']:
        assert (prefix / row['path']).stat().st_size == row['bytes'] and sha(prefix / row['path']) == row['sha256']
observer = (BASE / 'observer.py').read_text()
borrowed = []
for name in ('run_attempt.py', 'attempt_child.py', 'targets.json', 'references/approved-external-roots.json'):
    source = TEMPLATE / name
    copied = 'references/original-' + source.name
    put(HARNESS / copied, source.read_bytes())
    borrowed.append(dict(source=str(source.relative_to(ROOT)), copy=copied, bytes=source.stat().st_size, sha256=sha(source)))
    old = source.read_text()
    new = old
    if name == 'run_attempt.py':
        new = replace(new, "stage = here.parent / 'implementation02'",
            "stage = here.parents[3] / 'artifacts/implementation/pat-native-supervisor/implementation02'")
        new = replace(new, "prefix='hms-native-supervisor-actual-'", "prefix='hms-native-worker-accounting-'")
    elif name == 'attempt_child.py':
        new = replace(new, 'current_test = None\nsqlite_connections = []',
            'current_test = None\naccounting_launch_audit = []\nsqlite_connections = []')
        needle = "        if not valid: prohibited.append(event); raise RuntimeError('Only exact owned I/O entry may launch')"
        new = replace(new, needle, needle + "\n        if accounting_launch_audit:\n            prohibited.append(event); raise RuntimeError('Diagnostic permits exactly one original worker launch')\n        accounting_launch_audit.append({'argv': list(argv), 'cwd': str(cwd), 'testId': current_test})")
        insertion = ('\n# BEGIN FROZEN HARNESS OBSERVER\n' + observer +
            "\nimport subprocess\nworker_accounting = _WorkerAccounting(persist=write)\nsubprocess.Popen = _observed_popen(subprocess.Popen, worker_accounting)\n# END FROZEN HARNESS OBSERVER\n")
        new = replace(new, '\ndef actual_origins():', insertion + '\ndef actual_origins():')
        new = replace(new, '            executed_ids.append(test.id())\n            super().startTest(test)',
            '            executed_ids.append(test.id())\n            worker_accounting.start_test(test.id())\n            super().startTest(test)')
        new = replace(new, '            super().stopTest(test)\n            current_test = None',
            '            super().stopTest(test)\n            worker_accounting.stop_test()\n            current_test = None')
        needle = "    finalize('sqlite-connections', lambda: write('sqlite-connections.json', sqlite_connections))"
        new = replace(new, needle, needle + "\n    finalize('accounting-launch-audit', lambda: write('worker-accounting-launch-audit.json', accounting_launch_audit))")
    if name.endswith('.py'):
        ast.parse(new)
        put(HARNESS / (name + '.patch'), ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
            fromfile='frozen-native/' + name, tofile='native-accounting/' + name)))
    put(HARNESS / name, new)
dump(HARNESS / 'borrowed-inputs.json', borrowed)
put(HARNESS / 'README.md', '# Native worker accounting\n\n[Scope](SCOPE.md). Project sources and the full original matrix remain unchanged. This harness adds observations only.\n')
put(HARNESS / 'SCOPE.md', '# Diagnostic scope\n\nThe exact 291-file native supervisor candidate runs its original thirty-case worker and authority-vault test. A harness observer records self/waited-child usage and bounded global pressure at the existing test/launch/reap boundaries. No extra wait, poll, signal, PID-based read, worker case or scheduling change is added. The prior native audit remains intact.\n\nOriginal bounds remain: 60-second worker, 180-second parent, six parent SQLite opens, 16 MiB file, 256 MiB retained scratch, 8192 files, 8 MiB log, five-second held snapshot and 15 MiB vault. No physical hardware, MCU, inference, external service or acquired controller code runs. Unknown case effects remain unknown; no interrupted case DB may be opened for recovery.\n\nGlobal pressure is context, not process attribution. Peak RSS is not additive. CPU observations do not establish a wait cause or deadline guarantee. Audit hooks remain cooperative controls rather than an OS sandbox.\n')
dump(BASE / 'preparation.json', dict(sourceIndexSha256=SOURCE_PIN, templateIndexSha256=TEMPLATE_PIN,
    observerSha256=sha(BASE / 'observer.py'), projectFilesChanged=0, projectFiles=291,
    originalMatrixCases=30, workerMaxWallMs=60000, parentMaxSeconds=180,
    composedHarnessExecuted=False, controlsPending=True))
print(json.dumps(dict(status='prepared-unexecuted', sourceIndexSha256=SOURCE_PIN)))
