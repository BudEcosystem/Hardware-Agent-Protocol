"""Catalog authority/atomicity tests with explicitly synthetic evaluator services.

The fixture reports test-vector results; it is not a production PAT evaluator or
evidence that the illustrated artifact's complete domain has been qualified.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest

from hms.contracts import ContractError, SAFE_INTEGER, canonical
from hms.journal import Context, JournalError
from hms.pat_catalog import Evaluator, PatCatalog
from hms.runtime import Runtime


ROOT = Path(__file__).resolve().parents[1]
OWNER = Context("pat-owner", "simulation:local")
OTHER = Context("pat-reader", OWNER.deployment)
CHECKS = (("nominal", "positive"), ("edge", "boundary"), ("reject", "negative"), ("interrupt", "fault"))


def digest(text):
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def artifact():
    return json.loads((ROOT / "tests/fixtures/pat-catalog.json").read_text())


def environment(context, program):
    return {"profile": "hms.pat.environment/0.1", "deployment": context.deployment,
            "evidenceMode": "simulation", "compilerDigest": digest("fixture-compiler"),
            "roles": {name: {"typeDigest": digest("fixture-type"), "bindingDigest": digest("fixture-binding"),
                "installationDigest": digest("fixture-installation"), "argumentMetadataDigest": digest("fixture-metadata"),
                "driverProfile": "sqlite-simulation", "driverDigest": digest("fixture-driver")}
                for name in program["roles"]}}


def result():
    return {"checks": [{"id": name, "category": category, "outcome": "passed", "evidenceDigest": digest(name)}
                       for name, category in CHECKS], "unresolvedEffects": 0,
            "limitations": ["Synthetic catalog test fixture; not a production qualification evaluator"]}


class CatalogFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1000
        self.runtime = Runtime(self.temp.name, create=True, owner=OWNER,
                               wall_clock_ms=lambda: self.now, monotonic_ms=lambda: self.now)
        self.addCleanup(lambda: self.runtime.close())
        self.response = result()
        self.env = environment(OWNER, artifact())
        self.enabled = True
        self.calls = 0
        self.spec = Evaluator("fixture-evaluator", digest("fixture-evaluator"), digest("fixture-policy"), CHECKS,
                              self.evaluate, lambda: self.enabled)
        self.store = self.new_store()

    def new_store(self):
        return PatCatalog(self.runtime.journal, compiler_digest=lambda: digest("fixture-compiler"),
                          environment=lambda context, program: self.env, evaluators=(self.spec,))

    def evaluate(self, program, env):
        self.calls += 1
        return copy.deepcopy(self.response)

    def publish(self):
        return self.store.publish(OWNER, artifact())["artifactDigest"]

    def qualify(self, name="evaluation:1"):
        program = self.publish()
        receipt = self.store.evaluate(OWNER, program, "fixture-evaluator", name)
        return program, receipt

    def activate(self):
        program, receipt = self.qualify()
        entry = self.store.describe(OWNER, program)
        return program, receipt, self.store.transition(OWNER, program, expected_revision=entry["catalogRevision"], target="active")

    def code(self, expected, method, *args, **kwargs):
        with self.assertRaises(JournalError) as caught:
            method(*args, **kwargs)
        self.assertEqual(expected, caught.exception.code)


class PatCatalogTests(CatalogFixture):
    def test_compiler_environment_matches_catalog_receipt_identity(self):
        from hms.pat_compiler import compiler_digest
        from test_pat_compiler import compile_fixture
        program = artifact()
        compiled = compile_fixture(program, context={"taskKind": program["taskKind"],
            "inputProfile": program["inputProfile"], "evidenceMode": "simulation", "deployment": OWNER.deployment})
        catalog = PatCatalog(self.runtime.journal, compiler_digest=compiler_digest,
            environment=lambda context, value: compiled["evaluationEnvironment"], evaluators=(self.spec,))
        published = catalog.publish(OWNER, program)
        evaluated = catalog.evaluate(OWNER, published["artifactDigest"], "fixture-evaluator", "compiler-integration")
        self.assertEqual(compiled["patDigest"], published["artifactDigest"])
        self.assertEqual(compiled["environmentDigest"], evaluated["receipt"]["environmentDigest"])
        active = catalog.transition(OWNER, published["artifactDigest"], expected_revision=2, target="active")
        self.assertTrue(active["eligibleForNewInstances"])
        # A later endpoint session changes run identity, not the static tested
        # environment; a changed metadata/driver digest would require evaluation.
        self.assertNotIn("endpointSession", evaluated["receipt"]["environment"]["roles"]["fan"])

    def test_immutable_candidate_replay_and_detached_reads(self):
        document = artifact()
        first = self.store.publish(OWNER, document)
        self.assertEqual(first, self.store.publish(OWNER, document))
        document["name"] = "different"
        fetched = self.store.artifact(OWNER, first["artifactDigest"])
        self.assertNotEqual(fetched["name"], document["name"])
        fetched["steps"].clear()
        self.assertEqual(2, len(self.store.artifact(OWNER, first["artifactDigest"])["steps"]))
        self.assertEqual(1, self.store.snapshot(OWNER)["catalogRevision"])

    def test_receipt_promotion_and_scoped_evidence(self):
        program, evaluation, active = self.activate()
        self.assertTrue(active["eligibleForNewInstances"])
        self.assertEqual(3, active["catalogRevision"])
        receipt = self.store.evaluation(OWNER, evaluation["evaluationDigest"])
        self.assertEqual("passed", receipt["outcome"])
        self.assertFalse(receipt["physicalObjectiveVerified"])
        self.assertEqual(self.env, receipt["environment"])
        self.assertEqual(program, receipt["artifactDigest"])
        self.assertEqual([1, 2, 3], [e["sequence"] for e in self.store.events(OWNER)["events"]])

    def test_current_authority_even_for_replay_and_reads(self):
        program, evaluation = self.qualify()
        self.runtime.registry.grant(OWNER, OTHER.principal, "sim:home-fan", "read")
        self.runtime.registry.grant(OWNER, OTHER.principal, "sim:home-fan", "invoke:set_level")
        for method, args in ((self.store.publish, (artifact(),)), (self.store.artifact, (program,)),
                (self.store.describe, (program,)), (self.store.evaluate, (program, "fixture-evaluator", "evaluation:1")),
                (self.store.evaluation, (evaluation["evaluationDigest"],)), (self.store.snapshot, ()), (self.store.events, ())):
            self.code("ACCESS_DENIED", method, OTHER, *args)
        self.code("ACCESS_DENIED", self.store.transition, OTHER, program, expected_revision=2, target="active")

    def test_candidate_cannot_supply_own_receipt(self):
        program = self.publish()
        self.code("PAT_EVALUATOR_UNTRUSTED", self.store.evaluate, OWNER, program, "passed-true", "run")
        self.code("PAT_NOT_EVALUATED", self.store.transition, OWNER, program, expected_revision=1, target="active")
        with self.assertRaises(TypeError):
            self.store.evaluate(OWNER, program, "fixture-evaluator", "run", receipt={"passed": True})
        self.assertEqual(0, self.calls)

    def test_replay_does_not_repeat_evaluation_or_replace_latest(self):
        program, first = self.qualify()
        self.response["checks"][0]["outcome"] = "failed"
        failed = self.store.evaluate(OWNER, program, "fixture-evaluator", "evaluation:2")
        self.assertEqual(first, self.store.evaluate(OWNER, program, "fixture-evaluator", "evaluation:1"))
        self.assertEqual(2, self.calls)
        entry = self.store.describe(OWNER, program)
        self.assertEqual(failed["evaluationDigest"], entry["evaluationDigest"])
        self.assertEqual(3, entry["catalogRevision"])
        changed = artifact(); changed["version"] = "2"
        other = self.store.publish(OWNER, changed)["artifactDigest"]
        self.code("PAT_EVALUATION_KEY_CONFLICT", self.store.evaluate, OWNER, other, "fixture-evaluator", "evaluation:1")

    def test_incomplete_extra_failed_unresolved_and_malformed_are_not_passes(self):
        program = self.publish()
        variants = []
        missing = result(); missing["checks"].pop(); variants.append(missing)
        extra = result(); extra["checks"].append({"id": "extra", "category": "positive", "outcome": "failed", "evidenceDigest": digest("extra")}); variants.append(extra)
        unresolved = result(); unresolved["unresolvedEffects"] = 1; variants.append(unresolved)
        floating = result(); floating["unresolvedEffects"] = 0.0; variants.append(floating)
        unknown = result(); unknown["passed"] = True; variants.append(unknown)
        duplicate = result(); duplicate["checks"].append(duplicate["checks"][0]); variants.append(duplicate)
        for n, variant in enumerate(variants):
            with self.subTest(n=n):
                self.response = variant
                receipt = self.store.evaluate(OWNER, program, "fixture-evaluator", "negative:" + str(n))["receipt"]
                self.assertNotEqual("passed", receipt["outcome"])
                self.assertFalse(self.store.describe(OWNER, program)["eligibleForPromotion"])
        self.assertEqual(7, self.store.snapshot(OWNER)["catalogRevision"])

    def test_new_evidence_suspends_active_and_old_cas_cannot_promote(self):
        program, _, active = self.activate()
        self.response["checks"][0]["outcome"] = "failed"
        self.store.evaluate(OWNER, program, "fixture-evaluator", "new-failure")
        entry = self.store.describe(OWNER, program)
        self.assertEqual("suspended", entry["state"])
        self.assertFalse(entry["eligibleForNewInstances"])
        self.code("PAT_CATALOG_REVISION_CONFLICT", self.store.transition, OWNER, program,
                  expected_revision=active["catalogRevision"], target="active")
        self.code("PAT_EVALUATION_NOT_PASSED", self.store.transition, OWNER, program,
                  expected_revision=entry["catalogRevision"], target="active")

    def test_dependency_and_compiler_drift_block_new_use(self):
        program, _, _ = self.activate()
        self.env["roles"]["fan"]["driverDigest"] = digest("driver-changed")
        entry = self.store.describe(OWNER, program)
        self.assertEqual("PAT_DEPENDENCIES_CHANGED", entry["eligibilityReason"])
        self.assertFalse(entry["eligibleForNewInstances"])
        self.env = environment(OWNER, artifact())
        self.store._compiler_digest = lambda: digest("compiler-changed")
        self.assertFalse(self.store.describe(OWNER, program)["eligibleForNewInstances"])

    def test_evaluator_revocation_and_identity_change(self):
        program, _, _ = self.activate()
        self.enabled = False
        self.assertEqual("PAT_EVALUATOR_UNTRUSTED", self.store.describe(OWNER, program)["eligibilityReason"])
        self.code("PAT_EVALUATOR_UNTRUSTED", self.store.evaluate, OWNER, program, "fixture-evaluator", "evaluation:1")
        self.enabled = True
        changed = Evaluator("fixture-evaluator", digest("new-implementation"), self.spec.policy_digest, CHECKS, self.evaluate)
        store = PatCatalog(self.runtime.journal, compiler_digest=lambda: digest("fixture-compiler"),
                           environment=lambda c, p: self.env, evaluators=(changed,))
        self.assertEqual("PAT_EVALUATOR_CHANGED", store.describe(OWNER, program)["eligibilityReason"])

    def test_retirement_survives_re_evaluation_and_reopen(self):
        program, _, active = self.activate()
        retired = self.store.transition(OWNER, program, expected_revision=active["catalogRevision"], target="retired")
        self.store.evaluate(OWNER, program, "fixture-evaluator", "new-pass")
        current = self.new_store().describe(OWNER, program)
        self.assertEqual("retired", current["state"])
        self.assertFalse(current["eligibleForNewInstances"])
        self.code("PAT_TRANSITION_NOT_ALLOWED", self.store.transition, OWNER, program,
                  expected_revision=current["catalogRevision"], target="active")
        decision = json.loads(self.runtime.journal._db.execute("SELECT document FROM pc_decisions WHERE digest=?", (retired["decisionDigest"],)).fetchone()[0])
        self.assertEqual("retain_pinned_version", decision["admittedInstancePolicy"])

    def test_racing_promotions_have_one_cas_winner(self):
        program, _ = self.qualify()
        barrier = threading.Barrier(8)
        def promote(_):
            barrier.wait()
            try:
                return self.store.transition(OWNER, program, expected_revision=2, target="active")["state"]
            except JournalError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(promote, range(8)))
        self.assertEqual(1, outcomes.count("active"))
        self.assertEqual(7, outcomes.count("PAT_CATALOG_REVISION_CONFLICT"))
        self.assertEqual(3, self.store.snapshot(OWNER)["catalogRevision"])

    def test_exception_after_write_rolls_back_catalog_business_state(self):
        program, _ = self.qualify()
        before = self.store.snapshot(OWNER)
        original = self.store._event
        def fail(*args):
            original(*args)
            raise RuntimeError("injected failure after transition and event")
        self.store._event = fail
        with self.assertRaises(RuntimeError):
            self.store.transition(OWNER, program, expected_revision=2, target="active")
        self.store._event = original
        self.assertEqual(before, self.store.snapshot(OWNER))
        self.assertEqual(0, self.runtime.journal._db.execute("SELECT count(*) FROM pc_decisions").fetchone()[0])

    def test_clock_failure_allows_suspend_but_not_promotion(self):
        program, _, active = self.activate()
        self.now = 999
        suspended = self.store.transition(OWNER, program, expected_revision=active["catalogRevision"], target="suspended")
        self.assertEqual("regressed_clamped", self.store.events(OWNER)["events"][-1]["clock_status"])
        self.code("CLOCK_REGRESSION", self.store.transition, OWNER, program,
                  expected_revision=suspended["catalogRevision"], target="active")

    def test_exact_integer_cas_and_event_bounds(self):
        program, _ = self.qualify()
        for value in (True, 2.0, -1, SAFE_INTEGER + 1):
            with self.assertRaises(ContractError):
                self.store.transition(OWNER, program, expected_revision=value, target="active")
        for limit in (0, 101, True, 2.0):
            with self.assertRaises(ContractError):
                self.store.events(OWNER, limit=limit)
        page = self.store.events(OWNER, limit=1)
        self.assertEqual(1, page["nextSequence"])
        self.assertEqual(2, self.store.events(OWNER, after=page["nextSequence"])["events"][0]["sequence"])

    def test_partial_or_wrong_version_schema_is_not_repaired(self):
        self.runtime.journal._db.execute("UPDATE pc_meta SET value='future' WHERE key='version'")
        self.code("UNSUPPORTED_PAT_CATALOG", self.new_store)
        self.runtime.journal._db.execute("DROP TABLE pc_events")
        self.code("INCOMPLETE_PAT_CATALOG", self.new_store)
        self.assertIsNone(self.runtime.journal._db.execute("SELECT name FROM sqlite_master WHERE name='pc_events'").fetchone())


if __name__ == "__main__":
    unittest.main()
