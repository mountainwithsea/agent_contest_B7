import json
import os
import unittest
from unittest.mock import patch
from ref_app.anystyle_formatter import convert, fingerprint


class ElectronFormatterTests(unittest.TestCase):
    def test_remote_formatter_audit_does_not_require_local_runtime(self):
        with patch('ref_app.anystyle_formatter.runtime_paths',side_effect=AssertionError('Local runtime must not be accessed')):
            self.assertEqual(fingerprint('remote'),{})

    def test_run_as_node_only_applies_to_node_child(self):
        calls=[]
        def run(cmd,**kwargs):
            calls.append((cmd,kwargs['env']))
            value={'csl':[{'title':'Example'}],'locale_samples':['Example title']} if len(calls)==1 else [None]
            return type('Completed',(),{'returncode':0,'stderr':'','stdout':json.dumps(value)})()
        with patch.dict(os.environ,{'B7_NODE_IS_ELECTRON':'1'}),patch('ref_app.anystyle_formatter.subprocess.run',run):
            self.assertEqual(convert([[['title','Example']]])['csl'][0]['title'],'Example')
        self.assertNotIn('ELECTRON_RUN_AS_NODE',calls[0][1])
        self.assertEqual(calls[1][1].get('ELECTRON_RUN_AS_NODE'),'1')


if __name__=='__main__':unittest.main()
