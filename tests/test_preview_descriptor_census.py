import hashlib
import unittest

from scripts.preview_pipeline.descriptor_census import parse


ROOTS = ('/synthetic/previews', '/synthetic/catalog')


def fields(pid=7, name='/unrelated/library', kind='REG'):
    return f'p{pid}\ncoriginal\nf3\nt{kind}\nn{name}\n'.encode()


class DescriptorCensusTests(unittest.TestCase):
    def test_large_complete_listing_keeps_late_protected_descriptor(self):
        unrelated = fields(name='/unrelated/' + 'x' * 1000)
        tail = fields(19, '/synthetic/previews/key/image')
        count = 17000
        census = parse(iter([unrelated] * count + [tail]), ROOTS)
        self.assertGreater(census.input_bytes, 16 * 1024 * 1024)
        self.assertEqual(census.named_count, count + 1)
        self.assertEqual(census.process_ids, (7, 19))
        self.assertEqual([(r.pid, r.descriptor, r.kind, r.name)
                          for r in census.protected],
                         [(19, '3', 'REG', '/synthetic/previews/key/image')])
        self.assertEqual(census.input_sha256,
                         hashlib.sha256(unrelated * count + tail).hexdigest())
        self.assertIn(tail.split(b'\n', 2)[2], census.legacy_fields())
        self.assertLess(len(census.legacy_fields()), 1024)

    def test_chunk_boundaries_and_unicode_do_not_change_projection(self):
        raw = fields(name='/synthetic/previews/é') + fields(8, '/elsewhere')
        expected = parse([raw], ROOTS)
        for step in (1, 2, 7, 31):
            actual = parse((raw[i:i+step] for i in range(0, len(raw), step)), ROOTS)
            self.assertEqual(actual, expected)

    def test_literal_root_boundary_and_real_name_witness(self):
        raw = fields(name='/synthetic/previews-other/file')
        census = parse([raw], ROOTS)
        self.assertEqual(census.protected, ())
        self.assertIn(b'n/synthetic/previews-other/file\n', census.legacy_fields())
        self.assertNotIn(b'nonprotected', census.legacy_fields())

    def test_preserves_foreign_pid_unknown_kind_and_all_matching_records(self):
        raw = (b'p8\ncforeign\nfmem\nn/synthetic/catalog\n'
               b'f4\ntREG\nn/synthetic/previews/key\n'
               b'p9\ncother\nf5\ntDIR\nn/synthetic/previews\n')
        census = parse([raw], ROOTS)
        self.assertEqual([r.pid for r in census.protected], [8, 8, 9])
        self.assertIsNone(census.protected[0].kind)
        self.assertEqual(parse([census.legacy_fields()], ROOTS).protected,
                         census.protected)

    def test_refuses_incomplete_malformed_and_unrequested_fields(self):
        cases = [fields()[:-1], b'n/no-context\n', b'f3\n', b'p0\n',
                 b'p\xd9\xa7\n', b'p1\nf\nn/x\n', b'p1\nf1\ntREG\nn\n',
                 fields() + b'Xignored\n', fields() + b'n\xff\n',
                 fields() + b'n/hidden\x00name\n', fields() + b'\n']
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse([raw], ROOTS)

    def test_unnamed_pipe_does_not_supply_nonempty_witness(self):
        pipe = b'p1\ncpipe\nf3\ntPIPE\nn\n'
        with self.assertRaises(ValueError):
            parse([pipe], ROOTS)
        self.assertEqual(parse([pipe, fields(2)], ROOTS).named_count, 1)

    def test_every_resource_bound_fails_closed(self):
        raw = fields(name='/synthetic/previews/file')
        for kwargs in (dict(maximum_bytes=8), dict(maximum_line_bytes=8),
                       dict(maximum_fields=2)):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                parse([raw], ROOTS, **kwargs)
        with self.assertRaises(ValueError):
            parse([raw, raw], ROOTS, maximum_matches=1)
        with self.assertRaises(ValueError):
            parse([raw, fields(2)], ROOTS, maximum_processes=1)
        with self.assertRaises(ValueError):
            parse([raw], ROOTS).legacy_fields(maximum_bytes=8)

    def test_rejects_ambiguous_roots_chunks_and_limits(self):
        for roots in ((), ['/x'], ('/',), ('/x/../y',), ('/x/',), ('/x', '/x')):
            with self.subTest(roots=roots), self.assertRaises(ValueError):
                parse([fields()], roots)
        for chunks in ([b''], ['text'], [b'x' * (1024 * 1024 + 1)]):
            with self.assertRaises(ValueError):
                parse(chunks, ROOTS)
        with self.assertRaises(ValueError):
            parse([fields()], ROOTS, maximum_bytes=True)


if __name__ == '__main__':
    unittest.main()
