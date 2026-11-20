"""Pure reproduction of original repository fixture data, with explicit labels.

The descriptor is the default descriptor() construction retained in
baseline/sources/tests/test_pat_compiler.py. No test module or Runtime executes.
"""
from pathlib import Path
import copy
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from hms.demo import definitions
from hms.registry import validate_type_bundle

HERE = Path(__file__).resolve().parent


def descriptor():
    bundle = copy.deepcopy(definitions()[0][2])
    digest = validate_type_bundle(bundle)
    execution = bundle['execution']
    binding = {'profile':'hms.binding/0.1','instanceId':'sim:home-fan','generation':'binding:1',
        'typeDigest':digest,'calibrationRevision':'calibration:1','controlGeneration':'control:1',
        'mode':'simulation','adapterId':'simulator:fixture',
        'resourceMap':{role:'resource:'+role for action in execution['actions'].values() for role in action['resources']},
        'argumentSchemas':{name:copy.deepcopy(value['inputSchema']) for name,value in execution['actions'].items()}}
    return {'type':bundle,'binding':binding,'endpointSession':'session:1','driverProfile':'sqlite-simulation',
        'driverDigest':'sha256:'+'a'*64,'installationDigest':'sha256:'+'b'*64,
        'argumentMetadata':{'set_level':{
            'level':{'unit':'percent','frame':None,'unitArgument':'unit','frameArgument':None},
            'unit':{'unit':None,'frame':None,'unitArgument':None,'frameArgument':None}}}}


if __name__ == '__main__':
    output = json.dumps(descriptor(), indent=2) + '\n'
    if sys.argv[1:] == ['--write']:
        (HERE/'fixtures/fan-descriptor.json').write_text(output)
    elif sys.argv[1:] == ['--check']:
        assert (HERE/'fixtures/fan-descriptor.json').read_text() == output
        assert (HERE/'fixtures/fan-artifact.json').read_bytes() == (ROOT/'tests/fixtures/pat-compiler.json').read_bytes()
        print(json.dumps({'artifactExactCopy':True,'descriptorExactPureDerivation':True,
            'descriptorSha256':hashlib.sha256(output.encode()).hexdigest(),
            'scope':'Static original fixture data only; digest labels are not attestation.'}))
    else:
        raise SystemExit('usage: derive_fixtures.py --write|--check')
