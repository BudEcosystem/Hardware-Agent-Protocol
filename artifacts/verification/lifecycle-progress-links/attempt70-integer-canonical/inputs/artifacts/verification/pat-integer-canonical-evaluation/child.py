"""Bounded pure canonicalizer comparison; no runtime, worker or database."""
import ast
from decimal import Decimal, DecimalException
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import statistics
import struct
import sys
import time
import _json

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
    assert not path.is_symlink() and path.stat().st_size == row['bytes'] <= 16777216
    body = path.read_bytes(); assert hashlib.sha256(body).hexdigest() == row['sha256']
    return body
for name in pins:
    verify(Path(name))
external = json.loads(verify(BASE / 'runtime-inputs.json'))
for row in external['files']:
    path = Path(row['path'])
    assert path.stat().st_size == row['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
assert json.encoder.__file__ == external['jsonEncoderOrigin'] and _json.__file__ == external['jsonNativeOrigin']
denied = []
def guard(event, args):
    if event.startswith('socket.') or event in {'sqlite3.connect', 'subprocess.Popen', 'os.system', 'os.exec', 'os.fork', 'os.forkpty', 'os.posix_spawn'}:
        denied.append(event); raise RuntimeError('Pure evaluation forbids execution and external I/O')
    if event == 'open':
        mode, flags = args[1:3]
        if (type(mode) is str and any(c in mode for c in 'wax+')) or (type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            denied.append(event); raise RuntimeError('Pure child forbids file mutation')
sys.addaudithook(guard)
sys.path.insert(0, str(BASE / 'vendor'))
import eval_rfc8785 as rfc8785
for module in (rfc8785, rfc8785._impl):
    verify(Path(module.__file__))

def load(name, helpers=False):
    namespace = dict(MAX_BYTES=65536, MAX_DEPTH=32, MAX_NODES=16384, SAFE_INTEGER=2**53-1,
                     math=math, json=json, Decimal=Decimal, DecimalException=DecimalException, rfc8785=rfc8785)
    source = verify(BASE / name); tree = ast.parse(source)
    assert all(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in tree.body)
    exec(compile(tree, str(BASE / name), 'exec'), namespace)
    if helpers:
        exec(compile(verify(BASE / 'candidate_helpers.py'), str(BASE / 'candidate_helpers.py'), 'exec'), namespace)
    return namespace
reference = load('reference_functions.py')
candidate = load('candidate_functions.py', helpers=True)
assert candidate['_fast_allowed']()
def outcome(function, value):
    try:
        return ('accepted', function(value))
    except Exception as error:
        cause = error.__cause__
        return ('refused', type(error).__name__, error.args,
                None if cause is None else (type(cause).__name__, cause.args))
cases = []
def receipt_value(value):
    if type(value) is bytes:
        return {'bytesHex':value.hex()}
    if type(value) in (tuple,list):
        return [receipt_value(item) for item in value]
    assert value is None or type(value) in (str,int,bool)
    return value
def compare(value, label, expected=None, parse=False):
    def function(namespace):
        return (lambda value: namespace['canonical'](namespace['parse_json'](value))) if parse else namespace['canonical']
    wanted, actual = outcome(function(reference), value), outcome(function(candidate), value)
    assert actual == wanted, (label, wanted, actual)
    if expected is not None:
        assert (wanted[0] == 'accepted') is expected, (label, wanted)
    row = dict(id=label, status=wanted[0])
    if wanted[0] == 'accepted':
        row.update(bytes=len(wanted[1]), sha256=hashlib.sha256(wanted[1]).hexdigest())
    else:
        row.update(exception=wanted[1], arguments=receipt_value(wanted[2]), cause=receipt_value(wanted[3]))
    cases.append(row)
    return wanted

valid = [None, True, False, 0, 1, -(2**53-1), 2**53-1, 0.0, 0.1, 5e-324,
         1e-6, 1e-7, -1e-6, 9007199254740991.0, '', 'é😀', [], {}, {'a':[1,False,None]},
         {'nested':[{'z':0.1},'last']}, {'z':[1,2], 'a':[]}]
for i, value in enumerate(valid): compare(value, 'valid-'+str(i), True)
invalid = [2**53, -(2**53), 10**10000, float(2**53), -0.0, float('nan'), float('inf'),
           -float('inf'), b'a', bytearray(b'a'), (1,), {1}, {1:'a'}, '\ud800', {'\udfff':1}]
for i, value in enumerate(invalid): compare(value, 'invalid-'+str(i), False)
for size in (65533,65534,65535,65536,65537): compare('a'*size, 'ascii-'+str(size), size <= 65534)
for size in (32766,32767,32768,32769): compare('é'*size, 'utf8-'+str(size), size <= 32767)
for size in (10921,10922,10923): compare('\x00'*size, 'escaped-'+str(size), size <= 10922)
for size in (16382,16383,16384): compare([0]*size, 'nodes-'+str(size), size < 16384)
for size in (8191,8192): compare({str(i):0 for i in range(size)}, 'object-nodes-'+str(size), False)
for depth in (31,32,33):
    value = 0
    for _ in range(depth): value = [value]
    compare(value, 'depth-'+str(depth), depth <= 32)
cycle=[]; cycle.append(cycle); compare(cycle, 'cycle-list', False)
mapping={}; mapping['self']=mapping; compare(mapping, 'cycle-dict', False)
shared={'x':[1,2,3]}; compare([shared]*100, 'shared', True)
for i,value in enumerate(([b'a','\ud800'],['\ud800',b'a'],{'a':b'a','b':'\ud800'},{'a':'\ud800','b':b'a'},{1:'\ud800'})):
    compare(value, 'refusal-order-'+str(i), False)
hooks=[]
def forbidden(*args, **kwargs):
    hooks.append('called'); raise AssertionError('custom hook ran')
class Trap: __str__=__repr__=__iter__=__len__=__bool__=forbidden
class TrapList(list): __iter__=__len__=forbidden
class TrapDict(dict): items=__iter__=__len__=forbidden
class TrapStr(str): encode=__len__=forbidden
class TrapInt(int): __abs__=forbidden
class TrapFloat(float): is_integer=forbidden
for i,value in enumerate((Trap(),TrapList([1]),TrapDict(a=1),TrapStr('a'),TrapInt(1),TrapFloat(0.1))):
    compare(value, 'custom-'+str(i), False); compare([value], 'nested-custom-'+str(i), False)
assert not hooks

# Every Unicode scalar value, including noncharacters, appears in two contexts.
unicode_scalars=0
for first in range(0, 0x110000, 4096):
    value=''.join(chr(i) for i in range(first,min(first+4096,0x110000)) if not 0xd800<=i<=0xdfff)
    unicode_scalars += len(value)
    compare(value, 'unicode-value-'+str(first), True)
    compare({value:'x'}, 'unicode-key-'+str(first), True)
assert unicode_scalars == 1112064
ordered_keys=['\r','1','\x80','ö','€','😀','דּ']
ordering={key:i for i,key in reversed(list(enumerate(ordered_keys)))}
answer=compare(ordering,'rfc-key-order',True)[1]
assert list(json.loads(answer))==ordered_keys
answer=compare({'\ue000':1,'\U00010000':2},'utf16-not-codepoint',True)[1]
assert answer == b'{"\xf0\x90\x80\x80":2,"\xee\x80\x80":1}'
assert compare('\b\t\n\f\r"\\/\x00\x1f','escapes',True)[1] == b'"\\b\\t\\n\\f\\r\\"\\\\/\\u0000\\u001f"'

generator=random.Random(69017)
scalars=[None,True,False,0,1,-2,0.1,'','é','😀','\ue000','\U00010000',b'bad','\ud800',2**53,-0.0]
def generated(depth=0):
    kind=generator.randrange(3) if depth<5 else 0
    if kind==0:return generator.choice(scalars)
    if kind==1:return [generated(depth+1) for _ in range(generator.randrange(5))]
    return {generator.choice(['é','😀','\ue000','x'])+str(i):generated(depth+1) for i in range(generator.randrange(5))}
for i in range(400):compare(generated(),'generated-'+str(i))
for i in range(600):
    value=struct.unpack('>d',generator.getrandbits(64).to_bytes(8,'big'))[0]
    compare(value,'float-'+str(i))
wire=[b'{"a":1,"a":2}',b'-0',b'-0.0',b'0.1',b'1e-6',b'1e-7',b'1e30',b'1e-400',
      b'0.10000000000000001',b'NaN',b'Infinity',b'{"\\ud800":0}',b'"\\ud83d\\ude00"',b'\xff',
      b'{"a":[1,null,true],"z":"x"}',b'['*33+b'0'+b']'*33,b'0'*65537,bytearray(b'0')]
for i,value in enumerate(wire):compare(value,'parse-'+str(i),parse=True)
vectors=[]
for path in sorted((BASE/'vectors/input').glob('*.json')):
    value=json.loads(verify(path)); expected=verify(BASE/'vectors/output'/path.name)
    assert rfc8785.dumps(value)==expected, path.name
    outcome_row=compare(value,'upstream-vector-'+path.name)
    if outcome_row[0]=='accepted':assert outcome_row[1]==expected
    vectors.append(dict(name=path.name,upstreamBytesMatched=True,hostProfileOutcome=outcome_row[0]))

fallbacks=[]
def check_fallback(label, namespace, key, replacement, value={'x':[1,2]}):
    original=namespace[key];namespace[key]=replacement
    try:
        assert not candidate['_fast_allowed'](), label
        compare(value,'fallback-'+label)
        fallbacks.append(label)
    finally:namespace[key]=original
    assert candidate['_fast_allowed'](),label
check_fallback('public-dumps',vars(rfc8785),'dumps',lambda value:b'"replacement"')
def refuse(value):raise ValueError('replacement refused')
check_fallback('public-dumps-refusal',vars(rfc8785),'dumps',refuse)
check_fallback('recursive-dump',vars(rfc8785._impl),'dump',lambda value,sink:sink.write(b'"replacement"'))
check_fallback('string-helper',vars(rfc8785._impl),'_serialize_str',lambda value,sink:sink.write(b'"replacement"'))
check_fallback('integer-bound',vars(rfc8785._impl),'_INT_MAX',0)
check_fallback('escape-table',vars(rfc8785._impl),'_ESCAPE_DCT',dict(rfc8785._impl._ESCAPE_DCT)|{'\n':'changed'},'\n')
check_fallback('stdlib-class',vars(json),'JSONEncoder',object)
check_fallback('stdlib-c-encoder',vars(json.encoder),'c_make_encoder',None)
check_fallback('stdlib-string-encoder',vars(json.encoder),'encode_basestring',forbidden)
function=rfc8785.dumps; original=function.__code__
try:
    function.__code__=(lambda value:b'"code-replacement"').__code__
    assert not candidate['_fast_allowed']();compare({'x':1},'fallback-code-change');fallbacks.append('code-change')
finally:function.__code__=original
keywords=json.JSONEncoder.__init__.__kwdefaults__;original=keywords['indent']
try:
    keywords['indent']=2
    assert not candidate['_fast_allowed']();compare({'x':1},'fallback-keyword-change');fallbacks.append('keyword-change')
finally:keywords['indent']=original
for name,replacement in [('MAX_BYTES',20),('check_tree',lambda value:None)]:
    old_ref,old_cand=reference[name],candidate[name]
    try:
        reference[name]=candidate[name]=replacement
        assert not candidate['_fast_allowed']();compare(b'x' if name=='check_tree' else 'x'*21,'fallback-'+name)
        fallbacks.append(name)
    finally:reference[name],candidate[name]=old_ref,old_cand
assert candidate['_fast_allowed']() and not hooks
# Observe the unmodified reference function: floats must route the entire value.
routes=[]
for label,value,wanted in [('integer',{'x':[1]},0),('root-float',0.1,1),('nested-float',{'x':[1,0.1]},1)]:
    calls=[];code=rfc8785.dumps.__code__
    def profile(frame,event,arg):
        if event=='call' and frame.f_code is code:calls.append(1)
    sys.setprofile(profile)
    try:candidate['canonical'](value)
    finally:sys.setprofile(None)
    assert len(calls)==wanted
    routes.append(dict(input=label,originalEncoderCalls=len(calls)))
original={'z':[{'é':1}],'a':[2]};prepared=candidate['_integer_tree'](original)
assert prepared==original and prepared is not original and prepared['z'] is not original['z'] and prepared['z'][0] is not original['z'][0]
prepared['z'][0]['é']=9;assert original['z'][0]['é']==1

documents=[json.loads(verify(path)) for path in sorted((BASE/'documents').glob('*.json'))]
assert len(documents)==8
before=json.dumps(documents,sort_keys=True,ensure_ascii=True)
for i,document in enumerate(documents):compare(document,'document-'+str(i),True)
samples=[]
for namespace in (reference,candidate):
    for document in documents:namespace['canonical'](document)
for round_number in range(9):
    order=[('reference',reference),('candidate',candidate)]
    if round_number%2:order.reverse()
    for label,namespace in order:
        function=namespace['canonical'];wall=time.perf_counter_ns();cpu=time.process_time_ns()
        for _ in range(32):
            for document in documents:function(document)
        samples.append(dict(round=round_number,implementation=label,calls=256,
            cpuNanoseconds=time.process_time_ns()-cpu,wallNanoseconds=time.perf_counter_ns()-wall))
assert json.dumps(documents,sort_keys=True,ensure_ascii=True)==before and not denied and not hooks
for name in pins:verify(Path(name))
for row in external['files']:
    assert hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()==row['sha256']
medians={label:statistics.median(row['cpuNanoseconds'] for row in samples if row['implementation']==label) for label in ('reference','candidate')}
result=dict(status='passed',differentialCases=len(cases),cases=cases,unicodeScalarValues=unicode_scalars,
    fallbackChecks=fallbacks,originalEncoderRouting=routes,upstreamVectors=vectors,
    customHooksInvoked=len(hooks),prohibitedAttempts=denied,inputsUnchanged=True,documentInputsUnchanged=True,
    projectPackageImported=False,workerExecuted=False,productionChanged=False,physicalObjectiveVerified=False,
    extractedParserAndCanonicalizerTested=True,referenceValidationUnchanged=True,
    benchmarkRounds=9,callsPerSample=256,samples=samples,medianCpuNanoseconds=medians,
    candidateToReferenceMedianCpuRatio=medians['candidate']/medians['reference'],
    timingQualified=False,pythonVersion=sys.version,systemLibraryClosureAttested=False)
encoded=json.dumps(result,indent=2,allow_nan=False);assert len(encoded.encode())<=4194304
print(encoded)
