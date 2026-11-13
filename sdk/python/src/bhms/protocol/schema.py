"""The packaged BHMS JSON Schema and an opt-in strict validator.

``bhms.schema.json`` next to this module is a symlink to
``spec/bhms/schema/bhms.schema.json``: the repository keeps one source file and
``[tool.setuptools.package-data]`` ships its bytes (``tests/test_schema_module.py``
asserts equality).

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
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator, ValidationError, validators

from bhms.protocol.errors import BhmsError

_TOLERANCE = 1e-9


def schema_bytes() -> bytes:
    """The packaged schema file, byte for byte."""
    return resources.files("bhms.protocol").joinpath("bhms.schema.json").read_bytes()


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


@lru_cache(maxsize=None)
def validator(def_name: str) -> Draft202012Validator:
    """Cached validator for ``$defs/<def_name>`` (KeyError if the definition does not exist)."""
    document = load_schema()
    if def_name not in document["$defs"]:
        raise KeyError(def_name)
    return _Validator({"$schema": document["$schema"], "$ref": f"#/$defs/{def_name}", "$defs": document["$defs"]})


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
