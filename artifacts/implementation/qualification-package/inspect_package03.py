"""Read/import-only package inspection; no databases, network or worker launch."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import types
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
PROJECT = BASE / 'implementation02/project'
assert sys.flags.isolated and sys.flags.dont_write_bytecode
approved_path = BASE.parents[2] / 'artifacts/implementation/pat-vault-catalog/harness23/references/approved-external-roots.json'
approved_raw = approved_path.read_bytes()
assert hashlib.sha256(approved_raw).hexdigest() == '4155d501cb1e11fe535ea9d774a9b1b0e8f68bfabbc9195d79e392452d869570'
approved = json.loads(approved_raw)
for pin in approved['selectedMetadata']:
    body = Path(pin['metadataPath']).read_bytes()
    assert len(body) == pin['bytes'] and hashlib.sha256(body).hexdigest() == pin['sha256']
sys.path[:0] = [str(PROJECT)] + approved['roots']
for forbidden in ('supervisor', 'evidence', 'evidence_compact', 'evidence_vault',
                  'evidence_authority', 'recorded_io', 'vault_recorded_io'):
    assert not (PROJECT / forbidden).exists()
legacy = json.loads((BASE / 'implementation02/namespace-map.json').read_bytes())['modules']
poisons = {}
for name in legacy:
    sentinel = types.ModuleType(name)
    sys.modules[name] = sentinel
    poisons[name] = sentinel


def guard(event, args):
    if event.startswith('socket.') or event in {
            'sqlite3.connect', 'subprocess.Popen', 'os.system', 'os.exec', 'os.fork',
            'os.forkpty', 'os.posix_spawn', 'os.mkdir', 'os.remove', 'os.rename'}:
        raise AssertionError('Package import performed an effect: ' + event)
    if event == 'open':
        mode, flags = args[1:3]
        if type(mode) is str and any(c in mode for c in 'wax+') or type(flags) is int and flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise AssertionError('Package import wrote a file')


sys.addaudithook(guard)
for name in ('supervisor.io_service_execution', 'evidence.store', 'evidence_compact.store',
             'evidence_vault.store', 'evidence_authority.store', 'recorded_io.execution',
             'vault_recorded_io.execution'):
    importlib.import_module('hms_qualification.' + name)
from hms_qualification.supervisor import supervisor_contracts as contracts
from hms_qualification.supervisor.qualification_supervisor import _image_rows
from hms_qualification.evidence.contracts import identity as legacy_identity
from hms_qualification.evidence_authority.contracts import identity as consumer_identity
from hms_qualification.evidence_vault.contracts import identity as vault_identity
from hms_qualification.vault_recorded_io.contracts import identity as host_identity
from hms.pat_simulation_worker import simulation_identities

assert all(sys.modules[name] is sentinel for name, sentinel in poisons.items())
rows = _image_rows(); names = [row[0] for row in rows]
assert len(names) == len(set(names))
for expected in ('hms_qualification/__init__.py', 'hms_qualification/supervisor/__init__.py',
                 'hms_qualification/supervisor/worker_entry.py'):
    assert expected in names
assert not any(name.startswith('supervisor/') for name in names)
for name, path, expected in rows:
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
origins = []
for name, module in sorted(sys.modules.items()):
    if name == 'hms_qualification' or name.startswith('hms_qualification.'):
        path = Path(module.__file__).resolve()
        assert path.is_relative_to(PROJECT.resolve() / 'hms_qualification')
        origins.append(dict(module=name, path=str(path.relative_to(PROJECT.resolve())),
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
worker = simulation_identities()
drift_refusals = []
original_read = Path.read_bytes
for relative in ('hms_qualification/__init__.py', 'hms_qualification/supervisor/__init__.py'):
    target = PROJECT / relative
    def changed(path):
        body = original_read(path)
        return body + b'\n# injected initializer drift\n' if path == target else body
    for label, function, arguments in (
            ('supervisor', contracts.supervisor_identity, (worker,)),
            ('consumer', consumer_identity, ())):
        with patch.object(Path, 'read_bytes', changed):
            try:
                function(*arguments)
            except Exception as error:
                assert getattr(error, 'code', '').endswith('IMPLEMENTATION_CHANGED'), repr(error)
                drift_refusals.append(dict(initializer=relative, boundary=label, code=error.code))
            else:
                raise AssertionError('Changed package initializer retained eligibility')
assert len(drift_refusals) == 4
report = dict(passed=True, importEffects=False, poisonedLegacyModules=len(poisons),
    producerImageFiles=len(rows), packageInitializersPinned=True, origins=origins,
    initializerDriftRefusals=drift_refusals,
    host=host_identity(), consumer=consumer_identity(), vault=vault_identity(),
    legacy=legacy_identity(), supervisor=contracts.supervisor_identity(worker), worker=worker)
print(json.dumps(report, indent=2))
