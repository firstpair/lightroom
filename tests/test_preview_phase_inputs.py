import copy
from pathlib import Path
import tempfile
import unittest

from scripts.preview_pipeline.phase_inputs import read_claim_inputs
from scripts.preview_pipeline.work_queue import Queue


def pin(name):
    return dict(path='/synthetic/' + name, bytes=10, sha256='a' * 64)


class PhaseInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name).resolve() / 'queue.sqlite'
        self.q = Queue(self.path, create=True)
        self.records = [dict(key='key-%d' % i, source=pin('job-%d' % i)) for i in range(8)]
        self.q.enqueue(self.records)

    def tearDown(self):
        self.q.close()
        self.temp.cleanup()

    def test_render_has_no_prior_and_stage_retains_exact_receipt_across_reopen(self):
        render = self.q.claim('render')
        self.assertTrue(all(r['prior'] is None for r in read_claim_inputs(self.q, render)))
        proof = pin('actual-native-result')
        self.q.finish(render['id'], proof)
        stage = self.q.claim('stage')
        self.q.close()
        self.q = Queue(self.path)
        inputs = read_claim_inputs(self.q, stage)
        self.assertEqual([r['prior'] for r in inputs], [proof] * 8)
        self.assertEqual([dict(key=r['key'], source=r['source']) for r in inputs], self.records)

    def test_changed_order_source_or_phase_refuses(self):
        claim = self.q.claim('render')
        for kind in ('order', 'source', 'phase'):
            wrong = copy.deepcopy(claim)
            if kind == 'order':
                wrong['records'].reverse()
            elif kind == 'source':
                wrong['records'][0]['source'] = pin('foreign')
            else:
                wrong['phase'] = 'stage'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                read_claim_inputs(self.q, wrong)

    def test_held_claim_does_not_authorize_a_new_phase(self):
        claim = self.q.claim('render')
        self.q.hold(claim['id'], pin('failure'))
        with self.assertRaises(ValueError):
            read_claim_inputs(self.q, claim)

    def test_missing_stage_receipt_refuses(self):
        render = self.q.claim('render')
        self.q.finish(render['id'], pin('native'))
        stage = self.q.claim('stage')
        self.q.db.execute('UPDATE jobs SET proof=NULL WHERE key=?', ('key-0',))
        self.q.db.commit()
        with self.assertRaises(ValueError):
            read_claim_inputs(self.q, stage)

    def test_input_lookup_uses_primary_key_and_keeps_borrowed_connection_open(self):
        claim = self.q.claim('render')
        read_claim_inputs(self.q, claim)
        plan = self.q.db.execute('EXPLAIN QUERY PLAN SELECT source,state,claim,proof '
                                 'FROM jobs WHERE key=?', ('key-0',)).fetchall()
        self.assertTrue(all('SEARCH' in r[-1] and 'SCAN' not in r[-1] for r in plan))
        self.assertEqual(self.q.db.execute('SELECT count(*) FROM jobs').fetchone()[0], 8)


if __name__ == '__main__':
    unittest.main()
