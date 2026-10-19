import unittest

from scripts.preview_pipeline.candidate_window import select_window


def row(i, key=None):
    return dict(image_id=i, key=key or (str(i), 'digest'))


class CandidateWindowTests(unittest.TestCase):
    def choose(self, rows, **options):
        args = dict(after_image_id=0, completed_keys=set(), published_keys=set(),
                    reusable_keys=set())
        args.update(options)
        return select_window(rows, **args)

    def test_ten_thousand_boundary_does_not_consume_next_row(self):
        consumed = []
        def source():
            for i in range(1, 10002):
                consumed.append(i)
                yield row(i)
        result = self.choose(source())
        self.assertEqual(consumed, list(range(1, 10001)))
        self.assertEqual(len(result['candidates']), 10000)
        self.assertFalse(result['input_exhausted'])
        self.assertFalse(result['runtime_authorized'])

    def test_published_and_reusable_are_excluded_without_completion_claim(self):
        result = self.choose([row(i) for i in range(1, 5)],
                             completed_keys={('1', 'digest')},
                             published_keys={('2', 'digest')},
                             reusable_keys={('3', 'digest')})
        self.assertEqual(result['candidates'], [row(4)])
        self.assertEqual([o['state'] for o in result['observations'][:3]], [
            'EXCLUDED_COMPLETED_KEY', 'PUBLISHED_RECOGNITION_PENDING',
            'EXCLUDED_AUTHENTICATED_REUSABLE_KEY'])
        self.assertFalse(result['full_catalog_complete'])

    def test_scan_cursor_preserves_alias_and_excluded_observations(self):
        key = ('same', 'digest')
        result = self.choose([row(1, key), row(2, key), row(3)],
                             batch_limit=3, scan_limit=3)
        self.assertEqual(len(result['candidates']), 2)
        self.assertEqual(result['observations'][1]['state'],
                         'PENDING_DUPLICATE_KEY_ALIAS')
        self.assertEqual(result['next_image_id'], 3)
        # Reaching a bound is not proof of exhaustion.
        self.assertFalse(result['input_exhausted'])

    def test_invalid_coverage_refuses_before_consuming_rows(self):
        def source():
            self.fail('invalid coverage consumed input')
            yield row(1)
        for args in (dict(published_keys={('1', 'digest')},
                          reusable_keys={('1', 'digest')}),
                     dict(published_keys={('bad',)}),
                     dict(after_image_id=True), dict(batch_limit=10001)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.choose(source(), **args)

    def test_out_of_order_and_extra_fields_refuse(self):
        for rows in ([row(2), row(1)], [dict(row(1), status='completed')]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.choose(rows)
