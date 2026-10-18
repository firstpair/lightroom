import os
from pathlib import Path
from types import SimpleNamespace
import unittest

from scripts.preview_pipeline.census_adapter import JournaledCaptureBackend
from tests import test_preview_census_session as fixtures


class BackendUnknown(RuntimeError):
    def __init__(self, reason, owner):
        super().__init__(reason)
        self.owner = owner


class BackendRefusal(ValueError):
    pass


class CaptureAdapterTests(unittest.TestCase):
    """Actual tempfile journals; backend/process receipt facts are explicit doubles."""
    setUp = fixtures.CaptureSessionTests.setUp
    fake_capture = fixtures.CaptureSessionTests.fake_capture

    def adapter(self, invoke=None):
        self.calls = []
        def capture(root, roots, deadline, maximum):
            self.calls.append((root, roots, deadline, maximum))
            if invoke is not None:
                return invoke()
            return self.fake_capture(len(self.calls)-1)
        backend = SimpleNamespace(capture=capture, CaptureUnknown=BackendUnknown,
                                  CaptureRefusal=BackendRefusal)
        return JournaledCaptureBackend(backend, self.root, self.roots,
                                       self.journal_fd, str(self.journal_root),
                                       self.capture_fd, str(self.capture_root))

    def test_adapter_keeps_fixed_scope_but_routes_to_private_capture_namespace(self):
        adapter = self.adapter()
        for _ in range(2):
            adapter.capture(self.root, self.roots, 1234.0, 4096)
        reported = adapter.seal()
        self.assertEqual(self.calls, [(self.capture_root, self.roots, 1234.0, 4096)]*2)
        checked = self.check_adapter(reported)
        self.assertEqual(len(checked.captures), 2)
        self.assertFalse(checked.resource_release_authorized)
        os.fstat(self.journal_fd)
        os.fstat(self.capture_fd)

    def check_adapter(self, reported):
        from scripts.preview_pipeline.census_session import check_capture_session
        return check_capture_session(self.journal_fd, str(self.journal_root),
                                     reported['snapshot_pins'], self.capture_fd,
                                     str(self.capture_root), self.roots)

    def test_changed_scope_stops_before_any_backend_call_and_cannot_retry(self):
        for changed in ('root', 'roots'):
            with self.subTest(changed=changed):
                adapter = self.adapter()
                with self.assertRaises(BackendUnknown) as first:
                    adapter.capture(self.root/'other' if changed == 'root' else self.root,
                                    ('/other',) if changed == 'roots' else self.roots, 1, 10)
                with self.assertRaises(BackendUnknown) as second:
                    adapter.capture(self.root, self.roots, 1, 10)
                self.assertIs(first.exception, second.exception)
                self.assertEqual(self.calls, [])
                self.assertEqual(os.listdir(self.journal_fd), [])

    def test_backend_unknown_retains_actual_carrier_and_durable_intent(self):
        original = BackendUnknown('ACTUAL_CHILD_UNKNOWN', {'actual_handle': object()})
        def fail():
            raise original
        adapter = self.adapter(fail)
        with self.assertRaises(BackendUnknown) as raised:
            adapter.capture(self.root, self.roots, 1, 10)
        stopped = raised.exception.owner['original_error']
        self.assertIs(stopped.original_error.original_error, original)
        self.assertEqual(os.listdir(self.journal_fd), ['000000.json'])
        with self.assertRaises(BackendUnknown) as again:
            adapter.seal()
        self.assertIs(raised.exception, again.exception)
        self.assertEqual(len(self.calls), 1)

    def test_known_refusal_remains_unsealed_not_promoted_to_success(self):
        def fail():
            raise BackendRefusal('KNOWN_CHILD_CLOSED_BUT_NO_SUCCESS_RECEIPT')
        adapter = self.adapter(fail)
        with self.assertRaises(BackendUnknown):
            adapter.capture(self.root, self.roots, 1, 10)
        self.assertEqual(os.listdir(self.journal_fd), ['000000.json'])

    def test_double_seal_is_not_replayed_or_resource_release(self):
        adapter = self.adapter()
        adapter.capture(self.root, self.roots, 1, 10)
        reported = adapter.seal()
        with self.assertRaises(ValueError):
            adapter.seal()
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(reported['resource_release_authorized'])


if __name__ == '__main__':
    unittest.main()
