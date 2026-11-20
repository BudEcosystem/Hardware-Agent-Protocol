"""Retained evaluation integrity before selection filters; synthetic evaluation."""
import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import sqlite3
import tempfile
import threading
import unittest

from hms.contracts import canonical
from hms.journal import JournalError
from hms.pat_catalog import PatCatalog
from hms.pat_compiler import compiler_digest
from hms.pat_contracts import pat_digest
from test_pat_catalog import result
from test_pat_execution import Fixture, OWNER


class EvaluationIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.f = Fixture(self.directory.name)
        self.addCleanup(self.f.close)
        self.key = self.f.activate()
        self.evaluation = self.f.catalog._entry(OWNER.deployment, self.key)['evaluation']
        self.receipt = self.f.catalog.evaluation(OWNER, self.evaluation)
        self.body = canonical(self.receipt)

    @property
    def db(self):
        return self.f.runtime.journal._db

    def write_body(self, body):
        with self.f.runtime.journal._transaction():
            self.db.execute('UPDATE pc_evaluations SET document=? WHERE digest=?', (body, self.evaluation))

    def code(self, expected, call, *args, **kwargs):
        with self.assertRaises(JournalError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected)

    def test_corrupt_receipt_is_not_filtered_into_false_uniqueness(self):
        alternative = copy.deepcopy(self.f.program); alternative['name'] += '-other'
        self.f.activate(alternative)
        changed_outcome = copy.deepcopy(self.receipt); changed_outcome['outcome'] = 'failed'
        changed_environment = copy.deepcopy(self.receipt)
        changed_environment['environment']['roles']['fan']['bindingDigest'] = 'sha256:' + 'f' * 64
        for index, receipt in enumerate((changed_outcome, changed_environment)):
            self.write_body(canonical(receipt))
            before = self.f.counts()
            try:
                with self.subTest(index=index):
                    self.code('PAT_EVALUATION_INVALID', self.f.store.run, OWNER, self.f.request('damaged:' + str(index)))
                    self.assertEqual(self.f.counts(), before)
            finally:
                self.write_body(self.body)

    def test_wrong_storage_malformed_and_oversized_body_refuse_reads_and_promotion(self):
        self.f.catalog.transition(OWNER, self.key,
            expected_revision=self.f.catalog._revision(OWNER.deployment), target='suspended')
        before, revision = self.f.counts(), self.f.catalog._revision(OWNER.deployment)
        for body in (self.body.decode(), b'', b'{}', b'not json', b'x' * 65537,
                     canonical(dict(self.receipt, physicalObjectiveVerified=True))):
            self.write_body(body)
            try:
                with self.subTest(bodyType=type(body).__name__, length=len(body)):
                    self.code('PAT_EVALUATION_INVALID', self.f.catalog.evaluation, OWNER, self.evaluation)
                    self.code('PAT_EVALUATION_INVALID', self.f.catalog.evaluate, OWNER, self.key,
                              self.f.spec.evaluator_id, self.receipt['runId'])
                    self.code('PAT_EVALUATION_INVALID', self.f.catalog.transition, OWNER, self.key,
                              expected_revision=revision, target='active')
                    self.assertEqual(self.f.counts(), before)
                    self.assertEqual(self.f.catalog._revision(OWNER.deployment), revision)
            finally:
                self.write_body(self.body)

    def test_row_associations_and_missing_referenced_receipt_refuse(self):
        other = copy.deepcopy(self.f.program); other['name'] += '-other'
        other_key = self.f.activate(other)
        for field, value, original in (('artifact', other_key, self.key),
                                       ('evaluator', 'wrong:evaluator', self.f.spec.evaluator_id),
                                       ('run_id', 'wrong:run', self.receipt['runId'])):
            with self.f.runtime.journal._transaction():
                self.db.execute('UPDATE pc_evaluations SET ' + field + '=? WHERE digest=?', (value, self.evaluation))
            before = self.f.counts()
            try:
                with self.subTest(field=field):
                    self.code('PAT_EVALUATION_INVALID', self.f.catalog.describe, OWNER, self.key)
                    self.code('PAT_EVALUATION_INVALID', self.f.catalog.evaluation, OWNER, self.evaluation)
                    self.code('PAT_EVALUATION_INVALID', self.f.store.run, OWNER, self.f.request('metadata:' + field))
                    self.assertEqual(self.f.counts(), before)
            finally:
                with self.f.runtime.journal._transaction():
                    self.db.execute('UPDATE pc_evaluations SET ' + field + '=? WHERE digest=?', (original, self.evaluation))
        with self.f.runtime.journal._transaction():
            self.db.execute('DELETE FROM pc_evaluations WHERE digest=?', (self.evaluation,))
        before = self.f.counts()
        self.code('PAT_EVALUATION_INVALID', self.f.catalog.describe, OWNER, self.key)
        self.code('PAT_EVALUATION_INVALID', self.f.store.run, OWNER, self.f.request('missing'))
        self.assertEqual(self.f.counts(), before)

    def test_exact_historical_run_survives_catalog_receipt_damage(self):
        request = self.f.request()
        first = self.f.store.run(OWNER, request)
        self.write_body(b'{}')
        self.assertEqual(self.f.store.run(OWNER, request), first)
        before = self.f.counts()
        self.code('PAT_EVALUATION_INVALID', self.f.store.run, OWNER, self.f.request('new'))
        self.assertEqual(self.f.counts(), before)

    def test_impossible_active_entry_does_not_disappear_from_candidates(self):
        alternative = copy.deepcopy(self.f.program); alternative['name'] += '-other'
        self.f.activate(alternative)
        for column, wrong, original in (('evaluation', None, self.evaluation),
                                         ('evaluation_conflict', 1, 0)):
            with self.f.runtime.journal._transaction():
                self.db.execute('UPDATE pc_entries SET ' + column + '=? WHERE deployment=? AND artifact=?',
                                (wrong, OWNER.deployment, self.key))
            before = self.f.counts()
            try:
                with self.subTest(column=column):
                    self.code('PAT_EVALUATION_INVALID', self.f.store.run, OWNER, self.f.request('entry:' + column))
                    self.code('PAT_EVALUATION_INVALID', self.f.catalog.describe, OWNER, self.key)
                    self.assertEqual(self.f.counts(), before)
            finally:
                with self.f.runtime.journal._transaction():
                    self.db.execute('UPDATE pc_entries SET ' + column + '=? WHERE deployment=? AND artifact=?',
                                    (original, OWNER.deployment, self.key))

    def test_replay_metadata_is_bounded_before_host_fetch(self):
        for column, original in (('digest', self.evaluation), ('artifact', self.key)):
            wrong = 'sha256:' + 'a' * 100000
            with self.f.runtime.journal._transaction():
                if column == 'artifact':
                    self.db.execute('INSERT INTO pc_artifacts VALUES (?,?)', (wrong, b'{}'))
                self.db.execute('UPDATE pc_evaluations SET ' + column + '=? WHERE deployment=? AND evaluator=? AND run_id=?',
                    (wrong, OWNER.deployment, self.f.spec.evaluator_id, self.receipt['runId']))
            sizes = []
            previous_factory = self.db.row_factory
            def measure(cursor, row):
                sizes.extend(len(value) for value in row if type(value) in (str, bytes))
                return sqlite3.Row(cursor, row)
            self.db.row_factory = measure
            try:
                with self.subTest(column=column):
                    self.code('PAT_EVALUATION_INVALID', self.f.catalog.evaluate, OWNER, self.key,
                              self.f.spec.evaluator_id, self.receipt['runId'])
                    self.assertLessEqual(max(sizes, default=0), 65536)
            finally:
                self.db.row_factory = previous_factory
                with self.f.runtime.journal._transaction():
                    self.db.execute('UPDATE pc_evaluations SET ' + column + '=? WHERE deployment=? AND evaluator=? AND run_id=?',
                        (original, OWNER.deployment, self.f.spec.evaluator_id, self.receipt['runId']))

    def test_conflict_receipt_remains_linked_to_its_original_run(self):
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        issued = []
        def evaluate(artifact, environment):
            with lock:
                number = len(issued); issued.append(number)
            barrier.wait(timeout=30)
            return dict(result(), limitations=['Concurrent synthetic result ' + str(number)])
        spec = replace(self.f.spec, evaluate=evaluate)
        catalog = PatCatalog(self.f.runtime.journal, compiler_digest=compiler_digest,
            environment=lambda context, artifact: copy.deepcopy(self.f.environments[pat_digest(artifact)]),
            evaluators=(spec,))
        def run():
            try:
                return catalog.evaluate(OWNER, self.key, spec.evaluator_id, 'concurrent:run')
            except JournalError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as executor:
            answers = list(executor.map(lambda _: run(), range(2)))
        self.assertEqual(sum(type(a) is dict for a in answers), 1)
        self.assertIn('PAT_EVALUATION_KEY_CONFLICT', answers)
        conflict, prior = self.db.execute('SELECT digest,prior_evaluation FROM pc_evaluation_conflicts').fetchone()
        self.assertNotEqual(prior, self.evaluation)
        self.assertEqual(catalog.evaluation(OWNER, conflict)['runId'], 'concurrent:run')
        with self.f.runtime.journal._transaction():
            self.db.execute('UPDATE pc_evaluation_conflicts SET prior_evaluation=? WHERE digest=?',
                            (self.evaluation, conflict))
        self.code('PAT_EVALUATION_INVALID', catalog.evaluation, OWNER, conflict)


if __name__ == '__main__':
    unittest.main()
