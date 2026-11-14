"""Type annotations and decorator builders that turn Python functions into BHMS properties and actions.

A device author writes ordinary functions; this module turns their signatures into the JSON Schemas of
spec/bhms/04-devices.md §4.5 so that descriptions never drift from code:

* :class:`Range` is a numeric annotation with a unit and optional bounds/step: ``target: Range(0, 200, unit="um")``
  becomes ``{"type": "number", "x-bhms-unit": "um", "minimum": 0, "maximum": 200}``.
* :class:`OneOf`, :class:`Text`, :class:`Array` and :class:`Schema` cover enums, strings, arrays and raw schemas;
  ``bool``, ``str``, ``Literal[...]``, ``enum.Enum`` subclasses, ``list[...]`` and ``X | None`` work as well.
* A return annotation that is a ``dict`` maps result members to units or annotations:
  ``-> {"position": "um"}`` becomes a closed object schema with one numeric member in micrometres.

Every ``number``/``integer`` schema must carry a unit (BHMS-DEV-041): a bare ``float`` or ``int`` annotation is
refused with an error naming the parameter and showing the fix, rather than being given a guessed unit. Python default
values become schema ``default`` members and make the argument optional.

Example::

    @stage.action(effect="reversible", idempotency="absolute", max_duration_ms=5000)
    async def move_to(ctx, target: Range(0, 200, unit="um"), speed: Range(1, 50, unit="um/s") = 10) -> {"position": "um"}:
        ...

Thread-safety: builders are pure functions of their arguments; the resulting specs are immutable after registration.
"""

from __future__ import annotations

import enum
import inspect
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from bhms.protocol.units import UNITS

EFFECTS = ("none", "reversible", "irreversible", "hazardous")
IDEMPOTENCY = ("idempotent", "absolute", "relative", "toggle")
COMPLETION_EVIDENCE = ("measured", "reported", "none")
EVIDENCE = ("measured", "reported", "commanded", "estimated", "simulated")
ON_LEASE_LOSS = ("finish", "cancel", "hold")


class DescriptionError(ValueError):
    """A device declaration that cannot produce a valid BHMS description; the message names the item and the fix."""


class SchemaType:
    """Base class of annotation objects that know their JSON Schema."""

    def schema(self) -> dict[str, Any]:
        raise NotImplementedError


class Range(SchemaType):
    """A numeric value with a unit and optional bounds (BHMS-DEV-041).

    Args:
        minimum / maximum: inclusive bounds (``None`` for unbounded).
        unit: UCUM code from the BHMS registry (``"mm"``, ``"um"``, ``"1"`` for counts, ``"%"``).
        step: ``multipleOf``; evaluated with a 1e-9 relative tolerance (BHMS-DEV-071).
        integer: ``type: integer`` instead of ``number``.
        exclusive_minimum / exclusive_maximum: exclusive bounds.
        nullable: also accept ``null``.
        frame: ``x-bhms-frame`` for coordinates.
        description: schema ``description``.

    Example: ``Range(0, 200, unit="um", step=0.1)``; ``Range(1, 50, unit="1", integer=True)`` for a count.
    """

    def __init__(self, minimum: float | None = None, maximum: float | None = None, *, unit: str,
                 step: float | None = None, integer: bool = False, exclusive_minimum: float | None = None,
                 exclusive_maximum: float | None = None, nullable: bool = False, frame: str | None = None,
                 description: str | None = None) -> None:
        if not isinstance(unit, str) or not unit:
            raise DescriptionError('Range needs unit="<ucum>" (use "1" for counts, "%" for percentages)')
        if minimum is not None and maximum is not None and minimum > maximum:
            raise DescriptionError(f"Range minimum {minimum} is above maximum {maximum}")
        if step is not None and step <= 0:
            raise DescriptionError(f"Range step must be positive, got {step}")
        self.minimum, self.maximum, self.unit, self.step = minimum, maximum, unit, step
        self.integer, self.nullable, self.frame, self.description = integer, nullable, frame, description
        self.exclusive_minimum, self.exclusive_maximum = exclusive_minimum, exclusive_maximum

    def schema(self) -> dict[str, Any]:
        kind = "integer" if self.integer else "number"
        out: dict[str, Any] = {"type": [kind, "null"] if self.nullable else kind, "x-bhms-unit": self.unit}
        for key, value in (("minimum", self.minimum), ("maximum", self.maximum),
                           ("exclusiveMinimum", self.exclusive_minimum), ("exclusiveMaximum", self.exclusive_maximum),
                           ("multipleOf", self.step), ("x-bhms-frame", self.frame),
                           ("description", self.description)):
            if value is not None:
                out[key] = value
        return out

    def __repr__(self) -> str:
        return f"Range({self.minimum}, {self.maximum}, unit={self.unit!r})"


