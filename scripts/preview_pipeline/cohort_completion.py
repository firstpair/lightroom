"""Validate an outer coordinator's completion independently of native success.

The caller authenticates the underlying receipts before constructing this view.
This policy performs no I/O, grants no lease-release authority, and does not
replace the native result, output, reader, group or input-binding validators.
An owned child wait supports continuous orchestration without an external tool
event between stages. Recovery preserves the original nonzero terminal.
"""
import re

SCHEMA = 'PREVIEW_COHORT_OUTER_COMPLETION_V1'


def require(value, code):
    if not value:
        raise ValueError(code)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def closed_wait(value):
    fields = {'pid', 'returncode', 'reaped', 'other_group_members_absent_before_reap',
              'members_before_reap', 'timed_out', 'scope'}
    require(type(value) is dict and set(value) == fields and integer(value.get('pid'), 2)
            and type(value.get('returncode')) is int and value['returncode'] == 0
            and value.get('reaped') is True
            and value.get('other_group_members_absent_before_reap') is True
            and value.get('timed_out') is False
            and value['scope'] == 'owned group only; separate sessions require independently audited proofs'
            and type(value['members_before_reap']) is list
            and len(value['members_before_reap']) == 1
            and value['members_before_reap'][0] == {'pid': value['pid'], 'state': 'Z'},
            'ACTUAL_SUCCESSFUL_CHILD_WAIT_REQUIRED')


def terminal(value, exit_code):
    require(type(value) is dict and integer(value.get('session'), 1)
            and type(value.get('exitCode')) is int and value['exitCode'] == exit_code
            and value.get('noRunningSession') is True
            and all(type(value.get(k)) is str
                    and re.fullmatch('[0-9a-f]{6}', value[k])
                    for k in ('initialChunk', 'terminalChunk')),
            'ACTUAL_TOOL_TERMINAL_REQUIRED')


def validate(value, native_wait):
    require(type(value) is dict and value.get('schema') == SCHEMA,
            'OUTER_COMPLETION_SCHEMA')
    closed_wait(native_wait)
    require(type(value.get('cohortSession')) is str
            and re.fullmatch('[0-9a-f]{32}', value['cohortSession']), 'COHORT_SESSION')
    startup = value.get('startup')
    require(type(startup) is dict and integer(startup.get('pid'), 2)
            and type(startup.get('start')) is str and startup['start']
            and startup.get('allSevenStartupPhasesVerified') is True,
            'SAME_CLASSIC_STARTUP_VERIFIED')
    require(startup['pid'] != native_wait['pid'], 'CLASSIC_IS_NOT_NATIVE_OWNER')
    mode = value.get('mode')
    if mode == 'DIRECT_CHILD':
        require(set(value) == {'schema', 'cohortSession', 'mode', 'rootWait',
                              'resourcesClosed', 'startup'}, 'DIRECT_CHILD_FIELDS')
        closed_wait(value['rootWait'])
        require(value['rootWait']['pid'] not in (native_wait['pid'], startup['pid']),
                'DISTINCT_OWNERS')
        require(value['resourcesClosed'] is True, 'ROOT_RESOURCES_CLOSED')
        original_exit = 0
    elif mode == 'RECOVERED_IDLE_TOOL_ROOT':
        require(set(value) == {'schema', 'cohortSession', 'mode', 'originalTerminal',
                              'idleStop', 'recoveryClosure', 'startup',
                              'startupTerminal', 'startupHelperWait'}, 'RECOVERY_FIELDS')
        terminal(value['originalTerminal'], 137)
        terminal(value['startupTerminal'], 0)
        require(value['originalTerminal']['session'] != value['startupTerminal']['session'],
                'STARTUP_SUCCESS_IS_NOT_ORIGINAL_ROOT_SUCCESS')
        closed_wait(value['startupHelperWait'])
        stop = value['idleStop']
        require(type(stop) is dict and integer(stop.get('onlySignaledPID'), 2)
                and stop.get('directChildren') == []
                and stop.get('rootGroup') == [stop['onlySignaledPID']]
                and stop.get('onlyOpenRegularDescriptorsAreTenCanonicalLeases') is True
                and stop.get('originalReadersClosed') is True
                and stop.get('watcherAlreadyClosed') is True
                and stop.get('noClassicNativeWorkerGroupSignals') is True
                and stop.get('originalRootNormalExitNotClaimed') is True
                and stop.get('preservedClassicPID') == startup['pid']
                and stop['onlySignaledPID'] not in
                    (native_wait['pid'], startup['pid'], value['startupHelperWait']['pid']),
                'ONLY_PROVEN_IDLE_ROOT_STOPPED')
        recovery = value['recoveryClosure']
        require(type(recovery) is dict
                and recovery.get('freshEXglobalThenPhoto8ThenUIAcquiredAndClosed') is True
                and recovery.get('noChildrenLaunchedByProbe') is True
                and recovery.get('originalOwnerSuccessNotClaimed') is True
                and recovery.get('nativeSignals') is False
                and recovery.get('ClassicPreservedPID') == startup['pid']
                and recovery.get('originalRetentionPreserved') is True
                and recovery.get('renderReplay') is False,
                'INDEPENDENT_RECOVERY_CLOSED')
        original_exit = 137
    else:
        raise ValueError('EXPLICIT_COMPLETION_MODE_REQUIRED')
    return dict(schema='VALIDATED_PREVIEW_OUTER_COMPLETION_V1',
                mode=mode, cohortSession=value['cohortSession'],
                originalRootExitCode=original_exit,
                originalRootSucceeded=(original_exit == 0),
                nativeOwnerSucceeded=True, renderReplayAllowed=False,
                resourceReleaseAuthority=False,
                fullNativeProofStillRequired=True)
