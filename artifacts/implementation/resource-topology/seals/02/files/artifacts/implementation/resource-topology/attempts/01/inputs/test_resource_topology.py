"""Original pure topology contract tests, not runtime resource exclusion tests."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
from hms import resource_topology as graph
from hms.contracts import canonical

HERE = Path(__file__).resolve().parent


def node(kind, properties=None, *, contains=(), requires=()):
    return {"kind": kind, "contains": list(contains), "requires": list(requires), "properties": properties or {}}


def pin():
    return node("pin", {"electrical": {"evidenceMode": "simulation", "nominalMilliVolt": 3300,
        "maxSourceMicroAmp": 10000, "maxSinkMicroAmp": 10000,
        "modes": ["digital_input", "push_pull_output", "pwm_output"], "idleMode": "high_impedance"}})


def topology():
    nodes = {
        "hub": node("hub", contains=("board", "svcA", "svcB")),
        "board": node("board", contains=("pin5", "pin6", "timer0", "gpio5", "gpio6", "pwm5", "rawtimer")),
        "svcA": node("service", {"serviceProfile": "synthetic-service/0.1"}, contains=("driverA",), requires=("hub",)),
        "svcB": node("service", {"serviceProfile": "synthetic-service/0.1"}, contains=("driverB",), requires=("hub",)),
        "driverA": node("driver", {"driverProfile": "synthetic-io-hub/0.1", "implementationDigest": "sha256:" + "a" * 64}, requires=("svcA",)),
        "driverB": node("driver", {"driverProfile": "synthetic-io-hub/0.1", "implementationDigest": "sha256:" + "a" * 64}, requires=("svcB",)),
        "pin5": pin(), "pin6": pin(),
        "timer0": node("timer", {"minFrequencyHz": 100, "maxFrequencyHz": 10000, "resolutionBits": 8}, contains=("chan0",)),
        "chan0": node("timer_channel", {"timer": "timer0", "pin": "pin5"}),
        "gpio5": node("gpio_access", {"pin": "pin5"}, requires=("driverA",)),
        "gpio6": node("gpio_access", {"pin": "pin6"}, requires=("driverB",)),
        "pwm5": node("pwm_access", {"channel": "chan0"}, requires=("driverA",)),
        "rawtimer": node("timer_access", {"timer": "timer0"}, requires=("driverA",)),
    }
    atoms = {"atom:" + key: {"node": key, "purpose": "lifecycle" if value["kind"] in {"driver", "service"} else "exclusive_hardware"}
             for key, value in nodes.items() if value["kind"] in {"driver", "service", "pin", "timer", "timer_channel"}}
    aliases = {"alias:gpio5": {"node": "gpio5", "includes": ["atom:pin5"]},
               "alias:gpio6": {"node": "gpio6", "includes": ["atom:pin6"]},
               "alias:pwm5": {"node": "pwm5", "includes": ["alias:gpio5", "atom:timer0", "atom:chan0"]},
               "alias:timer0": {"node": "rawtimer", "includes": ["atom:timer0"]}}
    consumers = [{"instanceId": "sim:" + item, "actionId": action, "rootAliases": [root], "requires": []}
                 for item, action, root in (("gpio5", "pulse", "alias:gpio5"), ("gpio6", "pulse", "alias:gpio6"),
                                           ("pwm5", "burst", "alias:pwm5"), ("timer0", "reconfigure", "alias:timer0"))]
    return {"profile": graph.PROFILE, "topologyId": "synthetic:board-hub", "deployment": "simulation:io-hub",
            "nodes": nodes, "atoms": atoms, "aliases": aliases, "consumers": consumers}


def generations(value):
    return {"profile": graph.GENERATION_PROFILE, "topologyDigest": graph.topology_digest(value),
            "revision": 1, "nodes": {key: "generation:1" for key in value["nodes"]}}


def with_bus():
    value = topology()
    value["nodes"].update({
        "bus0": node("bus", {"busProfile": "synthetic-i2c/0.1", "pins": ["pin5", "pin6"],
            "minRateHz": 100, "maxRateHz": 100000, "addressBits": 7}),
        "address1": node("bus_address", {"bus": "bus0", "address": 16}),
        "rawbus": node("bus_access", {"bus": "bus0", "addressNode": None}, requires=("driverA",)),
        "devicebus": node("bus_access", {"bus": "bus0", "addressNode": "address1"}, requires=("driverA",))})
    for name in ("bus0", "address1"):
        value["atoms"]["atom:" + name] = {"node": name, "purpose": "exclusive_hardware"}
    value["aliases"].update({"alias:rawbus": {"node": "rawbus", "includes": ["atom:bus0", "atom:pin5", "atom:pin6"]},
        "alias:devicebus": {"node": "devicebus", "includes": ["alias:rawbus", "atom:address1"]}})
    for name, root in (("rawbus", "alias:rawbus"), ("devicebus", "alias:devicebus")):
        value["consumers"].append({"instanceId": "sim:" + name, "actionId": "transaction", "rootAliases": [root], "requires": []})
    return value


class ResourceTopologyTests(unittest.TestCase):
    def test_gpio_pwm_overlap_and_independent_pad_have_exact_atoms(self):
        value = topology(); current = generations(value)
        gpio = graph.binding_proof(value, current, "sim:gpio5")
        pwm = graph.binding_proof(value, current, "sim:pwm5")
        other = graph.binding_proof(value, current, "sim:gpio6")
        self.assertEqual(gpio["expandedClaims"], {"pulse": ["atom:pin5"]})
        self.assertEqual(pwm["expandedClaims"], {"burst": ["atom:chan0", "atom:pin5", "atom:timer0"]})
        self.assertEqual(set(gpio["expandedClaims"]["pulse"]) & set(pwm["expandedClaims"]["burst"]), {"atom:pin5"})
        self.assertFalse(set(other["expandedClaims"]["pulse"]) & set(pwm["expandedClaims"]["burst"]))
        self.assertIn("svcA", pwm["dependencies"])
        self.assertNotIn("atom:svcA", pwm["expandedClaims"]["burst"])
        self.assertNotIn("hub", pwm["expandedClaims"]["burst"])

    def test_unrelated_generation_is_ignored_relevant_generation_changes_binding(self):
        value = topology(); current = generations(value)
        before = graph.binding_proof(value, current, "sim:gpio5")
        current["revision"] = 2; current["nodes"]["svcB"] = "generation:2"
        self.assertEqual(before, graph.binding_proof(value, current, "sim:gpio5"))
        current["nodes"]["svcA"] = "generation:2"
        after = graph.binding_proof(value, current, "sim:gpio5")
        self.assertNotEqual(before["closureDigest"], after["closureDigest"])
        self.assertNotEqual(before["bindingGeneration"], after["bindingGeneration"])
        self.assertEqual(before["expandedClaims"], after["expandedClaims"])

    def test_scoped_identity_excludes_unrelated_properties_and_structural_containment(self):
        value = topology(); before = graph.binding_proof(value, generations(value), "sim:gpio5")
        value["nodes"]["pin6"]["properties"]["electrical"]["nominalMilliVolt"] = 3000
        value["nodes"]["board"]["contains"].remove("pin5")
        value["nodes"]["hub"]["contains"].append("pin5")
        after = graph.binding_proof(value, generations(value), "sim:gpio5")
        self.assertNotEqual(before["topologyDigest"], after["topologyDigest"])
        self.assertEqual(before["closureDigest"], after["closureDigest"])

    def test_relevant_electrical_and_driver_implementation_changes_visible(self):
        value = topology(); before = graph.binding_proof(value, generations(value), "sim:gpio5")
        for node_id, field, changed in (("pin5", "electrical", None), ("driverA", "implementationDigest", "sha256:" + "b" * 64)):
            other = copy.deepcopy(value)
            if changed is None:
                other["nodes"][node_id]["properties"][field]["nominalMilliVolt"] = 3000
            else:
                other["nodes"][node_id]["properties"][field] = changed
            self.assertNotEqual(before["closureDigest"], graph.binding_proof(other, generations(other), "sim:gpio5")["closureDigest"])

    def test_lifecycle_scope_is_reverse_dependencies_not_whole_hub(self):
        value = topology()
        scope = graph.generation_change_claims(value, "svcA")
        self.assertEqual(scope["claims"], ["atom:chan0", "atom:pin5", "atom:svcA", "atom:timer0"])
        self.assertEqual({row["instanceId"] for row in scope["affectedConsumers"]}, {"sim:gpio5", "sim:pwm5", "sim:timer0"})
        self.assertNotIn("atom:pin6", scope["claims"])
        self.assertEqual(scope["policy"], "refuse_if_busy")
        value["consumers"] = []
        self.assertEqual(graph.generation_change_claims(value, "svcA")["claims"], ["atom:svcA"])
        with self.assertRaisesRegex(graph.ResourceTopologyError, "RESOURCE_UNSUPPORTED_LIFECYCLE"):
            graph.generation_change_claims(value, "hub")

    def test_bus_raw_and_addressed_share_controller_and_pins(self):
        value = with_bus(); current = generations(value)
        raw = graph.binding_proof(value, current, "sim:rawbus")["expandedClaims"]["transaction"]
        addressed = graph.binding_proof(value, current, "sim:devicebus")["expandedClaims"]["transaction"]
        self.assertEqual(raw, ["atom:bus0", "atom:pin5", "atom:pin6"])
        self.assertEqual(addressed, ["atom:address1", *raw])
        self.assertIn("atom:pin5", raw)

    def test_missing_or_shrunken_pwm_alias_refuses(self):
        for includes in (["atom:timer0", "atom:chan0"], ["atom:pin5"], ["missing"], []):
            value = topology(); value["aliases"]["alias:pwm5"]["includes"] = includes
            with self.subTest(includes=includes), self.assertRaises(graph.ResourceTopologyError):
                graph.parse_topology(value)

    def test_all_graph_cycle_classes_and_multiple_parent_refuse(self):
        value = topology(); value["nodes"]["board"]["contains"].append("hub")
        with self.assertRaisesRegex(graph.ResourceTopologyError, "RESOURCE_CONTAINMENT_CYCLE"):
            graph.parse_topology(value)
        value = topology(); value["nodes"]["svcA"]["requires"].append("driverA")
        with self.assertRaisesRegex(graph.ResourceTopologyError, "RESOURCE_DEPENDENCY_CYCLE"):
            graph.parse_topology(value)
        value = topology(); value["aliases"]["alias:gpio5"]["includes"] = ["alias:pwm5"]
        with self.assertRaisesRegex(graph.ResourceTopologyError, "RESOURCE_ALIAS_CYCLE"):
            graph.parse_topology(value)
        value = topology(); value["nodes"]["hub"]["contains"].append("pin5")
        with self.assertRaisesRegex(graph.ResourceTopologyError, "RESOURCE_MULTIPLE_PARENTS"):
            graph.parse_topology(value)

    def test_missing_and_wrong_kind_references_including_unused_access_refuse(self):
        mutations = [lambda d: d["nodes"]["board"]["contains"].append("missing"),
            lambda d: d["nodes"]["svcA"]["requires"].append("missing"),
            lambda d: d["nodes"]["chan0"]["properties"].update(timer="pin5"),
            lambda d: d["nodes"].update(unused=node("gpio_access", {"pin": "missing"})),
            lambda d: d["consumers"][0]["rootAliases"].append("missing"),
            lambda d: d["consumers"][0]["requires"].append("missing")]
        for index, mutate in enumerate(mutations):
            value = topology(); mutate(value)
            with self.subTest(mutation=index), self.assertRaises(graph.ResourceTopologyError):
                graph.parse_topology(value)

    def test_exact_atom_coverage_duplicate_purpose_and_namespace_refuse(self):
        mutations = [lambda d: d["atoms"].pop("atom:driverA"),
            lambda d: d["atoms"].update(duplicate={"node": "pin5", "purpose": "exclusive_hardware"}),
            lambda d: d["atoms"]["atom:pin5"].update(purpose="lifecycle"),
            lambda d: d["atoms"].update(illegal={"node": "hub", "purpose": "lifecycle"}),
            lambda d: d["aliases"].update({"atom:pin5": copy.deepcopy(d["aliases"]["alias:gpio5"])})]
        for index, mutate in enumerate(mutations):
            value = topology(); mutate(value)
            with self.subTest(mutation=index), self.assertRaises(graph.ResourceTopologyError):
                graph.parse_topology(value)

    def test_electrical_range_mode_and_exact_integer_refusals(self):
        for field, wrong in (("nominalMilliVolt", 0), ("nominalMilliVolt", 5001), ("maxSourceMicroAmp", 20001),
                             ("nominalMilliVolt", True), ("nominalMilliVolt", 3300.0), ("idleMode", "drive_low")):
            value = topology(); value["nodes"]["pin5"]["properties"]["electrical"][field] = wrong
            with self.subTest(field=field, wrong=wrong), self.assertRaises(graph.ResourceTopologyError):
                graph.parse_topology(value)
        value = topology(); value["nodes"]["pin5"]["properties"]["electrical"]["modes"] = ["digital_input"]
        with self.assertRaisesRegex(graph.ResourceTopologyError, "RESOURCE_ELECTRICAL_MODE"):
            graph.parse_topology(value)
        value = topology(); value["nodes"]["timer0"]["properties"]["minFrequencyHz"] = 11000
        with self.assertRaisesRegex(graph.ResourceTopologyError, "RESOURCE_INVALID_RANGE"):
            graph.parse_topology(value)

    def test_bus_address_bounds_duplicate_and_cross_bus_refuse(self):
        for wrong in (128, -1, True, 16.0):
            value = with_bus(); value["nodes"]["address1"]["properties"]["address"] = wrong
            with self.subTest(wrong=wrong), self.assertRaises(graph.ResourceTopologyError):
                graph.parse_topology(value)
        value = with_bus(); value["nodes"]["address2"] = copy.deepcopy(value["nodes"]["address1"])
        value["atoms"]["atom:address2"] = {"node": "address2", "purpose": "exclusive_hardware"}
        with self.assertRaisesRegex(graph.ResourceTopologyError, "RESOURCE_DUPLICATE_ADDRESS"):
            graph.parse_topology(value)
        value = with_bus(); value["nodes"]["bus1"] = copy.deepcopy(value["nodes"]["bus0"])
        value["atoms"]["atom:bus1"] = {"node": "bus1", "purpose": "exclusive_hardware"}
        value["nodes"]["address1"]["properties"]["bus"] = "bus1"
        with self.assertRaisesRegex(graph.ResourceTopologyError, "RESOURCE_BUS_MISMATCH"):
            graph.parse_topology(value)

    def test_generations_close_exactly_and_do_not_claim_historical_nonreuse(self):
        value = topology(); current = generations(value)
        self.assertEqual(graph.parse_generations(value, current), current)
        mutations = [lambda g: g["nodes"].pop("hub"), lambda g: g["nodes"].update(extra="generation:1"),
            lambda g: g.update(topologyDigest="sha256:" + "0" * 64), lambda g: g.update(revision=True),
            lambda g: g.update(revision=1.0), lambda g: g.update(revision=0)]
        for index, mutate in enumerate(mutations):
            candidate = copy.deepcopy(current); mutate(candidate)
            with self.subTest(mutation=index), self.assertRaises(graph.ResourceTopologyError):
                graph.parse_generations(value, candidate)
        # This pure function has no historical store; it must not pretend that
        # accepting the same snapshot proves token nonreuse over time.
        self.assertEqual(graph.parse_generations(value, current), current)

    def test_order_normalization_and_detachment(self):
        value = topology(); original = copy.deepcopy(value)
        current = generations(value); proof = graph.binding_proof(value, current, "sim:pwm5")
        value["consumers"].reverse()
        for item in value["nodes"].values():
            item["contains"].reverse(); item["requires"].reverse()
        value["aliases"]["alias:pwm5"]["includes"].reverse()
        self.assertEqual(graph.topology_digest(value), graph.topology_digest(original))
        self.assertEqual(proof, graph.binding_proof(value, current, "sim:pwm5"))
        parsed = graph.parse_topology(value); parsed["nodes"]["hub"]["contains"].clear()
        proof["dependencies"].clear(); proof["expandedClaims"]["burst"].clear()
        self.assertEqual(graph.binding_proof(value, current, "sim:pwm5"), graph.binding_proof(original, current, "sim:pwm5"))

    def test_alias_depth_and_node_count_limits_refuse_without_truncation(self):
        value = topology(); previous = "atom:pin5"
        for index in range(17):
            key = "alias:chain" + str(index)
            value["aliases"][key] = {"node": "gpio5", "includes": [previous]}; previous = key
        with self.assertRaisesRegex(graph.ResourceTopologyError, "RESOURCE_GRAPH_DEPTH"):
            graph.parse_topology(value)
        value = topology()
        for index in range(129):
            value["nodes"]["extra" + str(index)] = node("board")
        with self.assertRaises(graph.ResourceTopologyError):
            graph.parse_topology(value)

    def test_consumer_and_lifecycle_claim_bounds_are_separate(self):
        value = topology()
        for index in range(31):
            key = "extra" + str(index)
            value["nodes"][key] = pin()
            value["nodes"]["access" + key] = node("gpio_access", {"pin": key}, requires=("svcA",))
            value["atoms"]["atom:" + key] = {"node": key, "purpose": "exclusive_hardware"}
            value["aliases"]["alias:" + key] = {"node": "access" + key, "includes": ["atom:" + key]}
            value["consumers"].append({"instanceId": "sim:" + key, "actionId": "pulse", "rootAliases": ["alias:" + key], "requires": []})
        graph.parse_topology(value)  # Every ordinary action still needs <=3.
        with self.assertRaisesRegex(graph.ResourceTopologyError, "RESOURCE_CLAIM_LIMIT"):
            graph.generation_change_claims(value, "svcA")
        value["consumers"][0]["rootAliases"] = list(value["aliases"])
        with self.assertRaisesRegex(graph.ResourceTopologyError, "RESOURCE_CLAIM_LIMIT"):
            graph.parse_topology(value)

    def test_closed_shape_duplicate_consumer_and_carrier_refusals(self):
        for value in ({}, [], topology() | {"command": "no"}, b'{"profile":"x","profile":"y"}'):
            with self.subTest(value=value), self.assertRaises(graph.ResourceTopologyError):
                graph.parse_topology(value)
        value = topology(); value["consumers"].append(copy.deepcopy(value["consumers"][0]) | {"requires": ["svcA"]})
        with self.assertRaisesRegex(graph.ResourceTopologyError, "RESOURCE_DUPLICATE_CONSUMER"):
            graph.parse_topology(value)
        value = topology(); value["topologyId"] = "x" * 65537
        with self.assertRaises(graph.ResourceTopologyError):
            graph.parse_topology(value)
        value = topology(); value["nodes"]["hub\n"] = value["nodes"].pop("hub")
        with self.assertRaises(graph.ResourceTopologyError):
            graph.parse_topology(value)

    def test_schema_outputs_and_pure_calls_do_not_open_authority(self):
        value = topology(); current = generations(value)
        with patch("pathlib.Path.read_bytes", side_effect=AssertionError("I/O")), \
             patch("time.time_ns", side_effect=AssertionError("clock")), \
             patch("sqlite3.connect", side_effect=AssertionError("authority")):
            parsed = graph.parse_topology(canonical(value))
            proof = graph.binding_proof(parsed, current, "sim:pwm5")
            scope = graph.generation_change_claims(parsed, "driverA")
        self.assertEqual(scope["policy"], "refuse_if_busy")
        for profile, data in ((graph.PROFILE, parsed), (graph.GENERATION_PROFILE, current), (graph.PROOF_PROFILE, proof)):
            self.assertIsNone(next(graph._VALIDATORS[profile].iter_errors(data), None))
