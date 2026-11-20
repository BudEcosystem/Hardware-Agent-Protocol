"""Prepare a fresh namespaced copy; never alter the sealed source candidate."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
OLD = ROOT / 'artifacts/implementation/pat-vault-catalog/implementation03'
DEST = BASE / 'implementation02'
PROJECT = DEST / 'project'
GROUPS = ('supervisor', 'evidence', 'evidence_compact', 'evidence_vault',
          'evidence_authority', 'recorded_io', 'vault_recorded_io')
PACKAGE = 'hms_qualification'


def sha(body):
    return hashlib.sha256(body).hexdigest()


def write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(body.encode() if type(body) is str else body)


def json_file(path, value):
    write(path, json.dumps(value, indent=2) + '\n')


def rewrite_imports(text, mapping):
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line.encode()))
    raw = text.encode(); edits = []
    for node in ast.walk(ast.parse(text)):
        replacement = None
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            head, _, tail = node.module.partition('.')
            if head in mapping:
                node.module = mapping[head] + ('.' + tail if tail else '')
                replacement = ast.unparse(node)
        elif isinstance(node, ast.Import):
            changed = False
            for alias in node.names:
                if alias.name in mapping:
                    alias.asname = alias.asname or alias.name
                    alias.name = mapping[alias.name]; changed = True
            if changed:
                replacement = ast.unparse(node)
        elif isinstance(node, ast.Constant) and type(node.value) is str:
            head, dot, tail = node.value.partition('.')
            if head in mapping and not node.value.endswith('.py') and (dot or node.value in mapping):
                replacement = repr(mapping[head] + (dot + tail if dot else ''))
        if replacement is not None:
            start = offsets[node.lineno - 1] + node.col_offset
            end = offsets[node.end_lineno - 1] + node.end_col_offset
            edits.append((start, end, replacement.encode()))
    for start, end, value in sorted(edits, reverse=True):
        raw = raw[:start] + value + raw[end:]
    ast.parse(raw)
    return raw.decode()


def main():
    assert not DEST.exists()
    old_index = (OLD / 'index.json').read_bytes()
    assert sha(old_index) == '5ffd155119c12c73d6090a6684973f7f14474ebbfdb0fce228f880476df4e3a9'
    old = json.loads(old_index)
    for row in old['files']:
        body = (ROOT / row['path']).read_bytes()
        assert len(body) == row['bytes'] and sha(body) == row['sha256'], row['path']
    write(DEST / 'original-index.json', old_index)
    modules = {p.stem: PACKAGE + '.supervisor.' + p.stem
               for p in (OLD / 'project/supervisor').glob('*.py')}
    modules.update({name: PACKAGE + '.' + name for name in GROUPS if name != 'supervisor'})
    moved, changes = [], []
    prefix = str((OLD / 'project').relative_to(ROOT)) + '/'
    for row in old['files']:
        if not row['path'].startswith(prefix):
            continue
        old_name = row['path'][len(prefix):]
        name = PACKAGE + '/' + old_name if old_name.split('/')[0] in GROUPS else old_name
        body = (ROOT / row['path']).read_bytes()
        after = rewrite_imports(body.decode(), modules).encode() if name.endswith('.py') else body
        write(PROJECT / name, after)
        moved.append(dict(originalPath=old_name, path=name, originalSha256=row['sha256'], sha256=sha(after)))
        if after != body:
            changes.extend(difflib.unified_diff(body.decode().splitlines(True), after.decode().splitlines(True),
                fromfile=old_name, tofile=name))
    write(PROJECT / PACKAGE / '__init__.py',
        '"""Installed original qualification components; imports perform no worker launch."""\n')
    write(PROJECT / PACKAGE / 'supervisor/__init__.py',
        '"""Explicit original-worker supervision package; no flat import aliases."""\n')
    json_file(DEST / 'namespace-map.json', dict(modules=modules, files=moved))
    write(DEST / 'namespace.patch', ''.join(changes))
    print(json.dumps(dict(projectFiles=len(moved)+2, namespaceImportsChangedFiles=sum(
        row['originalSha256'] != row['sha256'] for row in moved), implementation=str(DEST.relative_to(ROOT)))))


if __name__ == '__main__':
    main()
