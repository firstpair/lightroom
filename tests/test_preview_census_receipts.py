import hashlib
import stat
import unittest

from scripts.preview_pipeline.census_receipts import check_reported_capture
from scripts.preview_pipeline.descriptor_census import parse

ROOTS = ('/synthetic/cache', '/synthetic/catalog', '/synthetic/catalog-wal')
RAW = b'p123\ncworker\nf2\ntREG\nn/synthetic/cache/image\np777\nclsof\nf1\ntREG\nn/synthetic/control\n'


def fixture(raw=RAW):
    census = parse([raw], ROOTS)
    projected = census.legacy_fields()
    return {
        'state': 'COMPLETE_GLOBAL_CENSUS_PROJECTED_CHILD_GROUP_FDS_CLOSED',
        'command': ['/usr/sbin/lsof', '-nP', '-Fpcftn'],
        'actual': {'pid': 777, 'returncode': 0, 'reaped': True,
                   'other_group_members_absent_before_reap': True,
                   'members_before_reap': [{'pid': 777, 'state': 'Z'}],
                   'timed_out': False, 'signals_sent': 0},
        'raw': {'path': '/synthetic/capture/stdout', 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(),
                'identity8': [1, 2, len(raw), 3, 4, stat.S_IFREG | 0o600, 501, 1]},
        'projection': {'bytes': len(projected), 'sha256': hashlib.sha256(projected).hexdigest()},
        'process_count': len(census.process_ids), 'named_count': census.named_count,
        'protected_count': len(census.protected), 'owned_fds_closed': True,
        'caller_grants_released': False, 'signals_sent': 0,
    }


class CaptureReceiptTests(unittest.TestCase):
    def check(self, value, raw=RAW, **kwargs):
        return check_reported_capture(value, [raw[:11], raw[11:]], ROOTS, **kwargs)

    def test_complete_capture_keeps_foreign_descriptor_and_no_authority(self):
        result = self.check(fixture(), ancestor_pids=(100, 200))
        self.assertFalse(result.resource_release_authorized)
        self.assertEqual(result.census.protected[0].pid, 123)
        self.assertEqual(result.census.protected[0].name, '/synthetic/cache/image')
        self.assertEqual(result.raw_identity8, tuple(fixture()['raw']['identity8']))

    def test_result_cannot_be_constructed_with_release_authority(self):
        result = self.check(fixture())
        with self.assertRaises(TypeError):
            type(result)(result.census, result.reported_child_pid, result.raw_identity8,
                         result.projection, resource_release_authorized=True)

    def test_unprotected_capture_still_needs_real_name_witness(self):
        raw = RAW.replace(b'/synthetic/cache/image', b'/synthetic/unrelated')
        result = self.check(fixture(raw), raw)
        self.assertFalse(result.census.protected)
        self.assertIn(b'n/synthetic/unrelated\n', result.projection)

    def test_hashes_bind_full_raw_stream_not_only_projection(self):
        raw = RAW.replace(b'/synthetic/control', b'/synthetic/changed')
        with self.assertRaisesRegex(ValueError, 'RAW_CONTENT'):
            self.check(fixture(), raw)

    def test_projection_substitution_and_counter_forgery_rejected(self):
        for key, value in [('process_count', 1), ('named_count', 1), ('protected_count', 0)]:
            with self.subTest(key=key):
                changed = fixture(); changed[key] = value
                with self.assertRaises(ValueError): self.check(changed)
        for key, value in [('bytes', 1), ('sha256', '0' * 64)]:
            changed = fixture(); changed['projection'][key] = value
            with self.assertRaises(ValueError): self.check(changed)

    def test_wait_group_signal_and_fd_claims_must_be_exact(self):
        mutations = [('returncode', 1), ('returncode', False), ('reaped', False),
                     ('timed_out', True), ('other_group_members_absent_before_reap', False),
                     ('signals_sent', 9)]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                changed = fixture(); changed['actual'][key] = value
                with self.assertRaises(ValueError): self.check(changed)
        for key, value in [('owned_fds_closed', False), ('caller_grants_released', True),
                           ('signals_sent', 1)]:
            changed = fixture(); changed[key] = value
            with self.assertRaises(ValueError): self.check(changed)

    def test_leader_ancestor_alias_or_other_group_member_rejected(self):
        with self.assertRaises(ValueError): self.check(fixture(), ancestor_pids=(777,))
        for rows in ([], [{'pid': 777, 'state': 'R'}], [{'pid': 777, 'state': 'Z\n'}],
                     [{'pid': 123, 'state': 'Z'}],
                     [{'pid': 777, 'state': 'Z'}, {'pid': 778, 'state': 'Z'}]):
            changed = fixture(); changed['actual']['members_before_reap'] = rows
            with self.assertRaises(ValueError): self.check(changed)

    def test_raw_epoch_mode_link_and_label_reports_are_constrained(self):
        for index, value in [(0, 0), (1, 0), (2, 1), (3, True),
                             (5, stat.S_IFREG | 0o644), (7, 2)]:
            changed = fixture(); changed['raw']['identity8'][index] = value
            with self.assertRaises(ValueError): self.check(changed)
        changed = fixture(); changed['raw']['path'] = '/synthetic/../capture'
        with self.assertRaises(ValueError): self.check(changed)

    def test_failed_command_unknown_fields_and_missing_proof_rejected(self):
        for change in ('missing', 'extra', 'wrong-command', 'failed-state'):
            changed = fixture()
            if change == 'missing': del changed['actual']
            if change == 'extra': changed['release'] = True
            if change == 'wrong-command': changed['command'] = ['/usr/bin/true']
            if change == 'failed-state': changed['state'] = 'CENSUS_COMMAND_FAILED_CHILD_GROUP_FDS_CLOSED'
            with self.assertRaises(ValueError): self.check(changed)


if __name__ == '__main__':
    unittest.main()
