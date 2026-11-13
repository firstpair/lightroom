from pathlib import Path
import tempfile
import unittest

from scripts.preview_pipeline.phase_controller import (
    Controller, ControllerOwnershipUnknown, Outcome, PhaseFailed, PHASES, RETAINED)
from scripts.preview_pipeline.work_queue import Queue, UnsettledBatch


def pin(name='synthetic'):
    return dict(path='/synthetic/' + name, bytes=10, sha256='a' * 64)


def wait(code=0):
    return dict(pid=100, returncode=code, reaped=True,
                other_group_members_absent_before_reap=True,
                members_before_reap=[dict(pid=100, state='Z')], timed_out=False,
                scope='owned group only; separate sessions require independently audited proofs')


class Adapter:
    def __init__(self, phase, events):
        self.phase, self.events = phase, events
        self.result = Outcome(pin(phase), wait(), True)
        self.authenticated = True
        self.error = None
        self.claims = []
        self.owner = object()

    def execute(self, claim):
        self.events.append(self.phase)
        self.claims.append(claim)
        if self.error:
            raise self.error
        return self.result

    def authenticate(self, claim, outcome):
        return self.authenticated


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name).resolve() / 'queue.sqlite'
        self.q = Queue(self.path, create=True)
        self.events = []
        self.adapters = {p: Adapter(p, self.events) for p in PHASES}
        self.c = Controller(self.q, self.adapters)

    def tearDown(self):
        # These fixtures own only disposable SQLite files, no native processes.
        # Explicit test cleanup does not model a production unknown-owner release.
        self.q.close()
        RETAINED.clear()
        self.temp.cleanup()

    def enqueue(self, n, state='PENDING'):
        self.q.enqueue([dict(key='key-%d' % i, source=pin()) for i in range(n)],
                       state=state, adoption=pin('adoption') if state != 'PENDING' else None)

    def test_two_windows_finish_downstream_before_second_render(self):
        self.enqueue(16)
        result = self.c.drain()
        self.assertEqual(self.events, ['render', 'stage', 'publish', 'recognize'] * 2)
        self.assertEqual(result['completed'], 16)
        self.assertEqual(self.q.counts(), {'COMPLETE': 16})

    def test_ten_thousand_metadata_jobs_run_without_phase_or_record_replay(self):
        self.enqueue(10000)
        result = self.c.drain()
        self.assertEqual(result, dict(actions=5000, completed=10000, stopped_at_bound=True))
        for adapter in self.adapters.values():
            keys = [r['key'] for c in adapter.claims for r in c['records']]
            self.assertEqual(len(keys), 10000)
            self.assertEqual(len(set(keys)), 10000)
            self.assertTrue(all(len(c['records']) == 8 for c in adapter.claims))
        self.assertEqual(self.q.counts(), {'COMPLETE': 10000})

    def test_saved_native_jobs_start_at_stage(self):
        self.enqueue(8, 'NATIVE_READY')
        self.c.drain()
        self.assertEqual(self.events, ['stage', 'publish', 'recognize'])

    def test_completion_bound_does_not_overshoot(self):
        self.enqueue(16)
        result = self.c.drain(maximum_completed=3)
        self.assertEqual(result['completed'], 3)
        self.assertEqual(self.q.counts(), {'COMPLETE': 3, 'PENDING': 13})

    def test_known_closed_failure_is_held_and_never_replayed_after_restart(self):
        self.enqueue(8)
        self.adapters['render'].result = Outcome(pin('failure'), wait(1), False)
        with self.assertRaises(PhaseFailed):
            self.c.drain()
        self.q.close()
        self.q = Queue(self.path)
        with self.assertRaises(UnsettledBatch):
            Controller(self.q, self.adapters).drain()
        self.assertEqual(self.events, ['render'])

    def test_unknown_execution_retains_exact_adapter_claim_and_queue(self):
        self.enqueue(8)
        adapter = self.adapters['render']
        adapter.error = OSError('uncertain child observation')
        with self.assertRaises(ControllerOwnershipUnknown) as caught:
            self.c.advance()
        self.assertIs(caught.exception.controller, self.c)
        self.assertIs(self.c.adapter, adapter)
        self.assertIs(self.c.queue, self.q)
        self.assertIs(RETAINED[-1], self.c)
        with self.assertRaises(UnsettledBatch):
            self.c.advance()
        self.assertEqual(self.events, ['render'])

    def test_top_level_wait_without_contained_authentication_cannot_advance(self):
        self.enqueue(8)
        self.adapters['render'].authenticated = False
        with self.assertRaises(ControllerOwnershipUnknown):
            self.c.advance()
        self.assertEqual(self.q.counts(), {'PENDING': 8})

    def test_missing_or_uncertain_child_settlement_cannot_advance(self):
        self.enqueue(8)
        w = wait()
        w['other_group_members_absent_before_reap'] = None
        self.adapters['render'].result = Outcome(pin(), w, True)
        with self.assertRaises(ControllerOwnershipUnknown):
            self.c.advance()
        self.assertEqual(self.q.counts(), {'PENDING': 8})

    def test_queue_finish_error_retains_authenticated_outcome_without_relaunch(self):
        self.enqueue(8)
        def uncertain(*args):
            raise OSError('result commit not observed')
        self.q.finish = uncertain
        with self.assertRaises(ControllerOwnershipUnknown):
            self.c.advance()
        self.assertTrue(self.c.outcome.successful)
        self.assertEqual(self.events, ['render'])

    def test_execution_cannot_mutate_the_claim_given_to_authentication(self):
        self.enqueue(8)
        adapter = self.adapters['render']
        def execute(claim):
            claim['records'][0]['key'] = 'forged'
            return adapter.result
        adapter.execute = execute
        adapter.authenticate = lambda claim, outcome: claim['records'][0]['key'] == 'key-0'
        self.c.advance()
        self.assertEqual(self.q.counts(), {'NATIVE_READY': 8})


if __name__ == '__main__':
    unittest.main()
