/** The local Python client owns SO_PEERCRED authentication and method-result validation. */
export const BRIDGE = String.raw`
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from hms.contracts import parse_json, ContractError
from hms.ipc import IpcError
from hms.client import Client
from hms.api_contracts import ResponseError
try:
    payload = parse_json(sys.stdin.buffer.read(65537))
    result = Client(Path(sys.argv[2])).request(payload['method'], payload['params'])
    output = {'ok': True, 'result': result}
except ResponseError:
    output = {'ok': False, 'error': {'code': 'INVALID_RESPONSE'}, 'outcome': 'unconfirmed'}
except (IpcError, ContractError) as error:
    output = {'ok': False, 'error': {'code': getattr(error, 'code', 'CONTRACT_ERROR')}, 'outcome': 'unconfirmed'}
print(json.dumps(output, allow_nan=False, separators=(',', ':')))
`
