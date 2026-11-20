"""Pure bounded synthetic resource topology; no provider or admission authority.

Structural containment never expands claims. Caller documents are declarations,
not physical attestations. Runtime installation, historical generation nonreuse,
authorization, atomic publication and real electrical behavior are separate.
"""
from __future__ import annotations

import copy
from collections import OrderedDict
from functools import wraps
import hashlib
import json
from pathlib import Path
import threading

from jsonschema import Draft202012Validator

from .contracts import ContractError, MAX_BYTES, canonical, identifier, parse_json
from .journal import JournalError

PROFILE = "hms.resource-topology/0.1"
GENERATION_PROFILE = "hms.resource-generations/0.1"
PROOF_PROFILE = "hms.resource-binding-proof/0.1"
MAX_DEPTH = 16
MAX_CLAIMS = 32
_PHYSICAL = {"pin", "timer", "timer_channel", "bus", "bus_address"}
_ACCESS = {"gpio_access", "pwm_access", "timer_access", "bus_access"}
_ROOT = Path(__file__).resolve().parents[1]
_VALIDATORS = {}
for _profile, _filename in ((PROFILE, "resource-topology.schema.json"),
                           (GENERATION_PROFILE, "resource-generations.schema.json"),
                           (PROOF_PROFILE, "resource-binding-proof.schema.json")):
    _schema = json.loads((_ROOT / "schemas" / _filename).read_bytes())
    Draft202012Validator.check_schema(_schema)
    _VALIDATORS[_profile] = Draft202012Validator(_schema)

# Successful JSON Schema checks retain an immutable snapshot, keyed by exact
# bounded canonical bytes and validator identity. Callers get detached built-in
# containers; every graph/generation/authority-dependent semantic check remains.
# Eight entries retain at most512KiB of byte keys plus their bounded frozen trees.
# Validators are private import-time objects; this is not deployment attestation.
_SCHEMA_MEMO_LIMIT = 8
_SCHEMA_MEMO = OrderedDict()
_SCHEMA_MEMO_LOCK = threading.Lock()


class ResourceTopologyError(JournalError):
    """Stable refusal without interpreting a document as authority."""


def _require(condition, code):
    if not condition:
        raise ResourceTopologyError(code)


def _errors(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ContractError, KeyError, TypeError, ValueError, RecursionError) as error:
            raise ResourceTopologyError("RESOURCE_INVALID_DOCUMENT") from error
    return checked


def _strict_tree(value):
    # Reject integral float tokens before canonical JSON can normalize them.
    _require(type(value) in {dict, list, str, int, bool, type(None)}, "RESOURCE_INVALID_SCALAR")
    if type(value) is dict:
        _require(all(type(key) is str for key in value), "RESOURCE_INVALID_DOCUMENT")
        for child in value.values():
            _strict_tree(child)
    elif type(value) is list:
        for child in value:
            _strict_tree(child)


def _freeze_snapshot(value):
    """Only called on a bounded parsed/strict/schema-checked built-in tree."""
    if type(value) is dict:
        return ('dict', tuple((key, _freeze_snapshot(child)) for key, child in value.items()))
    if type(value) is list:
        return ('list', tuple(_freeze_snapshot(child) for child in value))
    return value


def _thaw_snapshot(value):
    # Frozen entries contain no caller objects or copy hooks.
    if type(value) is tuple:
        if value[0] == 'dict':
            return {key: _thaw_snapshot(child) for key, child in value[1]}
        return [_thaw_snapshot(child) for child in value[1]]
    return value


def _cached_snapshot(profile, encoded):
    validator = _VALIDATORS[profile]
    key = (profile, encoded)
    with _SCHEMA_MEMO_LOCK:
        entry = _SCHEMA_MEMO.get(key)
        if entry is not None and entry[0] is validator:
            _SCHEMA_MEMO.move_to_end(key)
            return entry[1]
    return None


