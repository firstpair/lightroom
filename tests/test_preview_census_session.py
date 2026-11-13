import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.preview_pipeline.census_files import CaptureFileCloseUnknown, identity
from scripts.preview_pipeline.census_journal import CaptureAttempts, CaptureAttemptUnknown
from scripts.preview_pipeline.census_session import (
    CaptureSessionProducer, CaptureSessionStopped, check_capture_session,
)
from scripts.preview_pipeline.census_store import DurableCaptureWriter, CaptureJournalWriteUnknown
from scripts.preview_pipeline.descriptor_census import parse


class CaptureSessionTests(unittest.TestCase):
    """Original fake census receipts and actual tempfile IO, no lsof/native calls."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.journal_root = self.root/'journal'
        self.capture_root = self.root/'captures'
        self.journal_root.mkdir(mode=0o700)
        self.capture_root.mkdir(mode=0o700)
        self.journal_fd = os.open(self.journal_root, os.O_RDONLY | os.O_DIRECTORY)
        self.capture_fd = os.open(self.capture_root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.journal_fd)
        self.addCleanup(os.close, self.capture_fd)
        self.writer = DurableCaptureWriter(self.journal_fd, str(self.journal_root))
        self.journal = CaptureAttempts(self.writer)
        self.receipts = []
        self.pin_rows = []
        self.roots = ('/synthetic/cache',)

    def fake_capture(self, index):
        directory = self.capture_root/('owned-census-' + str(index+1)*32)
        directory.mkdir(mode=0o700)
        pid = 777+index
        raw = (f'p123\ncworker\nf2\ntREG\nn/synthetic/cache/image\np{pid}\n'
               'clsof\nf1\ntREG\nn/synthetic/control\n').encode()
        source = directory/'stdout'
        source.write_bytes(raw)
        source.chmod(0o600)
        census = parse([raw], self.roots)
        projected = census.legacy_fields()
        receipt = dict(
            state='COMPLETE_GLOBAL_CENSUS_PROJECTED_CHILD_GROUP_FDS_CLOSED',
            command=['/usr/sbin/lsof', '-nP', '-Fpcftn'],
            actual=dict(pid=pid, returncode=0, reaped=True,
                        other_group_members_absent_before_reap=True,
                        members_before_reap=[dict(pid=pid, state='Z')],
                        timed_out=False, signals_sent=0),
            raw=dict(path=str(source), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                     identity8=list(identity(source.stat()))),
            projection=dict(bytes=len(projected), sha256=hashlib.sha256(projected).hexdigest()),
            process_count=2, named_count=2, protected_count=1,
            owned_fds_closed=True, caller_grants_released=False, signals_sent=0)
        path = directory/'RESULT.json'
        encoded = json.dumps(receipt).encode()
        path.write_bytes(encoded)
        path.chmod(0o600)
        pin = dict(path=str(path), bytes=len(encoded), sha256=hashlib.sha256(encoded).hexdigest())
        self.receipts.append(receipt)
        self.pin_rows.append(pin)
        return 0, projected, b'', pin

    def prepare(self):
        for index in range(2):
            self.journal.capture(lambda index=index: self.fake_capture(index))
        self.journal.seal()

    def check(self, **kwargs):
        pins = [{key:row[key] for key in ('path', 'bytes', 'sha256')}
                for row in self.writer.records()]
        return check_capture_session(self.journal_fd, str(self.journal_root), pins,
                                     self.capture_fd, str(self.capture_root), self.roots, **kwargs)

    def test_all_durable_attempts_bind_all_independent_raw_captures(self):
        self.prepare()
        result = self.check(ancestor_pids=(100, 200))
        self.assertEqual(len(result.captures), 2)
        self.assertEqual(len(result.journal.snapshot_pins), 5)
        self.assertEqual(len(result.receipt_pins), 2)
        self.assertEqual(result.captures[0].census.protected[0].pid, 123)
        self.assertFalse(result.resource_release_authorized)
        self.assertFalse(result.journal.resource_release_authorized)
        os.fstat(self.journal_fd)
        os.fstat(self.capture_fd)

    def test_unrecorded_extra_capture_cannot_be_ignored(self):
        self.prepare()
        (self.capture_root/('owned-census-'+'f'*32)).mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, 'DIRECTORY_INVENTORY'):
            self.check()

    def test_missing_capture_is_not_accepted_from_a_valid_journal(self):
        self.prepare()
        directory = self.capture_root/('owned-census-'+'2'*32)
        directory.rename(self.root/'preserved-outside-capture-scope')
        with self.assertRaisesRegex(ValueError, 'DIRECTORY_INVENTORY'):
            self.check()

    def test_raw_substitution_is_not_saved_result_success(self):
        self.prepare()
        path = Path(self.receipts[0]['raw']['path'])
        path.write_bytes(path.read_bytes().replace(b'worker', b'altered'))
        with self.assertRaisesRegex(ValueError, 'RAW_EPOCH'):
            self.check()

    def test_receipt_substitution_is_not_accepted_by_the_journal(self):
        self.prepare()
        Path(self.pin_rows[0]['path']).write_text('{}')
        with self.assertRaises(ValueError):
            self.check()

    def test_failed_or_unsealed_invocation_is_never_a_complete_session(self):
        self.journal.capture(lambda: self.fake_capture(0))
        with self.assertRaises(ValueError):
            self.check()

    def test_ancestor_wait_alias_is_not_accepted(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, 'WAIT_REPORT'):
            self.check(ancestor_pids=(777,))

    def test_even_valid_content_with_unknown_readback_close_retains(self):
        self.prepare()
        real_close = os.close

        def uncertain(fd):
            real_close(fd)
            raise OSError('test close uncertainty')

        with patch('scripts.preview_pipeline.census_readback.os.close', side_effect=uncertain) as close:
            with self.assertRaises(CaptureFileCloseUnknown):
                self.check()
        self.assertEqual(close.call_count, 1)

    def test_same_directory_cannot_be_both_journal_and_capture_namespace(self):
        self.prepare()
        pins = [{key:row[key] for key in ('path', 'bytes', 'sha256')}
                for row in self.writer.records()]
        with self.assertRaisesRegex(ValueError, 'DISTINCT_NAMESPACES'):
            check_capture_session(self.journal_fd, str(self.journal_root), pins,
                                  self.journal_fd, str(self.journal_root), self.roots)

    def producer(self, invoke):
        return CaptureSessionProducer(self.journal_fd, str(self.journal_root),
                                      self.capture_fd, str(self.capture_root), invoke)

    def test_producer_durable_intents_then_parent_full_session_audit(self):
        calls = []

        def invoke(root, roots, deadline, maximum):
            self.assertEqual((root, roots, deadline, maximum),
                             (self.capture_root, self.roots, 123.0, 1048576))
            intent = json.loads((self.journal_root/f'{len(calls)*2:06d}.json').read_bytes())
            self.assertEqual(intent['state'], 'INTENT')
            calls.append(len(calls))
            return self.fake_capture(calls[-1])

        producer = self.producer(invoke)
        producer.capture(self.roots, 123.0, 1048576)
        producer.capture(self.roots, 123.0, 1048576)
        report = producer.seal()
        self.assertEqual(report['reported_captures'], 2)
        self.assertFalse(report['resource_release_authorized'])
        self.assertEqual(report['capture_root']['identity8'], list(identity(os.fstat(self.capture_fd))))
        checked = check_capture_session(self.journal_fd, str(self.journal_root),
                                         report['snapshot_pins'], self.capture_fd,
                                         str(self.capture_root), self.roots)
        self.assertEqual(len(checked.captures), 2)
        with self.assertRaises(ValueError):
            producer.capture(self.roots, 123.0, 1048576)

    def test_producer_unknown_callback_retains_original_and_prevents_next_call(self):
        original = RuntimeError('original child state unknown')
        calls = []

        def invoke(*_args):
            calls.append(True)
            raise original

        producer = self.producer(invoke)
        with self.assertRaises(CaptureSessionStopped) as caught:
            producer.capture(self.roots, 123.0, 1048576)
        self.assertIsInstance(caught.exception.original_error, CaptureAttemptUnknown)
        self.assertIs(caught.exception.original_error.original_error, original)
        self.assertIs(caught.exception.session, producer)
        with self.assertRaises(CaptureSessionStopped) as again:
            producer.capture(self.roots, 123.0, 1048576)
        self.assertIs(again.exception, caught.exception)
        self.assertEqual(calls, [True])
        with self.assertRaises(CaptureSessionStopped):
            producer.seal()
        os.fstat(self.journal_fd)
        os.fstat(self.capture_fd)

    def test_producer_intent_flush_failure_prevents_callback(self):
        calls = []
        producer = self.producer(lambda *_args: calls.append(True))
        real_fsync = os.fsync

        def fsync(fd):
            if fd == self.journal_fd:
                raise OSError('injected intent durability failure')
            return real_fsync(fd)

        with patch('scripts.preview_pipeline.census_store.os.fsync', side_effect=fsync):
            with self.assertRaises(CaptureSessionStopped) as caught:
                producer.capture(self.roots, 123.0, 1048576)
        self.assertEqual(calls, [])
        self.assertIsInstance(caught.exception.original_error, CaptureJournalWriteUnknown)
        self.assertEqual(list(self.capture_root.iterdir()), [])

    def test_producer_duplicate_receipt_stops_even_when_callback_claims_success(self):
        response = self.fake_capture(0)
        # The constructor requires a fresh capture root, so preserve the fake
        # first result and move it back only from inside the qualified callback.
        directory = next(self.capture_root.iterdir())
        parked = self.root/'parked-fixture'
        directory.rename(parked)
        calls = []

        def invoke(*_args):
            if not calls:
                parked.rename(directory)
            calls.append(True)
            return response

        producer = self.producer(invoke)
        producer.capture(self.roots, 123.0, 1048576)
        with self.assertRaisesRegex(CaptureSessionStopped, 'NO_AUTOMATIC_REPLAY'):
            producer.capture(self.roots, 123.0, 1048576)
        with self.assertRaises(CaptureSessionStopped):
            producer.seal()
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
