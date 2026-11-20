"""Closed, bounded parametric sequence artifacts; no execution or inference.

Only static selection predicates and already installed primitive guards are
supported. This is not a standing-controller, learning or physical-I/O profile.
"""
from __future__ import annotations

import copy
import hashlib

from .contracts import SAFE_INTEGER, ContractError, canonical, identifier, parse_json
from .journal import JournalError

PAT_PROFILE = "hms.pat.bound-sequence/0.1"
TARGET_PROFILE = "hms.bound-sequence/0.1"
_DIGEST_PREFIX = b"HMS-PAT-JCS-SHA256-v0.1\x00"


class PatError(JournalError):
    """Stable refusal code; detail is diagnostic and never grants authority."""
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.detail = detail


def require(condition, code="PAT_INVALID_ARTIFACT", detail=None):
    if not condition:
        raise PatError(code, detail)


def closed(value, fields, code="PAT_INVALID_ARTIFACT"):
    require(type(value) is dict and set(value) == set(fields), code)


def snapshot(value, code="PAT_INVALID_ARTIFACT"):
    """Preserve Python numeric types before JCS can normalize 1.0 into 1."""
    try:
        if type(value) is bytes:
            return parse_json(value)
        canonical(value)
        result = copy.deepcopy(value)
        canonical(result)
        return result
    except (ContractError, RecursionError, TypeError, ValueError) as error:
        raise PatError(code) from error


def name(value, code="PAT_INVALID_ARTIFACT"):
    try:
        return identifier(value)
    except ContractError as error:
        raise PatError(code) from error


def integer(value, minimum=0, maximum=SAFE_INTEGER, code="PAT_INVALID_ARTIFACT"):
    require(type(value) is int and minimum <= value <= maximum, code)
    return value


def semantic(value, code="PAT_INVALID_ARTIFACT"):
    if value is not None:
        name(value, code)


def scalar(value):
    return value is None or type(value) in {str, int, bool}


def equal(left, right):
    return type(left) is type(right) and left == right


def accepts(schema, value):
    kind = schema["type"]
    if ((kind == "integer" and type(value) is not int) or
            (kind == "boolean" and type(value) is not bool) or
            (kind == "string" and type(value) is not str)):
        return False
    if kind == "integer" and not schema["minimum"] <= value <= schema["maximum"]:
        return False
    if kind == "string" and not schema["minLength"] <= len(value) <= schema["maxLength"]:
        return False
    return "enum" not in schema or any(equal(value, item) for item in schema["enum"])


def _parameter_schema(schema):
    require(type(schema) is dict)
    kind = schema.get("type")
    require(type(kind) is str, "PAT_UNSUPPORTED_SCHEMA")
    fields = {"integer": {"type", "minimum", "maximum"},
              "boolean": {"type"}, "string": {"type", "minLength", "maxLength"}}.get(kind)
    require(fields is not None, "PAT_UNSUPPORTED_SCHEMA")
    require(set(schema) in (fields, fields | {"enum"}), "PAT_UNSUPPORTED_SCHEMA")
    if kind == "integer":
        integer(schema["minimum"], -SAFE_INTEGER)
        integer(schema["maximum"], schema["minimum"])
    if kind == "string":
        integer(schema["minLength"], 0, 4096)
        integer(schema["maxLength"], schema["minLength"], 4096)
    if "enum" in schema:
        values = schema["enum"]
        require(type(values) is list and 1 <= len(values) <= 64)
        bare = {key: value for key, value in schema.items() if key != "enum"}
        require(all(accepts(bare, value) for value in values))
        require(len({canonical(value) for value in values}) == len(values))