def _snapshot(value, profile):
    if type(value) is bytes:
        # A byte hit can only match a previously accepted canonical carrier.
        # Oversized bytes must reach the original bounded parser without hashing
        # or retaining a new unbounded key. Noncanonical carriers take that same
        # original parse/strict/encode path below.
        if len(value) <= MAX_BYTES:
            cached = _cached_snapshot(profile, value)
            if cached is not None:
                return _thaw_snapshot(cached)
        value = parse_json(value)
        _strict_tree(value)
        encoded = canonical(value)
    else:
        # Reject unsupported Python objects and bound the original tree before
        # traversing it recursively. Canonical encoding does not mutate scalar
        # types: inspect the original before accepting its detached JSON copy.
        encoded = canonical(value)
        _strict_tree(value)
        cached = _cached_snapshot(profile, encoded)
        if cached is not None:
            return _thaw_snapshot(cached)
        value = parse_json(encoded)
        _strict_tree(value)
        # Reuse the bounded canonical bytes that produced this detached tree.
    validator = _VALIDATORS[profile]
    key = (profile, encoded)
    with _SCHEMA_MEMO_LOCK:
        entry = _SCHEMA_MEMO.get(key)
        if entry is not None and entry[0] is validator:
            _SCHEMA_MEMO.move_to_end(key)
            return value
    _require(next(validator.iter_errors(value), None) is None, "RESOURCE_INVALID_DOCUMENT")
    frozen = _freeze_snapshot(value)
    with _SCHEMA_MEMO_LOCK:
        if _VALIDATORS[profile] is validator:
            _SCHEMA_MEMO[key] = (validator, frozen)
            _SCHEMA_MEMO.move_to_end(key)
            while len(_SCHEMA_MEMO) > _SCHEMA_MEMO_LIMIT:
                _SCHEMA_MEMO.popitem(last=False)
    return value


def _hash(domain, value):
    return "sha256:" + hashlib.sha256(domain + b"\0" + canonical(value)).hexdigest()


def _dag(edges, code):
    """Validate a DAG and its longest path with memoization, not path expansion."""
    active, depths = set(), {}

    def visit(node):
        _require(node not in active, code)
        if node in depths:
            return depths[node]
        active.add(node)
        depth = 1
        for child in edges[node]:
            _require(child in edges, "RESOURCE_MISSING_REFERENCE")
            depth = max(depth, 1 + visit(child))
        active.remove(node)
        _require(depth <= MAX_DEPTH, "RESOURCE_GRAPH_DEPTH")
        depths[node] = depth
        return depth

    for node in edges:
        visit(node)


def _node(nodes, key, kind=None):
    _require(key in nodes, "RESOURCE_MISSING_REFERENCE")
    value = nodes[key]
    _require(kind is None or value["kind"] == kind, "RESOURCE_REFERENCE_KIND")
    return value


def _atom_index(document):
    result = {}
    for name, atom in document["atoms"].items():
        node = _node(document["nodes"], atom["node"])
        expected = "exclusive_hardware" if node["kind"] in _PHYSICAL else "lifecycle" if node["kind"] in {"service", "driver"} else None
        _require(atom["purpose"] == expected, "RESOURCE_ATOM_KIND")
        key = (atom["node"], atom["purpose"])
        _require(key not in result, "RESOURCE_DUPLICATE_ATOM")
        result[key] = name
    for key, node in document["nodes"].items():
        purpose = "exclusive_hardware" if node["kind"] in _PHYSICAL else "lifecycle" if node["kind"] in {"service", "driver"} else None
        if purpose is not None:
            _require((key, purpose) in result, "RESOURCE_MISSING_ATOM")
    return result


def _footprint(document, access, atoms):
    nodes = document["nodes"]
    function = _node(nodes, access)
    kind, fields = function["kind"], function["properties"]
    touched = {access}
    physical = set()
    if kind == "gpio_access":
        pin = _node(nodes, fields["pin"], "pin")
        _require("push_pull_output" in pin["properties"]["electrical"]["modes"], "RESOURCE_ELECTRICAL_MODE")
        physical.add(fields["pin"])
    elif kind == "pwm_access":
        channel = _node(nodes, fields["channel"], "timer_channel")["properties"]
        _node(nodes, channel["timer"], "timer")
        pin = _node(nodes, channel["pin"], "pin")
        _require("pwm_output" in pin["properties"]["electrical"]["modes"], "RESOURCE_ELECTRICAL_MODE")
        physical.update((fields["channel"], channel["timer"], channel["pin"]))
    elif kind == "timer_access":
        _node(nodes, fields["timer"], "timer")
        physical.add(fields["timer"])
    elif kind == "bus_access":
        bus = _node(nodes, fields["bus"], "bus")["properties"]
        physical.update((fields["bus"], *bus["pins"]))
        if fields["addressNode"] is not None:
            address = _node(nodes, fields["addressNode"], "bus_address")
            _require(address["properties"]["bus"] == fields["bus"], "RESOURCE_BUS_MISMATCH")
            physical.add(fields["addressNode"])
    else:
        raise ResourceTopologyError("RESOURCE_ALIAS_KIND")
    touched.update(physical)
    return {atoms[(node, "exclusive_hardware")] for node in physical}, touched


