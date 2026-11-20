"""Pure bounded PAT lowering to immutable ordered HMS invocation envelopes.

Bindings are trusted caller snapshots, not attested by this compiler. No clock,
registry, driver, process, resource or model is called while compiling. Runtime
admission independently checks actual installation/authority/freshness/support.
"""
from __future__ import annotations

import copy
from functools import wraps
import hashlib
import importlib.metadata
import platform
from pathlib import Path
import re

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from .contracts import SAFE_INTEGER, ContractError, canonical
from .journal import JournalError
from .pat_contracts import (PatError, accepts, closed, equal, integer, matches_static,
                            name, parse_pat, pat_digest, require, semantic, snapshot,
                            validate_parameters)
from .procedures import parse_procedure, procedure_digest
from .registry import schema_profile, validate_type_bundle


def _identity():
    root = Path(__file__).resolve().parents[1]
    paths = ["hms/pat_contracts.py", "hms/pat_compiler.py", "hms/pat_catalog.py",
             "hms/pat_execution.py", "hms/pat_bindings.py", "hms/contracts.py",
             "hms/procedures.py", "hms/registry.py", "hms/journal.py", "hms/projections.py",
             "hms/_vendor/rfc8785/__init__.py", "hms/_vendor/rfc8785/_impl.py",
             "schemas/invoke.schema.json", "research/protocols/wot-artifacts/td-schema-1.1.json"]
    sources = [{"path": path, "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()}
               for path in paths]
    dependencies = []
    for package in ("jsonschema", "referencing", "jsonschema-specifications", "attrs", "rpds-py"):
        distribution = importlib.metadata.distribution(package)
        files = []
        for item in sorted(distribution.files or [], key=str):
            # Hash imported Python/native validation code and retained schemas;
            # exclude pycache, installation paths, timestamps and RECORD order.
            if item.suffix in {".py", ".json", ".so", ".pyd"}:
                path = distribution.locate_file(item)
                if path.is_file():
                    files.append({"path": str(item), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        require(bool(files), "PAT_COMPILER_IDENTITY_UNAVAILABLE")
        dependencies.append({"package": package, "version": distribution.version, "files": files})
    # Package file closures exceed the host message budget on some installations;
    # reduce each closure to a deterministic digest, retaining counts and versions.
    packages = []
    for dependency in dependencies:
        closure = b"".join(canonical(row) + b"\n" for row in dependency["files"])
        packages.append({"package": dependency["package"], "version": dependency["version"],
                         "fileCount": len(dependency["files"]),
                         "codeDigest": "sha256:" + hashlib.sha256(closure).hexdigest()})
    return {"profile": "hms.pat-compiler-identity/0.1", "sources": sources, "packages": packages,
            "pythonImplementation": platform.python_implementation(), "pythonVersion": platform.python_version()}


# Import is the explicit implementation-identity boundary. Hot patching files
# underneath an imported module is unsupported; reload a new trusted deployment.
_COMPILER_MANIFEST = _identity()
COMPILER_DIGEST = "sha256:" + hashlib.sha256(
    b"HMS-PAT-COMPILER-SHA256-v0.1\0" + canonical(_COMPILER_MANIFEST)).hexdigest()


def compiler_digest():
    return COMPILER_DIGEST


def compiler_manifest():
    return copy.deepcopy(_COMPILER_MANIFEST)


def _input_errors(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ContractError, SchemaError, KeyError, TypeError, ValueError) as error:
            raise PatError("PAT_INVALID_COMPILATION") from error
    return checked


def _digest(value):
    require(type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None,
            "PAT_INVALID_DEPENDENCY")


def _target_scalar(schema):
    """The binder proves scalar domain inclusion only in this finite grammar."""
    require(type(schema) is dict, "PAT_UNSUPPORTED_SCHEMA")
    kind = schema.get("type")
    specific = {"integer": {"minimum", "maximum"}, "number": {"minimum", "maximum"},
                "string": {"minLength", "maxLength"}, "boolean": set(), "null": set()}
    require(type(kind) is str and kind in specific and set(schema) <= {"type", "enum", "const"} | specific[kind], "PAT_UNSUPPORTED_SCHEMA")
    if "enum" in schema:
        require(type(schema["enum"]) is list and 1 <= len(schema["enum"]) <= 64, "PAT_UNSUPPORTED_SCHEMA")
    try:
        schema_profile(schema)
    except (ContractError, JournalError, TypeError, ValueError, KeyError) as error:
        raise PatError("PAT_UNSUPPORTED_SCHEMA") from error


def _fits(schema, value):
    kind = schema["type"]
    if kind in {"integer", "number"} and type(value) not in {int, float}:
        return False
    if kind == "integer" and type(value) is not int:
        return False
    return next(Draft202012Validator(schema).iter_errors(value), None) is None


def _domain_subset(domain, target):
    _target_scalar(target)
    kind = domain["type"]
    require(target["type"] == kind or (kind == "integer" and target["type"] == "number"), "PAT_ARGUMENT_DOMAIN")
    if "enum" in domain:
        require(all(_fits(target, value) for value in domain["enum"]), "PAT_ARGUMENT_DOMAIN")
        return
    if kind == "boolean":
        require(all(_fits(target, value) for value in (False, True)), "PAT_ARGUMENT_DOMAIN")
        return
    choices = [target["const"]] if "const" in target else target.get("enum")
    if choices is not None:
        if kind == "integer":
            size = domain["maximum"] - domain["minimum"] + 1
            require(size <= len(choices) and all(_fits(target, value) for value in
                    range(domain["minimum"], domain["maximum"] + 1)), "PAT_ARGUMENT_DOMAIN")
        elif kind == "string":
            require(domain["minLength"] == domain["maxLength"] == 0 and _fits(target, ""), "PAT_ARGUMENT_DOMAIN")
        return
    if kind == "integer":
        require(domain["minimum"] >= target.get("minimum", -SAFE_INTEGER) and
                domain["maximum"] <= target.get("maximum", SAFE_INTEGER), "PAT_ARGUMENT_DOMAIN")
    elif kind == "string":
        require(domain["minLength"] >= target.get("minLength", 0) and
                domain["maxLength"] <= target["maxLength"], "PAT_ARGUMENT_DOMAIN")


def _validate_object_schema(schema):
    try:
        schema_profile(schema)
    except (ContractError, JournalError, TypeError, ValueError, KeyError) as error:
        raise PatError("PAT_INVALID_BINDING") from error
    require(schema["type"] == "object" and schema["additionalProperties"] is False,
            "PAT_UNSUPPORTED_SCHEMA")
    for value in schema["properties"].values():
        _target_scalar(value)


def _binding(descriptor, requirement):
    code = "PAT_INVALID_BINDING"
    closed(descriptor, {"type", "binding", "endpointSession", "driverProfile", "driverDigest",
                        "installationDigest", "argumentMetadata"}, code)
    for field in ("endpointSession", "driverProfile"):
        name(descriptor[field], code)
    for field in ("installationDigest", "driverDigest"):
        _digest(descriptor[field])
    require(descriptor["driverProfile"] in requirement["driverProfiles"], "PAT_DRIVER_MISMATCH")
    try:
        digest = validate_type_bundle(descriptor["type"])
    except (ContractError, JournalError, TypeError, ValueError, KeyError) as error:
        raise PatError(code) from error
    binding = descriptor["binding"]
    closed(binding, {"profile", "instanceId", "generation", "typeDigest", "calibrationRevision",
                     "controlGeneration", "mode", "adapterId", "resourceMap", "argumentSchemas"}, code)
    require(binding["profile"] == "hms.binding/0.1" and binding["mode"] == "simulation", "PAT_BINDING_MISMATCH")
    for field in ("instanceId", "generation", "calibrationRevision", "controlGeneration", "adapterId"):
        name(binding[field], code)
    require(binding["typeDigest"] == digest, "PAT_DEPENDENCY_MISMATCH")
    execution = descriptor["type"]["execution"]
    require(requirement["capabilityFamily"] in execution["capabilities"], "PAT_CAPABILITY_MISMATCH")
    require(set(requirement["actions"]) <= set(execution["actions"]), "PAT_ACTION_MISMATCH")
    require(type(binding["argumentSchemas"]) is dict and set(binding["argumentSchemas"]) == set(execution["actions"]), code)
    resources = {r for action in execution["actions"].values() for r in action["resources"]}
    require(type(binding["resourceMap"]) is dict and set(binding["resourceMap"]) == resources, code)
    for value in binding["resourceMap"].values():
        name(value, code)
    metadata = descriptor["argumentMetadata"]
    require(type(metadata) is dict and set(metadata) == set(requirement["actions"]), "PAT_METADATA_REQUIRED")
    for action_id in requirement["actions"]:
        action = execution["actions"][action_id]
        require("simulation" in action["completionEvidence"], "PAT_UNSUPPORTED_EFFECT")
        schemas = (action["inputSchema"], binding["argumentSchemas"][action_id])
        for schema in schemas:
            _validate_object_schema(schema)
        require(set(schemas[0]["properties"]) == set(schemas[1]["properties"]), "PAT_ARGUMENT_DOMAIN")
        properties = schemas[0]["properties"]
        require(type(metadata[action_id]) is dict and set(metadata[action_id]) == set(properties), "PAT_METADATA_REQUIRED")
        for argument, info in metadata[action_id].items():
            closed(info, {"unit", "frame", "unitArgument", "frameArgument"}, "PAT_METADATA_REQUIRED")
            semantic(info["unit"], "PAT_METADATA_MISMATCH")
            semantic(info["frame"], "PAT_METADATA_MISMATCH")
            numeric = properties[argument]["type"] in {"integer", "number"}
            if numeric:
                require(info["unit"] is not None, "PAT_METADATA_REQUIRED")
            else:
                require(info["unit"] is None and info["frame"] is None, "PAT_METADATA_MISMATCH")
            for dimension in ("unit", "frame"):
                companion = info[dimension + "Argument"]
                if companion is not None:
                    name(companion, "PAT_METADATA_MISMATCH")
                    require(companion != argument and companion in properties and properties[companion]["type"] == "string" and
                            info[dimension] is not None, "PAT_METADATA_MISMATCH")
                elif dimension == "frame":
                    require(info[dimension] is None, "PAT_METADATA_REQUIRED")
                elif info[dimension] not in {None, "1"}:
                    raise PatError("PAT_METADATA_REQUIRED")
    return digest


@_input_errors
def compile_pat(artifact, parameters, bindings, *, origin_ms, replay_namespace,
                procedure_key, operation_keys, caller_deadline_ms, context):
    """Return a detached plan and dependency evidence, without admitting it.

    context is exactly {taskKind,inputProfile,evidenceMode,deployment}; operation_keys is a
    complete stepId->key map. All freshness/identity is explicitly supplied and
    must be retained by the caller; this function generates no time or key.
    """
    artifact = parse_pat(artifact)
    parameters = validate_parameters(artifact, parameters)
    bindings = snapshot(bindings, "PAT_INVALID_BINDING")
    context = snapshot(context, "PAT_INVALID_CONTEXT")
    closed(bindings, artifact["roles"], "PAT_INVALID_BINDING")
    closed(context, {"taskKind", "inputProfile", "evidenceMode", "deployment"}, "PAT_INVALID_CONTEXT")
    name(context["deployment"], "PAT_INVALID_CONTEXT")
    require(matches_static(artifact, parameters, task_kind=context["taskKind"], input_profile=context["inputProfile"],
                           evidence_mode=context["evidenceMode"]), "PAT_NOT_APPLICABLE")
    integer(origin_ms, code="PAT_TIME_BOUNDS")
    integer(caller_deadline_ms, origin_ms + 1, code="PAT_TIME_BOUNDS")
    name(replay_namespace, "PAT_INVALID_IDENTITY")
    name(procedure_key, "PAT_INVALID_IDENTITY")
    operation_keys = snapshot(operation_keys, "PAT_INVALID_IDENTITY")
    closed(operation_keys, [step["stepId"] for step in artifact["steps"]], "PAT_INVALID_IDENTITY")
    for key in operation_keys.values():
        name(key, "PAT_INVALID_IDENTITY")
    require(len(set(operation_keys.values()) | {procedure_key}) == len(operation_keys) + 1, "PAT_INVALID_IDENTITY")
    budget = artifact["timingBudget"]
    end = origin_ms + budget["latestCompletionOffsetMs"]
    require(end <= min(caller_deadline_ms, SAFE_INTEGER), "PAT_TIME_BOUNDS")
    dependencies = []
    for role, requirement in artifact["roles"].items():
        descriptor = bindings[role]
        type_digest = _binding(descriptor, requirement)
        binding = descriptor["binding"]
        dependencies.append({"role": role, "descriptionDigest": type_digest,
            "bindingDigest": "sha256:" + hashlib.sha256(canonical(binding)).hexdigest(),
            "instanceId": binding["instanceId"], "bindingGeneration": binding["generation"],
            "controlGeneration": binding["controlGeneration"], "calibrationRevision": binding["calibrationRevision"],
            "endpointSession": descriptor["endpointSession"], "driverProfile": descriptor["driverProfile"],
            "driverDigest": descriptor["driverDigest"], "installationDigest": descriptor["installationDigest"],
            "metadataDigest": "sha256:" + hashlib.sha256(canonical(descriptor["argumentMetadata"])).hexdigest()})
    children = []
    for step in artifact["steps"]:
        descriptor = bindings[step["role"]]
        binding = descriptor["binding"]
        action = descriptor["type"]["execution"]["actions"][step["actionId"]]
        require(step["timing"]["maxRunMs"] <= action["maxRunMs"], "PAT_TIME_BOUNDS")
        schemas = (action["inputSchema"], binding["argumentSchemas"][step["actionId"]])
        args = {key: parameters[expression["parameter"]] if "parameter" in expression else expression["literal"]
                for key, expression in step["arguments"].items()}
        metadata = descriptor["argumentMetadata"][step["actionId"]]
        for schema in schemas:
            require(set(schema["required"]) <= set(args) <= set(schema["properties"]), "PAT_ARGUMENT_DOMAIN")
            require(next(Draft202012Validator(schema).iter_errors(args), None) is None, "PAT_ARGUMENT_DOMAIN")
            for argument, expression in step["arguments"].items():
                if "parameter" in expression:
                    declaration = artifact["parameters"][expression["parameter"]]
                    _domain_subset(declaration["valueSchema"], schema["properties"][argument])
                    require(declaration["unit"] == metadata[argument]["unit"] and
                            declaration["frame"] == metadata[argument]["frame"], "PAT_SEMANTICS_MISMATCH")
                else:
                    require(_fits(schema["properties"][argument], expression["literal"]), "PAT_ARGUMENT_DOMAIN")
        for argument in args:
            for dimension in ("unit", "frame"):
                info = metadata[argument]
                companion = info[dimension + "Argument"]
                if companion is not None:
                    require(companion in args and equal(args[companion], info[dimension]), "PAT_SEMANTICS_MISMATCH")
                    expression = step["arguments"][companion]
                    if "parameter" in expression:
                        _domain_subset(artifact["parameters"][expression["parameter"]]["valueSchema"],
                                       {"type": "string", "maxLength": 4096, "const": info[dimension]})
        window = step["timing"]
        intent = {"instanceId": binding["instanceId"], "actionId": step["actionId"],
            "endpointSession": descriptor["endpointSession"], "controlGeneration": binding["controlGeneration"],
            "descriptionDigest": binding["typeDigest"], "bindingGeneration": binding["generation"],
            "calibrationRevision": binding["calibrationRevision"], "arguments": args,
            "requiredEffect": "capability_completion", "timing": {
                "notBeforeUnixMs": origin_ms + window["notBeforeOffsetMs"],
                "latestStartUnixMs": origin_ms + window["latestStartOffsetMs"],
                "maxRunMs": window["maxRunMs"],
                "latestCompletionUnixMs": origin_ms + window["latestCompletionOffsetMs"]}}
        children.append({"stepId": step["stepId"], "request": {"protocol": "hms.invoke/0.1",
            "replayNamespace": replay_namespace, "operationKey": operation_keys[step["stepId"]], "intent": intent}})
    request = {"protocol": "hms.procedure/0.1", "replayNamespace": replay_namespace,
        "procedureKey": procedure_key, "procedure": {"profile": "hms.bound-sequence/0.1", "timing": {
            "notBeforeUnixMs": origin_ms, "latestStartUnixMs": origin_ms + budget["latestStartOffsetMs"],
            "latestCompletionUnixMs": end}, "steps": children}}
    try:
        request = parse_procedure(request)
    except ContractError as error:
        raise PatError("PAT_LOWERING_INVALID") from error
    dependencies.sort(key=lambda value: value["role"])
    evaluation_environment = {"profile": "hms.pat.environment/0.1", "deployment": context["deployment"],
        "evidenceMode": "simulation", "compilerDigest": COMPILER_DIGEST, "roles": {
        row["role"]: {"typeDigest": row["descriptionDigest"], "bindingDigest": row["bindingDigest"],
                      "installationDigest": row["installationDigest"], "argumentMetadataDigest": row["metadataDigest"],
                      "driverProfile": row["driverProfile"], "driverDigest": row["driverDigest"]}
        for row in dependencies}}
    binding_document = {"bindings": bindings, "compilerDigest": COMPILER_DIGEST,
                        "targetProfile": artifact["targetProfile"]}
    result = {"request": request, "requestDigest": procedure_digest(request), "patDigest": pat_digest(artifact),
        "compilerDigest": COMPILER_DIGEST,
        "evaluationEnvironment": evaluation_environment,
        "environmentDigest": "sha256:" + hashlib.sha256(b"HMS-PAT-ENVIRONMENT-v0.1\0" + canonical(evaluation_environment)).hexdigest(),
        "runBindingDigest": "sha256:" + hashlib.sha256(b"HMS-PAT-RUN-BINDING-v0.1\0" + canonical(binding_document)).hexdigest(),
        "dependencies": dependencies,
        "report": {"targetProfile": artifact["targetProfile"], "stepCount": len(children), "admitted": False,
            "parameterDomainPreserved": True, "unitConversions": [], "frameConversions": [],
            "unsupported": [], "runtimeGuards": "installed_primitive_guards_only",
            "evidenceMode": "simulation", "physicalObjectiveVerified": False}}
    canonical(result)
    return result
