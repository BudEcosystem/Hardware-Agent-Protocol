"""RFC 8785 canonical JSON and content digests (sole owner of canonicalization).

:func:`canonical` encodes with a fast path for the values that dominate BHMS messages (objects, arrays, strings,
safe integers, and floats whose shortest decimal form needs no exponent) and delegates every other number to the
``rfc8785`` reference implementation, so the output is byte-identical to it (``tests/test_canonical.py`` checks this
property on generated JSON). Object members are ordered by their UTF-16 code units as RFC 8785 §3.2.3 requires.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

import rfc8785

from bhms.protocol.errors import BhmsError

_SAFE_INT = 2 ** 53 - 1
_ESCAPE = re.compile(r'[\x00-\x1f\\"]')
_ESCAPES = {"\\": "\\\\", '"': '\\"', "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}
for _code in range(0x20):
    _ESCAPES.setdefault(chr(_code), f"\\u{_code:04x}")


class _Unsupported(Exception):
    pass


def _ordered(members: Any) -> list[str]:
    keys = list(members)
    if all(k.isascii() for k in keys):
        return sorted(keys)
    return sorted(keys, key=lambda k: k.encode("utf-16-be", "surrogatepass"))


def _string(value: str) -> str:
    if _ESCAPE.search(value) is None:
        return f'"{value}"'
    return '"' + _ESCAPE.sub(lambda m: _ESCAPES[m.group(0)], value) + '"'


def _float(value: float) -> str:
    if math.isnan(value) or math.isinf(value):
        raise _Unsupported
    if value == 0:
        return "0"
    magnitude = abs(value)
    if value.is_integer():
        if magnitude <= _SAFE_INT:
            return str(int(value))
    elif 1e-4 <= magnitude < 1e16:
        text = repr(value)  # shortest round-trip digits; decimal notation in this range, as ECMAScript prints them
        if "e" not in text:
            return text
    return rfc8785.dumps(value).decode()


def _encode(value: Any, out: list[str]) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, str):
        out.append(_string(value))
    elif isinstance(value, int):
        if not -_SAFE_INT <= value <= _SAFE_INT:
            raise _Unsupported
        out.append(str(value))
    elif isinstance(value, float):
        out.append(_float(value))
    elif isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise _Unsupported
        out.append("{")
        first = True
        for member in _ordered(value):
            if not first:
                out.append(",")
            first = False
            out.append(_string(member))
            out.append(":")
            _encode(value[member], out)
        out.append("}")
    elif isinstance(value, (list, tuple)):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _encode(item, out)
        out.append("]")
    else:
        raise _Unsupported


def canonical(obj: Any) -> bytes:
    """Return the RFC 8785 (JCS) UTF-8 encoding of ``obj``.

    Raises INVALID_ARGUMENT for NaN/Infinity or values JSON cannot represent.
    Pure; thread-safe.
    """
    parts: list[str] = []
    try:
        _encode(obj, parts)
        return "".join(parts).encode("utf-8")
    except (_Unsupported, UnicodeEncodeError, RecursionError):
        pass
    try:
        return rfc8785.dumps(obj)
    except (rfc8785.CanonicalizationError, TypeError) as exc:
        raise BhmsError("INVALID_ARGUMENT", f"value is not canonical-JSON serializable: {exc}",
                        hint="use finite numbers and JSON types only (null, bool, int, float, str, list, dict)") from exc


def digest(obj: Any) -> str:
    """Return ``"sha256:<hex>"`` over the canonical form of ``obj``."""
    return "sha256:" + hashlib.sha256(canonical(obj)).hexdigest()