def _alias_closures(document):
    aliases, atoms = document["aliases"], document["atoms"]
    _require(not set(aliases) & set(atoms), "RESOURCE_AMBIGUOUS_REFERENCE")
    edges = {}
    for key, value in aliases.items():
        for item in value["includes"]:
            _require(item in aliases or item in atoms, "RESOURCE_MISSING_REFERENCE")
        edges[key] = [item for item in value["includes"] if item in aliases]
    _dag(edges, "RESOURCE_ALIAS_CYCLE")
    resolved = {}

    def resolve(key):
        if key not in resolved:
            result = set()
            for item in aliases[key]["includes"]:
                result.update(resolve(item) if item in aliases else {item})
            resolved[key] = result
        return resolved[key]

    for key in aliases:
        resolve(key)
    return resolved


def _normalize(document):
    for node in document["nodes"].values():
        node["contains"].sort()
        node["requires"].sort()
        if node["kind"] == "pin":
            node["properties"]["electrical"]["modes"].sort()
        elif node["kind"] == "bus":
            node["properties"]["pins"].sort()
    for alias in document["aliases"].values():
        alias["includes"].sort()
    for consumer in document["consumers"]:
        consumer["rootAliases"].sort()
        consumer["requires"].sort()
    document["consumers"].sort(key=lambda row: (row["instanceId"], row["actionId"]))
    return document


@_errors
def parse_topology(value):
    """Validate closed structure and exact typed footprints; return detached data."""
    document = _snapshot(value, PROFILE)
    nodes = document["nodes"]
    parents = {}
    for key, node in nodes.items():
        for child in node["contains"]:
            _require(child not in parents, "RESOURCE_MULTIPLE_PARENTS")
            parents[child] = key
        fields = node["properties"]
        if node["kind"] == "timer":
            _require(fields["minFrequencyHz"] <= fields["maxFrequencyHz"], "RESOURCE_INVALID_RANGE")
        elif node["kind"] == "timer_channel":
            _node(nodes, fields["timer"], "timer")
            _node(nodes, fields["pin"], "pin")
        elif node["kind"] == "bus":
            _require(fields["minRateHz"] <= fields["maxRateHz"], "RESOURCE_INVALID_RANGE")
            for pin in fields["pins"]:
                _node(nodes, pin, "pin")
        elif node["kind"] == "bus_address":
            _node(nodes, fields["bus"], "bus")
    _dag({key: value["contains"] for key, value in nodes.items()}, "RESOURCE_CONTAINMENT_CYCLE")
    _dag({key: value["requires"] for key, value in nodes.items()}, "RESOURCE_DEPENDENCY_CYCLE")
    addresses = [(node["properties"]["bus"], node["properties"]["address"])
                 for node in nodes.values() if node["kind"] == "bus_address"]
    _require(len(addresses) == len(set(addresses)), "RESOURCE_DUPLICATE_ADDRESS")
    atoms = _atom_index(document)
    for key, node in nodes.items():
        if node["kind"] in _ACCESS:
            _footprint(document, key, atoms)
    closures = _alias_closures(document)
    for key, alias in document["aliases"].items():
        footprint, _ = _footprint(document, alias["node"], atoms)
        _require(closures[key] == footprint, "RESOURCE_ALIAS_FOOTPRINT")
    seen = set()
    for consumer in document["consumers"]:
        key = (consumer["instanceId"], consumer["actionId"])
        _require(key not in seen, "RESOURCE_DUPLICATE_CONSUMER")
        seen.add(key)
        for dependency in consumer["requires"]:
            _node(nodes, dependency)
        claims = set()
        for alias in consumer["rootAliases"]:
            _require(alias in closures, "RESOURCE_MISSING_REFERENCE")
            claims.update(closures[alias])
        _require(1 <= len(claims) <= MAX_CLAIMS, "RESOURCE_CLAIM_LIMIT")
    return _normalize(document)


@_errors
def topology_digest(value):
    return _hash(b"HMS-RESOURCE-TOPOLOGY-v0.1", parse_topology(value))


def _generations(document, value):
    result = _snapshot(value, GENERATION_PROFILE)
    _require(result["topologyDigest"] == _hash(b"HMS-RESOURCE-TOPOLOGY-v0.1", document), "RESOURCE_TOPOLOGY_CHANGED")
    _require(set(result["nodes"]) == set(document["nodes"]), "RESOURCE_GENERATION_CLOSURE")
    return result


