import unittest
class Probe(unittest.TestCase):
    @unittest.expectedFailure
    def test_original_bookkeeping_fixture(self):
        self.fail("controlled expected failure")
