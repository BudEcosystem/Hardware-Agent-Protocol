"""Exact baseline bodies for independent differential comparison."""
import copy
import hashlib
from hms.synthetic_io_installation import (_handler_details, type_bundle, argument_schema,
    validate_type_bundle, control_generation)
from hms.resource_topology import (_errors, identifier, parse_topology, _generations,
    _require, _atom_index, _alias_closures, _consumer_details, _hash,
    PROOF_PROFILE, _VALIDATORS, canonical)

def reference_definitions(document):
    """Return original I/O type bundles and proof-derived exact bindings."""
    result = {}
    instances = sorted({row['instanceId'] for row in document['handlers']})
    for instance in instances:
        bundle = None; resources = {}; proof = None
        for row in (item for item in document['handlers'] if item['instanceId'] == instance):
            action = row['actionId']
            detail, proof = _handler_details(document, instance, action, proof)
            role = 'io-root:' + action
            part = type_bundle('finite-io-' + hashlib.sha256(instance.encode()).hexdigest()[:16], action,
                argument_schema(detail), {'type': 'integer', 'minimum': 0, 'maximum': 9007199254740991},
                unit='1', effect=detail['primitive'], resource=role)
            part['execution']['actions'][action]['preconditions'] = []
            part['execution']['capabilities'] = ['sim:finite-gpio-pwm']
            part['td']['description'] = 'Original finite synthetic I/O; value counts activations, not measured electrical state.'
            if bundle is None:
                bundle = part
            else:
                bundle['execution']['actions'].update(part['execution']['actions'])
                bundle['td']['actions'].update(part['td']['actions'])
            resources[role] = detail['root']
        digest = validate_type_bundle(bundle)
        adapter = next(key for key, values in document['routes']['adapters'].items() if instance in values)
        binding = {'profile': 'hms.binding/0.1', 'instanceId': instance, 'generation': proof['bindingGeneration'],
            'typeDigest': digest, 'calibrationRevision': 'synthetic:finite-io:1', 'controlGeneration': control_generation(proof),
            'mode': 'simulation', 'adapterId': adapter, 'resourceMap': resources,
            'argumentSchemas': {key: copy.deepcopy(item['inputSchema']) for key, item in bundle['execution']['actions'].items()}}
        result[instance] = {'type': bundle, 'binding': binding, 'proof': proof}
    return result


@_errors
def reference_binding_proof(topology, generations, instance_id):
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
