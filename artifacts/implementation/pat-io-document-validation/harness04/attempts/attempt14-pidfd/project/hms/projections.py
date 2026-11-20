"""WoT-compatible DataSchema projection of the strict host invocation envelope."""
import copy

from .contracts import _SCHEMA


def data_schema(schema):
    if type(schema) is list:
        return [data_schema(child) for child in schema]
    if type(schema) is not dict:
        return schema
    return {key: data_schema(child) for key, child in schema.items() if key != "additionalProperties"}


def invoke_td_input(argument_schema):
    def expand(value):
        if type(value) is list:
            return [expand(child) for child in value]
        if type(value) is not dict:
            return value
        if "$ref" in value:
            reference = value["$ref"]
            if not reference.startswith("#/$defs/"):
                raise ValueError("only retained local schema references are allowed")
            return expand(_SCHEMA["$defs"][reference[len("#/$defs/"):]])
        return {key: expand(child) for key, child in value.items()
                if key not in {"$schema", "$id", "$defs", "additionalProperties"}}
    projected = expand(_SCHEMA)
    projected["properties"]["intent"]["properties"]["arguments"] = expand(copy.deepcopy(argument_schema))
    return projected
