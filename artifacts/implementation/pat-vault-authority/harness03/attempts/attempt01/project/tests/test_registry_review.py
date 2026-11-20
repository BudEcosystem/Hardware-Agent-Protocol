"""Adversarial regressions from the independent registry review.

Every device and evidence source is synthetic. No external source, network
service, acquired implementation, or hardware is exercised.
"""
import copy
from pathlib import Path
import tempfile
import threading
import unittest

from hms.contracts import ContractError, SAFE_INTEGER, canonical
from hms.demo import definitions, install
from hms.journal import Context, Evidence, Journal, JournalError
from hms.registry import Registry, RegistryPolicy


class RegistryReview(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "authority.sqlite"
        self.wall = 1000
        self.monotonic = 1000
        self.owner = Context("review-owner", "review-deployment")
        self.instance = "sim:home-fan"
        self.adapter = "simulator:local"
        self.session = "session:A"
        self.binding_generation = "sim-binding:1"
        self._open(create=True)
        install(self.registry, self.owner)
        self.presence(self.session)
        self.ready(self.session, "stream:1")

    def _open(self, *, create=False):
        self.policy = RegistryPolicy()
        self.journal = Journal(self.path, self.policy, clock_ms=lambda: self.wall, create=create)
        self.addCleanup(self.journal.close)
        self.registry = Registry(self.journal, monotonic_ms=lambda: self.monotonic,
                                 bootstrap_owner=self.owner if create else None)
        self.policy.attach(self.registry)

    def presence(self, session):
        self.registry.report_presence(self.instance, adapter_id=self.adapter,
                                      endpoint_session=session, ttl_ms=60000)

    def ready(self, session, epoch, *, sequence=1, latency=0, uncertainty=0):
        self.registry.start_stream(self.instance, "ready", adapter_id=self.adapter,
                                   endpoint_session=session,
                                   binding_generation=self.binding_generation, stream_epoch=epoch)
        self.registry.report_observation(
            self.instance, "ready", adapter_id=self.adapter, endpoint_session=session,
            binding_generation=self.binding_generation, value=True,
            evidence_kind="simulation", quality="valid", stream_epoch=epoch,
            sequence=sequence,
            acquisition={"clockDomain": "simulation", "clockEpoch": epoch, "ticksMs": 1000},
            acquisition_latency_bound_ms=latency, clock_uncertainty_ms=uncertainty,
            measurement_uncertainty=None,
        )

    def submit(self, key="review-operation"):
        namespace = self.journal.issue_namespace(self.owner, expires_ms=10000)["token"]
        description = self.registry.describe(self.owner, self.instance)
        wire = canonical({
            "protocol": "hms.invoke/0.1", "replayNamespace": namespace, "operationKey": key,
            "intent": {
                "instanceId": self.instance, "actionId": "set_level",
                "endpointSession": self.session, "controlGeneration": "sim-control:1",
                "descriptionDigest": description["descriptionDigest"],
                "bindingGeneration": self.binding_generation, "calibrationRevision": "synthetic:1",
                "arguments": {"level": 25, "unit": "percent"},
                "timing": {"notBeforeUnixMs": 1000, "latestStartUnixMs": 5000,
                           "maxRunMs": 500, "latestCompletionUnixMs": 5500},
                "requiredEffect": "capability_completion",
            },
        })
        return self.journal.submit(self.owner, wire)

    def rebind(self, **changes):
        binding = self.registry.describe(self.owner, self.instance)["binding"]
        binding.update(generation="sim-binding:2", **changes)
        self.registry.bind(self.owner, canonical(binding))
        self.binding_generation = binding["generation"]
        return binding

    def evidence(self, *assertions, source=None):
        return Evidence("simulation", source or self.adapter, "review-trace:1", assertions)

    def test_reused_endpoint_session_cannot_revive_pre_reset_queued_work(self):
        operation = self.submit()
        self.presence("session:B")
        with self.assertRaisesRegex(JournalError, "ENDPOINT_SESSION_CHANGED"):
            self.journal.claim_dispatch(operation["id"])
        with self.assertRaisesRegex(JournalError, "ENDPOINT_SESSION_REUSED"):
            self.presence("session:A")
        self.ready("session:B", "stream:2")
        with self.assertRaisesRegex(JournalError, "ENDPOINT_SESSION_CHANGED"):
            self.journal.claim_dispatch(operation["id"])
        self.assertEqual(self.journal.status(self.owner, operation["id"])["state"], "accepted")

    def test_endpoint_session_history_survives_authority_reopen(self):
        self.presence("session:B")
        self.journal.close()
        self._open()
        with self.assertRaisesRegex(JournalError, "ENDPOINT_SESSION_REUSED"):
            self.presence("session:A")

    def test_binding_change_does_not_invent_an_endpoint_reboot(self):
        self.rebind()
        self.presence("session:A")
        self.ready("session:A", "stream:2")
        observation = self.registry.observe(self.owner, self.instance, "ready", max_age_ms=1000)
        self.assertEqual(observation["endpointSession"], "session:A")
        self.assertEqual(observation["bindingGeneration"], "sim-binding:2")

    def test_clock_regression_cannot_refresh_a_stale_observation(self):
        self.monotonic = 2500
        with self.assertRaisesRegex(JournalError, "OBSERVATION_STALE"):
            self.registry.observe(self.owner, self.instance, "ready", max_age_ms=1000)
        self.monotonic = 1100
        with self.assertRaisesRegex(JournalError, "OBSERVATION_STALE"):
            self.registry.observe(self.owner, self.instance, "ready", max_age_ms=1000)
        # Catching the clock up cannot silently repair an invalid mapping.
        self.monotonic = 3000
        observation = self.registry.observe(self.owner, self.instance, "ready")
        self.assertEqual(observation["quality"], "unknown")
        self.assertIsNone(observation["ageUpperBoundMs"])

    def test_age_bound_overflow_stays_serializable_and_cannot_satisfy_freshness(self):
        self.ready(self.session, "stream:large-bound", latency=SAFE_INTEGER, uncertainty=SAFE_INTEGER)
        observation = self.registry.observe(self.owner, self.instance, "ready")
        self.assertEqual(observation["quality"], "unknown")
        self.assertIsNone(observation["ageUpperBoundMs"])
        canonical(observation)
        with self.assertRaisesRegex(JournalError, "OBSERVATION_STALE"):
            self.registry.observe(self.owner, self.instance, "ready", max_age_ms=600000)

    def test_malformed_type_and_schema_structures_have_a_contract_error_boundary(self):
        mutations = {
            "null_features": lambda d: d["execution"].__setitem__("requiredFeatures", None),
            "array_schema_type": lambda d: d["execution"]["actions"]["set_level"]["inputSchema"].__setitem__("type", []),
            "unhashable_required": lambda d: d["execution"]["actions"]["set_level"]["inputSchema"].__setitem__("required", [{}]),
            "string_maximum": lambda d: d["execution"]["properties"]["value"]["schema"].__setitem__("maximum", "bad"),
            "unhashable_completion_kind": lambda d: d["execution"]["actions"]["set_level"].__setitem__("completionEvidence", [{}]),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                document = copy.deepcopy(definitions()[0][2])
                mutate(document)
                with self.assertRaises(ContractError):
                    self.registry.publish_type(self.owner, canonical(document))

    def test_scalar_td_action_is_not_a_publishable_description(self):
        document = copy.deepcopy(definitions()[0][2])
        document["td"]["actions"]["set_level"] = 42
        with self.assertRaises(ContractError):
            self.registry.publish_type(self.owner, canonical(document))

    def test_duplicate_required_feature_is_rejected(self):
        document = copy.deepcopy(definitions()[0][2])
        document["execution"]["requiredFeatures"].append(document["execution"]["requiredFeatures"][0])
        with self.assertRaises(ContractError):
            self.registry.publish_type(self.owner, canonical(document))

    def test_td_property_units_and_frames_cannot_disagree_with_execution(self):
        for field, replacement in (("unit", "kelvin"), ("hms:coordinateFrame", "wrong:frame"),
                                   ("readOnly", False), ("maximum", 1000)):
            with self.subTest(field=field):
                document = copy.deepcopy(definitions()[0][2])
                document["td"]["properties"]["value"][field] = replacement
                with self.assertRaises(ContractError):
                    self.registry.publish_type(self.owner, canonical(document))

    def test_td_action_cannot_advertise_a_different_interface_or_effect(self):
        for field, replacement in (("input", {"type": "string"}), ("safe", True),
                                   ("idempotent", True), ("synchronous", True)):
            with self.subTest(field=field):
                document = copy.deepcopy(definitions()[0][2])
                document["td"]["actions"]["set_level"][field] = replacement
                with self.assertRaises(ContractError):
                    self.registry.publish_type(self.owner, canonical(document))

    def test_td_forms_cannot_advertise_raw_writes_or_wrong_affordance_operations(self):
        cases = (
            ("properties", "value", ["readproperty", "writeproperty"]),
            ("properties", "value", "writeproperty"),
            ("properties", "value", "invokeaction"),
            ("actions", "set_level", ["invokeaction", "writeproperty"]),
            ("actions", "set_level", "readproperty"),
        )
        for category, name, operations in cases:
            with self.subTest(category=category, operations=operations):
                document = copy.deepcopy(definitions()[0][2])
                document["td"][category][name]["forms"][0]["op"] = operations
                with self.assertRaises(ContractError):
                    self.registry.publish_type(self.owner, canonical(document))

    def test_td_forms_require_explicit_nonempty_operations(self):
        for category, name in (("properties", "value"), ("actions", "set_level")):
            for replacement in (None, "", [], [None], ["readproperty", 42]):
                with self.subTest(category=category, replacement=replacement):
                    document = copy.deepcopy(definitions()[0][2])
                    form = document["td"][category][name]["forms"][0]
                    if replacement is None:
                        del form["op"]
                    else:
                        form["op"] = replacement
                    with self.assertRaises(ContractError):
                        self.registry.publish_type(self.owner, canonical(document))

    def test_td_does_not_publish_unsupported_top_level_forms_or_events(self):
        for field, replacement in (
            ("forms", [{"href": "https://example.invalid/raw", "op": "writeallproperties"}]),
            ("forms", [{"href": "https://example.invalid/read", "op": "readallproperties"}]),
            ("events", {}),
        ):
            with self.subTest(field=field, replacement=replacement):
                document = copy.deepcopy(definitions()[0][2])
                document["td"][field] = replacement
                with self.assertRaises(ContractError):
                    self.registry.publish_type(self.owner, canonical(document))

    def test_historical_evidence_policy_survives_rebinding_to_another_adapter(self):
        operation = self.submit()
        ticket = self.journal.claim_dispatch(operation["id"])
        self.journal.record_execution(ticket, "completed", self.evidence("completed"))
        self.journal.release_resources(operation["id"], self.evidence("resources_quiescent"))
        self.rebind(adapterId="simulator:replacement")
        self.journal.dispute(operation["id"], self.evidence("disputed"))
        with self.assertRaisesRegex(JournalError, "UNTRUSTED_EVIDENCE"):
            self.journal.dispute(operation["id"], self.evidence("disputed", source="simulator:replacement"))
        events = self.journal.events(self.owner, operation["id"])["events"]
        self.assertEqual(events[-1]["kind"], "evidence_dispute")
        self.assertEqual(events[-1]["payload"]["evidence"]["source"], self.adapter)
        self.assertEqual(self.journal.status(self.owner, operation["id"])["state"], "completed")

    def test_grant_enabled_rejects_truthy_non_booleans_without_granting(self):
        reader = Context("review-reader", self.owner.deployment)
        for enabled in ("false", "true", 1, 0, None, [], {}):
            with self.subTest(enabled=enabled):
                with self.assertRaises(ContractError):
                    self.registry.grant(self.owner, reader.principal, self.instance, "read", enabled=enabled)
                with self.assertRaisesRegex(JournalError, "ACCESS_DENIED"):
                    self.registry.describe(reader, self.instance)

    def test_policy_cannot_attach_to_another_journals_registry(self):
        other_policy = RegistryPolicy()
        other_journal = Journal(Path(self.directory.name) / "other.sqlite", other_policy,
                                clock_ms=lambda: self.wall, create=True)
        self.addCleanup(other_journal.close)
        with self.assertRaises(JournalError):
            other_policy.attach(self.registry)

    def test_namespace_revocation_cannot_commit_between_authorization_and_issuance(self):
        actor = Context("review-namespace-owner", self.owner.deployment)
        self.registry.grant(self.owner, actor.principal, "*", "namespace")
        authorized = threading.Event()
        proceed = threading.Event()
        attempting_revocation = threading.Event()
        revoked = threading.Event()
        failures = []
        results = []
        original_authorize = self.policy.authorize

        def paused_authorize(context, verb, target):
            original_authorize(context, verb, target)
            if context == actor and verb == "namespace":
                authorized.set()
                if not proceed.wait(3):
                    raise RuntimeError("review synchronization timed out")

        self.policy.authorize = paused_authorize

        def issue():
            try:
                results.append(self.journal.issue_namespace(actor, expires_ms=10000))
            except BaseException as error:
                failures.append(error)

        def revoke():
            attempting_revocation.set()
            try:
                self.registry.grant(self.owner, actor.principal, "*", "namespace", enabled=False)
                revoked.set()
            except BaseException as error:
                failures.append(error)

        issuer = threading.Thread(target=issue)
        revoker = threading.Thread(target=revoke)
        issuer.start()
        try:
            self.assertTrue(authorized.wait(3))
            revoker.start()
            self.assertTrue(attempting_revocation.wait(3))
            # The old authorization-before-transaction implementation lets the
            # revocation commit here, while the authorized issuance is paused.
            revoked_before_issuance_continues = revoked.wait(0.15)
        finally:
            proceed.set()
            issuer.join(3)
            if revoker.ident is not None:
                revoker.join(3)
            self.policy.authorize = original_authorize
        self.assertFalse(issuer.is_alive())
        self.assertFalse(revoker.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(len(results), 1)
        self.assertTrue(revoked.is_set())
        self.assertFalse(revoked_before_issuance_continues)
        with self.assertRaisesRegex(JournalError, "ACCESS_DENIED"):
            self.journal.issue_namespace(actor, expires_ms=10001)


if __name__ == "__main__":
    unittest.main()
