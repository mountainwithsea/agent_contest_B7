import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ref_app.jobs import JobStore
from ref_app.worker import run


class FailureAuditTests(unittest.TestCase):
    def test_failed_status_is_published_after_inventory(self):
        original=JobStore.update
        def observed(store,jid,**values):
            if values.get('state')=='failed':
                self.assertTrue((store.folder(jid)/'inventory.json').is_file(),
                                'Failed state must not expose a half-written audit export')
            return original(store,jid,**values)
        with tempfile.TemporaryDirectory() as d:
            store=JobStore(Path(d));job=store.create('test.txt',b'Offline audit ordering test.')
            with patch('b7_shared.config.load_values',return_value={}),patch('ref_app.worker.ModelConfig.from_values',side_effect=ValueError('offline-test')),patch.object(JobStore,'update',observed):
                run(store.folder(job['id']))
            self.assertEqual(store.read(job['id'])['state'],'failed')


if __name__=='__main__':unittest.main()
