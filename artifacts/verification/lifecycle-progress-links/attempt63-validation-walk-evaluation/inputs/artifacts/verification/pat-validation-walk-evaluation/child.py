"""Execute exactly two reviewed pure functions with fixed inputs and budgets."""
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import statistics
import sys
import time

BASE = Path(__file__).resolve().parent
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
index = json.loads((BASE / 'inputs.json').read_bytes())
pins = {str(BASE / row['path']): row for row in index['files']}
def verify(path):
    row = pins[str(path)]
    assert not path.is_symlink() and path.stat().st_size == row['bytes'] <= 16 * 1024 * 1024
    body = path.read_bytes(); assert hashlib.sha256(body).hexdigest() == row['sha256']
    return body
for name in pins: verify(Path(name))
denied = []
def guard(event, args):
    if event.startswith('socket.') or event in {'sqlite3.connect','subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn'}:
        denied.append(event); raise RuntimeError('Pure evaluation forbids external execution and I/O')
    if event == 'open':
        mode, flags = args[1:3]
        if (type(mode) is str and any(c in mode for c in 'wax+')) or (type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            denied.append(event); raise RuntimeError('Pure child forbids file mutation')
sys.addaudithook(guard)
class ContractError(ValueError): pass
def load(name):
    path = BASE / name; source = verify(path); tree = ast.parse(source)
    assert len(tree.body) == 1 and isinstance(tree.body[0], ast.FunctionDef) and tree.body[0].name == 'check_tree'
    namespace = dict(ContractError=ContractError, MAX_BYTES=65536, MAX_DEPTH=32, MAX_NODES=16384,
                     SAFE_INTEGER=2**53 - 1, math=math)
    exec(compile(tree, str(path), 'exec'), namespace)
    return namespace['check_tree']
reference, candidate = load('reference_check_tree.py'), load('candidate_check_tree.py')
def outcome(function, value):
    try: return ('accepted', function(value))
    except Exception as error:
        cause = error.__cause__
        return ('refused', type(error).__name__, error.args,
                None if cause is None else (type(cause).__name__, cause.args))
checked = 0
def compare(value, accepted=None):
    global checked
    expected, actual = outcome(reference, value), outcome(candidate, value)
    assert actual == expected, (checked, expected, actual)
    if accepted is not None: assert (actual[0] == 'accepted') is accepted, (checked, actual)
    checked += 1

for value in (None, True, False, 0, 1, -(2**53-1), 2**53-1, 0.0, 0.1, 5e-324, '', 'é😀', [], {}, {'a':[1,False,None]}): compare(value, True)
for value in (2**53, -(2**53), float(2**53), -0.0, float('nan'), float('inf'), -float('inf'), b'a', bytearray(b'a'), (1,), {1}, {1:'a'}, '\ud800', {'\udfff':1}): compare(value, False)
for size in (65535,65536,65537): compare('a' * size, size <= 65536)
for size in (32768,32769): compare('é' * size, size == 32768)
compare(['a'*32768,'b'*32768], True); compare(['a'*32768,'b'*32769], False)
for size in (16382,16383,16384): compare([0]*size, size < 16384)
for size in (8191,8192): compare({str(i):0 for i in range(size)}, size == 8191)
for depth in (31,32,33):
    value = 0
    for _ in range(depth): value = [value]
    compare(value, depth <= 32)
cycle=[]; cycle.append(cycle); compare(cycle,False)
mapping={}; mapping['self']=mapping; compare(mapping,False)
shared={'x':[1,2,3]}; compare([shared]*100,True)
# Refusal order matters when a tree contains more than one invalid value.
for value in ([b'a', '\ud800'], ['\ud800', b'a'], {'a':b'a','b':'\ud800'}, {'a':'\ud800','b':b'a'}, {1:'\ud800'}): compare(value,False)
hooks=[]
def forbidden(*args, **kwargs): hooks.append('called'); raise AssertionError('custom hook ran')
class Trap: __str__=__repr__=__iter__=__len__=__bool__=forbidden
class TrapList(list): __iter__=__len__=forbidden
class TrapDict(dict): items=__iter__=__len__=forbidden
class TrapStr(str): encode=__len__=forbidden
class TrapInt(int): __abs__=forbidden
class TrapFloat(float): is_integer=forbidden
for value in (Trap(),TrapList([1]),TrapDict(a=1),TrapStr('a'),TrapInt(1),TrapFloat(0.1)):
    compare(value,False); compare([value],False)
assert not hooks
generator = random.Random(60417)
scalars = [None,True,False,0,1,-2,0.1,'','é','😀',b'bad','\ud800',2**53,-0.0]
def generated(depth=0):
    kind = generator.randrange(3) if depth < 5 else 0
    if kind == 0: return generator.choice(scalars)
    if kind == 1: return [generated(depth+1) for _ in range(generator.randrange(5))]
    return {str(i):generated(depth+1) for i in range(generator.randrange(5))}
for _ in range(400): compare(generated())
documents = [json.loads(verify(BASE / 'documents' / name)) for name in ('installation.json','candidate.json','bindings.json','matrix.json')]
before = json.dumps(documents,sort_keys=True,ensure_ascii=True)
for document in documents: compare(document,True)
# Fixed alternating order, equal work, no profiler and no adaptive repetitions.
samples=[]
for function in (reference,candidate):
    for document in documents: function(document)
for round_number in range(9):
    order = [('reference',reference),('candidate',candidate)]
    if round_number % 2: order.reverse()
    for label,function in order:
        wall=time.perf_counter_ns(); cpu=time.process_time_ns()
        for _ in range(64):
            for document in documents: function(document)
        samples.append(dict(round=round_number,implementation=label,calls=256,
            cpuNanoseconds=time.process_time_ns()-cpu,wallNanoseconds=time.perf_counter_ns()-wall))
assert json.dumps(documents,sort_keys=True,ensure_ascii=True)==before and not denied and not hooks
for name in pins: verify(Path(name))
medians={label:statistics.median(row['cpuNanoseconds'] for row in samples if row['implementation']==label) for label in ('reference','candidate')}
result=dict(status='passed',differentialCases=checked,customHooksInvoked=len(hooks),prohibitedAttempts=denied,
    inputsUnchanged=True,documentInputsUnchanged=True,publicParserTested=False,canonicalizerTested=False,
    workerExecuted=False,productionChanged=False,physicalObjectiveVerified=False,sourceFunctionsOnly=True,
    benchmarkRounds=9,callsPerSample=256,samples=samples,medianCpuNanoseconds=medians,
    candidateToReferenceMedianCpuRatio=medians['candidate']/medians['reference'],
    timingQualified=False,pythonVersion=sys.version)
encoded=json.dumps(result,indent=2,allow_nan=False); assert len(encoded.encode())<=65536
print(encoded)
