"""Closed planning records. Attached discovery is attributed, not trusted evidence."""
import hashlib
import re

from hms.contracts import ContractError, SAFE_INTEGER, canonical, identifier, parse_json
from hms.api_contracts import validate_params, validate_result, _shape
from hms.pat_contracts import PatError, parse_pat, validate_parameters, matches_static

MAX_REQUEST = 32768
MAX_RECORD = 65536
QUALIFICATION = {'state': 'unavailable', 'reason': 'PUBLIC_QUALIFICATION_MOUNT_UNAVAILABLE'}
READ_METHODS = frozenset({'discover', 'describe', 'observe'})
METHODS = frozenset({'intent_put', 'intent_get', 'proposal_put'})


class HandoffError(RuntimeError):
    def __init__(self, code):
        self.code = 'IH_' + code
        super().__init__(self.code)


def require(condition, code='INVALID_INPUT'):
    if not condition:
        raise HandoffError(code)


def closed(value, fields):
    require(type(value) is dict and set(value) == set(fields))


def integer(value, minimum=0, maximum=SAFE_INTEGER):
    require(type(value) is int and minimum <= value <= maximum)


def text(value, maximum, *, minimum=1):
    require(type(value) is str)
    require(minimum <= len(value.encode('utf-8')) <= maximum)


def name(value):
    identifier(value)


def digest(value):
    require(type(value) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', value) is not None)


def identity(domain, value):
    return 'sha256:' + hashlib.sha256(domain.encode('ascii') + b'\0' + canonical(value)).hexdigest()


def detached(value):
    return parse_json(canonical(value))


def attribution(value):
    closed(value, {'kind', 'sessionId', 'callId', 'model'})
    require(value['kind'] in ('external-agent', 'harness-agent', 'scripted-fixture'))
    for field in ('sessionId', 'callId', 'model'):
        if value[field] is not None:
            text(value[field], 256)


def discovery(value):
    require(type(value) is list and len(value) <= 8)
    require(len(canonical(value)) <= 16384)
    for row in value:
        closed(row, {'method', 'params', 'reply', 'sessionId', 'callId'})
        method, params, reply = row['method'], row['params'], row['reply']
        require(type(method) is str and method in READ_METHODS)
        validate_params(method, params)
        require(type(reply) is dict and type(reply.get('ok')) is bool)
        if reply['ok']:
            closed(reply, {'ok', 'result'})
            validate_result(method, reply['result'], params)
        else:
            closed(reply, {'ok', 'error', 'outcome'})
            _shape('error', reply['error'])
            require(reply['outcome'] == 'unconfirmed')
        # Existing API shape/correlation checks do not authenticate the supplied
        # reply or make it fresh authority, device truth or qualification.
        for field in ('sessionId', 'callId'):
            if row[field] is not None:
                text(row[field], 256)


def validate_request(method, value):
    """Validate original types before canonical JSON can normalize 1.0 to 1."""
    require(type(method) is str and method in METHODS, 'UNKNOWN_METHOD')
    require(len(canonical(value)) <= MAX_REQUEST)
    if method == 'intent_put':
        closed(value, {'profile', 'applicationId', 'operationKey', 'expectedRevision', 'prompt'})
        require(value['profile'] == 'hms.application-intent/0.1')
        name(value['applicationId']); name(value['operationKey'])
        integer(value['expectedRevision'])
        text(value['prompt'], 8192)
    elif method == 'intent_get':
        require(type(value) is dict and set(value) in ({'applicationId'}, {'applicationId', 'revision'}))
        name(value['applicationId'])
        if 'revision' in value:
            integer(value['revision'], 1)
    else:
        closed(value, {'profile', 'applicationId', 'intentRevision', 'operationKey',
                      'expectedHandoffDigest', 'interpretation', 'discovery', 'proposal', 'plannerAttribution'})
        require(value['profile'] == 'hms.application-proposal/0.1')
        name(value['applicationId']); name(value['operationKey'])
        integer(value['intentRevision'], 1); digest(value['expectedHandoffDigest'])
        text(value['interpretation'], 4096)
        discovery(value['discovery']); attribution(value['plannerAttribution'])
        proposal = value['proposal']
        require(type(proposal) is dict)
        if proposal.get('kind') == 'supported_candidate':
            closed(proposal, {'kind', 'artifact', 'initialParameters'})
            artifact = parse_pat(proposal['artifact'])
            parameters = validate_parameters(artifact, proposal['initialParameters'])
            require(matches_static(artifact, parameters, task_kind=artifact['taskKind'],
                input_profile=artifact['inputProfile'], evidence_mode='simulation'), 'INITIAL_PARAMETERS_NOT_APPLICABLE')
        else:
            closed(proposal, {'kind', 'reason', 'details'})
            require(proposal['kind'] == 'unresolved' and proposal['reason'] in
                    ('unsupported_capability', 'unsupported_profile', 'ambiguous_intent', 'context_unavailable'))
            text(proposal['details'], 4096)
    return detached(value)


def checked_request(method, value):
    try:
        return validate_request(method, value)
    except HandoffError:
        raise
    except (ContractError, PatError, UnicodeError, TypeError, ValueError, KeyError, RecursionError) as error:
        raise HandoffError('INVALID_INPUT') from error
