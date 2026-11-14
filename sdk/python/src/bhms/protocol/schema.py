"""The packaged BHMS JSON Schema and an opt-in strict validator.

``bhms.schema.json`` next to this module is a symlink to
``spec/bhms/schema/bhms.schema.json``: the repository keeps one source file, and
the build hook (``setup.py``) copies its bytes into every wheel and sdist and
refuses to build without them (``tests/test_schema_module.py`` asserts equality,
``tests/test_hardening_packaging.py`` builds a wheel and imports from it).

Hot paths validate with the pydantic models in :mod:`bhms.protocol.types`; full JSON
Schema validation (this module) is the opt-in ``strict=True`` mode and the
conformance suite's oracle.

``multipleOf`` follows BHMS-DEV-071: ``jsonschema`` divides binary floats, so
``50.1`` is not a multiple of ``0.1`` there. Here a float quotient within 1e-9
(relative) of an integer counts as a multiple; integers stay exact.

Thread-safety: validators are immutable after construction; the caches are
idempotent.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator, ValidationError, validators

from bhms.protocol.errors import BhmsError

_TOLERANCE = 1e-9


def schema_bytes() -> bytes:
    """The packaged schema file, byte for byte.

    Raises ``FileNotFoundError`` that says what to do when the file is a dangling symbolic link: in a checkout it is a
    link into ``spec/``, and a copy of the package made without following links has the link but not its target.
    """
    packaged = resources.files("bhms.protocol").joinpath("bhms.schema.json")
    try:
        return packaged.read_bytes()
    except FileNotFoundError:
        raise FileNotFoundError(
            f"{packaged} cannot be read: in a checkout it is a symbolic link to spec/bhms/schema/bhms.schema.json, and "
            "this copy of the package has no such file behind it. Install the package with pip install (a built wheel "
            "contains the file), or copy it with symbolic links followed (cp -L, rsync -L) or together with spec/"
        ) from None


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """The parsed schema document (shared; do not mutate)."""
    return json.loads(schema_bytes())


def _multiple_of(validator: Any, divisor: Any, instance: Any, schema: dict[str, Any]) -> Any:
    if not validator.is_type(instance, "number"):
        return
    if isinstance(instance, float) or isinstance(divisor, float):
        quotient = instance / divisor
        if abs(quotient - round(quotient)) <= _TOLERANCE * max(1.0, abs(quotient)):
            return
    elif instance % divisor == 0:
        return
    yield ValidationError(f"{instance!r} is not a multiple of {divisor!r}")


_Validator = validators.extend(Draft202012Validator, {"multipleOf": _multiple_of})


def compile_schema(schema: dict[str, Any] | bool) -> Draft202012Validator:
    """A validator for an embedded JSON Schema (an action ``input``/``output``, a property ``schema``).

    Uses the same DEV-071 ``multipleOf`` tolerance as the message validators. The schema is used as given; callers
    check BHMS-DEV-040/041 rules separately (``bhms.server.validation.check_units``).
    """
    return _Validator(schema)


@lru_cache(maxsize=None)
def validator(def_name: str) -> Draft202012Validator:
    """Cached validator for ``$defs/<def_name>`` (KeyError if the definition does not exist)."""
    document = load_schema()
    if def_name not in document["$defs"]:
        raise KeyError(def_name)
    return _Validator({"$schema": document["$schema"], "$ref": f"#/$defs/{def_name}", "$defs": document["$defs"]})


MAX_SCHEMA_DEPTH = 32
"""BHMS-SEC-021: the deepest subschema of an embedded schema is at most this many subschema steps below its root (the root is depth 0)."""
MAX_SUBSCHEMAS = 10_000
"""BHMS-SEC-021: an embedded schema has at most this many schemas, its root and boolean schemas included."""
SUBSCHEMA_SINGLE = ("items", "not", "if", "then", "else", "additionalProperties", "contains", "propertyNames", "unevaluatedItems",
                    "unevaluatedProperties", "contentSchema")
SUBSCHEMA_LISTS = ("allOf", "anyOf", "oneOf", "prefixItems")
SUBSCHEMA_MAPS = ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas")
_REFERENCES = ("$ref", "$dynamicRef")


class SchemaBoundsError(ValueError):
    """An embedded schema exceeds the BHMS-SEC-021 bounds or refers outside itself (BHMS-DEV-040); the message names the path."""


def iter_subschemas(schema: Any, where: str = "schema") -> Iterator[tuple[str, Any]]:
    """Yield ``(path, subschema)`` for the root of an embedded schema and every subschema, in document order (pre-order), enforcing
    BHMS-SEC-021 and BHMS-DEV-040 on the way. This is the one schema walker of the SDK: the device server (its own descriptions,
    program inputs) and the gateway (upstream descriptions) both use it, so their bounds cannot disagree.

    Rules (spec/bhms/13-security.md §13.3):

    * depth: the root is depth 0 and every step through a subschema keyword adds one; a subschema deeper than
      :data:`MAX_SCHEMA_DEPTH` raises;
    * count: the root and every subschema position count (``true``/``false`` are schemas); more than :data:`MAX_SUBSCHEMAS` raises;
    * references: a ``$ref``/``$dynamicRef`` that is not a fragment of the schema itself (``#...``) raises; nothing is ever fetched.

    The subschema keywords are those of JSON Schema 2020-12 (the applicator, unevaluated and content vocabularies plus
    ``definitions``). A value that is not a schema (a number where a schema belongs) is yielded as it is and has no children:
    structural validity is the JSON Schema validator's business, not this walk's.

    Args:
        schema: the embedded schema (an action ``input``/``output``, a property ``schema``, an event ``data`` schema, a program ``input``).
        where: the path prefix used in messages and yielded paths.

    Raises:
        SchemaBoundsError: a ``ValueError`` naming the path and the violated requirement.

    Iterative, and children are counted before they are queued, so time and memory are bounded by the limits whatever the input
    is. Thread-safety: pure function. Example::

        for path, node in iter_subschemas(action["input"], "actions.move.input"):
            ...
    """
    max_depth, max_nodes = MAX_SCHEMA_DEPTH, MAX_SUBSCHEMAS  # read at call time: one place to change them
    count = 1
    stack: list[tuple[str, Any, int]] = [(where, schema, 0)]
    while stack:
        path, node, depth = stack.pop()
        if depth > max_depth:
            raise SchemaBoundsError(f"{_short(path)}: schema nested deeper than {max_depth} (BHMS-SEC-021)")
        if isinstance(node, dict):
            for keyword in _REFERENCES:
                ref = node.get(keyword)
                if isinstance(ref, str) and not ref.startswith("#"):
                    raise SchemaBoundsError(f"{_short(path)}: {keyword} {ref[:80]!r} points outside the schema; schemas are never fetched "
                                            "(BHMS-DEV-040)")
        yield path, node
        if not isinstance(node, dict):
            continue
        children: list[tuple[str, Any, int]] = []
        for path_of, members in _children(node, path):
            count += 1
            if count > max_nodes:
                raise SchemaBoundsError(f"{where}: more than {max_nodes} subschemas (BHMS-SEC-021)")
            children.append((path_of, members, depth + 1))
        stack.extend(reversed(children))


def _short(path: str) -> str:
    """A path for a message: property names come from the (possibly hostile) schema, so it is cut."""
    return path if len(path) <= 160 else f"{path[:120]}...{path[-37:]}"


def _children(node: dict[str, Any], path: str) -> Iterator[tuple[str, Any]]:
    for key in SUBSCHEMA_SINGLE:
        if key in node:
            yield f"{path}.{key}", node[key]
    for key in SUBSCHEMA_LISTS:
        members = node.get(key)
        if isinstance(members, list):
            for index, child in enumerate(members):
                yield f"{path}.{key}[{index}]", child
    for key in SUBSCHEMA_MAPS:
        members = node.get(key)
        if isinstance(members, dict):
            for name, child in members.items():
                yield f"{path}.{key}.{name}", child


def schema_bounds_problem(schema: Any, where: str = "schema") -> str | None:
    """Why an embedded schema must not be validated or served (the :func:`iter_subschemas` refusal), or None."""
    try:
        for _ in iter_subschemas(schema, where):
            pass
    except SchemaBoundsError as exc:
        return str(exc)
    return None


def _pointer(error: ValidationError) -> str:
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in error.absolute_path)


def validate(def_name: str, obj: Any) -> None:
    """Validate ``obj`` against ``$defs/<def_name>``.

    Raises ``BhmsError("INVALID_ARGUMENT")`` whose ``field`` is the JSON pointer of the
    offending member (empty string = the whole value) and whose hint names the failed
    keyword. KeyError for an unknown definition.
    """
    errors = list(validator(def_name).iter_errors(obj))
    if not errors:
        return
    from jsonschema.exceptions import best_match

    error = best_match(errors) or errors[0]
    pointer = _pointer(error)
    message = f"{def_name}{pointer or ''}: {error.message}"[:500]
    raise BhmsError("INVALID_ARGUMENT", message, field=pointer[:512], bound=None,
                    hint=f"schema keyword {error.validator!r} failed; see spec/bhms/schema/bhms.schema.json "
                         f"$defs/{def_name}"[:2000])


def from_pydantic_error(exc: Any, *, what: str = "params") -> BhmsError:
    """Map a ``pydantic.ValidationError`` to ``INVALID_ARGUMENT`` naming the first offending member.

    ``field`` is the spec's path form (``arguments.position``, ``resources[2]``): dotted members, ``[i]``
    indexes; pydantic's internal union/function markers are skipped. A model-level rule that raises
    :class:`~bhms.protocol.types._base.MemberError` names the member at fault (``resolution.effect``).
    """
    first = exc.errors(include_url=False)[0]
    field = ""
    for part in first["loc"]:
        if isinstance(part, int):
            field += f"[{part}]"
        elif not any(c in part for c in "[()"):
            field += f".{part}" if field else part
    member = getattr((first.get("ctx") or {}).get("error"), "member", None)
    if isinstance(member, str):  # a model rule names the member at fault (Ruling R45: the most specific member wins)
        field += f".{member}" if field else member
    message = f"{what}{'.' + field if field else ''}: {first['msg']}"[:500]
    return BhmsError("INVALID_ARGUMENT", message, field=field[:512],
                     hint=f"fix {field or what} ({first['type']}); see spec/bhms/schema/bhms.schema.json"[:2000])
