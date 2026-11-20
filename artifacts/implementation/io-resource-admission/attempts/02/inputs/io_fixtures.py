"""Original synthetic topology fixture helpers copied from the pinned pure tests."""
import copy
from hms import resource_topology as graph

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

