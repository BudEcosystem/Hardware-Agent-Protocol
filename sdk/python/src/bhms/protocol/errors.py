"""BHMS error model and the JSON-RPC code table.

Wire form: ``{code, message, data: {bhmsCode, field?, bound?, operationId?, mayHaveActed, retry, hint}}``.
Normative source: ``spec/bhms/10-errors.md``; the schema's ``x-bhms-errors`` map mirrors this table.

Code table (JSON-RPC number, default ``retry``):

====================  ======  ===============  =====================================
BHMS code             Number  Default retry    Meaning
====================  ======  ===============  =====================================
INVALID_ARGUMENT      -32602  never            malformed or unknown argument/unit
OUT_OF_RANGE          -32602  never            value outside the declared envelope
UNIT_MISMATCH         -32602  never            incompatible units, no silent convert
UNKNOWN_DEVICE        -32001  never            device id not registered
UNKNOWN_ACTION        -32002  never            action not on the device
UNSUPPORTED           -32003  never            capability not available; refuse
LEASE_REQUIRED        -32004  never            acquire a lease first
LEASE_CONFLICT        -32005  backoff          another principal holds the lease
LEASE_EXPIRED         -32006  never            reacquire the lease
FENCED                -32007  never            stale fence token; reacquire
KEY_CONFLICT          -32008  never            idempotency key reused, other payload
STALE                 -32009  after-reconcile  precondition/state revision is stale
DEVICE_UNAVAILABLE    -32010  backoff          device offline or unreachable
UNAUTHORIZED          -32011  never            principal lacks the scope
BUSY                  -32012  backoff          device or server saturated
DEADLINE_EXCEEDED     -32013  after-reconcile  outcome unknown; reconcile first
INTERNAL              -32014  never            server bug
UNSUPPORTED_VERSION   -32015  never            protocol version not served; bound lists versions
UNVERIFIED            -32016  after-reconcile  required measured evidence absent or contradicts
DEVICE_FAULT          -32017  after-reconcile  device reported a fault while acting
====================  ======  ===============  =====================================

``DEVICE_FAULT`` and ``UNVERIFIED`` describe what happened while a device acted:
they are carried only in an operation's ``error`` (:meth:`BhmsError.to_operation_error`),
never as JSON-RPC error responses (BHMS-ERR-012).

``retry`` semantics: ``never`` (do not retry), ``same-key`` (retry with the same
idempotency key), ``after-reconcile`` (read the operation state, then decide),
``backoff`` (retry later with the same key, with delay). ``may_have_acted``
defaults to False; callers set it True whenever a command may have reached the
device (e.g. DEADLINE_EXCEEDED after dispatch).
"""

from __future__ import annotations

import warnings
from typing import Any, NamedTuple

RETRY_VALUES = ("never", "same-key", "after-reconcile", "backoff")
_INVALID_PARAMS = -32602


class CodeSpec(NamedTuple):
    number: int
    retry: str


CODES: dict[str, CodeSpec] = {
    # The numbers are wire contract (spec/bhms/10-errors.md): written out, never derived from their position.
    "INVALID_ARGUMENT": CodeSpec(_INVALID_PARAMS, "never"),
    "OUT_OF_RANGE": CodeSpec(_INVALID_PARAMS, "never"),
    "UNIT_MISMATCH": CodeSpec(_INVALID_PARAMS, "never"),
    "UNKNOWN_DEVICE": CodeSpec(-32001, "never"),
    "UNKNOWN_ACTION": CodeSpec(-32002, "never"),
    "UNSUPPORTED": CodeSpec(-32003, "never"),
    "LEASE_REQUIRED": CodeSpec(-32004, "never"),
    "LEASE_CONFLICT": CodeSpec(-32005, "backoff"),
    "LEASE_EXPIRED": CodeSpec(-32006, "never"),
    "FENCED": CodeSpec(-32007, "never"),
    "KEY_CONFLICT": CodeSpec(-32008, "never"),
    "STALE": CodeSpec(-32009, "after-reconcile"),
    "DEVICE_UNAVAILABLE": CodeSpec(-32010, "backoff"),
    "UNAUTHORIZED": CodeSpec(-32011, "never"),
    "BUSY": CodeSpec(-32012, "backoff"),
    "DEADLINE_EXCEEDED": CodeSpec(-32013, "after-reconcile"),
    "INTERNAL": CodeSpec(-32014, "never"),
    "UNSUPPORTED_VERSION": CodeSpec(-32015, "never"),
    "UNVERIFIED": CodeSpec(-32016, "after-reconcile"),
    "DEVICE_FAULT": CodeSpec(-32017, "after-reconcile"),
}

# Codes that describe admitted work; never sent as JSON-RPC errors (BHMS-ERR-012).
OPERATION_ONLY_CODES: frozenset[str] = frozenset({"DEVICE_FAULT", "UNVERIFIED"})


