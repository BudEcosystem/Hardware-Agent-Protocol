"""Cumulative budgets of grants (spec/bhms/07-leases-and-authority.md §7.4.1, BHMS-AUTH-030..035).

A per-call bound limits one call, never a total: a live agent asked for 600 uL from a pump whose ``dispense`` allows
500 uL per call dispensed 500 uL and then 100 uL (Task 14). A **budget** of a grant limits the total. It names an action
pattern (``<deviceGlob>/<actionGlob>``, split at the last ``/``), a numeric quantity in the action's arguments (an RFC 6901
JSON Pointer to a member that declares ``x-bhms-unit``), a ``total`` in its own ``unit`` and optionally a rolling
``windowMs``.

* **Reservation at admission.** The enforcement point computes each matching budget's charge (the absolute value of the
  quantity, converted to the budget's unit) and refuses the whole request with ``OUT_OF_RANGE`` when one would exceed
  what remains (``field`` the quantity, ``bound = {"maximum": <what remains, in the argument's unit>, "budget":
  BudgetState}``): never a partial dispatch. It calls :meth:`BudgetLedger.charges` in the one admission path, after the
  last lease check and with no ``await`` before the record is written, and writes the reservation in the *same* store
  transaction as the operation (device server: :meth:`~bhms.runtime.operations.Journal.create`) or the pending-forward row
  (gateway: :meth:`~bhms.gateway.journal.ForwardJournal.pending_put`), so the two are durable together.
* **Release only on proof of no effect.** A reservation is released when the operation ends ``rejected``, ``failed``
  with ``mayHaveActed: false``, or ``canceled`` with ``effect: "none"``; ``unknown`` and every other outcome keep it
  consumed. A gateway also releases it when the upstream refused the forward before creating anything.
* **Durable.** Reservations are rows of the server's one store (table ``budget_ledger``), keyed by
  ``(principal, budget id, operationKey)``; they survive restarts and are never pruned with the operations. At start
  :meth:`BudgetLedger.repair` releases reservations whose operation was settled with proof of no effect while the release
  itself was lost in a crash (the conservative state in between counts them as consumed).
* **Windows** are measured on the server's wall clock from the reservation's admission time.

The same module serves the device server (``Executor.admit``) and the gateway (``Router._admit``); nothing about budgets
is implemented twice.

Example::

    budget = Budget.from_wire({"id": "pump-volume", "action": "pump-1/dispense", "quantity": "/volume",
                               "unit": "uL", "total": 500})

Thread-safety: one event loop (the store's thread).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from bhms.protocol import units
from bhms.protocol.errors import BhmsError
from bhms.runtime.operations import iso, now_ns

if TYPE_CHECKING:
    from bhms.runtime.authority import Principal
    from bhms.runtime.operations import Journal, OperationRecord
    from bhms.runtime.store import Store

_EPSILON = 1e-9


def _glob_match(pattern: str, text: str) -> bool:
    from bhms.runtime.authority import glob_match

    return glob_match(pattern, text)


def pointer_tokens(pointer: str) -> list[str]:
    """The reference tokens of an RFC 6901 JSON Pointer (``"/dose/volume"`` -> ``["dose", "volume"]``)."""
    if not pointer.startswith("/") or pointer == "/":
        raise ValueError(f"{pointer!r} is not a JSON Pointer to a member (it must start with / and name one)")
    return [token.replace("~1", "/").replace("~0", "~") for token in pointer[1:].split("/")]


@dataclass(frozen=True)
class Budget:
    """One budget of a grant (the schema's ``Budget``)."""

    id: str
    action: str
    quantity: str
    unit: str
    total: float
    window_ms: int | None = None

    @classmethod
    def from_wire(cls, raw: dict[str, Any]) -> Budget:
        budget = cls(raw["id"], raw["action"], raw["quantity"], raw["unit"], float(raw["total"]), raw.get("windowMs"))
        pointer_tokens(budget.quantity)
        if "/" not in budget.action:
            raise ValueError(f"budget {budget.id!r}: action {budget.action!r} is not <deviceGlob>/<actionGlob>")
        try:
            units.convert(1.0, budget.unit, budget.unit)  # a UCUM code of the registry (4.5)
        except BhmsError as exc:
            raise ValueError(f"budget {budget.id!r}: {exc.message}; {exc.hint}") from None
        if not math.isfinite(budget.total) or budget.total <= 0:
            raise ValueError(f"budget {budget.id!r}: total must be a positive number")
        return budget

    def wire(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "action": self.action, "quantity": self.quantity, "unit": self.unit,
                               "total": self.total}
        if self.window_ms is not None:
            out["windowMs"] = self.window_ms
        return out

    def matches(self, device_id: str, action: str) -> bool:
        """Whether the budget's pattern names ``<device_id>/<action>`` (split at the last ``/``, as scopes are, §7.4)."""
        device_glob, _, action_glob = self.action.rpartition("/")
        return _glob_match(device_glob, device_id) and _glob_match(action_glob, action)

    def field(self, prefix: str = "arguments") -> str:
        return ".".join([prefix, *pointer_tokens(self.quantity)])

    def declared_unit(self, input_schema: dict[str, Any]) -> str | None:
        """The ``x-bhms-unit`` of the numeric member the quantity names in ``input_schema``, or None when it names none or a
        member whose unit does not convert to the budget's (the budget cannot measure this action)."""
        node: Any = input_schema
        for token in pointer_tokens(self.quantity):
            if not isinstance(node, dict):
                return None
            node = (node.get("properties") or {}).get(token)
        if not isinstance(node, dict) or node.get("type") not in ("number", "integer"):
            return None
        unit = node.get("x-bhms-unit")
        if not isinstance(unit, str):
            return None
        try:
            return unit if units.compatible(unit, self.unit) else None
        except (ValueError, BhmsError):
            return None


@dataclass(frozen=True)
class Charge:
    """What one admission reserves of one budget (in the budget's unit), and how to say it."""

    budget: Budget
    amount: float
    declared_unit: str


@dataclass
class _Row:
    op_key: str
    amount: float
    at_ns: int


@dataclass
class Reservation:
    """The reservations of one admission: :meth:`write` inside the transaction that records the operation (or the
    gateway's pending forward), :meth:`commit` once that transaction has committed."""

    ledger: BudgetLedger
    principal: str
    key: str
    charges: tuple[Charge, ...]
    at_ns: int = field(default_factory=now_ns)

    def write(self) -> None:
        self.ledger.write(self)

    def commit(self) -> None:
        self.ledger.remember(self)


class BudgetLedger:
    """The durable budget ledger of one server (device server or gateway); see the module docstring.

    Args:
        store: the server's store (the ledger table lives in it).
        journal: its operation journal: settled operations release their reservations (``on_settled``).
    """

    def __init__(self, store: Store, journal: Journal) -> None:
        self.store = store
        self.journal = journal
        self._rows: dict[tuple[str, str], list[_Row]] = {}
        self._by_key: dict[tuple[str, str], list[str]] = {}  # (principal, operationKey) -> budget ids reserved
        self._deferred: set[tuple[str, str]] = set()  # releases asked for inside an enclosing transaction
        for principal, budget, op_key, amount, at_ns in store.open_reservations():
            self._rows.setdefault((principal, budget), []).append(_Row(op_key, amount, at_ns))
            self._by_key.setdefault((principal, op_key), []).append(budget)
        journal.on_settled.append(self.on_settled)

    # ------------------------------------------------------------------ what remains

    def _counted(self, principal: str, budget: Budget, at_ns: int) -> list[_Row]:
        rows = self._rows.get((principal, budget.id), [])
        if budget.window_ms is None:
            return rows
        since = at_ns - budget.window_ms * 1_000_000
        return [row for row in rows if row.at_ns > since]

    def remaining(self, principal: str, budget: Budget, *, at_ns: int | None = None) -> tuple[float, int | None]:
        """``(what remains of budget, when the oldest counted reservation leaves its window or None)``."""
        self._flush_deferred()
        at = now_ns() if at_ns is None else at_ns
        counted = self._counted(principal, budget, at)
        used = math.fsum(row.amount for row in counted)
        resets = min(row.at_ns for row in counted) + budget.window_ms * 1_000_000 \
            if budget.window_ms is not None and counted else None
        return max(0.0, budget.total - used), resets

    def state(self, principal: str, budget: Budget) -> dict[str, Any]:
        """The ``BudgetState`` of one budget."""
        left, resets = self.remaining(principal, budget)
        out = {**budget.wire(), "remaining": _round(left)}
        if resets is not None:
            out["resetsAt"] = iso(resets)
        return out

    def states(self, principal: Principal) -> list[dict[str, Any]]:
        """Every budget of ``principal`` with what remains (``server/discover`` ``principal.budgets``)."""
        return [self.state(principal.id, budget) for budget in principal.budgets]

    # ------------------------------------------------------------------ admission

    def charges(self, principal: Principal, key: str, device_id: str, action: str, arguments: dict[str, Any],
                input_schema: dict[str, Any], *, field_prefix: str = "arguments") -> Reservation | None:
        """The reservation a request of ``principal`` with ``operationKey`` ``key`` for ``<device_id>/<action>`` and the
        admitted ``arguments`` makes, or
        None when no budget applies. Raises the refusal of BHMS-AUTH-032 (``OUT_OF_RANGE``) when one would be exceeded and
        ``UNAUTHORIZED`` when a budget that names the action cannot measure it (fail closed, BHMS-AUTH-031). Call it with
        no ``await`` between it and writing the reservation."""
        found = [b for b in principal.budgets if b.matches(device_id, action)]
        if not found:
            return None
        at = now_ns()
        charges = []
        for budget in found:
            declared = budget.declared_unit(input_schema)
            value = _member(arguments, budget.quantity)
            if declared is None or not isinstance(value, (int, float)) or isinstance(value, bool):
                raise BhmsError("UNAUTHORIZED", f"your budget {budget.id!r} names {device_id}/{action} but cannot measure "
                                f"its quantity {budget.quantity} in {budget.unit}", field=budget.field(field_prefix),
                                hint=f"{device_id}/{action} is unavailable to you until the budget's quantity names a "
                                     f"numeric argument in a unit convertible to {budget.unit} (BHMS-AUTH-031)")
            amount = abs(units.convert(float(value), declared, budget.unit))
            left, resets = self.remaining(principal.id, budget, at_ns=at)
            if amount > left + _EPSILON * max(1.0, budget.total):
                raise _exceeded(device_id, action, budget, amount, left, resets, declared, field_prefix)
            charges.append(Charge(budget, amount, declared))
        return Reservation(self, principal.id, key, tuple(charges), at)

    def write(self, reservation: Reservation) -> None:
        """Insert the reservation's rows (inside the caller's transaction)."""
        self.store.put_reservations(reservation.principal, reservation.key,
                                    [(charge.budget.id, charge.amount) for charge in reservation.charges], reservation.at_ns)

    def remember(self, reservation: Reservation) -> None:
        """Count the reservation (after its transaction committed)."""
        for charge in reservation.charges:
            rows = self._rows.setdefault((reservation.principal, charge.budget.id), [])
            rows[:] = [row for row in rows if row.op_key != reservation.key]
            rows.append(_Row(reservation.key, charge.amount, reservation.at_ns))
            budgets = self._by_key.setdefault((reservation.principal, reservation.key), [])
            if charge.budget.id not in budgets:
                budgets.append(charge.budget.id)

    # ------------------------------------------------------------------ release

    def release(self, principal: str, key: str) -> bool:
        """Release the reservations of ``(principal, operationKey)`` (proof that the operation had no effect); True when
        any was released. A failed write leaves them consumed (the safe direction; :meth:`repair` retries at start)."""
        budgets = self._by_key.get((principal, key))
        if not budgets:
            return False
        if self.store.in_transaction:
            # Inside an enclosing unit of work (a gateway's forward record) that may still roll back: release once it is
            # known to have committed, from what the journal then says (the safe direction meanwhile is "consumed").
            self._deferred.add((principal, key))
            return False
        from bhms.runtime.store import StoreError

        try:
            self.store.release_reservations(principal, key)
        except StoreError:
            return False
        for budget in self._by_key.pop((principal, key)):
            rows = self._rows.get((principal, budget), [])
            rows[:] = [row for row in rows if row.op_key != key]
        return True

    def _flush_deferred(self) -> None:
        if not self._deferred or self.store.in_transaction:
            return
        pending, self._deferred = self._deferred, set()
        for principal, key in pending:
            rec = self.journal.lookup_key(principal, key)
            if rec is not None and rec.terminal and proves_no_effect(rec.op):
                self.release(principal, key)

    def on_settled(self, rec: OperationRecord) -> None:
        """Journal hook: an operation that ended with proof of no effect gives its reservation back (BHMS-AUTH-033)."""
        if rec.terminal and proves_no_effect(rec.op):
            self.release(rec.principal, rec.op["operationKey"])

    def repair(self, lookup: Callable[[str, str], OperationRecord | None], pending: Iterable[tuple[str, str]] = ()) -> int:
        """At start: release the reservations whose operation settled with proof of no effect (the release was lost in a
        crash) or that have neither an operation nor a pending forward (an admission whose record was rolled back).
        ``pending`` lists the ``(principal, key)`` of a gateway's pending forwards, which keep theirs. Returns how many
        operations' reservations were released."""
        keep = set(pending)
        released = 0
        for principal, key in list(self._by_key):
            if (principal, key) in keep:
                continue
            rec = lookup(principal, key)
            if (rec is None or (rec.terminal and proves_no_effect(rec.op))) and self.release(principal, key):
                released += 1
        return released


def principal_wire(principal: Principal, ledger: BudgetLedger) -> dict[str, Any]:
    """``server/discover`` ``principal``: id, scopes and, when it has any, its budgets with what remains (7.4.1)."""
    wire = principal.wire()
    if principal.budgets:
        wire["budgets"] = ledger.states(principal)
    return wire


def proves_no_effect(operation: dict[str, Any]) -> bool:
    """Whether a terminal operation's record proves that nothing happened: ``rejected``; ``failed`` with
    ``mayHaveActed: false``; ``canceled`` with ``effect: "none"``."""
    state = operation.get("state")
    if state == "rejected":
        return True
    if state == "failed":
        return (operation.get("error") or {}).get("mayHaveActed") is False
    if state == "canceled":
        return operation.get("effect") == "none"
    return False


def _member(arguments: Any, pointer: str) -> Any:
    node = arguments
    for token in pointer_tokens(pointer):
        if not isinstance(node, dict) or token not in node:
            return None
        node = node[token]
    return node


def _round(value: float) -> float | int:
    rounded = round(value, 9)
    return int(rounded) if rounded == int(rounded) else rounded


def _exceeded(device_id: str, action: str, budget: Budget, amount: float, left: float, resets: int | None,
              declared: str, field_prefix: str) -> BhmsError:
    """The refusal of a request that would exceed ``budget`` (BHMS-AUTH-032)."""
    maximum = _round(units.convert(left, budget.unit, declared))
    window = f" per {budget.window_ms} ms window" if budget.window_ms is not None else ""

    def amount_of(value: float, unit: str) -> str:
        return f"{_round(value)}" if unit == "1" else f"{_round(value)} {unit}"

    state: dict[str, Any] = {**budget.wire(), "remaining": _round(left)}
    when = ""
    if resets is not None:
        state["resetsAt"] = iso(resets)
        when = f"; part of it is freed at {state['resetsAt']}"
    message = (f"{device_id}/{action} needs {amount_of(amount, budget.unit)} of budget {budget.id!r}, which has "
               f"{amount_of(left, budget.unit)} left of {amount_of(budget.total, budget.unit)}{window}")
    hint = (f"ask for at most {amount_of(maximum, declared)} ({budget.quantity}){when}, or for nothing: nothing was done; "
            "earlier calls stay counted unless they ended with proof that nothing happened (BHMS-AUTH-032)")
    return BhmsError("OUT_OF_RANGE", message[:2000], field=budget.field(field_prefix),
                     bound={"maximum": maximum, "budget": state}, hint=hint[:2000])


__all__ = ["Budget", "BudgetLedger", "Charge", "Reservation", "pointer_tokens", "principal_wire", "proves_no_effect"]
