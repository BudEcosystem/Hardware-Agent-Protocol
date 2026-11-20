import unittest, importlib.util
class Probe(unittest.TestCase):
    def test_controlled_foreign_origin(self):
        spec=importlib.util.spec_from_file_location("shared_unpinned",'/home/bud/Desktop/bud/hms/artifacts/verification/io-lifecycle-harness-probes/revisions/03/attempts/attempt01/cases/test_unexpected_shared_origin_cannot_produce_current_pass/explicit-foreign-fixture.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.VALUE,"explicit-unpinned-origin")
