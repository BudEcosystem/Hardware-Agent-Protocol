"""Original one-case import fixture; not a lifecycle behavior test."""
import importlib.util
from pathlib import Path
import unittest
import shared_probe


class Probe(unittest.TestCase):
    def test_exact_sources_and_denied_sourceless_cache(self):
        import probe_source
        self.assertEqual(probe_source.VALUE,'source')
        self.assertEqual(shared_probe.VALUE,'shared-original')
        path=Path(__file__).parent/'fixtures/dynamic_origin.py'
        spec=importlib.util.spec_from_file_location('dynamic_unregistered_origin',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.VALUE,'dynamic-original')
        cached=Path(__file__).parent/'fixtures/sourceless.pyc'
        spec=importlib.util.spec_from_file_location('original_sourceless_refusal',cached)
        module=importlib.util.module_from_spec(spec)
        with self.assertRaises(FileNotFoundError):spec.loader.exec_module(module)