def parse_pat(value):
    """Return a detached, strictly typed artifact; accepting it admits no work."""
    artifact = snapshot(value)
    closed(artifact, {"protocol", "profile", "name", "version", "taskKind", "inputProfile",
        "parameters", "roles", "applicability", "targetProfile", "executionPlacement",
        "timingBudget", "steps", "effectBudget", "outcomeContract", "runtimeGuardProfile"})
    require(artifact["protocol"] == "hms.pat/0.1" and artifact["profile"] == PAT_PROFILE,
            "PAT_PROFILE_UNSUPPORTED")
    require(artifact["targetProfile"] == TARGET_PROFILE and
            artifact["executionPlacement"] == "hms-host-orchestration" and
            artifact["runtimeGuardProfile"] == "installed_primitive_guards_only", "PAT_UNSUPPORTED_FEATURE")
    for field in ("name", "version", "taskKind", "inputProfile"):
        name(artifact[field])
    parameters = artifact["parameters"]
    require(type(parameters) is dict and len(parameters) <= 32)
    for parameter, declaration in parameters.items():
        name(parameter)
        closed(declaration, {"valueSchema", "unit", "frame"})
        _parameter_schema(declaration["valueSchema"])
        semantic(declaration["unit"])
        semantic(declaration["frame"])
        if declaration["valueSchema"]["type"] == "integer":
            require(declaration["unit"] is not None, "PAT_SEMANTICS_REQUIRED")
        else:
            require(declaration["unit"] is None and declaration["frame"] is None, "PAT_SEMANTICS_MISMATCH")
    roles = artifact["roles"]
    require(type(roles) is dict and 1 <= len(roles) <= 16)
    for role, requirement in roles.items():
        name(role)
        closed(requirement, {"capabilityFamily", "actions", "driverProfiles"})
        name(requirement["capabilityFamily"])
        for field in ("actions", "driverProfiles"):
            values = requirement[field]
            require(type(values) is list and 1 <= len(values) <= 16)
            for item in values:
                name(item)
            require(len(set(values)) == len(values))
    applicability = artifact["applicability"]
    closed(applicability, {"phase", "all"})
    require(applicability["phase"] == "selection", "PAT_UNSUPPORTED_GUARD")
    predicates = applicability["all"]
    require(type(predicates) is list and len(predicates) <= 32)
    for predicate in predicates:
        require(type(predicate) is dict)
        op = predicate.get("op")
        if op == "equals":
            closed(predicate, {"field", "op", "literal"})
            require(scalar(predicate["literal"]))
        elif op == "range":
            closed(predicate, {"field", "op", "minimum", "maximum"})
            integer(predicate["minimum"], -SAFE_INTEGER)
            integer(predicate["maximum"], predicate["minimum"])
        else:
            raise PatError("PAT_UNSUPPORTED_PREDICATE")
        field = predicate["field"]
        require(type(field) is str, "PAT_UNSUPPORTED_PREDICATE")
        if field.startswith("parameters."):
            parameter = field[len("parameters."):]
            require(parameter in parameters, "PAT_UNSUPPORTED_PREDICATE")
            domain = parameters[parameter]["valueSchema"]
            if op == "equals":
                require(accepts(domain, predicate["literal"]), "PAT_INVALID_PREDICATE")
            else:
                require(domain["type"] == "integer" and
                        domain["minimum"] <= predicate["minimum"] <= predicate["maximum"] <= domain["maximum"],
                        "PAT_INVALID_PREDICATE")
        else:
            require(field in {"trigger.taskKind", "trigger.inputProfile", "context.evidenceMode"} and
                    op == "equals" and type(predicate["literal"]) is str, "PAT_UNSUPPORTED_PREDICATE")
    timing = artifact["timingBudget"]
    closed(timing, {"latestStartOffsetMs", "latestCompletionOffsetMs", "maxRunSumMs"})
    integer(timing["latestStartOffsetMs"], 1, 2**32 - 1)
    integer(timing["latestCompletionOffsetMs"], timing["latestStartOffsetMs"], 2**32 - 1)
    integer(timing["maxRunSumMs"], 1, 16 * (2**32 - 1))
    steps = artifact["steps"]
    require(type(steps) is list and 1 <= len(steps) <= 16)
    ids, used, used_actions, run_sum = set(), set(), {}, 0
    for index, step in enumerate(steps):
        closed(step, {"stepId", "role", "actionId", "arguments", "timing"})
        for key in ("stepId", "role", "actionId"):
            name(step[key])
        require(step["stepId"] not in ids)
        ids.add(step["stepId"])
        require(step["role"] in roles and step["actionId"] in roles[step["role"]]["actions"])
        used_actions.setdefault(step["role"], set()).add(step["actionId"])
        arguments = step["arguments"]
        require(type(arguments) is dict and len(arguments) <= 32)
        for argument, expression in arguments.items():
            name(argument)
            require(type(expression) is dict and len(expression) == 1, "PAT_UNSUPPORTED_EXPRESSION")
            if set(expression) == {"parameter"}:
                require(type(expression["parameter"]) is str and expression["parameter"] in parameters,
                        "PAT_UNKNOWN_PARAMETER")
                used.add(expression["parameter"])
            elif set(expression) == {"literal"}:
                require(scalar(expression["literal"]), "PAT_UNSUPPORTED_EXPRESSION")
            else:
                raise PatError("PAT_UNSUPPORTED_EXPRESSION")
        window = step["timing"]
        closed(window, {"notBeforeOffsetMs", "latestStartOffsetMs", "maxRunMs", "latestCompletionOffsetMs"})
        integer(window["notBeforeOffsetMs"], 0, 2**32 - 1)
        integer(window["latestStartOffsetMs"], window["notBeforeOffsetMs"], 2**32 - 1)
        integer(window["latestCompletionOffsetMs"], window["latestStartOffsetMs"], timing["latestCompletionOffsetMs"])
        integer(window["maxRunMs"], 1, 2**32 - 1)
        require(window["maxRunMs"] <= window["latestCompletionOffsetMs"] - window["notBeforeOffsetMs"], "PAT_TIME_BOUNDS")
        if index == 0:
            require(window["latestStartOffsetMs"] <= timing["latestStartOffsetMs"], "PAT_TIME_BOUNDS")
        run_sum += window["maxRunMs"]
    require(used == set(parameters), "PAT_UNUSED_PARAMETER")
    require(set(used_actions) == set(roles) and all(used_actions[r] == set(roles[r]["actions"]) for r in roles),
            "PAT_UNUSED_REQUIREMENT")
    require(run_sum <= timing["maxRunSumMs"] <= timing["latestCompletionOffsetMs"], "PAT_TIME_BOUNDS")
    closed(artifact["effectBudget"], {"maxInvocations", "scope"})
    integer(artifact["effectBudget"]["maxInvocations"], len(steps), 16)
    require(artifact["effectBudget"]["scope"] == "simulation_only", "PAT_UNSUPPORTED_EFFECT")
    outcome = artifact["outcomeContract"]
    closed(outcome, {"requiredEffect", "requiredCompletedSteps", "evidenceMode", "physicalObjectiveVerified"})
    require(outcome["requiredEffect"] == "capability_completion" and outcome["evidenceMode"] == "simulation" and
            outcome["physicalObjectiveVerified"] is False, "PAT_UNSUPPORTED_EFFECT")
    require(outcome["requiredCompletedSteps"] == [step["stepId"] for step in steps])
    return artifact


