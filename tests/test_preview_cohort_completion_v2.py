import copy
import unittest

from scripts.preview_pipeline import cohort_completion_v2 as m
from test_preview_cohort_completion import fixture as legacy_fixture, wait


def pin(name):
    return dict(path='/synthetic/' + name, bytes=10, sha256='a' * 64)


def fixture():
    return dict(schema=m.SCHEMA, mode=m.MODE, cohortSession='a' * 32,
                rootWait=wait(100), resourcesClosed=True, closedMainEpochId='e' * 32,
                normalClose=dict(normalQuitSubmittedOnce=True, forceTerminationUsed=False,
                                 classicProcessesAbsent=True, previousPID=300,
                                 previousStart='synthetic Classic start', backupPolicyChanged=False),
                normalCloseEvidence=pin('normal-close'), closedMainGateEvidence=pin('reader-gate'),
                nativeResultEvidence=pin('native-result'), helperWaits=[wait(400), wait(500)],
                allHelpersSettled=True, originalReadersClosed=True,
                closedMainEpochGuardClosed=True, classicReopened=False, startupVerified=False,
                finalStartupRequired=True, closedMainObservationScope=m.SCOPE)


class ClosedNativeWindowTests(unittest.TestCase):
    def test_native_ready_does_not_claim_final_startup_or_publication(self):
        result = m.validate(fixture(), wait(200))
        self.assertTrue(result['nativeOwnerSucceeded'])
        self.assertTrue(result['finalStartupStillRequired'])
        for name in ('startupVerified', 'publicationAuthorized', 'resourceReleaseAuthority',
                     'renderReplayAllowed'):
            self.assertFalse(result[name])

    def test_legacy_outcomes_are_preserved_byte_for_byte_as_data(self):
        for recovered in (False, True):
            value = legacy_fixture(recovered)
            original = copy.deepcopy(value)
            self.assertEqual(m.validate(value, wait(200)), m.legacy.validate(value, wait(200)))
            self.assertEqual(value, original)

    def test_incomplete_or_untrue_close_views_refuse(self):
        for kind in ('native', 'root', 'helper', 'missing_helper', 'force', 'backup',
                     'resource', 'reader', 'startup', 'final_startup', 'atomic', 'extra'):
            v, native = fixture(), wait(200)
            if kind == 'native': native['returncode'] = 1
            elif kind == 'root': v['rootWait']['returncode'] = 1
            elif kind == 'helper': v['helperWaits'][0]['other_group_members_absent_before_reap'] = None
            elif kind == 'missing_helper': v['helperWaits'].pop()
            elif kind == 'force': v['normalClose']['forceTerminationUsed'] = True
            elif kind == 'backup': v['normalClose']['backupPolicyChanged'] = True
            elif kind == 'resource': v['resourcesClosed'] = False
            elif kind == 'reader': v['originalReadersClosed'] = False
            elif kind == 'startup': v['startupVerified'] = True
            elif kind == 'final_startup': v['finalStartupRequired'] = False
            elif kind == 'atomic': v['closedMainObservationScope'] = 'ABSOLUTE_OS_SILENCE'
            else: v['unreviewedAuthority'] = True
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                m.validate(v, native)

    def test_pid_aliases_and_duplicate_helpers_refuse(self):
        for kind in ('root', 'classic', 'helper'):
            v = fixture()
            if kind == 'root': v['rootWait'] = wait(200)
            elif kind == 'classic': v['normalClose']['previousPID'] = 200
            else: v['helperWaits'][1] = copy.deepcopy(v['helperWaits'][0])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                m.validate(v, wait(200))


if __name__ == '__main__':
    unittest.main()
