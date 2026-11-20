"""Installed-handler admission regressions; trusted synthetic provisioning only.

The observer/presence setup is in-process trusted ingress, not a public caller
authority bypass. Native compact tests use the original C simulation fixture.
"""
import copy
import tempfile
import unittest
from unittest.mock import patch

from hms.contracts import canonical
from hms.demo import definitions
from hms.endpoint_wire import Opcode
from hms.journal import Context, JournalError
from hms.runtime import Runtime

import test_endpoint_binding as compact_helpers


def authority_snapshot(runtime):
    db = runtime.journal._db
    return {
        table: [tuple(row) for row in db.execute("SELECT * FROM " + table)]
        for table in ("operations", "replay_keys", "claims", "resource_floors")
    }


def trusted_ready(runtime, binding, session, serial=1):
    """Supply otherwise valid trusted ingress so installed support is decisive."""
    reg = runtime.registry
    instance, adapter = binding["instanceId"], binding["adapterId"]
    epoch = "support-probe-stream:" + str(serial)
    reg.report_presence(instance, adapter_id=adapter, endpoint_session=session, ttl_ms=3000)
    reg.start_stream(instance, "ready", adapter_id=adapter, endpoint_session=session,
                     binding_generation=binding["generation"], stream_epoch=epoch)
    reg.report_observation(instance, "ready", adapter_id=adapter, endpoint_session=session,
        binding_generation=binding["generation"], value=True, evidence_kind="simulation",
        quality="valid", stream_epoch=epoch, sequence=1,
        acquisition={"clockDomain": "support-probe-monotonic", "clockEpoch": reg.receipt_epoch,
                     "ticksMs": reg._monotonic()},
        acquisition_latency_bound_ms=0, clock_uncertainty_ms=0,
        measurement_uncertainty={"absolute": 0, "unit": "1", "method": "synthetic_setup"})


def direct_request(runtime, context, namespace, params):
    """Construct a valid current intent without relying on prepare succeeding."""
    description = runtime.request(context, "describe", {"instanceId": params["instanceId"]})
    binding = description["binding"]
    return {
        "protocol": "hms.invoke/0.1", "replayNamespace": namespace,
        "operationKey": params["operationKey"],
        "intent": {
            "instanceId": params["instanceId"], "actionId": params["actionId"],
            "endpointSession": description["presence"]["session"],
            "controlGeneration": binding["controlGeneration"],
            "descriptionDigest": description["descriptionDigest"],
            "bindingGeneration": binding["generation"],
            "calibrationRevision": binding["calibrationRevision"],
            "arguments": copy.deepcopy(params["arguments"]),
            "timing": copy.deepcopy(params["timing"]),
            "requiredEffect": params["requiredEffect"],
        },
    }


class InstalledSupportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.wall = self.mono = 1000
        self.owner = Context("installed-support-owner", "simulation:local")
        self.open(create=True)
        self.namespace = self.call("namespace", expiresUnixMs=10000)["token"]

    def open(self, create=False):
        self.runtime = Runtime(self.directory.name, create=create,
            owner=self.owner if create else None,
            wall_clock_ms=lambda: self.wall, monotonic_ms=lambda: self.mono)
        self.addCleanup(self.runtime.close)

    def call(self, method, **params):
        return self.runtime.request(self.owner, method, params)

    def params(self, *, key="support:one", level=25):
        return dict(instanceId="sim:home-fan", actionId="set_level",
            arguments={"level": level, "unit": "percent"}, operationKey=key,
            replayNamespace=self.namespace, requiredEffect="capability_completion",
            timing={"notBeforeUnixMs": 1000, "latestStartUnixMs": 5000,
                    "maxRunMs": 500, "latestCompletionUnixMs": 5500})

    def prepare(self, **options):
        return self.call("prepare", **self.params(**options))["request"]

    def complete(self, request):
        op = self.call("invoke", request=request)
        self.runtime.tick()
        self.wall += 100
        self.mono += 100
        self.runtime.tick()
        result = self.call("operation", operationId=op["operationId"])
        self.assertEqual(result["executionState"], "completed")
        self.assertEqual(result["resourceClaims"], [])
        return result

    def rebind(self, *, adapter=None, resource=None, maximum=None):
        binding, _ = self.runtime.registry._binding("sim:home-fan")
        binding["generation"] = "support-binding:changed"
        if adapter is not None:
            binding["adapterId"] = adapter
        if resource is not None:
            binding["resourceMap"]["fan-control"] = resource
        if maximum is not None:
            binding["argumentSchemas"]["set_level"]["properties"]["level"]["maximum"] = maximum
        self.runtime.registry.bind(self.owner, canonical(binding))
        return binding

    def assert_new_request_refused_without_reservation(self, binding):
        trusted_ready(self.runtime, binding, self.runtime.plant.session)
        params = self.params()
        request = direct_request(self.runtime, self.owner, self.namespace, params)
        before = authority_snapshot(self.runtime)
        with patch.object(self.runtime.plant, "begin", wraps=self.runtime.plant.begin) as begin:
            with self.assertRaisesRegex(JournalError, "^ADAPTER_INSTALLATION_UNSUPPORTED$"):
                self.call("prepare", **params)
            with self.assertRaisesRegex(JournalError, "^ADAPTER_INSTALLATION_UNSUPPORTED$"):
                self.call("invoke", request=request)
            self.runtime.tick()
            begin.assert_not_called()
        self.assertEqual(authority_snapshot(self.runtime), before)
        self.assertEqual(self.runtime.plant.observe("sim:home-fan")["effectCount"], 0)

    def test_uninstalled_adapter_refused_by_prepare_and_direct_invoke(self):
        self.assert_new_request_refused_without_reservation(
            self.rebind(adapter="support:missing-adapter"))

    def test_remapped_resource_refused_before_claim_or_fence_allocation(self):
        self.assert_new_request_refused_without_reservation(
            self.rebind(resource="support:unimplemented-resource"))

    def test_extra_local_instance_does_not_break_refresh_or_reopen(self):
        reg = self.runtime.registry
        document = definitions()[0][2]
        digest = reg.publish_type(self.owner, canonical(document))
        instance = "sim:support-extra-fan"
        reg.enroll(self.owner, instance, digest, identity_kind="simulation", identity_ref=instance)
        original, _ = reg._binding("sim:home-fan")
        binding = copy.deepcopy(original)
        binding.update(instanceId=instance, generation="support:extra-binding",
                       resourceMap={"fan-control": instance + ":fan-control"})
        reg.bind(self.owner, canonical(binding))
        self.runtime._refresh(force=True)
        self.assertIsNone(self.call("describe", instanceId=instance)["presence"])
        self.runtime.close()
        self.open()
        self.assertIsNone(self.call("describe", instanceId=instance)["presence"])
        self.complete(self.prepare())
        self.assertEqual(self.runtime.plant.observe("sim:home-fan")["effectCount"], 1)

    def test_supported_argument_narrowing_preserves_valid_execution(self):
        self.rebind(maximum=30)
        self.runtime._refresh(force=True)
        before = authority_snapshot(self.runtime)
        with self.assertRaisesRegex(JournalError, "^ARGUMENT_SCHEMA_MISMATCH$"):
            self.prepare(level=40)
        self.assertEqual(authority_snapshot(self.runtime), before)
        result = self.complete(self.prepare(level=25))
        self.assertEqual(result["result"]["output"]["level"], 25)
        self.assertEqual(self.runtime.plant.observe("sim:home-fan")["effectCount"], 1)

    def test_support_lost_after_acceptance_rejects_before_dispatch(self):
        request = self.prepare()
        op = self.call("invoke", request=request)
        with patch.object(self.runtime.plant, "validate_admission",
                          side_effect=JournalError("ADAPTER_INSTALLATION_UNSUPPORTED")) as support:
            replay = self.call("invoke", request=request)
            self.assertEqual(replay["operationId"], op["operationId"])
            self.assertEqual(replay["executionState"], "accepted")
            support.assert_not_called()
            with patch.object(self.runtime.plant, "begin", wraps=self.runtime.plant.begin) as begin:
                self.runtime.tick()
                begin.assert_not_called()
            support.assert_called_once()
        status = self.call("operation", operationId=op["operationId"])
        self.assertEqual(status["executionState"], "rejected_before_dispatch")
        self.assertFalse(status["mayHaveActed"])
        self.assertEqual(status["resourceClaims"], [])
        self.assertIsNone(self.runtime.plant.receipt(op["operationId"]))
        self.assertEqual(self.runtime.plant.observe("sim:home-fan")["effectCount"], 0)

    def test_binding_invalidation_after_acceptance_does_not_handoff(self):
        op = self.call("invoke", request=self.prepare())
        self.runtime.registry.invalidate(self.owner, "sim:home-fan")
        with patch.object(self.runtime.plant, "begin", wraps=self.runtime.plant.begin) as begin:
            self.runtime.tick()
            begin.assert_not_called()
        status = self.call("operation", operationId=op["operationId"])
        self.assertEqual(status["executionState"], "rejected_before_dispatch")
        self.assertFalse(status["mayHaveActed"])
        self.assertEqual(status["resourceClaims"], [])

    def test_completed_replay_and_status_survive_current_adapter_change(self):
        request = self.prepare()
        original = self.complete(request)
        self.rebind(adapter="support:missing-adapter")
        self.runtime.close()
        self.open()
        self.assertIsNone(self.call("describe", instanceId="sim:home-fan")["presence"])
        replay = self.call("invoke", request=request)
        self.assertEqual(replay, original)
        self.assertEqual(self.call("operation", operationId=original["operationId"]), original)
        self.assertEqual(self.runtime.plant.observe("sim:home-fan")["effectCount"], 1)

    def test_historical_receipt_reconciles_after_current_support_is_lost(self):
        request = self.prepare()
        op = self.call("invoke", request=request)
        self.runtime.tick()
        self.runtime.plant.finish(op["operationId"])
        self.runtime.registry.invalidate(self.owner, "sim:home-fan")
        self.runtime.close()
        self.open()
        self.assertEqual(self.call("operation", operationId=op["operationId"])["executionState"],
                         "outcome_unknown")
        with patch.object(self.runtime.plant, "validate_admission",
                          side_effect=JournalError("ADAPTER_INSTALLATION_UNSUPPORTED")) as support:
            self.runtime.tick()
            support.assert_not_called()
            replay = self.call("invoke", request=request)
        self.assertEqual(replay["operationId"], op["operationId"])
        self.assertEqual(replay["executionState"], "completed")
        self.assertEqual(replay["resourceClaims"], [])
        self.assertEqual(self.runtime.plant.observe("sim:home-fan")["effectCount"], 1)


