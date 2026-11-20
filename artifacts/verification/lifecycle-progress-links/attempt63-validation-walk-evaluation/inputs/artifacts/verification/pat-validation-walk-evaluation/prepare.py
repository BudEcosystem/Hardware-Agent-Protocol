"""Prepare an isolated pure-function comparison; execute no project code."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = ROOT / 'artifacts/implementation/pat-vault-original-run/implementation02'
PROFILE = ROOT / 'artifacts/verification/pat-vault-worker-profile'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_bytes())
def write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream: stream.write(body if type(body) is bytes else body.encode())
assert sha(SOURCE / 'index.json') == '4a1f5b97cb29e897fc865ca5dcf46397bfdec6c4154a302dfdac1b546e66c4f4'
assert sha(PROFILE / 'index.json') == '3dfd5586c4256b8e77a8d9ce3cbcf99eea515653d600e75deeb3a6ddb1383325'
source = SOURCE / 'project/hms/contracts.py'
source_row = next(row for row in read(SOURCE / 'index.json')['files'] if row['path'] == source.relative_to(ROOT).as_posix())
assert source.stat().st_size == source_row['bytes'] and sha(source) == source_row['sha256']
body = source.read_text(); tree = ast.parse(body)
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'check_tree')
reference = ast.get_source_segment(body, function) + '\n'
candidate = reference.replace('        if type(item) is dict:', '        kind = type(item)\n        if kind is dict:')
candidate = candidate.replace('type(item) is ', 'kind is ')
candidate = candidate.replace('            for key, child in item.items():', '            child_depth = depth + 1\n            for key, child in item.items():')
candidate = candidate.replace('stack.append((key, depth + 1))', 'stack.append((key, child_depth))')
candidate = candidate.replace('stack.append((child, depth + 1))', 'stack.append((child, child_depth))')
candidate = candidate.replace('            stack.extend((child, depth + 1) for child in item)', '            child_depth = depth + 1\n            stack.extend((child, child_depth) for child in item)')
assert candidate.count('type(item)') == 1 and reference.count('type(item)') == 6
assert ast.dump(ast.parse(reference).body[0]) == ast.dump(function)
for text in (reference, candidate):
    node = ast.parse(text).body[0]
    assert isinstance(node, ast.FunctionDef) and node.name == 'check_tree' and len(node.args.args) == 1
write(BASE / 'reference_check_tree.py', reference)
write(BASE / 'candidate_check_tree.py', candidate)
write(BASE / 'references/contracts.py', source.read_bytes())
write(BASE / 'candidate.patch', ''.join(difflib.unified_diff(reference.splitlines(True), candidate.splitlines(True), fromfile='reference', tofile='candidate')))
borrowed = [dict(source=source.relative_to(ROOT).as_posix(), copy='references/contracts.py', bytes=source_row['bytes'], sha256=source_row['sha256'])]
report = read(PROFILE / 'RESULTS.json')
output = PROFILE / 'harness01/attempts/attempt01-profile/scratch/test_actual_original_matrix_catalog_execution_and_historical_replay/supervisor' / report['originalAttemptId'] / 'output'
profile_rows = {row['path']: row for row in read(PROFILE / 'index.json')['files']}
for name in ('installation.json', 'candidate.json', 'bindings.json', 'matrix.json'):
    path = output / name; row = profile_rows[path.relative_to(PROFILE).as_posix()]
    assert path.stat().st_size == row['bytes'] <= 65536 and sha(path) == row['sha256']
    write(BASE / 'documents' / name, path.read_bytes())
    borrowed.append(dict(source=path.relative_to(ROOT).as_posix(), copy='documents/' + name, bytes=row['bytes'], sha256=row['sha256']))
write(BASE / 'borrowed-inputs.json', json.dumps(borrowed, indent=2) + '\n')
write(BASE / 'REVIEW.md', '# Pure validation evaluation\n\nOnly the extracted original `check_tree` function and the reviewed local-type/child-depth candidate execute, with identical fixed original constants and exception type. No project package is imported and no runtime, authority, worker, database, model, physical endpoint or live service runs. The four retained JSON documents are data, not executable source.\n\nDifferential cases compare exact success/refusal type, arguments and cause, plus retained-document immutability. Bounded fixed interleaved timings compare only this function; this neither tests public parsers nor qualifies an actual worker, canonicalizer, physical effect or deployment latency. Production adoption requires subsequent integration checks.\n\nChild: isolated Python, no site or bytecode, 30 CPU seconds, 512 MiB address space, 16 MiB file limit, 64 descriptors, no subprocess/network/SQLite, no file writes. Parent: one owned child, 60-second wall wait, retained output at most 4 MiB. Cooperative audit hooks are not an OS sandbox; startup standard library and dynamic system libraries are not a fully pinned execution closure. Primary-agent review only.\n')
files = []
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        if path.suffix == '.py': ast.parse(path.read_bytes())
        files.append(dict(path=path.relative_to(BASE).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
write(BASE / 'inputs.json', json.dumps(dict(scope='Pure validator evaluation only; no production adoption', files=files), indent=2) + '\n')
print(json.dumps(dict(inputs=len(files), indexSha256=sha(BASE / 'inputs.json'), projectExecution=False)))
