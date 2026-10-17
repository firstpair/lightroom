from copy import deepcopy
from types import SimpleNamespace
import unittest

from scripts.preview_pipeline.census_journal import (
    CaptureAttempts, CaptureAttemptUnknown, check_sealed_inventory,
)

PIN = dict(path='/synthetic/capture/RESULT.json', bytes=100, sha256='a' * 64)
RESPONSE = (0, b'original projection', b'', PIN)


class CaptureJournalTests(unittest.TestCase):
    def journal(self):
        saved = []
        journal = CaptureAttempts(lambda value: saved.append(value))
        return journal, saved

    def check(self, journal, pins=None, projections=None):
        return check_sealed_inventory(journal, [PIN] if pins is None else pins,
            (SimpleNamespace(projection=RESPONSE[1]),) if projections is None else projections)

    def test_intent_precedes_call_outcome_precedes_return_and_seal(self):
        journal, saved = self.journal()
        def invoke():
            self.assertEqual(saved[-1]['state'], 'INTENT')
            self.assertEqual(saved[-1]['attempts'][0]['state'], 'INTENT')
            return RESPONSE
        self.assertEqual(journal.capture(invoke), RESPONSE)
        self.assertEqual(saved[-1]['state'], 'OUTCOME')
        sealed = journal.seal()
        self.assertEqual(saved[-1], sealed)
        self.assertEqual(self.check(sealed), (PIN,))
        self.assertFalse(sealed['resource_release_authorized'])
        with self.assertRaises(ValueError): journal.capture(invoke)

    def test_intent_persist_failure_never_invokes_and_prevents_retry(self):
        calls = []
        def failing(value): raise OSError('intent persist')
        journal = CaptureAttempts(failing)
        with self.assertRaises(OSError): journal.capture(lambda: calls.append(True))
        self.assertFalse(calls)
        with self.assertRaises(ValueError): journal.capture(lambda: calls.append(True))
        with self.assertRaises(ValueError): journal.seal()

    def test_invocation_failure_preserves_pending_attempt_and_original(self):
        journal, saved = self.journal()
        original = RuntimeError('child may exist')
        def invoke(): raise original
        with self.assertRaises(CaptureAttemptUnknown) as caught: journal.capture(invoke)
        self.assertIs(caught.exception.original_error, original)
        self.assertIs(caught.exception.__cause__, original)
        self.assertEqual(caught.exception.journal['state'], 'UNKNOWN')
        self.assertEqual(saved[-1]['state'], 'INTENT')
        with self.assertRaises(ValueError): journal.seal()

    def test_outcome_and_seal_persist_failure_never_replays(self):
        for fail_state in ('OUTCOME', 'SEALED'):
            with self.subTest(state=fail_state):
                calls = []
                def persist(value):
                    if value['state'] == fail_state: raise OSError(fail_state)
                journal = CaptureAttempts(persist)
                def invoke(): calls.append(True); return RESPONSE
                with self.assertRaises(CaptureAttemptUnknown):
                    journal.capture(invoke)
                    journal.seal()
                self.assertEqual(len(calls), 1)
                with self.assertRaises(ValueError): journal.capture(invoke)
                self.assertEqual(len(calls), 1)

    def test_failed_command_or_malformed_success_is_unknown(self):
        for response in ((1, b'', b'error', PIN), (0, b'', b'', PIN),
                         (False, RESPONSE[1], b'', PIN), (0, RESPONSE[1], b'', {}), None):
            with self.subTest(response=response):
                journal, saved = self.journal()
                with self.assertRaises(CaptureAttemptUnknown):
                    journal.capture(lambda: response)
                self.assertEqual(saved[-1]['state'], 'INTENT')
                with self.assertRaises(ValueError): journal.seal()

    def test_persistence_cannot_mutate_internal_inventory_and_reentry_refused(self):
        def persist(value):
            value['attempts'].clear()
            with self.assertRaises(ValueError): journal.capture(lambda: RESPONSE)
        journal = CaptureAttempts(persist)
        journal.capture(lambda: RESPONSE)
        self.assertEqual(len(journal.seal()['attempts']), 1)

    def test_count_order_pin_and_projection_substitutions_rejected(self):
        journal, _ = self.journal(); journal.capture(lambda: RESPONSE); sealed = journal.seal()
        changes = [dict(state='OPEN'), dict(resource_release_authorized=True), dict(attempts=[])]
        for fields in changes:
            changed = deepcopy(sealed); changed.update(fields)
            with self.assertRaises(ValueError): self.check(changed)
        for key, value in [('index', True), ('state', 'INTENT'), ('command', ['other']),
                           ('receipt', dict(PIN, sha256='b' * 64)), ('projected_bytes', 1),
                           ('projected_sha256', 'b' * 64)]:
            changed = deepcopy(sealed); changed['attempts'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(changed)
        with self.assertRaises(ValueError): self.check(sealed, pins=[])
        with self.assertRaises(ValueError): self.check(sealed, projections=())

    def test_bounded_attempts_and_duplicate_receipts(self):
        journal = CaptureAttempts(lambda value: None, maximum=1)
        journal.capture(lambda: RESPONSE)
        with self.assertRaises(ValueError): journal.capture(lambda: RESPONSE)
        journal, _ = self.journal()
        journal.capture(lambda: RESPONSE); journal.capture(lambda: RESPONSE)
        with self.assertRaisesRegex(ValueError, 'JOURNAL_PIN'):
            self.check(journal.seal(), pins=[PIN, PIN],
                       projections=(SimpleNamespace(projection=RESPONSE[1]),) * 2)
        empty, _ = self.journal()
        with self.assertRaises(ValueError): empty.seal()


if __name__ == '__main__':
    unittest.main()
