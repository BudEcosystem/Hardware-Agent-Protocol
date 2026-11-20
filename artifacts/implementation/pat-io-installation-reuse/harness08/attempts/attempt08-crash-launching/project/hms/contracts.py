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
        result = rfc8785.dumps(value)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ContractError("cannot canonicalize JSON") from error
    if len(result) > MAX_BYTES:
        raise ContractError("canonical value exceeds byte limit")
    return result


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
