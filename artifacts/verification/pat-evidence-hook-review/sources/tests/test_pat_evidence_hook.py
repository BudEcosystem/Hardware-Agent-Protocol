"""Catalog evidence-provider boundaries with synthetic, retained test capsules.

These checks validate integrity gating and SQL isolation, not a qualification
policy. The actual simulation worker and its evidence store are separate work.
"""
import copy
from dataclasses import replace
import hashlib
import json
import sqlite3
import tempfile
import unittest

from hms.contracts import ContractError, canonical
from hms.journal import JournalError
from hms.pat_catalog import Evaluator, PatCatalog
from hms.pat_compiler import compiler_digest
from hms.pat_contracts import pat_digest
from test_pat_catalog import CHECKS, digest
from test_pat_execution import Fixture, OWNER


class EvidenceHookTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.f = Fixture(self.directory.name)
        self.addCleanup(lambda: self.f.close())
        self.calls = 0
        self.behavior = lambda receipt: True
        with self.f.runtime.journal._transaction():
            self.db.execute('CREATE TABLE test_pat_evidence(deployment TEXT, digest TEXT, document BLOB, '
                            'PRIMARY KEY(deployment,digest))')
        self.install_catalog()
        self.key = self.f.activate()
        self.calls = 0

    @property
    def db(self):
        return self.f.runtime.journal._db

    def install_catalog(self):
        self.f.spec = Evaluator('execution-fixture', digest('evidence-hook-fixture'), digest('evidence-hook-policy'),
            CHECKS, self.evaluate, evidence_profile='test:retained-capsules/0.1', verify_evidence=self.verify)
        self.f.catalog = PatCatalog(self.f.runtime.journal, compiler_digest=compiler_digest,
            environment=lambda context, artifact: copy.deepcopy(self.f.environments[pat_digest(artifact)]),
            evaluators=(self.f.spec,))
        self.f.store.catalog = self.f.catalog

    def evaluate(self, artifact, environment):
        checks = []
        with self.f.runtime.journal._transaction():
            for name, category in CHECKS:
                document = canonical({'profile': 'test:pat-evidence/0.1', 'artifactDigest': pat_digest(artifact),
                    'environment': environment, 'id': name, 'category': category, 'outcome': 'passed'})
                key = 'sha256:' + hashlib.sha256(document).hexdigest()
                self.db.execute('INSERT OR IGNORE INTO test_pat_evidence VALUES (?,?,?)',
                                (environment['deployment'], key, document))
                checks.append({'id': name, 'category': category, 'outcome': 'passed', 'evidenceDigest': key})
        return {'checks': checks, 'unresolvedEffects': 0, 'limitations': ['Synthetic integrity-hook fixture only']}

    def verify(self, context, receipt):
        self.calls += 1
        self.assertTrue(self.db.in_transaction)
        for check in receipt['result']['checks']:
            row = self.db.execute('SELECT document FROM test_pat_evidence WHERE deployment=? AND digest=?',
                                 (context.deployment, check['evidenceDigest'])).fetchone()
            if row is None or 'sha256:' + hashlib.sha256(row[0]).hexdigest() != check['evidenceDigest']:
                return False
            document = json.loads(row[0])
            if (document['artifactDigest'] != receipt['artifactDigest'] or
                    document['environment'] != receipt['environment'] or
                    any(document[name] != check[name] for name in ('id', 'category', 'outcome'))):
                return False
        return self.behavior(receipt)

    def code(self, expected, call, *args, **kwargs):
        with self.assertRaises(JournalError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected)

    def test_optional_pair_and_legacy_identity_are_exact(self):
        legacy = Evaluator('legacy', digest('implementation'), digest('policy'), CHECKS, lambda *_: {})
        self.assertEqual(legacy.identity(), {'evaluatorId': 'legacy', 'implementationDigest': digest('implementation'),
            'policyDigest': digest('policy'), 'requiredChecks': [{'id': key, 'category': category} for key, category in CHECKS]})
        self.assertEqual(self.f.spec.identity()['evidenceProfile'], 'test:retained-capsules/0.1')
        for fields in ({'evidence_profile': 'profile'}, {'verify_evidence': lambda *_: True},
                       {'evidence_profile': 'profile', 'verify_evidence': 1},
                       {'evidence_profile': False, 'verify_evidence': lambda *_: True}):
            with self.subTest(fields=fields), self.assertRaises(ContractError):
                replace(legacy, **fields)

    def test_verified_evidence_allows_run_but_exact_replay_does_not_requalify(self):
        request = self.f.request()
        admitted = self.f.store.run(OWNER, request)
        self.assertGreaterEqual(self.calls, 2)
        self.behavior = lambda receipt: False
        calls = self.calls
        replay = self.f.store.run(OWNER, request)
        self.assertEqual(replay['instanceId'], admitted['instanceId'])
        self.assertEqual(self.calls, calls)
        self.code('PAT_EVIDENCE_INVALID', self.f.store.run, OWNER, self.f.request('new-run'))

    def test_missing_and_corrupt_capsules_block_promotion_without_revision_change(self):
        catalog = self.f.catalog
        catalog.transition(OWNER, self.key, expected_revision=catalog._revision(OWNER.deployment), target='suspended')
        row = tuple(self.db.execute('SELECT deployment,digest,document FROM test_pat_evidence LIMIT 1').fetchone())
        for mutation in ('missing', 'corrupt'):
            with self.subTest(mutation=mutation):
                with self.f.runtime.journal._transaction():
                    if mutation == 'missing':
                        self.db.execute('DELETE FROM test_pat_evidence WHERE digest=?', (row[1],))
                    else:
                        self.db.execute('INSERT OR REPLACE INTO test_pat_evidence VALUES (?,?,?)', (row[0], row[1], b'{}'))
                before, revision = self.f.counts(), catalog._revision(OWNER.deployment)
                self.code('PAT_EVIDENCE_INVALID', catalog.transition, OWNER, self.key,
                          expected_revision=revision, target='active')
                self.assertEqual(catalog._revision(OWNER.deployment), revision)
                self.assertEqual(self.f.counts(), before)

    def test_invalid_candidate_beside_valid_candidate_cannot_manufacture_uniqueness(self):
        other = copy.deepcopy(self.f.program); other['name'] += '-alternative'
        self.f.activate(other)
        first = self.f.catalog._entry(OWNER.deployment, self.key)['evaluation']
        receipt = self.f.catalog.evaluation(OWNER, first)
        with self.f.runtime.journal._transaction():
            self.db.execute('DELETE FROM test_pat_evidence WHERE digest=?', (receipt['result']['checks'][0]['evidenceDigest'],))
        before = self.f.counts()
        self.code('PAT_EVIDENCE_INVALID', self.f.store.run, OWNER, self.f.request())
        self.assertEqual(self.f.counts(), before)

    def test_provider_errors_are_not_filtered_and_only_exact_true_is_valid(self):
        before = self.f.counts()
        for value in (None, 1, 'true', {}):
            self.behavior = lambda receipt, value=value: value
            self.code('PAT_EVIDENCE_INVALID_RESPONSE', self.f.store.run, OWNER, self.f.request())
        def error(receipt):
            raise JournalError('PAT_DEPENDENCIES_CHANGED')
        self.behavior = error
        self.code('PAT_EVIDENCE_UNAVAILABLE', self.f.store.run, OWNER, self.f.request())
        self.assertEqual(self.f.counts(), before)

    def test_sql_guard_denies_cached_writes_schema_transactions_and_functions(self):
        # Warm this exact UPDATE in sqlite3's statement cache before the guard.
        update = 'UPDATE test_pat_evidence SET document=document'
        with self.f.runtime.journal._transaction():
            self.db.execute(update)
        statements = [update, 'DELETE FROM test_pat_evidence',
            'CREATE TABLE escaped(value TEXT)', 'DROP TABLE test_pat_evidence',
            'PRAGMA user_version=97', 'COMMIT', 'ROLLBACK', 'SAVEPOINT escaped',
            "ATTACH DATABASE ':memory:' AS escaped", 'SELECT abs(1)']
        for sql in statements:
            seen = []
            def attempt(receipt):
                try:
                    self.db.execute(sql).fetchall()
                except sqlite3.DatabaseError as error:
                    seen.append(error.sqlite_errorcode)
                return True  # Swallowing a denial must not hide the violation.
            self.behavior = attempt
            before, revision = self.f.counts(), self.f.catalog._revision(OWNER.deployment)
            with self.subTest(sql=sql):
                self.code('PAT_EVIDENCE_PROVIDER_IMPURE', self.f.catalog.describe, OWNER, self.key)
                # This SQLite build maps a denied function to SQLITE_ERROR,
                # while the other denied authorizer actions use SQLITE_AUTH.
                expected = sqlite3.SQLITE_ERROR if sql == 'SELECT abs(1)' else sqlite3.SQLITE_AUTH
                self.assertEqual(seen, [expected])
                self.assertEqual(self.f.counts(), before)
                self.assertEqual(self.f.catalog._revision(OWNER.deployment), revision)
                self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0], 0)
                self.assertIsNone(self.db.execute("SELECT name FROM sqlite_master WHERE name='escaped'").fetchone())
                self.assertEqual([row[1] for row in self.db.execute('PRAGMA database_list')], ['main'])
                # The connection's ordinary transaction/write behavior returns.
                with self.f.runtime.journal._transaction():
                    self.db.execute(update)

    def test_purity_failure_escapes_even_when_callback_raises(self):
        def attempt(receipt):
            try:
                self.db.execute('DELETE FROM test_pat_evidence')
            finally:
                raise JournalError('PAT_DEPENDENCIES_CHANGED')
        self.behavior = attempt
        before = self.f.counts()
        self.code('PAT_EVIDENCE_PROVIDER_IMPURE', self.f.store.run, OWNER, self.f.request())
        self.assertEqual(self.f.counts(), before)
        self.behavior = lambda receipt: True
        self.assertTrue(self.f.catalog.describe(OWNER, self.key)['eligibleForNewInstances'])

    def test_second_catalog_reentry_cannot_replace_or_clear_outer_guard(self):
        other = PatCatalog(self.f.runtime.journal, compiler_digest=compiler_digest,
            environment=lambda context, artifact: copy.deepcopy(self.f.environments[pat_digest(artifact)]),
            evaluators=(self.f.spec,))
        for also_write in (False, True):
            seen = []
            def reenter(receipt):
                try:
                    other._verify_evidence(self.f.spec, OWNER, receipt)
                except JournalError as error:
                    seen.append(error.code)
                if also_write:
                    try:
                        self.db.execute('DELETE FROM test_pat_evidence')
                    except sqlite3.DatabaseError as error:
                        seen.append(error.sqlite_errorcode)
                return True
            self.behavior = reenter
            before = self.f.counts()
            with self.subTest(also_write=also_write):
                self.code('PAT_EVIDENCE_PROVIDER_IMPURE', self.f.store.run, OWNER, self.f.request())
                self.assertEqual(seen, ['PAT_EVIDENCE_REENTRANT'] + ([sqlite3.SQLITE_AUTH] if also_write else []))
                self.assertEqual(self.f.counts(), before)
                self.assertIsNone(self.f.runtime.journal._pat_evidence_guard)
                with self.f.runtime.journal._transaction():
                    self.db.execute('UPDATE test_pat_evidence SET document=document')
        self.behavior = lambda receipt: True
        self.assertTrue(self.f.catalog.describe(OWNER, self.key)['eligibleForNewInstances'])

    def test_detached_receipt_and_final_verification_failure(self):
        def mutate_copy(receipt):
            receipt['environment']['roles'].clear()
            return True
        self.behavior = mutate_copy
        evaluated = self.f.catalog._entry(OWNER.deployment, self.key)['evaluation']
        before_receipt = self.f.catalog.evaluation(OWNER, evaluated)
        self.f.catalog.describe(OWNER, self.key)
        self.assertEqual(self.f.catalog.evaluation(OWNER, evaluated), before_receipt)
        self.calls = 0
        self.behavior = lambda receipt: self.calls == 1
        before = self.f.counts()
        self.code('PAT_SELECTION_CHANGED', self.f.store.run, OWNER, self.f.request())
        self.assertEqual(self.calls, 2)
        self.assertEqual(self.f.counts(), before)

    def test_reopen_retains_evidence_and_historical_run_without_requalification(self):
        request = self.f.request()
        admitted = self.f.store.run(OWNER, request)
        saved = (copy.deepcopy(self.f.bindings), copy.deepcopy(self.f.environments), self.f.namespace)
        self.f.close()
        self.f = Fixture(self.directory.name, create=False)
        self.f.bindings, self.f.environments, self.f.namespace = saved
        self.install_catalog()
        self.assertTrue(self.f.catalog.describe(OWNER, self.key)['eligibleForNewInstances'])
        with self.f.runtime.journal._transaction():
            self.db.execute('DELETE FROM test_pat_evidence')
        calls = self.calls
        self.assertEqual(self.f.store.run(OWNER, request)['instanceId'], admitted['instanceId'])
        self.assertEqual(self.calls, calls)
        self.code('PAT_EVIDENCE_INVALID', self.f.store.run, OWNER, self.f.request('after-reopen'))


if __name__ == '__main__':
    unittest.main()
