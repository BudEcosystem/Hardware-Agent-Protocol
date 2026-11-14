"""Recording an operator's resolution of an ``unknown`` operation (``operations/resolve``, spec §6.10, BHMS-OPS-102).

One function, :func:`record_operator_resolution`, used by every enforcement point that keeps a journal: the device server
(:meth:`bhms.server.server.DeviceServer.resolve`) and the gateway when the upstream cannot be asked
(:mod:`bhms.gateway.router`). The rules live here once:

* An operator's statement is never a measurement. The recorded ``effect`` is at most ``unverified`` and the evidence is
  ``{"kind": "reported"}``; ``verified``/``measured`` come only from the device itself (the reconciliation that every
  resolve attempts first). An operation that required a verified effect therefore cannot be resolved as ``completed``.
* ``completed`` needs a ``result`` that the action's ``output`` schema accepts (``{}`` when the action declares none) and
  records ``unverified`` (``none`` for an action without effect).
* ``failed`` records ``DEVICE_FAULT`` with the basis as its message; ``mayHaveActed: false`` is a claim of proof that
  nothing happened and goes with ``effect: "none"`` (and only then); otherwise the effect is ``unknown`` or, when the
  operator says so, ``unverified``.
* The history entry is a ``reconciliation`` carrying ``operator: {principal, basis}``; earlier entries are untouched.

A resolution that breaks a rule raises :class:`~bhms.protocol.errors.BhmsError` naming the member of ``resolution``
(``mayHaveActed`` false: nothing was recorded). Thread-safety: call on the journal's event loop.
"""

from __future__ import annotations

from typing import Any

from bhms.protocol.canonical import canonical
from bhms.protocol.errors import BhmsError
from bhms.runtime.operations import Journal, OperationRecord

RANGE_KEYWORDS = frozenset({"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"})
"""Output-schema keywords whose violation means "a number outside its declared range" (BHMS-OPS-008)."""
OPERATOR_EVIDENCE = {"kind": "reported"}
"""The evidence of every operator resolution: a person's report, never a measurement (BHMS-OPS-102)."""


def _refuse(member: str, message: str, hint: str, *, code: str = "INVALID_ARGUMENT", bound: Any = None) -> BhmsError:
    return BhmsError(code, f"resolution.{member}: {message}"[:2000], field=f"resolution.{member}", bound=bound, hint=hint)


def _checked_result(resolution: Any, action: str, validator: Any) -> Any:
    """The result of a ``completed`` resolution, checked like a handler's result (I-JSON, the action's output schema)."""
    if "result" in resolution.model_fields_set:
        result = resolution.result
    elif validator is None:
        result = {}
    else:
        raise _refuse("result", f"state completed needs the result of {action}",
                      f"state the result {action} produced (bhms describe shows its output), or resolve it as failed")
    try:
        canonical(result)
    except BhmsError as exc:
        raise _refuse("result", f"cannot be recorded ({exc.message})", "results are I-JSON values") from None
    errors = list(validator.iter_errors(result)) if validator is not None else []
    if errors and all(error.validator in RANGE_KEYWORDS for error in errors):
        first = errors[0]
        member = ".".join(["result", *(str(part) for part in first.absolute_path)])
        raise _refuse(member, f"{first.instance!r} is outside the declared output range of {action}",
                      "state the result the device produced, or resolve the operation as failed", code="OUT_OF_RANGE",
                      bound={first.validator: first.validator_value})
    if errors:
        raise _refuse("result", f"does not match the declared output of {action}: {errors[0].message}",
                      f"state a result that matches the output of {action}, or resolve the operation as failed")
    return result


def record_operator_resolution(journal: Journal, rec: OperationRecord, resolution: Any, principal: str, *,
                               output_validator: Any = None, where: str = "") -> None:
    """Record ``resolution`` (a validated ``OperatorResolution``) on the ``unknown`` operation ``rec``.

    ``output_validator`` is the JSON Schema validator of the action's ``output`` (None when it declares none or the
    action is not known here). ``where`` is appended to the entry's detail after the principal (a gateway says why it
    records the resolution itself). See the module docstring for the rules; raises ``BhmsError`` and records nothing when
    one is broken, and :class:`~bhms.runtime.store.StoreError` when the journal cannot be written.
    """
    action = str(rec.op.get("action") or "the action")
    effectless = rec.private.get("effectClass", "none") == "none"
    operator = {"principal": principal, "basis": resolution.basis}
    detail = f"operator resolution by {principal}{where}: {resolution.basis}"
    common = {"kind": "reconciliation", "detail": detail, "operator": operator, "evidence": dict(OPERATOR_EVIDENCE)}
    if resolution.state == "completed":
        if (rec.op.get("require") or {}).get("effect") == "verified":
            raise _refuse("state", "the operation required a verified effect, which an operator's statement cannot "
                          "establish", "resolve it as failed and state what was found; only device evidence verifies")
        expected = "none" if effectless else "unverified"
        if resolution.effect not in (None, expected):
            raise _refuse("effect", f"a completed {action} is recorded with effect {expected}",
                          f"omit effect or state {expected}; an operator's report is never a measurement")
        journal.transition(rec, "completed", result=_checked_result(resolution, action, output_validator), effect=expected,
                           **common)
        return
    acted = True if resolution.may_have_acted is None else resolution.may_have_acted
    if (resolution.effect == "none") == acted:  # "none" is the claim that nothing happened: the two go together
        raise _refuse("effect", "effect none and mayHaveActed false are one claim (proof that nothing happened) and must "
                      "be stated together", "state both, or neither")
    error = BhmsError("DEVICE_FAULT", resolution.basis, may_have_acted=acted,
                      hint="read the device state before retrying").to_operation_error()
    journal.transition(rec, "failed", error=error, effect=resolution.effect or "unknown",
                       proof=None if acted else resolution.basis, **common)


__all__ = ["OPERATOR_EVIDENCE", "RANGE_KEYWORDS", "record_operator_resolution"]
