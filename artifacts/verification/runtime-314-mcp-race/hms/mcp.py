"""Bounded local MCP tool projection; durable operations belong to HMS, not MCP.

Supports stdio MCP 2026-07-28 and the 2025-11-25 initialization handshake.
No network listener, SDK dependency, implicit daemon startup, or automatic retry.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import threading
import time

from .api_contracts import METHOD_RESULTS, ResponseError, validate_params, validate_result
from .client import Client
from .contracts import ContractError, SAFE_INTEGER, parse_json
from .ipc import IpcError, _code
from .journal import JournalError

MODERN = '2026-07-28'
LEGACY = '2025-11-25'
PREFIX = 'io.modelcontextprotocol/'
SERVER_INFO = {'name': 'hms-local', 'version': '0.1.0'}
CAPABILITIES = {'tools': {'listChanged': False}}
MAX_CALLS = 8
MAX_SUBSCRIPTIONS = 8
RATE = 8.0
BURST = 16.0
INSTRUCTIONS = (
    'Local HMS simulator; all clients running under this Unix UID share authority. '
    'Discover and describe devices, allocate a bounded replay namespace, prepare an intent, '
    'and retain the entire prepared request before invoking it. Preparation is advisory. '
    'Poll hardware_operation and hardware_events using the returned operationId. '
    'A completed simulation does not verify a physical effect. MCP cancellation, timeout, '
    'process exit, and malformed or lost replies do not cancel or roll back an HMS operation. '
    'Use hardware_cancel explicitly, then inspect its durable state. Never automatically '
    'retry a mutation or create a new operation key to recover a lost reply. A deliberate '
    'exact replay is possible only while the retained replay namespace remains valid. '
    'Request IDs and clientInfo are correlation/display metadata, never authority.'
)
DESCRIPTIONS = {
    'discover': 'List authorized local devices with bounded pagination; presence is not a completion claim.',
    'describe': 'Read a device type, binding, generations, limits, units, and execution contract.',
    'observe': 'Read evidence with explicit age and evidence-kind requirements; simulation is not physical evidence.',
    'namespace': 'Allocate a durable replay namespace with explicit expiry. Retain it; repeated calls allocate new namespaces.',
    'prepare': 'Prepare and digest an immutable action request without admitting it. Retain the entire request before invocation.',
    'invoke': 'Admit the exact retained request once. Never replace its operation key or generations to recover a lost reply; inspect the operation or deliberately replay the identical request within its valid namespace.',
    'operation': 'Read durable execution, cancellation, evidence, and resource-claim state for an operation.',
    'events': 'Read bounded, ordered durable operation events after an explicit cursor.',
    'cancel': 'Request HMS operation cancellation explicitly. This is not an emergency stop or proof of quiescence; inspect the returned operation and subsequent evidence.',
}


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _closed(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def catalog():
    """Project exact local schemas, retaining only their reachable local definitions."""
    schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas/local-api.schema.json').read_text())
    definitions = schema['$defs']

    def bundle(root):
        result = copy.deepcopy(root)
        found = {}

        def visit(value):
            if isinstance(value, dict):
                if '$ref' in value:
                    ref = value['$ref']
                    if not ref.startswith('#/$defs/') or ref[8:] not in definitions:
                        raise ValueError('MCP projection requires local known schema references')
                    name = ref[8:]
                    if name not in found:
                        found[name] = copy.deepcopy(definitions[name])
                        visit(found[name])
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(result)
        result['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
        if found:
            result['$defs'] = found
        return result

    tools = []
    for method in sorted(METHOD_RESULTS):
        error = _closed({'ok': {'const': False}, 'error': _closed({
            'code': {'type': 'string', 'pattern': '^[A-Z][A-Z0-9_]{0,63}$'},
            'outcome': {'const': 'unconfirmed'}})})
        success = _closed({'ok': {'const': True}, 'result': {'$ref': '#/$defs/' + METHOD_RESULTS[method]}})
        tools.append({'name': 'hardware_' + method, 'description': DESCRIPTIONS[method],
                      'inputSchema': bundle(definitions[method + 'Params']),
                      'outputSchema': bundle({'type': 'object', 'oneOf': [success, error]}),
                      'annotations': {'readOnlyHint': method not in {'namespace', 'invoke', 'cancel'},
                                      'destructiveHint': method in {'invoke', 'cancel'},
                                      'idempotentHint': False, 'openWorldHint': False}})
    return tools


class ProtocolError(Exception):
    def __init__(self, code, message, data=None):
        self.code, self.message, self.data = code, message, data


class TransportClosed(Exception):
    """Fatal framing, duplicate in-flight IDs, or bounded-output exhaustion."""


def _id(value):
    return ((type(value) is str and len(value) <= 128) or
            (type(value) is int and abs(value) <= SAFE_INTEGER))


def _fields(params, required=(), optional=()):
    if type(params) is not dict or not set(required) <= params.keys() or params.keys() - set(required) - set(optional):
        raise ProtocolError(-32602, 'Invalid method parameters')


def _implementation(value):
    if type(value) is not dict or not all(type(value.get(k)) is str for k in ('name', 'version')):
        return False
    if any(type(value[k]) is not str for k in ('title', 'description', 'websiteUrl') if k in value):
        return False
    if 'icons' not in value:
        return True
    if type(value['icons']) is not list:
        return False
    for icon in value['icons']:
        if type(icon) is not dict or type(icon.get('src')) is not str:
            return False
        if 'mimeType' in icon and type(icon['mimeType']) is not str:
            return False
        if 'theme' in icon and (type(icon['theme']) is not str or icon['theme'] not in {'light', 'dark'}):
            return False
        if 'sizes' in icon and (type(icon['sizes']) is not list or any(type(v) is not str for v in icon['sizes'])):
            return False
    return True


_LABEL = r'[A-Za-z](?:[A-Za-z0-9-]*[A-Za-z0-9])?'
_NAME = r'(?:[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?)?'
_META_KEY = re.compile(r'(?:' + _LABEL + r'(?:\.' + _LABEL + r')*/)?' + _NAME)


def _capabilities(value):
    if type(value) is not dict:
        return False
    for name in ('roots', 'sampling', 'elicitation', 'experimental', 'extensions'):
        if name in value and type(value[name]) is not dict:
            return False
    for name, keys in (('sampling', ('context', 'tools')), ('elicitation', ('form', 'url'))):
        if name in value and any(type(value[name][key]) is not dict for key in keys if key in value[name]):
            return False
    for name in ('experimental', 'extensions'):
        if name in value and any(type(v) is not dict for v in value[name].values()):
            return False
    if 'extensions' in value and any('/' not in key or not _META_KEY.fullmatch(key) for key in value['extensions']):
        return False
    return True  # Unknown capability members remain open and unused.


def _metadata(value):
    if type(value) is not dict:
        raise ProtocolError(-32602, 'Missing or invalid per-request metadata')
    version = value.get(PREFIX + 'protocolVersion')
    if (type(version) is not str or not _capabilities(value.get(PREFIX + 'clientCapabilities')) or
            any(not _META_KEY.fullmatch(key) for key in value) or
            'progressToken' in value and type(value['progressToken']) not in (str, int, float)):
        raise ProtocolError(-32602, 'Missing or invalid per-request metadata')
    if version != MODERN:
        raise ProtocolError(-32022, 'Unsupported version; 2025-11-25 requires initialize',
                            {'supported': [MODERN, LEGACY], 'requested': version})
    if PREFIX + 'clientInfo' in value and not _implementation(value[PREFIX + 'clientInfo']):
        raise ProtocolError(-32602, 'Invalid clientInfo')
    if PREFIX + 'logLevel' in value and (type(value[PREFIX + 'logLevel']) is not str or
            value[PREFIX + 'logLevel'] not in {
                'debug', 'info', 'notice', 'warning', 'error', 'critical', 'alert', 'emergency'}):
        raise ProtocolError(-32602, 'Invalid log level')
    # Capabilities are never used as authentication or to request client actions.


@dataclass
class _Call:
    id: object
    modern: bool
    cancelled: threading.Event = field(default_factory=threading.Event)


class Projection:
    """Thread-safe protocol state with a bounded number of one-attempt client calls.

    emit must enqueue synchronously without blocking. A response is committed when
    emit accepts it; a subsequent cancellation can race with delivery of that response.
    """
    def __init__(self, client, emit, *, clock=time.monotonic):
        self.client, self.emit, self.clock = client, emit, clock
        self.tools = catalog()
        self.tool_names = {tool['name']: tool['name'][9:] for tool in self.tools}
        digest = hashlib.sha256(dumps(self.tools).encode()).hexdigest()
        self.pages = {f'{digest}:{n}': n for n in range(3, len(self.tools), 3)}
        self.page_tokens = {n: cursor for cursor, n in self.pages.items()}
        self.lock = threading.RLock()
        self.calls = {}
        self.subscriptions = set()
        self.legacy = 'new'
        self.closed = False
        self.tokens, self.last_refill = BURST, clock()

    def close(self):
        with self.lock:
            self.closed = True
            for call in self.calls.values():
                call.cancelled.set()
            self.subscriptions.clear()

    def _result(self, request_id, result, modern):
        if modern:
            result = {**result, 'resultType': 'complete', '_meta': {PREFIX + 'serverInfo': SERVER_INFO}}
        self.emit({'jsonrpc': '2.0', 'id': request_id, 'result': result})

    def _error(self, request_id, error):
        body = {'code': error.code, 'message': error.message}
        if error.data is not None:
            body['data'] = error.data
        message = {'jsonrpc': '2.0', 'error': body}
        if request_id is not None:
            message['id'] = request_id
        self.emit(message)

    def receive(self, data):
        with self.lock:
            if self.closed:
                return
            try:
                value = parse_json(data)
            except ContractError:
                self._error(None, ProtocolError(-32700, 'Invalid or unsupported JSON frame'))
                return
            if type(value) is not dict or value.get('jsonrpc') != '2.0' or type(value.get('method')) is not str:
                self._error(None, ProtocolError(-32600, 'Invalid request'))
                return
            notification = 'id' not in value
            request_id = value.get('id')
            if not notification and not _id(request_id):
                self._error(None, ProtocolError(-32600, 'Invalid request ID'))
                return
            if value.keys() - {'jsonrpc', 'id', 'method', 'params'}:
                if not notification:
                    self._error(request_id, ProtocolError(-32600, 'Invalid request fields'))
                return
            params = value.get('params', {})
            if notification:
                self._notification(value['method'], params)
                return
            if request_id in self.calls or request_id in self.subscriptions:
                raise TransportClosed('duplicate in-flight request ID')
            try:
                self._request(request_id, value['method'], params)
            except ProtocolError as error:
                self._error(request_id, error)

    def _notification(self, method, params):
        if type(params) is not dict:
            return
        if method == 'notifications/initialized' and self.legacy == 'initializing':
            if not params or set(params) == {'_meta'} and type(params['_meta']) is dict:
                self.legacy = 'ready'
        elif method == 'notifications/cancelled':
            request_id = params.get('requestId')
            if (not _id(request_id) or params.keys() - {'requestId', 'reason', '_meta'} or
                    ('reason' in params and type(params['reason']) is not str) or
                    ('_meta' in params and type(params['_meta']) is not dict)):
                return
            self.subscriptions.discard(request_id)
            if request_id in self.calls:
                self.calls[request_id].cancelled.set()

    def _request(self, request_id, method, params):
        if type(params) is not dict:
            raise ProtocolError(-32602, 'Parameters must be an object')
        meta = params.get('_meta', {})
        if type(meta) is not dict:
            raise ProtocolError(-32602, 'Metadata must be an object')
        modern = method == 'server/discover' or any(key.startswith(PREFIX) for key in meta)
        if modern:
            _metadata(meta)
        elif method == 'initialize':
            _fields(params, ('protocolVersion', 'capabilities', 'clientInfo'), ('_meta',))
            if (self.legacy != 'new' or type(params['protocolVersion']) is not str or
                    not _capabilities(params['capabilities']) or not _implementation(params['clientInfo'])):
                raise ProtocolError(-32602, 'Invalid or repeated initialization')
            self.legacy = 'initializing'
            self._result(request_id, {'protocolVersion': LEGACY, 'capabilities': CAPABILITIES,
                                     'serverInfo': SERVER_INFO, 'instructions': INSTRUCTIONS}, False)
            return
        elif self.legacy != 'ready' and method != 'ping':
            raise ProtocolError(-32602, 'Use 2026-07-28 request metadata or initialize 2025-11-25')
        clean = {key: value for key, value in params.items() if key != '_meta'}
        if method == 'server/discover':
            _fields(clean)
            self._result(request_id, {'supportedVersions': [MODERN, LEGACY], 'capabilities': CAPABILITIES,
                                     'instructions': INSTRUCTIONS, 'ttlMs': 60000, 'cacheScope': 'private'}, True)
        elif method == 'ping' and not modern:
            _fields(clean)
            self._result(request_id, {}, False)
        elif method == 'tools/list':
            _fields(clean, optional=('cursor',))
            cursor = clean.get('cursor')
            if 'cursor' in clean and (type(cursor) is not str or cursor not in self.pages):
                raise ProtocolError(-32602, 'Invalid tool-list cursor')
            start = self.pages[cursor] if 'cursor' in clean else 0
            result = {'tools': self.tools[start:start + 3]}
            if start + 3 < len(self.tools):
                result['nextCursor'] = self.page_tokens[start + 3]
            if modern:
                result.update(ttlMs=60000, cacheScope='private')
            self._result(request_id, result, modern)
        elif method == 'subscriptions/listen' and modern:
            _fields(clean, ('notifications',))
            filters = clean['notifications']
            _fields(filters, optional=('toolsListChanged', 'promptsListChanged', 'resourcesListChanged', 'resourceSubscriptions'))
            if any(type(v) is not bool for k, v in filters.items() if k != 'resourceSubscriptions'):
                raise ProtocolError(-32602, 'Invalid subscription filter')
            if 'resourceSubscriptions' in filters and (type(filters['resourceSubscriptions']) is not list or
                    any(type(v) is not str for v in filters['resourceSubscriptions'])):
                raise ProtocolError(-32602, 'Invalid resource subscription filter')
            if len(self.subscriptions) >= MAX_SUBSCRIPTIONS:
                raise ProtocolError(1001, 'Subscription capacity reached')
            self.subscriptions.add(request_id)
            # This profile has a static tool list and no resource notifications.
            self.emit({'jsonrpc': '2.0', 'method': 'notifications/subscriptions/acknowledged',
                       'params': {'_meta': {PREFIX + 'subscriptionId': request_id}, 'notifications': {}}})
        elif method == 'tools/call':
            _fields(clean, ('name',), ('arguments',))
            name = clean['name']
            if type(name) is not str or name not in self.tool_names:
                raise ProtocolError(-32602, 'Unknown hardware tool')
            arguments = clean.get('arguments', {})
            if type(arguments) is not dict:
                raise ProtocolError(-32602, 'Tool arguments must be an object')
            if len(self.calls) >= MAX_CALLS:
                raise ProtocolError(1001, 'Concurrent tool-call capacity reached')
            now = self.clock()
            self.tokens = min(BURST, self.tokens + max(0, now - self.last_refill) * RATE)
            self.last_refill = now
            if self.tokens < 1:
                raise ProtocolError(1002, 'Tool-call rate limit reached')
            self.tokens -= 1
            call = _Call(request_id, modern)
            self.calls[request_id] = call
            threading.Thread(target=self._call, args=(call, self.tool_names[name], arguments), daemon=True).start()
        else:
            raise ProtocolError(-32601, 'Method is not supported by this profile')

    def _call(self, call, method, arguments):
        try:
            if call.cancelled.is_set():
                return
            validate_params(method, arguments)
            result = self.client.request(method, arguments)
            validate_result(method, result, arguments)
            reply = {'ok': True, 'result': result}
        except (ContractError, IpcError, JournalError) as error:
            reply = {'ok': False, 'error': {'code': _code(error), 'outcome': 'unconfirmed'}}
        except OSError:
            reply = {'ok': False, 'error': {'code': 'LOCAL_IO_ERROR', 'outcome': 'unconfirmed'}}
        except Exception:
            reply = {'ok': False, 'error': {'code': 'INTERNAL_ERROR', 'outcome': 'unconfirmed'}}
        finally:
            with self.lock:
                self.calls.pop(call.id, None)
                if not self.closed and not call.cancelled.is_set():
                    self._result(call.id, {'content': [{'type': 'text', 'text': dumps(reply)}],
                                          'structuredContent': reply, 'isError': not reply['ok']}, call.modern)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local HMS MCP stdio projection (simulation only)')
    parser.add_argument('--socket', type=Path, required=True)
    args = parser.parse_args(argv)
    from .mcp_stdio import serve
    return serve(Client(args.socket))


if __name__ == '__main__':
    raise SystemExit(main())
