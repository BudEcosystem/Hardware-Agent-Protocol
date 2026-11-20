"""Bounded host request parsing and versioned intent identity (experimental)."""
from __future__ import annotations

from decimal import Decimal, DecimalException
import hashlib
import json
import math
from pathlib import Path
import re

from jsonschema import Draft202012Validator

from ._vendor import rfc8785

MAX_BYTES = 65536
MAX_DEPTH = 32
MAX_NODES = 16384
SAFE_INTEGER = 2**53 - 1
DIGEST_PREFIX = b"HMS-INTENT-JCS-SHA256-v0.1\x00"


class ContractError(ValueError):
    """Invalid wire input; never authorizes admission."""


def _number(token: str):
    if len(token) > 128:
        raise ContractError("number token too long")
    try:
        decimal = Decimal(token)
    except DecimalException as error:
        raise ContractError("number exponent outside supported range") from error
    if not decimal.is_finite() or (decimal.is_zero() and decimal.is_signed()):
        raise ContractError("non-finite number or negative zero")
    if not any(c in token for c in ".eE"):
        value = int(token)
        if abs(value) > SAFE_INTEGER:
            raise ContractError("integer exceeds exact interoperable range")
        return value
    value = float(token)
    if not math.isfinite(value) or (value.is_integer() and abs(value) > SAFE_INTEGER):
        raise ContractError("number exceeds host numeric profile")
    # Compare decimal values, not binary approximations of customary 0.1 etc.
    # Excess supplied precision and underflow cannot silently change intent.
    if Decimal(repr(value)) != decimal:
        raise ContractError("number would lose supplied decimal precision")
    return value


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate JSON object field")
        result[key] = value
    return result


def _bad_constant(_):
    raise ContractError("non-JSON numeric constant")


def check_tree(value):
    """Validate in-memory JSON before canonicalization; reject implicit coercion."""
    stack = [(value, 0)]
    count = 0
    string_bytes = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if depth > MAX_DEPTH or count > MAX_NODES:
            raise ContractError("JSON depth/node limit exceeded")
        if type(item) is dict:
            if count + len(stack) + 2 * len(item) > MAX_NODES:
                raise ContractError("JSON node limit exceeded")
            for key, child in item.items():
                if type(key) is not str:
                    raise ContractError("JSON object keys must be strings")
                stack.append((key, depth + 1))
                stack.append((child, depth + 1))
        elif type(item) is list:
            if count + len(stack) + len(item) > MAX_NODES:
                raise ContractError("JSON node limit exceeded")
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            if len(item) > MAX_BYTES:
                raise ContractError("string exceeds host byte limit")
            try:
                string_bytes += len(item.encode("utf-8"))
            except UnicodeEncodeError as error:
                raise ContractError("lone Unicode surrogate") from error
            if string_bytes > MAX_BYTES:
                raise ContractError("strings exceed host byte limit")
        elif type(item) is int:
            if abs(item) > SAFE_INTEGER:
                raise ContractError("integer exceeds exact interoperable range")
        elif type(item) is float:
            if (not math.isfinite(item) or
                    (item == 0 and math.copysign(1, item) < 0) or
                    (item.is_integer() and abs(item) > SAFE_INTEGER)):
                raise ContractError("number exceeds host numeric profile")
        elif item is not None and type(item) is not bool:
            raise ContractError("unsupported JSON value")


def parse_json(data: bytes):
    if type(data) is not bytes or len(data) > MAX_BYTES:
        raise ContractError("expected at most 65536 UTF-8 bytes")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_object,
                           parse_int=_number, parse_float=_number,
                           parse_constant=_bad_constant)
        check_tree(value)
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ContractError("invalid bounded UTF-8 JSON") from error


def canonical(value) -> bytes:
    check_tree(value)
    try:
        result = _canonical_bytes(value)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ContractError("cannot canonicalize JSON") from error
    if len(result) > MAX_BYTES:
        raise ContractError("canonical value exceeds byte limit")
    return result


# Integer-only canonical byte path; original validation and float fallback remain.
from types import FunctionType as _FunctionType

_FAST_IMPL = rfc8785._impl


def _fast_anchor(function):
    if type(function) is not _FunctionType:
        return None
    keywords = function.__kwdefaults__
    return (function, function.__code__, function.__defaults__, keywords,
            None if keywords is None else tuple(keywords.items()))


