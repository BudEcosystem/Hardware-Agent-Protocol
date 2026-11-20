"""Checked isolated consumer seam; no model, transport or qualification mount."""
from hms.contracts import ContractError, canonical, parse_json
from hms.api_contracts import validate_params
from . import integrity
from .contracts import HandoffError, METHODS, READ_METHODS, closed, detached, discovery, require


class Dispatcher:
    """The embedding host supplies an authenticated principal at construction."""
    def __init__(self, store, *, principal):
        self._store, self._principal = store, principal

    def dispatch(self, wire):
        try:
            envelope = parse_json(wire)
            closed(envelope, {'method', 'params'})
            require(type(envelope['method']) is str and envelope['method'] in METHODS, 'UNKNOWN_METHOD')
            result = self._store.request(self._principal, envelope['method'], envelope['params'])
            return canonical({'ok': True, 'result': result})
        except HandoffError as error:
            return canonical({'ok': False, 'error': {'code': error.code}})
        except (ContractError, UnicodeError, TypeError, ValueError, KeyError, RecursionError):
            return canonical({'ok': False, 'error': {'code': 'IH_INVALID_INPUT'}})

    def request(self, method, params):
        # Direct in-process calls still validate original numeric types first.
        # Sending canonical JSON before validation could normalize 1.0 into 1.
        try:
            return {'ok': True, 'result': self._store.request(self._principal, method, params)}
        except HandoffError as error:
            return {'ok': False, 'error': {'code': error.code}}


class AgentConsumer:
    """An external/current agent calls this seam explicitly; no automatic planner.

    read_hardware is a trusted injected existing read-tool bridge, optional when
    only reading/submitting a retained handoff. It is never called on replay or
    startup. This object intentionally has no prepare/invoke/evaluate/run method.
    """
    def __init__(self, dispatcher, *, read_hardware=None):
        self.dispatcher, self._read_hardware = dispatcher, read_hardware

    def inspect(self, method, params):
        require(type(method) is str and method in READ_METHODS, 'READ_METHOD_REQUIRED')
        require(self._read_hardware is not None, 'DISCOVERY_UNAVAILABLE')
        try:
            integrity.verify(loaded=True)
            validate_params(method, params)
            retained = detached(params)
            reply = self._read_hardware(method, detached(retained))
            discovery([dict(method=method, params=retained, reply=reply, sessionId=None, callId=None)])
            integrity.verify(loaded=True)
            return detached(reply)
        except HandoffError:
            raise
        except (ContractError, UnicodeError, TypeError, ValueError, KeyError, RecursionError) as error:
            raise HandoffError('INVALID_DISCOVERY') from error

    def handoff(self, application_id):
        return self.dispatcher.request('intent_get', {'applicationId': application_id})

    def propose(self, request):
        return self.dispatcher.request('proposal_put', request)
