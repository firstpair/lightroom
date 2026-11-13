from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import tempfile
from threading import Barrier
import unittest

from scripts.preview_pipeline.work_queue import Queue, UnsettledBatch


def receipt(name='source'):
    return dict(path='/synthetic/' + name, bytes=20, sha256='a' * 64)


def records(n):
    return [dict(key='synthetic-key-%d' % i, source=receipt()) for i in range(n)]


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name).resolve() / 'queue.sqlite'
        self.q = Queue(self.path, create=True)

    def tearDown(self):
        self.q.close()
        self.temp.cleanup()

    def test_ten_thousand_input_batch_is_durable_and_native_claim_stays_eight(self):
        self.q.enqueue(records(10000))
        self.assertEqual(self.q.counts(), {'PENDING': 10000})
        claim = self.q.claim('render')
        self.assertEqual(len(claim['records']), 8)
        self.q.close()
        self.q = Queue(self.path)
        with self.assertRaises(UnsettledBatch):
            self.q.claim('render')
        self.q.hold(claim['id'], receipt('independent-failure-audit'))
        with self.assertRaises(ValueError):
            self.q.finish(claim['id'], receipt('wrong-normal-result'))
        self.q.finish(claim['id'], receipt('audited-recovery'), recovered=True)
        self.assertEqual(self.q.counts(), {'NATIVE_READY': 8, 'PENDING': 9992})
        stage = self.q.claim('stage')
        self.assertEqual(stage['records'], claim['records'])

    def test_success_advances_all_phases_without_rerender(self):
        self.q.enqueue(records(8))
        for phase, expected in [('render', 'NATIVE_READY'), ('stage', 'STAGED'),
                                ('publish', 'PUBLISHED'), ('recognize', 'COMPLETE')]:
            claim = self.q.claim(phase)
            self.q.finish(claim['id'], receipt(phase))
            with self.assertRaises(ValueError):
                self.q.finish(claim['id'], receipt('duplicate'))
            self.assertEqual(self.q.counts(), {expected: 8})
        self.assertIsNone(self.q.claim('render'))

    def test_duplicate_keys_roll_back_entire_enqueue(self):
        self.q.enqueue(records(2))
        with self.assertRaises(sqlite3.IntegrityError):
            self.q.enqueue([dict(key='new-key', source=receipt()), records(1)[0]])
        self.assertEqual(self.q.counts(), {'PENDING': 2})

    def test_two_coordinators_cannot_claim_same_or_parallel_work(self):
        self.q.enqueue(records(16))
        other = Queue(self.path)
        try:
            first = self.q.claim('render')
            with self.assertRaises(UnsettledBatch):
                other.claim('render')
            self.q.finish(first['id'], receipt('render'))
            second = other.claim('render')
            self.assertFalse({r['key'] for r in first['records']} &
                             {r['key'] for r in second['records']})
        finally:
            other.close()

    def test_saved_native_results_require_adoption_and_skip_render(self):
        with self.assertRaises(ValueError):
            self.q.enqueue(records(8), state='NATIVE_READY')
        self.q.enqueue(records(8), state='NATIVE_READY', adoption=receipt('qualified-native-result'))
        self.assertIsNone(self.q.claim('render'))
        self.assertEqual(len(self.q.claim('stage')['records']), 8)

    def test_simultaneous_claims_have_one_winner(self):
        self.q.enqueue(records(16))
        gate = Barrier(2)
        def compete():
            queue = Queue(self.path)
            try:
                gate.wait(timeout=5)
                try:
                    return queue.claim('render')
                except UnsettledBatch:
                    return None
            finally:
                queue.close()
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: compete(), range(2)))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(len(next(r for r in results if r)['records']), 8)

    def test_unrecognized_or_oversized_input_refuses_before_writes(self):
        for phase, limit in [('render', 9), ('render', True), ('arbitrary', 8)]:
            with self.assertRaises(ValueError):
                self.q.claim(phase, limit=limit)
        with self.assertRaises(ValueError):
            self.q.enqueue(records(10001))
        self.assertEqual(self.q.counts(), {})
