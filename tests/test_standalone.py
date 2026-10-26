import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from b7_shared.config import load_values, child_environment, data_dir


class StandaloneTests(unittest.TestCase):
    def test_optional_external_formatter_paths_survive_launch(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'B7_ANYSTYLE_HOME':'C:/optional/formatter','B7_NODE_EXE':'C:/optional/node.exe','ANYSTYLE_FORMAT_MODE':'local'},clear=True):
            env=child_environment(Path(d))
            self.assertEqual(env['B7_ANYSTYLE_HOME'],'C:/optional/formatter')
            self.assertEqual(env['B7_NODE_EXE'],'C:/optional/node.exe')
            self.assertEqual(env['ANYSTYLE_FORMAT_MODE'],'local')

    def test_reference_configuration_does_not_generate_other_application_keys(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{},clear=True):
            root=Path(d);p=root/'.env';p.write_text('DEEPSEEK_API_KEY=test-only\n',encoding='utf8')
            values=load_values(p)
            self.assertNotIn('B7_LLM_API_KEY',values)
            env=child_environment(root)
            self.assertNotIn('B7_DATA_DIR',env)
            self.assertNotIn('B7_LLM_MODEL',env)
            self.assertEqual(env['REFERENCE_DATA_DIR'],str(root/'data/reference'))
            self.assertIn(str(root/'reference-checker'),env['PYTHONPATH'])

    def test_other_application_is_not_a_supported_launch_target(self):
        with self.assertRaises(ValueError):data_dir('teaching')

    def test_empty_key_template_and_clean_source_layout(self):
        root=Path(__file__).resolve().parents[1]
        self.assertFalse((root/'teaching-assistant').exists())
        self.assertTrue((root/'start.ps1').is_file())
        self.assertTrue((root/'.env.example').is_file())
        for line in (root/'.env.example').read_text('utf8').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key,value=line.split('=',1)
                if key.endswith(('_KEY','_TOKEN')):self.assertFalse(value.strip())


if __name__=='__main__':unittest.main()
