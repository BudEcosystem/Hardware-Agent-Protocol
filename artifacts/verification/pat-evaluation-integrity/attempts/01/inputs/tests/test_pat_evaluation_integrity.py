"""Retained evaluation integrity before selection filters; synthetic evaluation."""
import copy
import tempfile
import unittest

from hms.contracts import canonical
from hms.journal import JournalError
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


if __name__ == '__main__':
    unittest.main()