def _fast_same(function, anchor):
    matched = (anchor is not None and type(function) is _FunctionType and
            function is anchor[0] and function.__code__ is anchor[1] and
            function.__defaults__ is anchor[2] and function.__kwdefaults__ is anchor[3])
    if not matched or anchor[4] is None:
        return matched
    keywords = function.__kwdefaults__
    return (type(keywords) is dict and len(keywords) == len(anchor[4]) and
            all(type(key) is str for key in keywords) and
            all(key in keywords and keywords[key] is value for key, value in anchor[4]))


_FAST_FUNCTIONS = tuple((namespace, name, _fast_anchor(namespace[name]))
    for namespace, names in (
        (globals(), ('check_tree',)),
        (vars(rfc8785), ('dumps', 'dump')),
        (vars(_FAST_IMPL), ('dumps', 'dump', '_serialize_str', '_serialize_float')),
        (vars(json.JSONEncoder), ('__init__', 'default', 'encode', 'iterencode')))
    for name in names)
_FAST_CONSTANTS = (MAX_BYTES, MAX_DEPTH, MAX_NODES, SAFE_INTEGER,
                   _FAST_IMPL._INT_MIN, _FAST_IMPL._INT_MAX)
_FAST_ESCAPES = tuple(_FAST_IMPL._ESCAPE_DCT.items())
_FAST_IDENTITIES = tuple((namespace, name, namespace[name])
    for namespace, names in (
        (vars(_FAST_IMPL), ('_ESCAPE', 'BytesIO')),
        (vars(json), ('JSONEncoder',)),
        (vars(json.encoder), ('JSONEncoder', 'c_make_encoder', 'encode_basestring')))
    for name in names)


def _fast_allowed():
    if json.encoder.c_make_encoder is None:
        return False
    constants = (MAX_BYTES, MAX_DEPTH, MAX_NODES, SAFE_INTEGER,
                 _FAST_IMPL._INT_MIN, _FAST_IMPL._INT_MAX)
    if any(type(value) is not int for value in constants) or constants != _FAST_CONSTANTS:
        return False
    if any(not _fast_same(namespace.get(name), anchor) for namespace, name, anchor in _FAST_FUNCTIONS):
        return False
    if any(namespace.get(name) is not expected for namespace, name, expected in _FAST_IDENTITIES):
        return False
    escapes = _FAST_IMPL._ESCAPE_DCT
    if type(escapes) is not dict or len(escapes) != len(_FAST_ESCAPES):
        return False
    if not all(type(key) is str and type(value) is str for key, value in escapes.items()):
        return False
    return all(escapes.get(key) == value for key, value in _FAST_ESCAPES)


class _UseReference(Exception):
    pass


def _integer_tree(value):
    kind = type(value)
    if kind is dict:
        # The original check_tree has already bounded and validated every key.
        return {key: _integer_tree(value[key])
                for key in sorted(value, key=lambda key: key.encode('utf-16be'))}
    if kind is list:
        return [_integer_tree(child) for child in value]
    if value is None or kind in (bool, int, str):
        return value
    # A float anywhere sends the whole original value to the original encoder.
    raise _UseReference


def _canonical_bytes(value):
    if not _fast_allowed():
        return rfc8785.dumps(value)
    try:
        ordered = _integer_tree(value)
    except _UseReference:
        return rfc8785.dumps(value)
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False,
        check_circular=True, sort_keys=False, skipkeys=False, separators=(',', ':'))
    return encoder.encode(ordered).encode('utf-8')

_SCHEMA = json.loads((Path(__file__).resolve().parents[1] /
                     "schemas/invoke.schema.json").read_text())
Draft202012Validator.check_schema(_SCHEMA)
_VALIDATOR = Draft202012Validator(_SCHEMA)


def parse_invoke(data: bytes) -> dict:
    request = parse_json(data)
    error = next(_VALIDATOR.iter_errors(request), None)
    if error:
        raise ContractError("request schema: " + error.message)
    timing = request["intent"]["timing"]
    # bool is excluded even though Python treats it as an int.
    if any(type(v) is not int for v in timing.values()):
        raise ContractError("timing requires integer milliseconds")
    if not (timing["notBeforeUnixMs"] <= timing["latestStartUnixMs"] <=
            timing["latestCompletionUnixMs"]):
        raise ContractError("inconsistent start/completion window")
    return request


def intent_digest(intent: dict) -> str:
    return "sha256:" + hashlib.sha256(DIGEST_PREFIX + canonical(intent)).hexdigest()


def identifier(value: str, name="identifier") -> str:
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", value):
        raise ContractError("invalid " + name)
    return value
