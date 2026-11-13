import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


MODULE = Path(__file__).resolve().parents[1] / "scripts/preview_pipeline/inherited_lock.py"
spec = importlib.util.spec_from_file_location("inherited_lock", MODULE)
locks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(locks)


class InheritedLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name).resolve() / "watcher.lock"
        self.path.touch(mode=0o600)
        self.fd = os.open(self.path, os.O_RDWR | os.O_NOFOLLOW)
        self.addCleanup(self.close_parent)
        self.expected = locks.identity(os.fstat(self.fd))
        fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def close_parent(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)

    def contender(self):
        code = """
import fcntl,os,sys
fd=os.open(sys.argv[1],os.O_RDWR|os.O_NOFOLLOW)
try:
 try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:sys.exit(7)
finally:os.close(fd)
"""
        return subprocess.run([sys.executable, "-I", "-c", code, str(self.path)],
                              timeout=5, check=False).returncode

    def test_inherited_child_exit_keeps_parent_lock_held(self):
        code = """
import importlib.util,json,sys
s=importlib.util.spec_from_file_location('borrowed',sys.argv[1])
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
r=m.verify_exclusive(int(sys.argv[2]),sys.argv[3],json.loads(sys.argv[4]))
assert r['exclusiveLockConfirmed'] and not r['parentOwnershipAndChildSettlementProven']
"""
        self.assertEqual(self.contender(), 7)
        child = subprocess.run(
            [sys.executable, "-I", "-c", code, str(MODULE), str(self.fd),
             str(self.path), json.dumps(self.expected)], pass_fds=(self.fd,),
            timeout=5, check=False,
        )
        self.assertEqual(child.returncode, 0)
        self.assertEqual(self.contender(), 7)
        self.assertEqual(locks.identity(os.fstat(self.fd)), self.expected)
        self.close_parent()
        self.assertEqual(self.contender(), 0)

    def test_separate_description_cannot_replace_inherited_description(self):
        fd = os.open(self.path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            with self.assertRaises(BlockingIOError):
                locks.verify_exclusive(fd, self.path, self.expected)
        finally:
            os.close(fd)
        self.assertEqual(self.contender(), 7)

    def test_foreign_visible_file_refused_without_releasing_original(self):
        self.path.rename(self.path.with_name("retained.lock"))
        self.path.touch(mode=0o600)
        with self.assertRaisesRegex(ValueError, "IDENTITY_CHANGED"):
            locks.verify_exclusive(self.fd, self.path, self.expected)
        self.assertEqual(locks.identity(os.fstat(self.fd)), self.expected)

    def test_symlink_visible_path_refused(self):
        alias = self.path.with_name("alias.lock")
        alias.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, "IDENTITY_CHANGED"):
            locks.verify_exclusive(self.fd, alias, self.expected)
        self.assertEqual(self.contender(), 7)