class BhmsError(Exception):
    """A protocol error. Names the field, the bound and a fix whenever known.

    ``bhms_code`` is the BHMS code (``"OUT_OF_RANGE"``): the same attribute name as on the ``OperationError`` and
    ``ErrorData`` models, and the wire member ``bhmsCode``. ``code`` is a deprecated alias kept for one release (it is
    easily mistaken for the JSON-RPC number); it warns with ``DeprecationWarning``. Instances pickle with every member.
    """

    def __init__(self, code: str, message: str, *, field: str | None = None, bound: Any = None,
                 operation_id: str | None = None, may_have_acted: bool = False,
                 retry: str | None = None, hint: str = "") -> None:
        if code not in CODES:
            raise ValueError(f"unknown BHMS error code {code!r}; known codes: {', '.join(CODES)}")
        if retry is None:
            retry = CODES[code].retry
        if retry not in RETRY_VALUES:
            raise ValueError(f"invalid retry {retry!r}; must be one of {', '.join(RETRY_VALUES)}")
        super().__init__(message)
        self.bhms_code = code
        self.message = message
        self.field = field
        self.bound = bound
        self.operation_id = operation_id
        self.may_have_acted = may_have_acted
        self.retry = retry
        self.hint = hint

    @property
    def code(self) -> str:
        """Deprecated alias of :attr:`bhms_code` (removed after one release)."""
        warnings.warn("BhmsError.code is deprecated; use BhmsError.bhms_code (the name OperationError uses)",
                      DeprecationWarning, stacklevel=2)
        return self.bhms_code

    def __reduce__(self) -> tuple[Any, ...]:
        """Pickle support: ``Exception`` would re-create the error from ``args`` alone and lose the keyword members."""
        return (_rebuild, (self.bhms_code, self.message, self.field, self.bound, self.operation_id, self.may_have_acted,
                           self.retry, self.hint))

    def _data(self) -> dict[str, Any]:
        data: dict[str, Any] = {"bhmsCode": self.bhms_code}
        if self.field is not None:
            data["field"] = self.field
        if self.bound is not None:
            data["bound"] = self.bound
        if self.operation_id is not None:
            data["operationId"] = self.operation_id
        data.update(mayHaveActed=self.may_have_acted, retry=self.retry, hint=self.hint)
        return data

    def to_jsonrpc(self) -> dict[str, Any]:
        """JSON-RPC error object; ValueError for operation-only codes (BHMS-ERR-012)."""
        if self.bhms_code in OPERATION_ONLY_CODES:
            raise ValueError(f"{self.bhms_code} describes admitted work and is reported only in an operation's "
                             "error; use to_operation_error()")
        return {"code": CODES[self.bhms_code].number, "message": self.message, "data": self._data()}

    def to_operation_error(self) -> dict[str, Any]:
        """The ``OperationError`` wire form: error data plus ``message`` (any code)."""
        data = self._data()
        data["message"] = self.message
        return data


def _rebuild(code: str, message: str, field: str | None, bound: Any, operation_id: str | None, may_have_acted: bool,
             retry: str, hint: str) -> BhmsError:
    return BhmsError(code, message, field=field, bound=bound, operation_id=operation_id, may_have_acted=may_have_acted,
                     retry=retry, hint=hint)


def from_jsonrpc(err: dict[str, Any]) -> BhmsError:
    """Rebuild a BhmsError from a JSON-RPC error object; ValueError if it is not a BHMS error."""
    data = err.get("data")
    if not isinstance(data, dict) or "bhmsCode" not in data:
        raise ValueError("not a BHMS error: data.bhmsCode is missing")
    code = data["bhmsCode"]
    if code not in CODES:
        raise ValueError(f"unknown BHMS error code {code!r}; known codes: {', '.join(CODES)}")
    number = err.get("code")
    if number != CODES[code].number:
        raise ValueError(f"code {code} must use JSON-RPC number {CODES[code].number}, got {number}")
    if code in OPERATION_ONLY_CODES:
        raise ValueError(f"{code} is operation-only and cannot be a JSON-RPC error (BHMS-ERR-012)")
    missing = [k for k in ("mayHaveActed", "retry", "hint") if k not in data]
    if missing:
        raise ValueError(f"BHMS error data is missing {', '.join(missing)}; mayHaveActed is never assumed")
    if not isinstance(data["mayHaveActed"], bool):
        raise ValueError("data.mayHaveActed must be a boolean")
    return BhmsError(code, str(err.get("message", "")), field=data.get("field"),
                     bound=data.get("bound"), operation_id=data.get("operationId"),
                     may_have_acted=data["mayHaveActed"], retry=data["retry"], hint=str(data["hint"]))
