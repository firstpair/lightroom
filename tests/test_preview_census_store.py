import errno
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts.preview_pipeline.census_journal import CaptureAttempts, CaptureAttemptUnknown
from scripts.preview_pipeline.census_store import DurableCaptureWriter, CaptureJournalWriteUnknown


class DurableCaptureStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        self.writer = DurableCaptureWriter(self.fd, str(self.root))

    def snapshot(self):
        return dict(schema='CAPTURE_ATTEMPTS_V1', state='INTENT', attempts=[],
                    resource_release_authorized=False)

    def test_real_persistence_precedes_invocation_and_seals_inventory(self):
        journal = CaptureAttempts(self.writer)

        def invoke():
            saved = json.loads((self.root/'000000.json').read_text())
            self.assertEqual(saved['state'], 'INTENT')
            self.assertTrue(self.writer.records()[0]['directory_fsynced'])
            return 0, b'projected fixture', b'', dict(path='/synthetic/RESULT.json',
                                                    bytes=5, sha256='a'*64)

        journal.capture(invoke)
        journal.seal()
        self.assertEqual([json.loads(p.read_text())['state'] for p in sorted(self.root.iterdir())],
                         ['INTENT', 'OUTCOME', 'SEALED'])
        for record in self.writer.records():
            self.assertTrue(record['file_closed'] and record['directory_fsynced'])
            self.assertFalse(record['resource_release_authorized'])
        with self.assertRaises(ValueError):
            self.writer(self.snapshot())
        os.fstat(self.fd)  # writer did not close the borrowed root

    def test_failed_intent_durability_prevents_any_invocation(self):
        calls = []
        real_fsync = os.fsync

        def fsync(fd):
            if fd == self.fd:
                raise OSError(errno.EIO, 'injected directory flush failure')
            return real_fsync(fd)

        journal = CaptureAttempts(self.writer)
        with patch('scripts.preview_pipeline.census_store.os.fsync', side_effect=fsync):
            with self.assertRaises(CaptureJournalWriteUnknown) as caught:
                journal.capture(lambda: calls.append('must not run'))
        self.assertEqual(calls, [])
        self.assertTrue(caught.exception.record['file_closed'])
        self.assertFalse(caught.exception.record['directory_fsynced'])
        self.assertTrue((self.root/'000000.json').is_file())
        with self.assertRaises(CaptureJournalWriteUnknown) as again:
            self.writer(self.snapshot())
        self.assertIs(again.exception, caught.exception)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_outcome_flush_failure_retains_attempt_and_never_replays(self):
        real_fsync = os.fsync
        counts = {'directory': 0, 'invoked': 0}

        def fsync(fd):
            if fd == self.fd:
                counts['directory'] += 1
                if counts['directory'] == 2:
                    raise OSError(errno.EIO, 'outcome directory failure')
            return real_fsync(fd)

        def invoke():
            counts['invoked'] += 1
            return 0, b'fixture', b'', dict(path='/synthetic/RESULT.json', bytes=4, sha256='b'*64)

        journal = CaptureAttempts(self.writer)
        with patch('scripts.preview_pipeline.census_store.os.fsync', side_effect=fsync):
            with self.assertRaises(CaptureAttemptUnknown) as caught:
                journal.capture(invoke)
        self.assertEqual(counts['invoked'], 1)
        self.assertIsInstance(caught.exception.original_error, CaptureJournalWriteUnknown)
        with self.assertRaises(ValueError):
            journal.capture(invoke)
        self.assertEqual(counts['invoked'], 1)
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_partial_writes_complete_without_duplication(self):
        real_write = os.write
        with patch('scripts.preview_pipeline.census_store.os.write',
                   side_effect=lambda fd, data: real_write(fd, data[:7])):
            self.writer(self.snapshot())
        self.assertEqual(json.loads((self.root/'000000.json').read_bytes()), self.snapshot())

    def test_interrupted_write_is_not_retried(self):
        with patch('scripts.preview_pipeline.census_store.os.write',
                   side_effect=InterruptedError(errno.EINTR, 'write uncertain')) as write:
            with self.assertRaises(CaptureJournalWriteUnknown) as caught:
                self.writer(self.snapshot())
        self.assertEqual(write.call_count, 1)
        self.assertIsInstance(caught.exception.original_error, InterruptedError)
        self.assertEqual(caught.exception.record['phase'], 'WRITE')
        self.assertEqual(self.writer.records(), ())

    def test_close_uncertainty_records_identity_and_never_retries(self):
        real_close = os.close
        failed_fd = []

        def close(fd):
            failed_fd.append(fd)
            # Model an error after the descriptor was actually closed. A retry
            # could close an unrelated reused number, so the writer must latch.
            real_close(fd)
            raise OSError(errno.EINTR, 'close result unknown')

        with patch('scripts.preview_pipeline.census_store.os.close', side_effect=close) as closer:
            with self.assertRaises(CaptureJournalWriteUnknown) as caught:
                self.writer(self.snapshot())
            with self.assertRaises(CaptureJournalWriteUnknown):
                self.writer(self.snapshot())
        self.assertEqual(closer.call_count, 1)
        row = caught.exception.uncertain_closes[0]
        self.assertEqual(row['fd'], failed_fd[0])
        self.assertEqual(len(row['preclose_identity']), 8)
        self.assertFalse(row['numeric_retry'])
        os.fstat(self.fd)

    def test_foreign_entry_is_not_overwritten(self):
        foreign = self.root/'000000.json'
        foreign.write_bytes(b'foreign original')
        with self.assertRaises(CaptureJournalWriteUnknown):
            self.writer(self.snapshot())
        self.assertEqual(foreign.read_bytes(), b'foreign original')

    def test_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as other:
            target = Path(other)/'untouched'
            target.write_bytes(b'preserve')
            (self.root/'000000.json').symlink_to(target)
            with self.assertRaises(CaptureJournalWriteUnknown):
                self.writer(self.snapshot())
            self.assertEqual(target.read_bytes(), b'preserve')

    def test_nonempty_or_public_directory_refused(self):
        (self.root/'existing').write_bytes(b'preserve')
        with self.assertRaises(ValueError):
            DurableCaptureWriter(self.fd, str(self.root))
        (self.root/'existing').unlink()
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):
            DurableCaptureWriter(self.fd, str(self.root))

    def test_returned_inventory_is_not_a_mutation_capability(self):
        self.writer(self.snapshot())
        record = self.writer.records()[0]
        record['sha256'] = '0'*64
        self.assertNotEqual(self.writer.records()[0]['sha256'], record['sha256'])

    def test_replaced_file_cannot_be_reported_as_durable_snapshot(self):
        real_fsync = os.fsync

        def fsync(fd):
            real_fsync(fd)
            if fd != self.fd:
                replacement = self.root/'replacement'
                replacement.write_bytes(b'foreign')
                os.replace(replacement, self.root/'000000.json')

        with patch('scripts.preview_pipeline.census_store.os.fsync', side_effect=fsync):
            with self.assertRaises(CaptureJournalWriteUnknown):
                self.writer(self.snapshot())
        self.assertEqual(self.writer.records(), ())
        self.assertEqual((self.root/'000000.json').read_bytes(), b'foreign')

    def test_writer_cannot_move_to_another_thread(self):
        errors = []

        def call():
            try:
                self.writer(self.snapshot())
            except ValueError as error:
                errors.append(str(error))

        thread = threading.Thread(target=call)
        thread.start()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, ['JOURNAL_ORIGINAL_SERIAL_OWNER_REQUIRED'])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_write_and_cleanup_close_failures_preserve_both_causes(self):
        original = OSError(errno.EIO, 'original write failure')
        real_close = os.close

        def close(fd):
            real_close(fd)
            raise OSError(errno.EINTR, 'cleanup close uncertain')

        with patch('scripts.preview_pipeline.census_store.os.write', side_effect=original), \
                patch('scripts.preview_pipeline.census_store.os.close', side_effect=close) as closer:
            with self.assertRaises(CaptureJournalWriteUnknown) as caught:
                self.writer(self.snapshot())
        self.assertIs(caught.exception.original_error, original)
        self.assertEqual(closer.call_count, 1)
        self.assertIn('cleanup close uncertain', caught.exception.uncertain_closes[0]['error'])
        self.assertEqual(len(caught.exception.uncertain_closes[0]['preclose_identity']), 8)

    def test_cleanup_identity_failure_retains_known_open_fd_without_close(self):
        real_fstat = os.fstat
        real_close = os.close
        failed = []

        def write(fd, _data):
            failed.append(fd)
            raise OSError(errno.EIO, 'original write failure')

        def fstat(fd):
            if fd in failed:
                raise OSError(errno.EIO, 'identity observation unavailable')
            return real_fstat(fd)

        with patch('scripts.preview_pipeline.census_store.os.write', side_effect=write), \
                patch('scripts.preview_pipeline.census_store.os.fstat', side_effect=fstat), \
                patch('scripts.preview_pipeline.census_store.os.close') as closer:
            with self.assertRaises(CaptureJournalWriteUnknown) as caught:
                self.writer(self.snapshot())
        self.assertEqual(closer.call_count, 0)
        self.assertEqual(caught.exception.retained_fds, tuple(failed))
        self.assertFalse(caught.exception.uncertain_closes[0]['close_attempted'])
        self.assertEqual(len(caught.exception.record['opened_identity']), 8)
        # Fixture knows no close syscall was attempted; close that known-open
        # descriptor once, not an uncertain numeric-descriptor retry.
        real_close(failed[0])


if __name__ == '__main__':
    unittest.main()
