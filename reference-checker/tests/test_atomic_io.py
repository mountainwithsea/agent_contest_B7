import ctypes
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from ref_app.jobs import atomic, JobStore


class AtomicIOTests(unittest.TestCase):
    def test_polling_during_cross_process_updates_keeps_complete_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(tmp);job = store.create('test.txt', b'citation')
            code = ('import sys;sys.path.insert(0,sys.argv[3]);from ref_app.jobs import JobStore;'
                    's=JobStore(sys.argv[1]);'
                    '[s.update(sys.argv[2],sequence=i,payload="x"*120000) for i in range(80)]')
            proc = subprocess.Popen([sys.executable, '-c', code, tmp, job['id'],
                                     str(Path(__file__).resolve().parents[1])],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                while proc.poll() is None:
                    self.assertEqual(store.read(job['id'])['id'], job['id'])
                    self.assertEqual(store.list()[0]['id'], job['id'])
                stdout, stderr = proc.communicate(timeout=5)
                self.assertEqual(proc.returncode, 0, stderr.decode(errors='replace'))
                self.assertEqual(store.read(job['id'])['sequence'], 79)
            finally:
                if proc.poll() is None:proc.kill();proc.wait()

    def test_transient_replace_failure_retries_without_truncating_old_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            atomic(path, {'old': True})
            original = os.replace
            attempts = []
            def replace(source, dest):
                attempts.append(1)
                if len(attempts) < 3:
                    self.assertEqual(path.read_text('utf-8').strip(), '{\n  "old": true\n}')
                    raise PermissionError(13, 'temporary sharing conflict')
                original(source, dest)
            with patch('ref_app.jobs.os.replace', side_effect=replace):
                atomic(path, {'new': True})
            self.assertEqual(len(attempts), 3)
            self.assertIn('new', path.read_text('utf-8'))
            self.assertFalse(list(Path(tmp).glob('*.tmp')))

    def test_permanent_failure_is_reported_and_old_record_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'; atomic(path, {'old': True})
            with patch('ref_app.jobs.os.replace', side_effect=PermissionError(13, 'read-only directory')):
                with self.assertRaises(PermissionError):
                    atomic(path, {'new': True})
            self.assertIn('old', path.read_text('utf-8'))
            self.assertFalse(list(Path(tmp).glob('*.tmp')))

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing semantics')
    def test_actual_windows_reader_handle_released_during_atomic_write(self):
        from ctypes import wintypes as w
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
        kernel.CreateFileW.restype = w.HANDLE
        kernel.CloseHandle.argtypes = [w.HANDLE]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'; atomic(path, {'old': True})
            # Read/write sharing is allowed; delete/rename sharing is not.
            handle = kernel.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x80, None)
            self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
            timer = threading.Timer(.15, lambda: kernel.CloseHandle(handle));timer.start()
            try:
                atomic(path, {'new': True})
                self.assertIn('new', path.read_text('utf-8'))
            finally:
                timer.join()


if __name__ == '__main__':
    unittest.main()
class LongFilenameTests(unittest.TestCase):
    def test_atomic_save_does_not_extend_the_destination_filename(self):
        import tempfile,json
        from pathlib import Path
        from ref_app.jobs import atomic
        with tempfile.TemporaryDirectory() as d:
            parent=Path(d)/('folder-'+'x'*70)/('source-'+'y'*60)
            target=parent/('a'*48+'.json')
            atomic(target,{'preserved':'完整证据'})
            self.assertEqual(json.loads(target.read_text('utf-8')),{'preserved':'完整证据'})
