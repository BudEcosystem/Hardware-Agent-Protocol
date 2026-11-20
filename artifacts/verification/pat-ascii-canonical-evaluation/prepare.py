"""Prepare an exact current encoder comparison without importing HMS."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
OLD = BASE.parent / 'pat-integer-canonical-evaluation'
SOURCE = ROOT / 'artifacts/implementation/qualification-package/implementation03'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p, body):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as out: out.write(body if type(body) is bytes else body.encode())
assert sha(SOURCE / 'index.json') == 'ec6df4066c89f38328030a28e2a5bd71d137abbc67cd51cb161cc246e2e8a268'
assert sha(OLD / 'inputs.json') == 'a0df3095c4225e11c4b1b0bfdeac21751ed1970cc0313c4c2d8f5dba853aba61'
source_rows = {v['path']: v for v in read(SOURCE / 'index.json')['files']}
old_rows = {v['path']: v for v in read(OLD / 'inputs.json')['files']}
borrowed = []
def copy(p, name, row):
    assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256']
    write(BASE / name, p.read_bytes())
    borrowed.append(dict(source=str(p), copy=name, bytes=row['bytes'], sha256=row['sha256']))
path = SOURCE / 'project/hms/contracts.py'
copy(path, 'references/contracts.py', source_rows[path.relative_to(ROOT).as_posix()])
assert path.read_bytes() == (ROOT / 'hms/contracts.py').read_bytes()
body = path.read_text()
names = {'ContractError', '_number', '_object', '_bad_constant', 'check_tree', 'parse_json', 'canonical'}
nodes = [n for n in ast.parse(body).body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
assert {n.name for n in nodes} == names
functions = '\n\n'.join(ast.get_source_segment(body, n) for n in nodes) + '\n'
write(BASE / 'reference_functions.py', functions)
write(BASE / 'candidate_functions.py', functions)
write(BASE / 'oracle_functions.py', functions.replace('result = _canonical_bytes(value)', 'result = rfc8785.dumps(value)'))
helpers = body[body.index('from types import FunctionType as _FunctionType'):body.index('_SCHEMA =')].rstrip() + '\n'
write(BASE / 'reference_helpers.py', helpers)
replacement = '''class _UseUtf16Order(Exception):
    pass


def _ascii_integer_tree(value):
    """Detach validated containers whose field names use ASCII ordering."""
    kind = type(value)
    if kind is dict:
        if not all(key.isascii() for key in value):
            raise _UseUtf16Order
        return {key: _ascii_integer_tree(child) for key, child in value.items()}
    if kind is list:
        return [_ascii_integer_tree(child) for child in value]
    if value is None or kind in (bool, int, str):
        return value
    raise _UseReference


def _canonical_bytes(value):
    if not _fast_allowed():
        return rfc8785.dumps(value)
    try:
        try:
            ordered = _ascii_integer_tree(value)
            sort_keys = True
        except _UseUtf16Order:
            ordered = _integer_tree(value)
            sort_keys = False
    except _UseReference:
        return rfc8785.dumps(value)
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False,
        check_circular=True, sort_keys=sort_keys, skipkeys=False, separators=(',', ':'))
    return encoder.encode(ordered).encode('utf-8')
'''
candidate = helpers[:helpers.index('def _canonical_bytes(value):')] + replacement
ast.parse(candidate)
write(BASE / 'candidate_helpers.py', candidate)
write(BASE / 'candidate.patch', ''.join(difflib.unified_diff(helpers.splitlines(True), candidate.splitlines(True), fromfile='reference_helpers.py', tofile='candidate_helpers.py')))
write(BASE / 'candidate-contracts.py', body.replace(helpers.rstrip(), candidate.rstrip()))
for name in ('__init__.py', '_impl.py'):
    p = SOURCE / 'project/hms/_vendor/rfc8785' / name
    copy(p, 'vendor/eval_rfc8785/' + name, source_rows[p.relative_to(ROOT).as_posix()])
for name, row in sorted(old_rows.items()):
    if name.startswith(('documents/', 'vectors/', 'references/installed-json-')):
        copy(OLD / name, name, row)
for name in ('run.py', 'child.py'):
    copy(OLD / name, 'original-' + name, old_rows[name])
write(BASE / 'run.py', (OLD / 'run.py').read_bytes())
child = (OLD / 'child.py').read_text()
child = child.replace("verify(BASE / 'candidate_helpers.py'), str(BASE / 'candidate_helpers.py')", "verify(BASE / helpers), str(BASE / helpers)")
child = child.replace("reference = load('reference_functions.py')", "reference = load('reference_functions.py', helpers='reference_helpers.py')\noracle = load('oracle_functions.py')")
child = child.replace("helpers=True)", "helpers='candidate_helpers.py')")
needle = '    assert actual == wanted, (label, wanted, actual)'
assert needle in child
child = child.replace(needle, needle + "\n    if candidate['_fast_allowed']() and reference['_fast_allowed']():\n        assert outcome(function(oracle), value) == wanted, ('vendor-reference', label)")
extra = '''# The added route keeps detached containers and delegates key sorting to C.
ascii_original = {'z': [{'value': 'é😀', 'b': 2, 'a': 1}], 'a': [0]}
ascii_prepared = candidate['_ascii_integer_tree'](ascii_original)
assert ascii_prepared == ascii_original and ascii_prepared is not ascii_original
assert ascii_prepared['z'] is not ascii_original['z'] and ascii_prepared['z'][0] is not ascii_original['z'][0]
ascii_prepared['z'][0]['value'] = 'changed'
assert ascii_original['z'][0]['value'] == 'é😀'
ascii_routes = []
for label, value, use_utf16, use_vendor in [
    ('ascii-fields', {'z': 1, 'A': 2, 'a': 3, '': 4, '\\x7f': 5}, False, False),
    ('unicode-values', ascii_original, False, False),
    ('nested-unicode-field', {'a': [{'é': 1}]}, True, False),
    ('astral-order', {'\\ue000': 1, '\\U00010000': 2}, True, False),
    ('float-before-unicode', {'a': 0.1, 'z': {'é': 1}}, False, True),
    ('float-after-unicode', {'a': {'é': 1}, 'z': 0.1}, True, True),
]:
    calls = []
    utf16_code = candidate['_integer_tree'].__code__
    vendor_code = rfc8785.dumps.__code__
    def route_profile(frame, event, arg):
        if event == 'call' and frame.f_code in (utf16_code, vendor_code):
            calls.append('utf16' if frame.f_code is utf16_code else 'vendor')
    sys.setprofile(route_profile)
    try: encoded = candidate['canonical'](value)
    finally: sys.setprofile(None)
    assert ('utf16' in calls) is use_utf16 and ('vendor' in calls) is use_vendor
    compare(value, 'ascii-route-' + label, True)
    assert encoded == oracle['canonical'](value)
    ascii_routes.append(dict(input=label, utf16Fallback=use_utf16, vendorFallback=use_vendor))

'''
needle = "documents=[json.loads(verify(path))"
assert needle in child
child = child.replace(needle, extra + needle)
child = child.replace("fallbackChecks=fallbacks,originalEncoderRouting=routes,upstreamVectors=vectors,", "fallbackChecks=fallbacks,originalEncoderRouting=routes,asciiRoutes=ascii_routes,detachedAsciiContainers=True,upstreamVectors=vectors,")
child = child.replace("timingQualified=False,pythonVersion", "referenceIsCurrentGuardedEncoder=True,vendorOracleCheckedOnUnmodifiedDependencies=True,\n    timingQualified=False,pythonVersion")
ast.parse(child)
write(BASE / 'child.py', child)
write(BASE / 'child.patch', ''.join(difflib.unified_diff((OLD / 'child.py').read_text().splitlines(True), child.splitlines(True), fromfile='previous/child.py', tofile='current/child.py')))
write(BASE / 'borrowed-inputs.json', json.dumps(borrowed, indent=2) + '\n')
print(json.dumps(dict(borrowedInputs=len(borrowed), extractedFunctions=len(nodes), packageImported=False)))
