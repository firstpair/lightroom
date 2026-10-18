"""Pure fault controls: sessions, persistence and actual close are doubles."""
from types import SimpleNamespace
import os
from pathlib import Path
import tempfile
import unittest

from scripts.preview_pipeline.capture_finalizer import (
    CaptureFinalizer, FinalizationRetained, ClosedFinalizationReportingError)
from scripts.preview_pipeline.census_session import CaptureSessionProducer, CaptureSessionStopped


class CaptureFinalizerTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.fail_at = None
        self.carrier = object()
        def session(role):
            return SimpleNamespace(
                seal=lambda: self.step(role + '-used'),
                seal_unused=lambda: self.step(role + '-unused'))
        self.owner = CaptureFinalizer(session('process'), session('descriptor'), self.carrier)

    def step(self, name):
        self.events.append(name)
        if name == self.fail_at:
            raise OSError(name)
        return {'reported': name}

    def persist(self, name, value):
        self.step(name)

    def close(self, carrier):
        self.assertIs(carrier, self.carrier)
        self.step('close')
        return True

    def finish(self, **kw):
        return self.owner.finish(process_used=True, descriptor_used=True,
                                 persist=self.persist, close_directories=self.close, **kw)

    def test_used_and_unused_branches(self):
        for process in (False, True):
            for descriptor in (False, True):
                self.setUp()
                result = self.owner.finish(process_used=process, descriptor_used=descriptor,
                                          persist=self.persist, close_directories=self.close)
                self.assertEqual(self.events, [
                    'process-' + ('used' if process else 'unused'), 'PROCESS-SESSION.json',
                    'descriptor-' + ('used' if descriptor else 'unused'), 'CAPTURE-SESSION.json',
                    'close', 'CAPTURE-FINALIZED.json'])
                self.assertTrue(self.owner.directories_closed)
                self.assertFalse(result['resource_release_authorized'])

    def test_seal_and_report_failure_preserve_original_and_sessions(self):
        for point in ('process-used', 'PROCESS-SESSION.json',
                      'descriptor-used', 'CAPTURE-SESSION.json', 'close'):
            self.setUp()
            original = ValueError('original query failure')
            self.fail_at = point
            with self.assertRaises(FinalizationRetained) as caught:
                self.finish(original_failure=original)
            self.assertIs(caught.exception.owner, self.owner)
            self.assertIs(caught.exception.original_failure, original)
            self.assertIs(caught.exception.finalization_failure, caught.exception.__cause__)
            self.assertFalse(self.owner.directories_closed)
            self.assertEqual(self.events.count('close'), int(point == 'close'))
            before = list(self.events)
            with self.assertRaises(ValueError):
                self.finish()
            self.assertEqual(before, self.events)

    def test_final_report_failure_is_known_closed(self):
        self.fail_at = 'CAPTURE-FINALIZED.json'
        with self.assertRaises(ClosedFinalizationReportingError) as caught:
            self.finish()
        self.assertIs(caught.exception.owner, self.owner)
        self.assertTrue(self.owner.directories_closed)
        self.assertEqual(self.events.count('close'), 1)

    def test_close_without_positive_acknowledgement_retains(self):
        with self.assertRaises(FinalizationRetained):
            self.owner.finish(process_used=True, descriptor_used=True,
                              persist=self.persist, close_directories=lambda owner: None)
        self.assertTrue(self.owner.close_attempted)
        self.assertFalse(self.owner.directories_closed)

    def test_invalid_config_does_not_consume_owner(self):
        with self.assertRaises(ValueError):
            self.owner.finish(process_used=1, descriptor_used=False,
                              persist=self.persist, close_directories=self.close)
        self.assertFalse(self.owner.started)
        self.assertEqual(self.events, [])

    def test_failed_unused_seal_is_not_promoted_to_empty_success(self):
        self.fail_at = 'process-unused'
        with self.assertRaises(FinalizationRetained):
            self.owner.finish(process_used=False, descriptor_used=False,
                              persist=self.persist, close_directories=self.close)
        self.assertEqual(self.events, ['process-unused'])

    def test_real_durable_attempt_cannot_be_relabelled_unused(self):
        # Actual journal/tempfile IO, no process, signal, census or payload call.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            journal, captures = root/'journal', root/'captures'
            journal.mkdir(mode=0o700)
            captures.mkdir(mode=0o700)
            journal_fd = os.open(journal, os.O_RDONLY | os.O_DIRECTORY)
            capture_fd = os.open(captures, os.O_RDONLY | os.O_DIRECTORY)
            try:
                calls = []
                def refused(*args):
                    calls.append(args)
                    raise ValueError('original fixture refusal')
                descriptor = CaptureSessionProducer(
                    journal_fd, str(journal), capture_fd, str(captures), refused)
                with self.assertRaises(CaptureSessionStopped) as first:
                    descriptor.capture(('/synthetic/cache',), 123.0, 4096)
                owner = CaptureFinalizer(self.owner.process_session, descriptor, self.carrier)
                with self.assertRaises(FinalizationRetained) as caught:
                    owner.finish(process_used=False, descriptor_used=False,
                                 persist=self.persist, close_directories=self.close,
                                 original_failure=first.exception)
                self.assertEqual(len(calls), 1)
                self.assertIs(caught.exception.finalization_failure, first.exception)
                self.assertIs(owner.descriptor_session, descriptor)
                self.assertNotIn('close', self.events)
                self.assertNotIn('CAPTURE-FINALIZED.json', self.events)
                self.assertTrue(os.listdir(journal_fd))  # INTENT was durable.
                os.fstat(journal_fd)
                os.fstat(capture_fd)
            finally:
                # These fixture-owned borrowed descriptors never moved to a
                # child; finalizer was proved not to invoke the close callback.
                os.close(capture_fd)
                os.close(journal_fd)


if __name__ == '__main__':
    unittest.main()
