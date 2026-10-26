import tempfile
import unittest
from pathlib import Path
from b7_shared.lifecycle import SuiteLock


class SuiteLockTests(unittest.TestCase):
    def test_duplicate_launcher_is_rejected_and_lock_releases(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'suite.lock'
            with SuiteLock(p):
                with self.assertRaises(RuntimeError):
                    with SuiteLock(p): pass
            with SuiteLock(p): pass


if __name__=='__main__':unittest.main()