class CompactInstalledSupportTests(unittest.TestCase):
    def test_changed_installed_binding_refuses_without_OP_or_reservation(self):
        fixture = compact_helpers.CompactBindingTests(methodName="runTest")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        runtime = fixture.runtime
        binding, _ = runtime.registry._binding("sim:home-fan")
        binding["generation"] = "support:compact-changed"
        binding["resourceMap"]["fan-control"] = "support:compact-other-resource"
        runtime.registry.bind(fixture.owner, canonical(binding))
        trusted_ready(runtime, binding, "compact-boot:" + runtime.compact._state()["boot"])
        params = dict(instanceId="sim:home-fan", actionId="set_level",
            arguments={"level": 25, "unit": "percent"}, operationKey="support:compact",
            replayNamespace=fixture.namespace, requiredEffect="capability_completion",
            timing={"notBeforeUnixMs": fixture.wall, "latestStartUnixMs": fixture.wall + 2000,
                    "maxRunMs": 1000, "latestCompletionUnixMs": fixture.wall + 5000})
        request = direct_request(runtime, fixture.owner, fixture.namespace, params)
        before = authority_snapshot(runtime)
        packets = fixture.packet_count(Opcode.OP)
        with self.assertRaisesRegex(JournalError, "^ADAPTER_INSTALLATION_UNSUPPORTED$"):
            fixture.call("prepare", **params)
        with self.assertRaisesRegex(JournalError, "^ADAPTER_INSTALLATION_UNSUPPORTED$"):
            fixture.call("invoke", request=request)
        self.assertEqual(authority_snapshot(runtime), before)
        self.assertEqual(fixture.packet_count(Opcode.OP), packets)
        self.assertEqual(runtime.journal._db.execute("SELECT COUNT(*) FROM ep_commands").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
