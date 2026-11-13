"""Native completion can precede the final Classic reopen.

Legacy views retain their original validator. The new closed-window view does
not assert startup success, authorize publication, or replace the full native
and normal-close receipt audits. Callers authenticate all referenced bytes.
"""
import re

from . import cohort_completion as legacy
from .work_queue import pin


SCHEMA = 'PREVIEW_COHORT_OUTER_COMPLETION_V2'
MODE = 'CLOSED_CLASSIC_NATIVE_WINDOW'
FIELDS = {'schema', 'mode', 'cohortSession', 'rootWait', 'resourcesClosed',
          'closedMainEpochId', 'normalClose', 'normalCloseEvidence',
          'closedMainGateEvidence', 'nativeResultEvidence', 'helperWaits',
          'allHelpersSettled', 'originalReadersClosed', 'closedMainEpochGuardClosed',
          'classicReopened', 'startupVerified', 'finalStartupRequired',
          'closedMainObservationScope'}
SCOPE = 'SAMPLED_PROCESS_AND_PATH_HANDLE_CENSUS_NOT_ATOMIC_GLOBAL_ABSENCE'


def validate(value, native_wait):
    if type(value) is dict and value.get('schema') == legacy.SCHEMA:
        return legacy.validate(value, native_wait)
    legacy.require(type(value) is dict and set(value) == FIELDS
                   and value['schema'] == SCHEMA and value['mode'] == MODE,
                   'EXPLICIT_CLOSED_NATIVE_WINDOW_REQUIRED')
    legacy.closed_wait(native_wait)
    legacy.closed_wait(value['rootWait'])
    for name in ('cohortSession', 'closedMainEpochId'):
        legacy.require(type(value[name]) is str
                       and re.fullmatch('[0-9a-f]{32}', value[name]), 'NATIVE_WINDOW_ID')
    for name in ('normalCloseEvidence', 'closedMainGateEvidence', 'nativeResultEvidence'):
        pin(value[name])
    close = value['normalClose']
    legacy.require(type(close) is dict and set(close) == {
        'normalQuitSubmittedOnce', 'forceTerminationUsed', 'classicProcessesAbsent',
        'previousPID', 'previousStart', 'backupPolicyChanged'}, 'EXACT_NORMAL_CLOSE_VIEW')
    legacy.require(close['normalQuitSubmittedOnce'] is True
                   and close['forceTerminationUsed'] is False
                   and close['classicProcessesAbsent'] is True
                   and close['backupPolicyChanged'] is False
                   and legacy.integer(close['previousPID'], 2)
                   and type(close['previousStart']) is str and close['previousStart'],
                   'NORMAL_CLOSE_REQUIRED_NO_FORCE')
    pids = {native_wait['pid'], value['rootWait']['pid'], close['previousPID']}
    legacy.require(len(pids) == 3, 'DISTINCT_NATIVE_ROOT_AND_CLASSIC')
    helpers = value['helperWaits']
    legacy.require(type(helpers) is list and 2 <= len(helpers) <= 4,
                   'ALL_NORMAL_CLOSE_HELPERS_REQUIRED')
    for helper in helpers:
        legacy.closed_wait(helper)
        legacy.require(helper['pid'] not in pids, 'DISTINCT_SETTLED_CLOSE_HELPERS')
        pids.add(helper['pid'])
    legacy.require(all(value[k] is True for k in (
        'resourcesClosed', 'allHelpersSettled', 'originalReadersClosed',
        'closedMainEpochGuardClosed', 'finalStartupRequired')),
        'NATIVE_WINDOW_RESOURCES_MUST_BE_SETTLED')
    legacy.require(value['classicReopened'] is False and value['startupVerified'] is False
                   and value['closedMainObservationScope'] == SCOPE,
                   'DEFERRED_STARTUP_IS_NOT_VERIFIED_STARTUP')
    return dict(schema='VALIDATED_PREVIEW_OUTER_COMPLETION_V2', mode=MODE,
                cohortSession=value['cohortSession'], closedMainEpochId=value['closedMainEpochId'],
                originalRootExitCode=0, originalRootSucceeded=True, nativeOwnerSucceeded=True,
                renderReplayAllowed=False, resourceReleaseAuthority=False,
                publicationAuthorized=False, startupVerified=False,
                finalStartupStillRequired=True, fullNativeProofStillRequired=True,
                fullNormalCloseProofStillRequired=True)
