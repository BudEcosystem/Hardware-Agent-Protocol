"""The one check of an action result before it is recorded (BHMS-OPS-008): an I-JSON value that the action's declared
``output`` schema accepts.

Used by every path that records a result: the executor for a handler's return value and a device's reconciliation
(:class:`bhms.server.executor.Executor`), and the operator resolution (:mod:`bhms.runtime.resolution`). Each caller turns a
:class:`ResultDefect` into its own outcome (a failed operation, a refused request, a hook error); the classification lives
here once:

* ``not-ijson``: the value cannot be carried as canonical JSON (NaN, an integer beyond +/-2^53, a non-JSON type);
* ``out-of-range``: the value has the declared shape and its only defects are numbers outside declared ranges, i.e. a
  measurement outside its declared range rather than a malformed result (BHMS-OPS-008 reports it as ``OUT_OF_RANGE``);
* ``schema``: anything else the output schema refuses.

Thread-safety: pure functions; a compiled validator may be shared.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from bhms.protocol.canonical import canonical
from bhms.protocol.errors import BhmsError

RANGE_KEYWORDS = frozenset({"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"})
"""Output-schema keywords whose violation means "a number outside its declared range" (BHMS-OPS-008)."""


@dataclass(frozen=True)
class ResultDefect:
    """Why a result cannot be recorded as it is.

    ``message`` is the reason in words, starting from the result ("result.speed is nan; ...", "the result does not match
    the declared output schema: ..."); ``cause`` is the underlying serializer or schema message alone. ``member`` is the
    path of the first offending member (``result`` for the whole value). For ``out-of-range`` only: ``instance`` is the
    offending value, ``keyword`` the range keyword it breaks and ``bound`` ``{keyword: declared value}``.
    """

    kind: Literal["not-ijson", "out-of-range", "schema"]
    message: str
    cause: str
    member: str = "result"
    instance: Any = None
    keyword: str | None = None
    bound: dict[str, Any] | None = None


def check_result(result: Any, validator: Any) -> ResultDefect | None:
    """Check ``result`` against I-JSON and, when ``validator`` (the compiled JSON Schema of the action's ``output``) is not
    None, against the declared output. Returns None when it can be recorded, else the first defect: an I-JSON defect
    before any schema defect, and ``out-of-range`` only when every schema error is a range keyword."""
    try:
        canonical(result)
    except BhmsError as exc:
        found = _ijson_violation(result, "result")
        if found is not None:
            member, message = found
            return ResultDefect("not-ijson", message, exc.message, member=member)
        return ResultDefect("not-ijson", f"the result is not JSON-serialisable ({exc.message})", exc.message)
    if validator is None:
        return None
    errors = list(validator.iter_errors(result))
    if not errors:
        return None
    first = errors[0]
    member = ".".join(["result", *(str(part) for part in first.absolute_path)])
    message = f"the result does not match the declared output schema: {first.message}"
    if all(error.validator in RANGE_KEYWORDS for error in errors):
        return ResultDefect("out-of-range", message, first.message, member=member, instance=first.instance,
                            keyword=first.validator, bound={first.validator: first.validator_value})
    return ResultDefect("schema", message, first.message, member=member)


def _ijson_violation(value: Any, path: str) -> tuple[str, str] | None:
    """The first member of ``value`` that breaks the I-JSON number rule (BHMS-OPS-008) and why, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and not -(2 ** 53 - 1) <= value <= 2 ** 53 - 1:
        return path, (f"{path} is the integer {value}, beyond +/-2^53 (9007199254740991); results are I-JSON, so numbers "
                      "must be exactly representable as IEEE 754 doubles: return it as a string, or as a float if rounding "
                      "is acceptable")
    if isinstance(value, float) and not math.isfinite(value):
        return path, f"{path} is {value}; NaN and Infinity are not JSON numbers: return null or a string"
    if isinstance(value, dict):
        for key, item in value.items():
            if found := _ijson_violation(item, f"{path}.{key}"):
                return found
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            if found := _ijson_violation(item, f"{path}[{index}]"):
                return found
    return None


__all__ = ["RANGE_KEYWORDS", "ResultDefect", "check_result"]