@_errors
def parse_generations(topology, value):
    """Validate one snapshot; historical token nonreuse needs the future catalog."""
    return _generations(parse_topology(topology), value)


def _consumer_details(document, consumer, atoms, closures):
    aliases, node_ids, claims = set(), set(), set()

    def alias_visit(key):
        if key in aliases:
            return
        aliases.add(key)
        alias = document["aliases"][key]
        _, touched = _footprint(document, alias["node"], atoms)
        node_ids.update(touched)
        claims.update(closures[key])
        for child in alias["includes"]:
            if child in document["aliases"]:
                alias_visit(child)

    for key in consumer["rootAliases"]:
        alias_visit(key)
    node_ids.update(consumer["requires"])

    def dependency_visit(key):
        for dependency in document["nodes"][key]["requires"]:
            if dependency not in node_ids:
                node_ids.add(dependency)
                dependency_visit(dependency)

    for key in list(node_ids):
        dependency_visit(key)
    return {"aliases": aliases, "nodes": node_ids, "claims": claims}


@_errors
def binding_proof(topology, generations, instance_id):
    """Return scoped static binding evidence; no authority or qualification claim."""
    identifier(instance_id)
    document = parse_topology(topology)
    current = _generations(document, generations)
    consumers = [row for row in document["consumers"] if row["instanceId"] == instance_id]
    _require(consumers, "RESOURCE_UNKNOWN_CONSUMER")
    atoms, closures = _atom_index(document), _alias_closures(document)
    details = {row["actionId"]: _consumer_details(document, row, atoms, closures) for row in consumers}
    nodes = set().union(*(value["nodes"] for value in details.values()))
    aliases = set().union(*(value["aliases"] for value in details.values()))
    claims = set().union(*(value["claims"] for value in details.values()))
    dependencies = {key: current["nodes"][key] for key in sorted(nodes)}
    # Containment is descriptive. Keep it in the full topology provenance but
    # exclude child lists from executable identity and exclusive-claim closure.
    identity = {"profile": "hms.resource-executable-closure/0.1", "deployment": document["deployment"],
        "topologyId": document["topologyId"], "instanceId": instance_id, "consumers": consumers,
        "nodes": {key: {field: document["nodes"][key][field] for field in ("kind", "requires", "properties")} for key in sorted(nodes)},
        "aliases": {key: document["aliases"][key] for key in sorted(aliases)},
        "atoms": {key: document["atoms"][key] for key in sorted(claims)}, "dependencies": dependencies}
    digest = _hash(b"HMS-RESOURCE-EXECUTABLE-CLOSURE-v0.1", identity)
    result = {"profile": PROOF_PROFILE, "instanceId": instance_id,
        "bindingGeneration": "resource-binding:" + digest.removeprefix("sha256:"),
        "topologyDigest": current["topologyDigest"],
        "actionRoots": {row["actionId"]: row["rootAliases"] for row in consumers},
        "expandedClaims": {key: sorted(value["claims"]) for key, value in details.items()},
        "dependencies": dependencies, "closureDigest": digest}
    _require(next(_VALIDATORS[PROOF_PROFILE].iter_errors(result), None) is None, "RESOURCE_INVALID_PROOF")
    canonical(result)
    return copy.deepcopy(result)


@_errors
def generation_change_claims(topology, target):
    """Resolve refuse-if-busy scope for every action of each rebound instance.

    Binding identity covers all actions of an instance. A sibling action must
    therefore be excluded even when its own dependencies omit the target.
    This computes claims only; it changes neither generations nor authority.
    """
    identifier(target)
    document = parse_topology(topology)
    node = _node(document["nodes"], target)
    _require(node["kind"] in {"driver", "service"}, "RESOURCE_UNSUPPORTED_LIFECYCLE")
    atoms, closures = _atom_index(document), _alias_closures(document)
    claims = {atoms[(target, "lifecycle")]}
    affected = []
    details = [(consumer, _consumer_details(document, consumer, atoms, closures))
               for consumer in document["consumers"]]
    rebound_instances = {consumer["instanceId"] for consumer, detail in details
                         if target in detail["nodes"]}
    for consumer, detail in details:
        if consumer["instanceId"] in rebound_instances:
            claims.update(detail["claims"])
            affected.append({"instanceId": consumer["instanceId"], "actionId": consumer["actionId"]})
    _require(len(claims) <= MAX_CLAIMS, "RESOURCE_CLAIM_LIMIT")
    return {"profile": "hms.resource-generation-change-scope/0.1", "target": target,
            "policy": "refuse_if_busy", "affectedConsumers": affected, "claims": sorted(claims)}
