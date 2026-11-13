import unittest
from scripts.preview_pipeline.candidate_page import select_page


def row(i, key=None):
    return dict(image_id=i, key=key or (str(i), 'digest'))


class CandidatePageTests(unittest.TestCase):
    def test_pages_do_not_drop_boundary_rows(self):
        source = [row(i) for i in range(1, 104)]
        completed = {('3', 'digest'), ('40', 'digest')}
        cursor, selected, observed = 0, [], []
        while True:
            page = select_page((r for r in source if r['image_id'] > cursor),
                               after_image_id=cursor, completed_keys=completed, batch_limit=7)
            selected.extend(r['key'] for r in page['candidates'])
            observed.extend(r['image_id'] for r in page['observations'])
            cursor = page['next_image_id']
            self.assertFalse(page['runtime_authorized'])
            self.assertFalse(page['full_catalog_complete'])
            if page['input_exhausted']:
                break
        self.assertEqual(observed, list(range(1, 104)))
        self.assertEqual(selected, [r['key'] for r in source if r['key'] not in completed])

    def test_scan_bound_preserves_pending_aliases(self):
        key = ('same', 'digest')
        page = select_page((row(i, key) for i in range(1, 10000)),
                           after_image_id=0, completed_keys=set(), batch_limit=2, scan_limit=8)
        self.assertEqual(len(page['candidates']), 1)
        self.assertEqual(page['next_image_id'], 8)
        self.assertEqual(sum(r['state'] == 'PENDING_DUPLICATE_KEY_ALIAS'
                             for r in page['observations']), 7)
        self.assertFalse(page['input_exhausted'])

    def test_does_not_pull_past_selected_boundary(self):
        def source():
            yield row(1)
            raise AssertionError('unconsumed row pulled')
        page = select_page(source(), after_image_id=0, completed_keys=set(), batch_limit=1)
        self.assertEqual(page['next_image_id'], 1)
        self.assertFalse(page['input_exhausted'])

    def test_all_excluded_still_advances_observed_cursor(self):
        page = select_page([row(10)], after_image_id=9, completed_keys={('10', 'digest')})
        self.assertEqual(page['candidates'], [])
        self.assertEqual(page['observations'][0]['state'], 'EXCLUDED_COMPLETED_KEY')
        self.assertEqual(page['next_image_id'], 10)
        self.assertTrue(page['input_exhausted'])

    def test_refuses_stale_or_ambiguous_input(self):
        for source in ([row(4)], [row(6), row(6)], [row(7), row(6)],
                       [dict(image_id=True, key=('a', 'b'))], [dict(image_id=6, key=('a', ''))]):
            with self.subTest(source=source), self.assertRaises(ValueError):
                select_page(source, after_image_id=4, completed_keys=set())

    def test_refuses_unbounded_or_untyped_contract(self):
        for kwargs in [dict(after_image_id=True), dict(batch_limit=33),
                       dict(scan_limit=513), dict(batch_limit=8, scan_limit=7),
                       dict(completed_keys=[('a', 'b')])]:
            options = dict(after_image_id=0, completed_keys=set())
            options.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                select_page([], **options)


if __name__ == '__main__':
    unittest.main()
