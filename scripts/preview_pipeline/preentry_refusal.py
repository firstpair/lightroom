"""Classify an exact source-pinned pre-entry refusal after actual settlement.

The supervisor supplies a reviewed policy tying complete diagnostic bytes to a
specific helper source. This pure classifier does not authenticate process
records, inspect paths, acquire locks, or authorize a retry. An absent callback
alone cannot satisfy it. Alternate recorded paths require separate exact
tracebacks in the policy; diagnostics are never rewritten to obtain a match.
"""
from dataclasses import dataclass
import hashlib
import re


@dataclass(frozen=True)
class RefusalPolicy:
    helper_sha256: str
    tracebacks: tuple[bytes, ...]

    def __post_init__(self):
        if (type(self.helper_sha256) is not str
                or re.fullmatch(r'[0-9a-f]{64}', self.helper_sha256) is None
                or type(self.tracebacks) is not tuple
                or not 1 <= len(self.tracebacks) <= 4
                or any(type(value) is not bytes or not 0 < len(value) <= 65536
                       for value in self.tracebacks)
                or len(set(self.tracebacks)) != len(self.tracebacks)):
            raise ValueError('EXACT_REVIEWED_REFUSAL_POLICY_REQUIRED')


def prove_refusal(actual, stdout, stderr, *, callback_present, helper_live,
                  helper_bytes, policy):
    """Consume independently authenticated wait/source/diagnostic observations."""
    if not (type(policy) is RefusalPolicy
            and type(actual) is dict
            and type(actual.get('returncode')) is int
            and actual['returncode'] == 1
            and actual.get('reaped') is True
            and actual.get('other_group_members_absent_before_reap') is True
            and actual.get('timed_out') is False
            and type(stdout) is bytes and stdout == b''
            and type(stderr) is bytes and stderr in policy.tracebacks
            and callback_present is False and helper_live is False
            and type(helper_bytes) is bytes
            and hashlib.sha256(helper_bytes).hexdigest() == policy.helper_sha256):
        raise ValueError('HELPER_PREENTRY_REFUSAL_NOT_PROVED')
    return dict(state='PINNED_HELPER_PREENTRY_REFUSAL',
                helperSourceSha256=policy.helper_sha256,
                matchedDiagnosticSha256=hashlib.sha256(stderr).hexdigest(),
                helperActuallyReaped=True, helperGroupOtherMembersAbsent=True,
                uiOperationEntered=False, callbackDispatched=False,
                successfulCallbackClaimed=False, retryAuthorized=False)
