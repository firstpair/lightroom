import hashlib
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.preview_pipeline.preentry_refusal import RefusalPolicy, prove_refusal


class RefusalControls(unittest.TestCase):
    source = b'original synthetic helper; lock refusal precedes dispatch'
    old = b'Traceback: /fixture/old/helper.py: lock busy before dispatch\n'
    canonical = b'Traceback: /fixture/checkout/helper.py: lock busy before dispatch\n'

    def fixture(self):
        return dict(actual=dict(returncode=1, reaped=True,
                                other_group_members_absent_before_reap=True,
                                timed_out=False), stdout=b'', stderr=self.old,
                    callback_present=False, helper_live=False,
                    helper_bytes=self.source,
                    policy=RefusalPolicy(hashlib.sha256(self.source).hexdigest(),
                                         (self.old, self.canonical)))

    def test_both_exact_diagnostics_keep_distinct_evidence(self):
        observed = []
        for diagnostic in (self.old, self.canonical):
            values = self.fixture(); values['stderr'] = diagnostic
            proof = prove_refusal(**values)
            self.assertFalse(proof['retryAuthorized'])
            self.assertFalse(proof['callbackDispatched'])
            observed.append(proof['matchedDiagnosticSha256'])
            self.assertEqual(values['stderr'], diagnostic)
        self.assertNotEqual(*observed)

    def test_absence_or_success_is_not_refusal_proof(self):
        for field, value in [('stderr', b''), ('stderr', b'foreign traceback'),
                             ('stdout', b'operation started'),
                             ('callback_present', True), ('helper_live', True),
                             ('helper_bytes', self.source + b'changed')]:
            values = self.fixture(); values[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                prove_refusal(**values)

    def test_every_actual_settlement_condition_required(self):
        for field, value in [('returncode', 0), ('returncode', True),
                             ('reaped', False),
                             ('other_group_members_absent_before_reap', False),
                             ('timed_out', True)]:
            values = self.fixture(); values['actual'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                prove_refusal(**values)
        values = self.fixture(); del values['actual']['reaped']
        with self.assertRaises(ValueError): prove_refusal(**values)

    def test_close_enough_diagnostics_do_not_match(self):
        for diagnostic in (self.old + b'additional output', self.old.rstrip(),
                           self.old.replace(b'/old/', b'/foreign/')):
            values = self.fixture(); values['stderr'] = diagnostic
            with self.subTest(diagnostic=diagnostic), self.assertRaises(ValueError):
                prove_refusal(**values)

    def test_invalid_policy_refused(self):
        digest = hashlib.sha256(self.source).hexdigest()
        for value in ((), (b'',), (self.old, self.old), [self.old],
                      (b'x' * 65537,), (self.old,) * 5):
            with self.subTest(value_type=type(value)), self.assertRaises(ValueError):
                RefusalPolicy(digest, value)
        with self.assertRaises(ValueError): RefusalPolicy('unreviewed', (self.old,))


if __name__ == '__main__': unittest.main()
