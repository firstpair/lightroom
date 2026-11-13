import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.preview_pipeline import census_files as module
from scripts.preview_pipeline.descriptor_census import parse

RAW = b'p123\ncworker\nf2\ntREG\nn/synthetic/cache/image\np777\nclsof\nf1\ntREG\nn/synthetic/control\n'
ROOTS = ('/synthetic/cache',)


class CaptureFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.directory = self.root / ('owned-census-' + 'a' * 32)
        self.directory.mkdir(mode=0o700)
        self.raw = self.directory / 'stdout'
        self.raw.write_bytes(RAW); self.raw.chmod(0o600)
        census = parse([RAW], ROOTS); projection = census.legacy_fields()
        self.receipt = {
            'state': 'COMPLETE_GLOBAL_CENSUS_PROJECTED_CHILD_GROUP_FDS_CLOSED',
            'command': ['/usr/sbin/lsof', '-nP', '-Fpcftn'],
            'actual': dict(pid=777, returncode=0, reaped=True,
                           other_group_members_absent_before_reap=True,
                           members_before_reap=[dict(pid=777, state='Z')],
                           timed_out=False, signals_sent=0),
            'raw': dict(path=str(self.raw), bytes=len(RAW), sha256=hashlib.sha256(RAW).hexdigest(),
                        identity8=list(module.identity(self.raw.stat()))),
            'projection': dict(bytes=len(projection), sha256=hashlib.sha256(projection).hexdigest()),
            'process_count': 2, 'named_count': 2, 'protected_count': 1,
            'owned_fds_closed': True, 'caller_grants_released': False, 'signals_sent': 0,
        }
        self.path = self.directory / 'RESULT.json'
        self.pin = self.write_receipt()
        self.root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)

    def tearDown(self):
        os.close(self.root_fd)
        self.temp.cleanup()

    def write_receipt(self):
        data = json.dumps(self.receipt).encode()
        self.path.write_bytes(data); self.path.chmod(0o600)
        return dict(path=str(self.path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

    def check(self, records=None, **kwargs):
        return module.check_capture_files(self.root_fd, str(self.root),
                                          [self.pin] if records is None else records,
                                          ROOTS, **kwargs)

    def test_real_files_checked_child_descriptors_closed_root_borrowed(self):
        close = os.close
        closed = []
        def observed(fd):
            closed.append(fd); close(fd)
        with mock.patch.object(module.os, 'close', side_effect=observed):
            result = self.check(ancestor_pids=(100, 200))
        self.assertEqual(len(closed), 3)
        self.assertNotIn(self.root_fd, closed)
        self.assertTrue(os.fstat(self.root_fd))
        self.assertEqual(result.captures[0].census.protected[0].pid, 123)
        self.assertFalse(result.resource_release_authorized)
        with self.assertRaises(TypeError):
            module.CheckedFiles(result.captures, resource_release_authorized=True)

    def test_missing_duplicate_or_outside_inventory_never_promoted(self):
        for records in ([], [self.pin, self.pin], [dict(self.pin, path='/other/RESULT.json')],
                        [dict(self.pin, path=str(self.directory / '../RESULT.json'))]):
            with self.subTest(records=records), self.assertRaises(ValueError):
                self.check(records)
        with self.assertRaisesRegex(ValueError, 'ANCESTOR|WAIT_REPORT'):
            self.check(ancestor_pids=(777,))

    def test_pinned_receipt_hash_and_size_are_both_required(self):
        for changed in (dict(self.pin, sha256='0' * 64), dict(self.pin, bytes=1),
                        dict(self.pin, bytes=True), dict(self.pin, sha256='A' * 64)):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.check([changed])

    def test_raw_substitution_epoch_mode_and_hardlink_refused(self):
        self.raw.write_bytes(RAW.replace(b'worker', b'altered'))
        with self.assertRaisesRegex(ValueError, 'RAW_EPOCH'): self.check()
        self.raw.write_bytes(RAW); self.raw.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'PRIVATE_FILE'): self.check()
        self.raw.chmod(0o600)
        os.link(self.raw, self.root / 'extra-link')
        with self.assertRaisesRegex(ValueError, 'PRIVATE_FILE'): self.check()

    def test_nofollow_directory_and_raw(self):
        self.raw.unlink(); self.raw.symlink_to(self.path)
        with self.assertRaises(OSError): self.check()
        alias = self.root / ('owned-census-' + 'b' * 32)
        alias.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(OSError):
            self.check([dict(self.pin, path=str(alias / 'RESULT.json'))])

    def test_replacing_visible_raw_after_read_refused(self):
        read = os.read
        raw_inode = self.raw.stat().st_ino
        replaced = False
        def changing(fd, count):
            nonlocal replaced
            value = read(fd, count)
            if value and os.fstat(fd).st_ino == raw_inode and not replaced:
                replaced = True
                replacement = self.directory / 'replacement'
                replacement.write_bytes(RAW); replacement.chmod(0o600)
                replacement.replace(self.raw)
            return value
        with mock.patch.object(module.os, 'read', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'FILE_EPOCH_CHANGED'):
                self.check()

    def test_multiple_close_uncertainties_attempted_once_keep_original(self):
        self.receipt['raw']['identity8'][2] += 1
        self.pin = self.write_receipt()
        close = os.close
        attempts = []
        def uncertain(fd):
            attempts.append(fd)
            close(fd)  # test knows this consumed the FD; production caller cannot assume
            raise OSError('injected close uncertainty')
        with mock.patch.object(module.os, 'close', side_effect=uncertain):
            with self.assertRaises(module.CaptureFileCloseUnknown) as caught:
                self.check()
        error = caught.exception
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len(set(attempts)), 3)
        self.assertEqual(len(error.uncertain_closes), 3)
        self.assertIn('RAW_EPOCH', str(error.original_error))
        self.assertIs(error.__cause__, error.original_error)
        for record in error.uncertain_closes:
            self.assertEqual(len(record['preclose_identity']), 8)
            self.assertTrue(record['close_attempted'])
            self.assertFalse(record['numeric_retry'])

    def test_successful_content_with_uncertain_close_is_not_success(self):
        close = os.close
        def uncertain(fd):
            close(fd)
            raise OSError('injected close uncertainty')
        with mock.patch.object(module.os, 'close', side_effect=uncertain):
            with self.assertRaises(module.CaptureFileCloseUnknown) as caught:
                self.check()
        self.assertIsNone(caught.exception.original_error)
        self.assertEqual(len(caught.exception.uncertain_closes), 3)


if __name__ == '__main__':
    unittest.main()