class OneOf(SchemaType):
    """An enumerated value: ``mode: OneOf("fast", "precise")``."""

    def __init__(self, *values: Any, description: str | None = None) -> None:
        if not values:
            raise DescriptionError("OneOf needs at least one value")
        self.values, self.description = list(values), description

    def schema(self) -> dict[str, Any]:
        out: dict[str, Any] = {"enum": self.values}
        kinds = {_json_type(v) for v in self.values}
        if len(kinds) == 1 and None not in kinds:
            out["type"] = kinds.pop()
        if self.description:
            out["description"] = self.description
        return out


class Text(SchemaType):
    """A string with optional length bounds and pattern: ``label: Text(max_length=32)``."""

    def __init__(self, *, min_length: int | None = None, max_length: int | None = None, pattern: str | None = None,
                 description: str | None = None) -> None:
        self.min_length, self.max_length, self.pattern, self.description = min_length, max_length, pattern, description

    def schema(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": "string"}
        for key, value in (("minLength", self.min_length), ("maxLength", self.max_length), ("pattern", self.pattern),
                           ("description", self.description)):
            if value is not None:
                out[key] = value
        return out


class Array(SchemaType):
    """An array of one item annotation: ``points: Array(Range(0, 10, unit="mm"), max_items=16)``."""

    def __init__(self, items: Any, *, min_items: int | None = None, max_items: int | None = None,
                 description: str | None = None) -> None:
        self.items, self.min_items, self.max_items, self.description = items, min_items, max_items, description

    def schema(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": "array", "items": schema_for(self.items, where="array item")}
        for key, value in (("minItems", self.min_items), ("maxItems", self.max_items),
                           ("description", self.description)):
            if value is not None:
                out[key] = value
        return out


class Schema(SchemaType):
    """A raw JSON Schema, used verbatim (still checked for units, BHMS-DEV-041): ``Schema({"type": "string"})``."""

    def __init__(self, schema: dict[str, Any]) -> None:
        if not isinstance(schema, dict):
            raise DescriptionError("Schema(...) takes a JSON Schema object")
        self._schema = schema

    def schema(self) -> dict[str, Any]:
        return dict(self._schema)


def _json_type(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return "object"


def _numeric_fix(where: str, kind: str) -> DescriptionError:
    return DescriptionError(
        f"{where} is a bare {kind} without a unit; every number needs one (BHMS-DEV-041). Annotate it as "
        f'Range(<min>, <max>, unit="<ucum>"{", integer=True" if kind == "int" else ""}) — use unit="1" for counts')


def schema_for(annotation: Any, *, where: str, unit: str | None = None) -> dict[str, Any]:
    """The JSON Schema of a type annotation; ``unit`` applies to bare ``float``/``int`` (property values).

    Raises :class:`DescriptionError` naming ``where`` when the annotation cannot be described honestly.
    """
    if annotation is inspect.Parameter.empty or annotation is inspect.Signature.empty:
        raise DescriptionError(f"{where} has no type annotation; annotate it (for example Range(0, 10, unit=\"mm\"))")
    if isinstance(annotation, SchemaType):
        return annotation.schema()
    if isinstance(annotation, str):
        if annotation in UNITS or unit is None:
            return {"type": "number", "x-bhms-unit": annotation}
        raise DescriptionError(f"{where}: a string annotation is read as a unit, got {annotation!r}")
    if isinstance(annotation, dict):
        return object_schema({name: value for name, value in annotation.items()}, where=where)
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is str:
        return {"type": "string"}
    if annotation in (float, int):
        kind = "number" if annotation is float else "integer"
        if unit is None:
            raise _numeric_fix(where, annotation.__name__)
        return {"type": kind, "x-bhms-unit": unit}
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return OneOf(*[member.value for member in annotation]).schema()
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is Literal:
        return OneOf(*args).schema()
    if origin in (typing.Union, types.UnionType):
        members = [a for a in args if a is not type(None)]
        if len(members) != 1 or len(args) != 2:
            raise DescriptionError(f"{where}: only `X | None` unions are supported; use Schema({{...}}) otherwise")
        inner = schema_for(members[0], where=where, unit=unit)
        kind = inner.get("type")
        if isinstance(kind, str):
            inner["type"] = [kind, "null"]
        elif "enum" in inner:
            inner["enum"] = [*inner["enum"], None]
        else:
            raise DescriptionError(f"{where}: cannot make this annotation nullable; use Schema({{...}})")
        return inner
    if origin is list and len(args) == 1:
        return {"type": "array", "items": schema_for(args[0], where=f"{where} item", unit=unit)}
    if annotation is type(None) or annotation is None:
        raise DescriptionError(f"{where}: None is not a value type")
    raise DescriptionError(f"{where}: unsupported annotation {annotation!r}; use Range, OneOf, Text, Array, bool, str, "
                           "a {member: unit} dict or Schema({...})")


def object_schema(members: dict[str, Any], *, where: str, required: list[str] | None = None) -> dict[str, Any]:
    """A closed object schema from ``{member: annotation-or-unit}``; every member is required unless listed."""
    props = {name: schema_for(value, where=f"{where}.{name}") for name, value in members.items()}
    out: dict[str, Any] = {"type": "object", "additionalProperties": False, "properties": props}
    req = list(members) if required is None else required
    if req:
        out["required"] = req
    return out


def describe_text(fn: Callable[..., Any], given: str | None, limit: int) -> str:
    """``given`` or the function's docstring, whitespace-normalised and checked against ``limit``."""
    text = given if given is not None else " ".join((inspect.getdoc(fn) or "").split())
    if len(text) > limit:
        raise DescriptionError(f"{fn.__name__}: description is {len(text)} characters; the limit is {limit}")
    return text


def _signature(fn: Callable[..., Any], localns: dict[str, Any] | None = None) -> inspect.Signature:
    """The signature with string annotations evaluated (``from __future__ import annotations``) in the function's
    globals and ``localns`` (the namespace where the decorator was applied, so locally defined enums resolve)."""
    try:
        return inspect.signature(fn, eval_str=True, locals=localns)
    except (NameError, SyntaxError) as exc:
        raise DescriptionError(f"{fn.__name__}: cannot evaluate its annotations ({exc})") from exc


@dataclass(frozen=True)
class PropertySpec:
    """A registered property: its getter and the members of its ``PropertyDescription``."""

    name: str
    getter: Callable[..., Any] | None
    schema: dict[str, Any]
    evidence: str
    observable: bool
    read_effect: str
    description: str
    max_rate_hz: float | None = None
    requires_lease: bool = False
    resources: tuple[str, ...] = ()
    validity_ms: int | None = None
    timeout_ms: int = 1000
    takes_ctx: bool = False
    blocking: bool = False

    def describe(self) -> dict[str, Any]:
        out: dict[str, Any] = {"description": self.description, "schema": self.schema, "evidence": self.evidence,
                               "observable": self.observable, "readEffect": self.read_effect}
        if self.max_rate_hz is not None:
            out["maxRateHz"] = self.max_rate_hz
        if self.requires_lease:
            out["requiresLease"] = True
        if self.resources:
            out["resources"] = list(self.resources)
        return out

    @property
    def unit(self) -> str | None:
        unit = self.schema.get("x-bhms-unit")
        return unit if isinstance(unit, str) else None


@dataclass(frozen=True)
class ActionSpec:
    """A registered action: its handler, parameter names and the members of its ``ActionDescription``."""

    name: str
    handler: Callable[..., Any]
    input: dict[str, Any]
    output: dict[str, Any] | None
    effect: str
    idempotency: str
    cancel: str
    completion_evidence: str
    max_duration_ms: int
    requires_lease: bool
    resources: tuple[str, ...]
    description: str
    params: tuple[str, ...] = ()
    ctx_param: str | None = None
    verified_by: tuple[str, ...] = ()
    typical_duration_ms: int | None = None
    on_lease_loss: str | None = None
    requires_fresh: tuple[tuple[str, int], ...] = ()
    preconditions: str | None = None
    blocking: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> dict[str, Any]:
        out: dict[str, Any] = {"description": self.description, "input": self.input, "effect": self.effect,
                               "idempotency": self.idempotency, "cancel": self.cancel,
                               "completionEvidence": self.completion_evidence, "maxDurationMs": self.max_duration_ms,
                               "requiresLease": self.requires_lease, "resources": list(self.resources)}
        if self.output is not None:
            out["output"] = self.output
        if self.verified_by:
            out["verifiedBy"] = list(self.verified_by)
        if self.typical_duration_ms is not None:
            out["typicalDurationMs"] = self.typical_duration_ms
        if self.on_lease_loss is not None:
            out["onLeaseLoss"] = self.on_lease_loss
        if self.requires_fresh:
            out["requiresFresh"] = [{"property": p, "maxAgeMs": m} for p, m in self.requires_fresh]
        if self.preconditions is not None:
            out["preconditions"] = self.preconditions
        return out

    @property
    def lease_loss(self) -> str:
        return self.on_lease_loss or "finish"


def _choice(value: Any, allowed: tuple[str, ...], what: str, owner: str) -> str:
    if value not in allowed:
        raise DescriptionError(f"{owner}: {what}={value!r} is not one of {', '.join(allowed)}")
    return value


def build_property(fn: Callable[..., Any] | None, *, name: str | None = None, unit: str | None = None,
                   evidence: str = "reported", observable: bool = True, read_effect: str = "none",
                   max_rate_hz: float | None = None, requires_lease: bool = False,
                   resources: tuple[str, ...] | list[str] = (), validity_ms: int | None = None, timeout_ms: int = 1000,
                   schema: Any = None, description: str | None = None, blocking: bool = False,
                   localns: dict[str, Any] | None = None) -> PropertySpec:
    """Build a :class:`PropertySpec` from a getter (``None`` for a push-only property published by the device)."""
    prop_name = name or (fn.__name__ if fn is not None else None)
    if not prop_name:
        raise DescriptionError("a property without a getter needs name=")
    owner = f"property {prop_name!r}"
    _choice(evidence, EVIDENCE, "evidence", owner)
    _choice(read_effect, ("none", "transaction"), "read_effect", owner)
    if requires_lease and read_effect != "transaction":
        raise DescriptionError(f"{owner}: requires_lease applies only to read_effect='transaction' (BHMS-DEV-050)")
    takes_ctx = False
    if schema is None:
        if fn is None:
            raise DescriptionError(f"{owner}: give schema= (or unit=) for a property without a getter")
        sig = _signature(fn, localns)
        takes_ctx = len(sig.parameters) > 0
        value_schema = schema_for(sig.return_annotation, where=f"{owner} return value", unit=unit)
    elif isinstance(schema, dict) and "type" in schema:
        value_schema = dict(schema)
    elif isinstance(schema, str) and fn is None:
        value_schema = {"type": "number", "x-bhms-unit": schema}
    else:
        value_schema = schema_for(schema, where=f"{owner} value", unit=unit)
        if fn is not None:
            takes_ctx = len(_signature(fn, localns).parameters) > 0
    if unit is not None and value_schema.get("type") in ("number", "integer", ["number", "null"],
                                                          ["integer", "null"]):
        value_schema.setdefault("x-bhms-unit", unit)
    text = describe_text(fn, description, 1000) if fn is not None else (description or "")
    return PropertySpec(prop_name, fn, value_schema, evidence, observable, read_effect, text, max_rate_hz,
                        requires_lease, tuple(resources), validity_ms, timeout_ms, takes_ctx, blocking)


def build_action(fn: Callable[..., Any], *, effect: str, idempotency: str, max_duration_ms: int | None = None,
                 requires_lease: bool = False, completion_evidence: str = "reported", cancel: str = "unsupported",
                 resources: tuple[str, ...] | list[str] | None = None, device_resources: tuple[str, ...] = (),
                 on_lease_loss: str | None = None, requires_fresh: dict[str, int] | list[Any] | None = None,
                 verified_by: tuple[str, ...] | list[str] = (), typical_duration_ms: int | None = None,
                 preconditions: str | None = None, description: str | None = None, name: str | None = None,
                 output: Any = None, blocking: bool = False, localns: dict[str, Any] | None = None) -> ActionSpec:
    """Build an :class:`ActionSpec` from a handler ``def name(ctx?, arg: Annotation = default, ...) -> output``.

    The first parameter is the :class:`~bhms.server.context.ActionContext` when it is named ``ctx`` (or has no
    annotation); every other parameter is an argument. ``resources`` defaults to the device's resources for an action
    with a physical effect (so leases and the unknown-operation inhibition cover it) and to none otherwise.
    """
    action_name = name or fn.__name__
    owner = f"action {action_name!r}"
    _choice(effect, EFFECTS, "effect", owner)
    _choice(idempotency, IDEMPOTENCY, "idempotency", owner)
    _choice(completion_evidence, COMPLETION_EVIDENCE, "completion_evidence", owner)
    _choice(cancel, ("supported", "unsupported"), "cancel", owner)
    if on_lease_loss is not None:
        _choice(on_lease_loss, ON_LEASE_LOSS, "on_lease_loss", owner)
        if on_lease_loss == "cancel" and cancel == "unsupported":
            raise DescriptionError(f"{owner}: on_lease_loss='cancel' needs cancel='supported'; an action that cannot be "
                                   "canceled would keep running after losing its lease. Declare cancel='supported' "
                                   "and honour ctx.cancelled, or use on_lease_loss='finish' or 'hold'")
    if max_duration_ms is None:
        if effect != "none":
            raise DescriptionError(f"{owner}: an action with a physical effect must declare max_duration_ms "
                                   "(BHMS-DEV-030); the server enforces it")
        max_duration_ms = 10_000
    if not isinstance(max_duration_ms, int) or max_duration_ms < 1:
        raise DescriptionError(f"{owner}: max_duration_ms must be a positive integer")
    sig = _signature(fn, localns)
    params = list(sig.parameters.values())
    ctx_param = None
    if params and (params[0].name == "ctx" or params[0].annotation is inspect.Parameter.empty):
        ctx_param = params.pop(0).name
    members: dict[str, Any] = {}
    required: list[str] = []
    for param in params:
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD, param.POSITIONAL_ONLY):
            raise DescriptionError(f"{owner}: parameter {param.name!r} must be a plain named parameter")
        member = schema_for(param.annotation, where=f"{owner} argument {param.name!r}")
        if param.default is inspect.Parameter.empty:
            required.append(param.name)
        else:
            member["default"] = param.default
        members[param.name] = member
    input_schema: dict[str, Any] = {"type": "object", "additionalProperties": False, "properties": members}
    if required:
        input_schema["required"] = required
    returned = output if output is not None else sig.return_annotation
    output_schema = None
    if returned not in (inspect.Signature.empty, None, type(None)):
        output_schema = schema_for(returned, where=f"{owner} result")
    if resources is None:
        resources = device_resources if effect != "none" or requires_lease else ()
    resources = tuple(resources)
    unknown = [r for r in resources if r not in device_resources]
    if unknown:
        raise DescriptionError(f"{owner}: resources {unknown} are not declared by the device "
                               f"({list(device_resources)}); action resources must be a subset (BHMS-DEV-032)")
    if effect == "hazardous" and not requires_lease:
        raise DescriptionError(f"{owner}: a hazardous action must declare requires_lease=True (BHMS-DEV-033): its "
                               "caller must hold exclusive control of the resources it acts on")
    if requires_lease and not resources:
        raise DescriptionError(f"{owner}: requires_lease=True needs at least one resource (BHMS-DEV-032); declare "
                               "resources on the device or the action")
    fresh: list[tuple[str, int]] = []
    if isinstance(requires_fresh, dict):
        fresh = [(str(p), int(m)) for p, m in requires_fresh.items()]
    elif requires_fresh:
        for item in requires_fresh:
            fresh.append((item["property"], int(item["maxAgeMs"])) if isinstance(item, dict) else
                         (str(item[0]), int(item[1])))
    names = [p for p, _ in fresh]
    if len(names) != len(set(names)):
        raise DescriptionError(f"{owner}: requires_fresh names a property twice (BHMS-DEV-034)")
    return ActionSpec(action_name, fn, input_schema, output_schema, effect, idempotency, cancel, completion_evidence,
                      max_duration_ms, requires_lease, resources, describe_text(fn, description, 1000),
                      tuple(p.name for p in params), ctx_param, tuple(verified_by), typical_duration_ms,
                      on_lease_loss, tuple(fresh), preconditions, blocking)
