"""Trusted test services; deliberately no hardware authentication or adapters."""
import json

from hms.journal import Admission, Context, Evidence, JournalError

CONTEXT = Context("test-principal", "test-deployment")


class TestPolicy:
    def __init__(self):
        self.denied = set()
        self.admissions = 0
        self.rechecks = 0
        self.binding = "binding:1"
        self.lease_expires_ms = 1900

    def authorize(self, context, verb, target):
        if verb in self.denied:
            raise JournalError("ACCESS_DENIED")

    def admit(self, context, intent, now_ms):
        self.admissions += 1
        self._validate(intent)
        return Admission(("axis:focus",), "test-policy:1", self.lease_expires_ms)

    def recheck(self, context, operation, now_ms):
        self.rechecks += 1
        self._validate(operation["intent"])

    def _validate(self, intent):
        if intent["bindingGeneration"] != self.binding:
            raise JournalError("BINDING_CHANGED")
        args = intent["arguments"]
        if (set(args) != {"distance", "unit", "frame"} or
                type(args["distance"]) not in {int, float} or not -10 <= args["distance"] <= 10 or
                args["unit"] != "um" or args["frame"] != "stage"):
            raise JournalError("INVALID_ACTION_ARGUMENTS")

    def evidence(self, operation, evidence):
        if evidence.source != "test-simulator" or evidence.kind != "simulation":
            raise JournalError("UNTRUSTED_EVIDENCE")


def request(namespace, key="first", **intent_changes):
    intent = {
        "instanceId": "sim:microscope", "actionId": "sim:focus-relative",
        "endpointSession": "session:1", "controlGeneration": "control:1",
        "descriptionDigest": "sha256:" + "a" * 64,
        "bindingGeneration": "binding:1", "calibrationRevision": "calibration:1",
        "arguments": {"distance": 5, "unit": "um", "frame": "stage"},
        "timing": {"notBeforeUnixMs": 1000, "latestStartUnixMs": 2000,
                   "maxRunMs": 500, "latestCompletionUnixMs": 2500},
        "requiredEffect": "capability_completion",
    }
    intent.update(intent_changes)
    return json.dumps({"protocol": "hms.invoke/0.1", "replayNamespace": namespace,
                       "operationKey": key, "intent": intent}, ensure_ascii=False).encode()


def evidence(*assertions):
    return Evidence("simulation", "test-simulator", "trace:1", assertions)
