"""Closed typed job/replay contracts. No dynamic executable or caller paths."""
import hashlib
import json
import re
from pathlib import Path

IMPORTED_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

PROFILE = 'hms.host.cpu-series/0.1'
OUTPUT_PROFILE = 'hms.host.cpu-series-result/0.1'
MAX_KEYS = 16
STATE_BYTES = 65536
MAX_STREAM = 4096
DEFAULT_LIMITS = dict(cpuSeconds=2, addressBytes=128*1024*1024,
                      fileBytes=4096, openFiles=32, wallMs=4000,
                      stopGraceMs=100, settleGraceMs=1000, streamBytes=2048)
CEILINGS = dict(cpuSeconds=(1,5), addressBytes=(64*1024*1024,256*1024*1024),
                fileBytes=(1,4096), openFiles=(16,32), wallMs=(100,10000),
                stopGraceMs=(1,500), settleGraceMs=(1,2000), streamBytes=(128,MAX_STREAM))


class JobError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code='INVALID'):
    if not condition:
        raise JobError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def parse(body, maximum=STATE_BYTES):
    require(type(body) is bytes and 0 < len(body) <= maximum, 'DOCUMENT_SIZE')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_KEY')
            result[key] = value
        return result
    try:
        result = json.loads(body, object_pairs_hook=pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(JobError('NUMBER')))
        require(canonical(result) == body, 'NONCANONICAL')
        return result
    except (ValueError, TypeError, RecursionError) as error:
        raise JobError('DOCUMENT') from error


def exact(value, keys):
    require(type(value) is dict and set(value) == set(keys), 'FIELDS')


def integer(value, low, high):
    require(type(value) is int and low <= value <= high, 'INTEGER')


def digest(body):
    return 'sha256:' + hashlib.sha256(body).hexdigest()


def fingerprint(value):
    require(type(value) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', value), 'DIGEST')


def key(value):
    exact(value, ('deployment', 'caller', 'operation'))
    for item in value.values():
        require(type(item) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,47}', item), 'KEY')
    return tuple(value[name] for name in ('deployment', 'caller', 'operation'))


def request(value):
    # Structural replay parsing intentionally does not inspect current code.
    try:
        body = canonical(value)
    except (TypeError, ValueError, RecursionError) as error:
        raise JobError('REQUEST') from error
    require(len(body) <= 2048, 'REQUEST_SIZE')
    value = parse(body, 2048)
    exact(value, ('profile', 'key', 'artifact', 'input', 'limits'))
    require(value['profile'] == PROFILE, 'PROFILE')
    key(value['key']); fingerprint(value['artifact'])
    inp = value['input']; exact(inp, ('first', 'step', 'count'))
    integer(inp['first'], -(2**31), 2**31-1)
    integer(inp['step'], -32768, 32767)
    integer(inp['count'], 0, 50_000_000)
    exact(value['limits'], CEILINGS)
    for name, (low, high) in CEILINGS.items():
        integer(value['limits'][name], low, high)
    return value


def request_digest(value):
    return digest(b'HMS-OWNED-HOST-JOB-REQUEST-v1\0' + canonical(value))


def identifier(value):
    return hashlib.sha256(b'HMS-OWNED-HOST-JOB-KEY-v1\0' + canonical(value)).hexdigest()


def expected_result(inp):
    a, d, n = inp['first'], inp['step'], inp['count']
    total = n*a*a + a*d*n*(n-1) + d*d*n*(n-1)*(2*n-1)//6
    return {'count': n, 'sumSquaresMod64': str(total % (1 << 64))}


def typed_result(result):
    exact(result, ('count', 'sumSquaresMod64'))
    integer(result['count'], 0, 50_000_000)
    number = result['sumSquaresMod64']
    require(type(number) is str and re.fullmatch(r'0|[1-9][0-9]{0,19}', number) and
            int(number) < 1 << 64, 'OUTPUT_INTEGER')
    return result


def validate_output(body, row):
    value = parse(body, 2048)
    exact(value, ('profile', 'requestDigest', 'nonce', 'artifact', 'result'))
    require(value['profile'] == OUTPUT_PROFILE and value['requestDigest'] == row['digest'] and
            value['nonce'] == row['nonce'] and value['artifact'] == row['request']['artifact'], 'OUTPUT_ASSOCIATION')
    typed_result(value['result'])
    require(value['result'] == expected_result(row['request']['input']), 'OUTPUT_RESULT')
    return value
