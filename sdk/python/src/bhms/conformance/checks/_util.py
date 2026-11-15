"""Helpers shared by the check modules: vector loading and description walking."""

from __future__ import annotations

import json
from collections.abc import Iterator
from importlib import resources
from typing import Any

from bhms.conformance.wire import tested_version


def vectors(name: str) -> dict[str, Any]:
    """A vector file of ``spec/bhms/conformance/vectors`` (shipped as ``bhms/conformance/vectors``)."""
    return json.loads(resources.files("bhms.conformance").joinpath("vectors", f"{name}.json").read_text())


def raw_bytes(template: str, encoding: str | None, meta: dict[str, Any]) -> bytes:
    text = template.replace("{{meta}}", json.dumps(meta)).replace("{{version}}", tested_version())
    return text.encode(encoding or "utf-8")


def numeric_inputs(description: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any], bool]]:
    """``(action, member, schema, required)`` for every top-level number/integer member of every action input."""
    for action, spec in (description.get("actions") or {}).items():
        schema = spec.get("input") or {}
        required = set(schema.get("required") or [])
        for member, sub in (schema.get("properties") or {}).items():
            if isinstance(sub, dict) and sub.get("type") in ("number", "integer"):
                yield action, member, sub, member in required


def walk_schema(schema: Any, path: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    """Every sub-schema (dict) with its path."""
    if isinstance(schema, dict):
        yield path, schema
        for key, value in schema.items():
            if key in ("properties", "$defs", "definitions", "patternProperties") and isinstance(value, dict):
                for name, sub in value.items():
                    yield from walk_schema(sub, f"{path}/{key}/{name}")
            elif key in ("items", "additionalProperties", "not", "if", "then", "else", "contains", "propertyNames"):
                yield from walk_schema(value, f"{path}/{key}")
            elif key in ("allOf", "anyOf", "oneOf", "prefixItems") and isinstance(value, list):
                for i, sub in enumerate(value):
                    yield from walk_schema(sub, f"{path}/{key}/{i}")
