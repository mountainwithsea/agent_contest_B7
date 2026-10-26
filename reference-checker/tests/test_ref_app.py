import unittest
import tempfile
from pathlib import Path
from ref_app.jobs import JobStore, safe_path
from ref_app.worker import validate_parse
from ref_app.worker import checkpoint
from ref_app.lifecycle import FileLock,OwnedProcess,stamp
import os


class AppTests(unittest.TestCase):
    def test_large_reference_lists_are_not_rejected_or_truncated(self):
        from ref_app.worker import validate_reference_list
        for count in (1,50,51,104,500):
            refs=[{'raw_text':f'Reference {i}'} for i in range(count)]
            validate_reference_list(refs)
            self.assertEqual(len(refs),count)
        with self.assertRaises(ValueError):validate_reference_list([])

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):safe_path(Path(d),'../.env')

    def test_upload_extension_and_job_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            store=JobStore(Path(d))
            with self.assertRaises(ValueError):store.create('evil.html',b'x')
            job=store.create('references.txt',b'Example citation')
            self.assertEqual(store.read(job['id'])['state'],'queued')
            self.assertTrue((Path(d)/job['id']/'input.txt').exists())

    def test_parsed_field_shapes(self):
        with self.assertRaises(ValueError):validate_parse({'title':'abc','authors':'Joe'})

    def test_event_order_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            store=JobStore(Path(d));job=store.create('a.txt',b'abc')
            store.event(job['id'],'extract','读取材料')
            store.event(job['id'],'parse','解析字段',done=1,total=2)
            self.assertEqual(len(store.events(job['id'])),2)
            self.assertEqual(store.read(job['id'])['current']['total'],2)

    def test_invalid_checkpoint_is_recoverable(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'result.json';p.write_text('{"broken":')
            self.assertIsNone(checkpoint(p))
            self.assertEqual(p.read_text(),'{"broken":')

    def test_file_lock_prevents_duplicate_writer(self):
        with tempfile.TemporaryDirectory() as d:
            with FileLock(Path(d)/'lock'):
                with self.assertRaises(RuntimeError):
                    with FileLock(Path(d)/'lock'):pass

    def test_process_identity_requires_creation_time(self):
        pid=os.getpid()
        self.assertIsNone(OwnedProcess(pid,stamp(pid)).poll())
        self.assertEqual(OwnedProcess(pid,'wrong-generation').poll(),0)

    def test_inventory_ignores_held_runtime_locks(self):
        from ref_app.worker import inventory_files
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'evidence.txt').write_text('actual evidence')
            with FileLock(root/'.worker.lock'):
                files=inventory_files(root)
            self.assertEqual(list(files),['evidence.txt'])

    def test_blank_ocr_lines_are_recorded_but_not_references(self):
        from reference_extractor.schema import normalize_ocr,validate_ocr
        value={'blocks':[{'text':'','uncertain':False},{'text':'Actual citation','uncertain':False}]}
        validate_ocr(value)
        result=normalize_ocr(value)
        self.assertEqual(len(result['blocks']),1)
        self.assertEqual(result['discarded_blank_blocks'],1)
        with self.assertRaises(ValueError):validate_ocr({'blocks':[{'text':'','uncertain':False}]})
        with self.assertRaises(ValueError):validate_ocr({'blocks':[{'text':'','uncertain':True}]})

if __name__=='__main__':unittest.main()
