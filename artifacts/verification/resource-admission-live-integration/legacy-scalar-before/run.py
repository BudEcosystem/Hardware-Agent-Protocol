"""One legacy scalar regression on an immutable copy of the staged-equivalent port."""
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
TREE = HERE / 'tree'
sys.dont_write_bytecode = True
sys.path[:0] = [str(TREE), str(TREE / 'tests')]

def pins():
    return [{'path': str(path.relative_to(TREE)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(TREE.rglob('*')) if path.is_file() and '__pycache__' not in path.parts]

before = pins()
(HERE / 'before.json').write_text(json.dumps(before, indent=2) + '\n')
from hms import registry
from hms.pat_compiler import compiler_manifest, _identity
import test_io_resource_admission as tests
assert Path(registry.__file__).resolve() == TREE / 'hms/registry.py'
assert Path(tests.__file__).resolve() == TREE / 'tests/test_io_resource_admission.py'
compiler_before = {'imported': compiler_manifest(), 'current': _identity()}
stream = io.StringIO()
test = tests.IoResourceAdmissionTests('test_extracted_binding_keeps_original_integral_float_refusal')
result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.TestSuite([test]))
(HERE / 'tests.txt').write_text(stream.getvalue())
after = pins()
(HERE / 'after.json').write_text(json.dumps(after, indent=2) + '\n')
compiler_after = {'imported': compiler_manifest(), 'current': _identity()}
(HERE / 'compiler-before.json').write_text(json.dumps(compiler_before, indent=2) + '\n')
(HERE / 'compiler-after.json').write_text(json.dumps(compiler_after, indent=2) + '\n')
report = {'schema': 'hms-resource-admission-scalar-before/1', 'tests': result.testsRun,
    'failures': len(result.failures), 'errors': len(result.errors), 'passed': result.wasSuccessful(),
    'inputsUnchanged': before == after, 'inputCount': len(before),
    'compilerStable': compiler_before == compiler_after and compiler_before['imported'] == compiler_before['current'],
    'scope': 'Exact pinned original Registry refusal versus staged-equivalent extraction, copied source only.'}
(HERE / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(stream.getvalue()); print(json.dumps(report))
raise SystemExit(0 if result.wasSuccessful() else 1)
