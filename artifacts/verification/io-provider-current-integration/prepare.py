"""Copy and hash source inputs only; never import HMS or execute provider tests."""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ATTEMPT = ROOT / 'artifacts/verification/runtime-attempts/20261107T001334.443472Z-59acecf941d0'
BASE = ATTEMPT / 'inputs-before'
STAGE = ROOT / 'artifacts/implementation/io-synthetic-provider'
PROVIDER_INDEX = 'b8ec279e86b8cea07173b6ce67cf521058535441d2feb8926dd1800641f19b2d'
MODULES = ('synthetic_io_adapter.py', 'synthetic_io_board.py', 'synthetic_io_catalog.py',
           'synthetic_io_installation.py', 'synthetic_io_runtime.py', 'synthetic_io_storage.py')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def copy_new(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    data = source.read_bytes()
    with target.open('xb') as stream:
        stream.write(data)
    return data


def main():
    assert not (HERE / 'baseline').exists() and not (HERE / 'tree').exists(), 'prepared source tree already exists'
    index_bytes = (STAGE / 'index.json').read_bytes()
    assert digest(index_bytes) == PROVIDER_INDEX
    stage_rows = {row['path']: row for row in json.loads(index_bytes)['files']}
    base_files = sorted(path for path in BASE.rglob('*') if path.is_file() and '__pycache__' not in path.parts)
    assert len(base_files) == 139
    baseline = []
    for source in base_files:
        relative = source.relative_to(BASE)
        data = copy_new(source, HERE / 'baseline' / relative)
        assert data == (ROOT / relative).read_bytes(), 'live baseline differs from immutable full-run input'
        copy_new(source, HERE / 'tree' / relative)
        baseline.append({'path': str(relative), 'bytes': len(data), 'sha256': digest(data),
            'acquiredFrom': str(source.relative_to(ROOT))})
    acquired = []
    for relative in [*('staged/hms/' + name for name in MODULES), 'staged/hms/state_path.py',
                     'test_io_synthetic_provider.py', 'io_fixtures.py', 'DESIGN.md', 'README.md', 'proof.json']:
        source = STAGE / relative
        data = source.read_bytes()
        pin = stage_rows[str(source.relative_to(ROOT))]
        assert len(data) == pin['bytes'] and digest(data) == pin['sha256']
        copy_new(source, HERE / 'provider-source' / relative)
        acquired.append({'path': str(source.relative_to(ROOT)), 'bytes': len(data), 'sha256': digest(data),
                         'copy': 'provider-source/' + relative})
    copy_new(STAGE / 'index.json', HERE / 'provider-source/index.json')
    changes = []
    for name in MODULES:
        source = HERE / 'provider-source/staged/hms' / name
        target = HERE / 'tree/hms' / name
        data = copy_new(source, target)
        changes.append({'path': 'hms/' + name, 'kind': 'exact-provider-module-addition', 'sha256': digest(data)})
    state = HERE / 'tree/hms/state_path.py'
    original = state.read_bytes()
    old = b"r'simulated-plant-[0-9a-f]{64}\\.db'"
    new = b"r'(?:simulated-plant|synthetic-io-board)-[0-9a-f]{64}\\.db'"
    assert original.count(old) == 1
    changed = original.replace(old, new)
    assert changed == (HERE / 'provider-source/staged/hms/state_path.py').read_bytes()
    state.write_bytes(changed)
    changes.append({'path': 'hms/state_path.py', 'kind': 'one-exact-private-database-prefix-addition',
                    'beforeSha256': digest(original), 'sha256': digest(changed)})
    original = (HERE / 'provider-source/test_io_synthetic_provider.py').read_bytes()
    old = b'from io_fixtures import topology, generations'
    new = b'from test_resource_topology import topology, generations'
    assert original.count(old) == 1
    changed = original.replace(old, new)
    target = HERE / 'tree/tests/test_io_synthetic_provider.py'
    assert not target.exists()
    target.write_bytes(changed)
    changes.append({'path': 'tests/test_io_synthetic_provider.py', 'kind': 'normal-current-topology-helper-import',
                    'beforeSha256': digest(original), 'sha256': digest(changed)})
    def helpers(path):
        tree = ast.parse(path.read_bytes())
        return {node.name: ast.dump(node, include_attributes=False) for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name in {'topology', 'generations', 'node', 'pin'}}
    assert helpers(HERE / 'provider-source/io_fixtures.py') == helpers(HERE / 'tree/tests/test_resource_topology.py')
    copy_new(ATTEMPT / 'started.json', HERE / 'parent-started-at-preparation.json')
    copy_new(ATTEMPT / 'outputs/pat-compiler-identity-before.json', HERE / 'parent-compiler-identity-before.json')
    prepared = []
    for path in sorted((HERE / 'tree').rglob('*')):
        if path.is_file():
            data = path.read_bytes()
            prepared.append({'path': str(path.relative_to(HERE / 'tree')), 'bytes': len(data), 'sha256': digest(data)})
    assert len(prepared) == 146
    write_json(HERE / 'baseline-inputs.json', baseline)
    write_json(HERE / 'prepared-inputs.json', prepared)
    write_json(HERE / 'assembly.json', {
        'schema': 'hms-provider-current-source-preparation/1',
        'baselineAttempt': str(ATTEMPT.relative_to(ROOT)), 'baselineStateAtPreparation': 'running',
        'baselineFileCount': len(baseline), 'baselineAllBytesMatchedFrozenLiveAtAcquisition': True,
        'baselineInventoryMethod': 'Derived from immutable inputs-before files; final full receipt rows were not yet published.',
        'providerIndex': {'path': str((STAGE / 'index.json').relative_to(ROOT)), 'sha256': PROVIDER_INDEX},
        'providerSourcePins': acquired, 'changes': changes, 'preparedFileCount': len(prepared),
        'fixtureHelperAstsEqual': True, 'hmsImported': False, 'testsRun': False, 'runtimeRun': False,
        'liveSourcesEdited': False,
        'identityScope': 'Parent compiler identity is acquisition provenance only. No prepared provider implementation_digest was invoked; its added whole-project closure is separate.',
        'limits': ['Source preparation only, no pass or provider qualification claim.',
                   'Execution remains on hold until the parent full696 run terminates.',
                   'No stock Runtime/daemon/IPC/CLI/MCP mounting or lifecycle execution is added.']})
    print(json.dumps({'baselineFiles': len(baseline), 'preparedFiles': len(prepared),
                      'providerModulesUnchanged': len(MODULES), 'testsRun': False, 'liveSourcesEdited': False}))


if __name__ == '__main__':
    main()
