"""Adversarial checks of exact embedded guard AST with an owned sealed image."""
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat

BASE = Path(__file__).resolve().parent
ROOT = BASE / 'implementation02/project'
text = (BASE / 'harness02/attempt_child.py').read_text()
module = ast.parse(text)
names = {'native_load', 'native_image', 'native_scans', 'NATIVE_DIGEST'}
nodes = [node for node in module.body if
    isinstance(node, ast.FunctionDef) and node.name in ('verify_native_image', 'native_boundary') or
    isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in names for target in node.targets)]
assert len(nodes) == 6
code = compile(ast.Module(body=nodes, type_ignores=[]), '<retained-native-guard>', 'exec')
artifact = ROOT / 'supervisor/retention_scan.so'
digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
scratch = Path('/tmp/hms-guard-pure-path-no-files-created')
expected = scratch / 'test_actual_original_matrix_import_and_cold_vault_history/supervisor'
target = 'test_vault_original_run.VaultOriginalRunTests.test_actual_original_matrix_import_and_cold_vault_history'
def context():
    value = dict(fcntl=fcntl, hashlib=hashlib, json=json, os=os, Path=Path, re=re, stat=stat,
        current_test=target, config=dict(targets=[target]), root=ROOT, scratch=scratch,
        acquired={str(artifact): digest}, sha=lambda path: hashlib.sha256(path.read_bytes()).hexdigest(), prohibited=[])
    exec(code, value)
    return value
rows = []
def rejected(name, value, event, args):
    try:
        value['native_boundary'](event, args)
    except RuntimeError:
        assert value['prohibited'][-1] == event
    else:
        raise AssertionError(name)
    rows.append(name)
load_args = (str(artifact), digest, 'hms.retention.linux-cpython312-x86_64/1')
c = context();c['current_test'] = None
rejected('outside-selected-test', c, 'hms.retention.load.v1', load_args)
for name, args in [('wrong-artifact-path', ('/tmp/other.so', *load_args[1:])),
                   ('wrong-artifact-digest', (load_args[0], '0' * 64, load_args[2])),
                   ('wrong-profile', (*load_args[:2], 'other'))]:
    rejected(name, context(), 'hms.retention.load.v1', args)
c = context()
c['native_boundary']('hms.retention.load.v1', load_args)
rejected('second-native-load', c, 'hms.retention.load.v1', load_args)
fd = os.memfd_create('hms-guard-owned-fixture', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
try:
    data = artifact.read_bytes();assert os.write(fd, data) == len(data)
    info = os.fstat(fd)
    seals = fcntl.F_SEAL_SEAL | fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK
    args = ('/proc/self/fd/' + str(fd), digest, info.st_dev, info.st_ino, seals)
    rejected('unsealed-image', c, 'hms.retention.image.v1', args)
    fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
    rejected('wrong-image-inode', c, 'hms.retention.image.v1', (*args[:3], info.st_ino + 1, seals))
    c['native_boundary']('hms.retention.image.v1', args)
    assert c['verify_native_image'](c['native_image'])
    rows.append('real-sealed-image-accepted')
    for name, scan in [('outside-root', (b'/tmp/foreign', 1, 1)),
            ('parent-traversal', (os.fsencode(expected / '../foreign'), 1, 1)),
            ('not-an-attempt', (os.fsencode(expected / 'other'), 1, 1)),
            ('root-file-cap', (os.fsencode(expected), 262145, 1)),
            ('attempt-byte-cap', (os.fsencode(expected / ('a' * 32)), 1, 67108865)),
            ('bool-limit', (os.fsencode(expected), True, 1))]:
        rejected(name, c, 'hms.retention.scan.v1', scan)
    c['native_boundary']('hms.retention.scan.v1', (os.fsencode(expected), 262144, 268435456))
    c['native_boundary']('hms.retention.scan.v1', (os.fsencode(expected / ('a' * 32)), 8192, 67108864))
    assert len(c['native_scans']) == 2
    rows.append('root-and-attempt-bounds-accepted')
    rejected('unknown-event', c, 'hms.retention.unknown', ())
finally:
    os.close(fd)
result = dict(status='passed', checks=rows, exactGuardAstSha256=hashlib.sha256(ast.dump(ast.Module(body=nodes,type_ignores=[])).encode()).hexdigest(),
    harnessChildSha256=hashlib.sha256(text.encode()).hexdigest(),
    fileDataEffects='One owned memfd, populated with pinned original bytes, sealed and closed; never loaded or executed',
    actualWorkerRun=False, originalStateTouched=False)
with (BASE / 'guard-controls02.json').open('x') as stream:
    json.dump(result, stream, indent=2);stream.write('\n')
print(json.dumps(dict(status='passed', checks=len(rows))))
