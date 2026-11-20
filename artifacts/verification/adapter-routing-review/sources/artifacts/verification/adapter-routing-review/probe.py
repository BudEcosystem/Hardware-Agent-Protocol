"""Original bounded routing probes; only temporary synthetic authority state.

These are trusted provisioning experiments, not untrusted public API attacks.
They reproduce limits in the reviewed single-adapter implementation. No target
or acquired code is executed. Run from the HMS root with PYTHONPATH=.
"""
import copy
import json
import tempfile

from hms.contracts import canonical
from hms.demo import definitions
from hms.journal import Context, JournalError
from hms.runtime import Runtime


OWNER = Context("routing-review-owner", "simulation:local")


def open_runtime(path, create=False):
    return Runtime(path, create=create, owner=OWNER if create else None,
                   wall_clock_ms=lambda: 1000, monotonic_ms=lambda: 1000)


def prepare(runtime, instance="sim:home-fan"):
    ns = runtime.request(OWNER, "namespace", {"expiresUnixMs": 10000})["token"]
    return runtime.request(OWNER, "prepare", {
        "instanceId": instance, "actionId": "set_level",
        "arguments": {"level": 25, "unit": "percent"},
        "operationKey": "routing-review:1", "replayNamespace": ns,
        "requiredEffect": "capability_completion",
        "timing": {"notBeforeUnixMs": 1000, "latestStartUnixMs": 5000,
                   "maxRunMs": 500, "latestCompletionUnixMs": 5500},
    })["request"]


def remapped_resource_is_accepted_then_unknown():
    with tempfile.TemporaryDirectory() as directory:
        runtime = open_runtime(directory, True)
        try:
            binding, _ = runtime.registry._binding("sim:home-fan")
            binding["generation"] = "routing-review:resource-generation"
            binding["resourceMap"]["fan-control"] = "review:alternate-resource"
            runtime.registry.bind(OWNER, canonical(binding))
            runtime._refresh(force=True)  # Existing adapter itself supplies presence/ready.
            request = prepare(runtime)
            accepted = runtime.request(OWNER, "invoke", {"request": request})
            runtime.tick()
            status = runtime.operation(OWNER, accepted["operationId"])
            sample = runtime.plant.observe("sim:home-fan")
            assert accepted["executionState"] == "accepted"
            assert status["executionState"] == "outcome_unknown"
            assert status["mayHaveActed"] is True
            assert status["resourceClaims"] == [{"resource": "review:alternate-resource", "fence": 1}]
            assert runtime.plant.receipt(accepted["operationId"]) is None
            assert sample["effectCount"] == 0
            return {"case": "remapped_resource", "accepted": accepted["executionState"],
                    "afterTick": status["executionState"], "mayHaveActed": status["mayHaveActed"],
                    "heldClaims": status["resourceClaims"], "syntheticEffects": sample["effectCount"]}
        finally:
            runtime.close()


def install_extra(runtime, adapter):
    document = copy.deepcopy(definitions()[0][2])
    document["execution"]["actions"]["set_level"]["preconditions"] = []
    digest = runtime.registry.publish_type(OWNER, canonical(document))
    instance = "sim:review-extra-fan"
    runtime.registry.enroll(OWNER, instance, digest, identity_kind="simulation", identity_ref=instance)
    runtime.registry.bind(OWNER, canonical({
        "profile": "hms.binding/0.1", "instanceId": instance, "generation": "routing-review:extra",
        "typeDigest": digest, "calibrationRevision": "synthetic:review:1", "controlGeneration": "review:control:1",
        "mode": "simulation", "adapterId": adapter,
        "resourceMap": {"fan-control": "review:extra-resource"},
        "argumentSchemas": {"set_level": document["execution"]["actions"]["set_level"]["inputSchema"]},
    }))
    return instance


def absent_adapter_admitted_with_trusted_presence():
    with tempfile.TemporaryDirectory() as directory:
        runtime = open_runtime(directory, True)
        try:
            instance = install_extra(runtime, "review:adapter-not-installed")
            # In-process trusted ingress; no such provisioning/presence RPC exists.
            runtime.registry.report_presence(instance, adapter_id="review:adapter-not-installed",
                                             endpoint_session="review:session:1", ttl_ms=3000)
            request = prepare(runtime, instance)
            accepted = runtime.request(OWNER, "invoke", {"request": request})
            runtime.tick()
            status = runtime.operation(OWNER, accepted["operationId"])
            assert accepted["executionState"] == "accepted"
            assert status["executionState"] == "outcome_unknown"
            assert status["mayHaveActed"] and status["resourceClaims"]
            assert runtime.plant.receipt(accepted["operationId"]) is None
            return {"case": "absent_adapter_with_trusted_presence", "accepted": accepted["executionState"],
                    "afterTick": status["executionState"], "heldClaimCount": len(status["resourceClaims"]),
                    "scope": "trusted provisioning only; not a public caller authority bypass"}
        finally:
            runtime.close()


def extra_instance_prevents_local_reopen():
    with tempfile.TemporaryDirectory() as directory:
        runtime = open_runtime(directory, True)
        try:
            instance = install_extra(runtime, "simulator:local")
            try:
                runtime._refresh(force=True)
            except JournalError as error:
                refresh_error = error.code
            else:
                raise AssertionError("extra instance unexpectedly supported")
        finally:
            runtime.close()
        try:
            reopened = open_runtime(directory)
        except JournalError as error:
            startup_error = error.code
        else:
            reopened.close()
            raise AssertionError("unsupported installation unexpectedly reopened")
        assert refresh_error == startup_error == "SIMULATOR_INSTANCE_UNSUPPORTED"
        return {"case": "extra_instance_local_reopen", "instance": instance,
                "refreshError": refresh_error, "startupError": startup_error}


if __name__ == "__main__":
    for case in (remapped_resource_is_accepted_then_unknown,
                 absent_adapter_admitted_with_trusted_presence,
                 extra_instance_prevents_local_reopen):
        print(json.dumps(case(), sort_keys=True))
