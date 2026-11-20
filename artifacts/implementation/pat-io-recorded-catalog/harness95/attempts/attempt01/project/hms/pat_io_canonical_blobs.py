"""Bounded reuse of successful exact-byte document validation in trusted trials.

Only an immutable byte string's canonical-JSON validation is reused. Callers
still read current storage and check its schema, counts, classes and sizes.
This is not a database, permission, binding, source-identity or outcome cache.
"""
from collections import OrderedDict
import json
from types import FunctionType

from . import contracts
from ._vendor import rfc8785
from ._vendor.rfc8785 import _impl as encoder

MAX_ENTRIES = 64
MAX_RETAINED_BYTES = 128 * 1024
MAX_DOCUMENT_BYTES = 65536


def _anchor(value):
    return (value, value.__code__, value.__defaults__, value.__kwdefaults__)


def _same_function(value, anchor):
    return (value is anchor[0] and type(value) is FunctionType and
            value.__code__ is anchor[1] and value.__defaults__ is anchor[2] and
            value.__kwdefaults__ is anchor[3])


def _dependencies_unchanged(canonical, parser):
    if canonical is not _CANONICAL or parser is not _PARSER:
        return False
    for namespace, name, anchor in _FUNCTIONS:
        if not _same_function(namespace.get(name), anchor):
            return False
    for namespace, name, kind, expected in _CONSTANTS:
        value = namespace.get(name)
        if type(value) is not kind or value != expected:
            return False
    for namespace, name, expected in _OBJECTS:
        if namespace.get(name) is not expected:
            return False
    escapes = encoder._ESCAPE_DCT
    return (type(escapes) is dict and len(escapes) == len(_ESCAPES) and
            all(type(key) is str and type(value) is str for key, value in escapes.items()) and
            escapes == _ESCAPES)


class CanonicalBlobs:
    """Per-engine LRU of immutable byte keys; invalid inputs are never retained.

    Dependency changes clear reuse and take the original validation path. These
    selected guards are conservative compatibility checks, not Python-process
    attestation. The worker's original installed-image and source checks remain.
    """
    def __init__(self):
        self._entries = OrderedDict()
        self.retained_bytes = 0

    @staticmethod
    def _validate(value, canonical, parser):
        return type(value) is bytes and canonical(parser(value)) == value

    def is_canonical(self, value, *, canonical, parser):
        allowed = _dependencies_unchanged(canonical, parser)
        if not allowed:
            self._entries.clear()
            self.retained_bytes = 0
        cacheable = allowed and type(value) is bytes and 0 < len(value) <= MAX_DOCUMENT_BYTES
        if cacheable and value in self._entries:
            self._entries.move_to_end(value)
            return True
        valid = self._validate(value, canonical, parser)
        if valid and cacheable and _dependencies_unchanged(canonical, parser):
            while self._entries and (len(self._entries) >= MAX_ENTRIES or
                    self.retained_bytes + len(value) > MAX_RETAINED_BYTES):
                old, _ = self._entries.popitem(last=False)
                self.retained_bytes -= len(old)
            if len(value) <= MAX_RETAINED_BYTES:
                self._entries[value] = True
                self.retained_bytes += len(value)
        return valid


_CANONICAL, _PARSER = contracts.canonical, contracts.parse_json
_FUNCTIONS = tuple((namespace, name, _anchor(value))
    for namespace in (vars(contracts), vars(rfc8785), vars(encoder), vars(json),
                      vars(json.decoder), vars(json.scanner), vars(json.JSONDecoder))
    for name, value in tuple(namespace.items()) if type(value) is FunctionType)
_CONSTANTS = tuple((namespace, name, type(namespace[name]), namespace[name])
    for namespace, names in (
        (globals(), ('MAX_ENTRIES', 'MAX_RETAINED_BYTES', 'MAX_DOCUMENT_BYTES')),
        (vars(contracts), ('MAX_BYTES', 'MAX_DEPTH', 'MAX_NODES', 'SAFE_INTEGER')),
        (vars(encoder), ('_INT_MIN', '_INT_MAX')))
    for name in names)
_OBJECTS = tuple((namespace, name, namespace[name]) for namespace, names in (
    (vars(contracts), ('json', 'math', 'Decimal', 'DecimalException', 'rfc8785', 'ContractError')),
    (vars(encoder), ('math', 'BytesIO', '_ESCAPE', 'CanonicalizationError', 'IntegerDomainError', 'FloatDomainError')),
    (vars(json), ('JSONDecoder',)),
    (vars(json.decoder), ('scanstring', 'scanner', 'WHITESPACE', 'WHITESPACE_STR', 'BACKSLASH', 'STRINGCHUNK')),
    (vars(json.scanner), ('make_scanner',))) for name in names)
_ESCAPES = dict(encoder._ESCAPE_DCT)
