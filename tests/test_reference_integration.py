import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'reference-checker'))
from ref_app.anystyle_formatter import runtime_paths
from ref_app.__main__ import default_data_root


class ReferenceIntegrationTests(unittest.TestCase):
    def test_shared_formatter_paths(self):
        with patch.dict(os.environ, {}, clear=True):
            deps, ruby, node = runtime_paths()
            self.assertTrue(deps.is_relative_to(ROOT/'shared/runtime'))
            self.assertTrue(ruby.is_relative_to(deps))
            self.assertTrue(node.is_relative_to(ROOT/'shared/runtime'))

    def test_reference_data_override(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'REFERENCE_DATA_DIR': d}):
            self.assertEqual(default_data_root(), Path(d).resolve())


if __name__ == '__main__': unittest.main()