def pat_digest(value):
    return "sha256:" + hashlib.sha256(_DIGEST_PREFIX + canonical(parse_pat(value))).hexdigest()


def validate_parameters(artifact, parameters):
    artifact = parse_pat(artifact)
    parameters = snapshot(parameters, "PAT_INVALID_PARAMETERS")
    closed(parameters, artifact["parameters"], "PAT_INVALID_PARAMETERS")
    for key, value in parameters.items():
        require(accepts(artifact["parameters"][key]["valueSchema"], value), "PAT_PARAMETER_OUT_OF_DOMAIN")
    return parameters


def matches_static(artifact, parameters, *, task_kind, input_profile, evidence_mode):
    """Deterministic selection only; no dynamic observations or admission."""
    artifact = parse_pat(artifact)
    parameters = validate_parameters(artifact, parameters)
    if (task_kind != artifact["taskKind"] or input_profile != artifact["inputProfile"] or evidence_mode != "simulation"):
        return False
    fields = {"trigger.taskKind": task_kind, "trigger.inputProfile": input_profile,
              "context.evidenceMode": evidence_mode}
    fields.update({"parameters." + key: value for key, value in parameters.items()})
    for predicate in artifact["applicability"]["all"]:
        value = fields[predicate["field"]]
        if predicate["op"] == "equals" and not equal(value, predicate["literal"]):
            return False
        if predicate["op"] == "range" and not predicate["minimum"] <= value <= predicate["maximum"]:
            return False
    return True
