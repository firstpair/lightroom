import copy
import unittest

from scripts.preview_pipeline import cohort_completion as policy


def wait(pid):
    return dict(pid=pid, returncode=0, reaped=True,
                other_group_members_absent_before_reap=True, timed_out=False,
                members_before_reap=[dict(pid=pid, state='Z')],
                scope='owned group only; separate sessions require independently audited proofs')


def terminal(session, code):
    return dict(session=session, initialChunk='abcdef', terminalChunk='123456',
                exitCode=code, noRunningSession=True)


def fixture(recovered=False):
    value = dict(schema=policy.SCHEMA, cohortSession='a' * 32,
                 mode='DIRECT_CHILD', rootWait=wait(100), resourcesClosed=True,
                 startup=dict(pid=300, start='bounded process start',
                              allSevenStartupPhasesVerified=True))
    if recovered:
        value.pop('rootWait')
        value.pop('resourcesClosed')
        value.update(mode='RECOVERED_IDLE_TOOL_ROOT',
                     originalTerminal=terminal(1, 137),
                     startupTerminal=terminal(2, 0), startupHelperWait=wait(400),
                     idleStop=dict(onlySignaledPID=100, directChildren=[], rootGroup=[100],
                                   onlyOpenRegularDescriptorsAreTenCanonicalLeases=True,
                                   originalReadersClosed=True, watcherAlreadyClosed=True,
                                   noClassicNativeWorkerGroupSignals=True,
                                   originalRootNormalExitNotClaimed=True,
                                   preservedClassicPID=300),
                     recoveryClosure=dict(freshEXglobalThenPhoto8ThenUIAcquiredAndClosed=True,
                                          noChildrenLaunchedByProbe=True,
                                          originalOwnerSuccessNotClaimed=True,
                                          nativeSignals=False, ClassicPreservedPID=300,
                                          originalRetentionPreserved=True, renderReplay=False))
    return value


class CompletionTests(unittest.TestCase):
    def test_direct_child_does_not_need_tool_session(self):
        value = fixture()
        before = copy.deepcopy(value)
        result = policy.validate(value, wait(200))
        self.assertEqual(value, before)
        self.assertTrue(result['originalRootSucceeded'])
        self.assertFalse(result['resourceReleaseAuthority'])

    def test_recovery_preserves_original_failure(self):
        result = policy.validate(fixture(True), wait(200))
        self.assertEqual(result['originalRootExitCode'], 137)
        self.assertFalse(result['originalRootSucceeded'])
        self.assertFalse(result['renderReplayAllowed'])
        self.assertTrue(result['fullNativeProofStillRequired'])

    def test_unknown_or_failed_child_cannot_advance(self):
        for key, replacement in [('returncode', 1), ('returncode', False),
                                 ('reaped', False), ('timed_out', True),
                                 ('members_before_reap', []),
                                 ('members_before_reap', [dict(pid=999, state='S')]),
                                 ('other_group_members_absent_before_reap', None)]:
            with self.subTest(key=key, replacement=replacement):
                native = wait(200)
                native[key] = replacement
                with self.assertRaises(ValueError):
                    policy.validate(fixture(True), native)

    def test_direct_root_failure_is_not_normalized(self):
        for code in (1, 137, False):
            value = fixture()
            value['rootWait']['returncode'] = code
            with self.subTest(code=code), self.assertRaises(ValueError):
                policy.validate(value, wait(200))

    def test_every_recovery_fence_is_required(self):
        for group in ('idleStop', 'recoveryClosure'):
            for key in fixture(True)[group]:
                with self.subTest(group=group, missing=key):
                    value = fixture(True)
                    del value[group][key]
                    with self.assertRaises(ValueError):
                        policy.validate(value, wait(200))

    def test_does_not_accept_signal_of_native_or_classic(self):
        for pid in (200, 300, 400):
            value = fixture(True)
            value['idleStop'].update(onlySignaledPID=pid, rootGroup=[pid])
            with self.subTest(pid=pid), self.assertRaises(ValueError):
                policy.validate(value, wait(200))

    def test_different_classic_or_live_child_refuses(self):
        for group, key, replacement in [('idleStop', 'preservedClassicPID', 999),
                                         ('idleStop', 'directChildren', [999]),
                                         ('idleStop', 'rootGroup', [100, 999]),
                                         ('recoveryClosure', 'nativeSignals', True),
                                         ('recoveryClosure', 'renderReplay', True)]:
            value = fixture(True)
            value[group][key] = replacement
            with self.subTest(key=key), self.assertRaises(ValueError):
                policy.validate(value, wait(200))

    def test_cannot_replace_original_terminal_with_startup_terminal(self):
        value = fixture(True)
        value['originalTerminal'] = value['startupTerminal']
        with self.assertRaises(ValueError):
            policy.validate(value, wait(200))

    def test_unverified_startup_or_extra_fields_refuse(self):
        for recovered in (False, True):
            value = fixture(recovered)
            value['startup']['allSevenStartupPhasesVerified'] = False
            with self.assertRaises(ValueError):
                policy.validate(value, wait(200))
            value = fixture(recovered)
            value['implicitRetry'] = True
            with self.assertRaises(ValueError):
                policy.validate(value, wait(200))
