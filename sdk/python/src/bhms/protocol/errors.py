"""BHMS error model and the JSON-RPC code table.

Wire form: ``{code, message, data: {bhmsCode, field?, bound?, mayHaveActed, retry, hint}}``.

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
====================  ======  ===============  =====================================

``retry`` semantics: ``never`` (do not retry), ``same-key`` (retry with the same
idempotency key), ``after-reconcile`` (read the operation state, then decide),
``backoff`` (retry later with the same key, with delay). ``may_have_acted``
defaults to False; callers set it True whenever a command may have reached the
device (e.g. DEADLINE_EXCEEDED after dispatch).
"""

from __future__ import annotations

from typing import Any, NamedTuple

RETRY_VALUES = ("never", "same-key", "after-reconcile", "backoff")
_INVALID_PARAMS = -32602


class CodeSpec(NamedTuple):
    number: int
    retry: str


def _build() -> dict[str, CodeSpec]:
    spec = [
        ("INVALID_ARGUMENT", "never"), ("OUT_OF_RANGE", "never"), ("UNIT_MISMATCH", "never"),
        ("UNKNOWN_DEVICE", "never"), ("UNKNOWN_ACTION", "never"), ("UNSUPPORTED", "never"),
        ("LEASE_REQUIRED", "never"), ("LEASE_CONFLICT", "backoff"), ("LEASE_EXPIRED", "never"),
        ("FENCED", "never"), ("KEY_CONFLICT", "never"), ("STALE", "after-reconcile"),
        ("DEVICE_UNAVAILABLE", "backoff"), ("UNAUTHORIZED", "never"), ("BUSY", "backoff"),
        ("DEADLINE_EXCEEDED", "after-reconcile"), ("INTERNAL", "never"),
    ]
    out: dict[str, CodeSpec] = {}
    next_number = -32001
    for name, retry in spec:
        if name in ("INVALID_ARGUMENT", "OUT_OF_RANGE", "UNIT_MISMATCH"):
            out[name] = CodeSpec(_INVALID_PARAMS, retry)
        else:
            out[name] = CodeSpec(next_number, retry)
            next_number -= 1
    return out


CODES: dict[str, CodeSpec] = _build()


class BhmsError(Exception):
    """A protocol error. Names the field, the bound and a fix whenever known."""

    def __init__(self, code: str, message: str, *, field: str | None = None, bound: Any = None,
                 may_have_acted: bool = False, retry: str | None = None, hint: str = "") -> None:
        if code not in CODES:
            raise ValueError(f"unknown BHMS error code {code!r}; known codes: {', '.join(CODES)}")
        if retry is None:
            retry = CODES[code].retry
        if retry not in RETRY_VALUES:
            raise ValueError(f"invalid retry {retry!r}; must be one of {', '.join(RETRY_VALUES)}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.bound = bound
        self.may_have_acted = may_have_acted
        self.retry = retry
        self.hint = hint

    def to_jsonrpc(self) -> dict[str, Any]:
        data: dict[str, Any] = {"bhmsCode": self.code}
        if self.field is not None:
            data["field"] = self.field
        if self.bound is not None:
            data["bound"] = self.bound
        data.update(mayHaveActed=self.may_have_acted, retry=self.retry, hint=self.hint)
        return {"code": CODES[self.code].number, "message": self.message, "data": data}


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
    return BhmsError(code, str(err.get("message", "")), field=data.get("field"),
                     bound=data.get("bound"), may_have_acted=bool(data.get("mayHaveActed", False)),
                     retry=data.get("retry"), hint=str(data.get("hint", "")))
