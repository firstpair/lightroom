"""Validate a reported complete census against its captured byte stream.

The caller must authenticate the receipt, hold/fence the raw file identity and
close its descriptors safely. This function does no IO, observes no process,
authenticates no wait event, and never authorizes resource release or writes.
"""
from dataclasses import dataclass, field
from collections.abc import Iterable
from pathlib import PurePosixPath
import stat
import hashlib

from .descriptor_census import Census, parse

MAX_RAW = 256 * 1024 * 1024
MAX_PROJECTION = 16 * 1024 * 1024
COMMAND = ['/usr/sbin/lsof', '-nP', '-Fpcftn']


def _require(value, why):
    if not value:
        raise ValueError(why)


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


@dataclass(frozen=True)
class CheckedCapture:
    census: Census
    reported_child_pid: int
    raw_identity8: tuple[int, ...]
    projection: bytes
    # The checked fields remain reports, not independently observed wait/FD facts.
    resource_release_authorized: bool = field(default=False, init=False)


def check_reported_capture(receipt: dict, raw_chunks: Iterable[bytes],
                           protected_roots: tuple[str, ...], *,
                           ancestor_pids: tuple[int, ...] = ()) -> CheckedCapture:
    """Consume all raw chunks once; refuse inconsistent or incomplete reports.

    An absent foreign descriptor can be considered only by the caller's separate
    exclusion policy. A valid result does not mean the protected roots are free.
    No peer-supplied hash or serialized process proof is itself release authority.
    """
    fields = {'state', 'command', 'actual', 'raw', 'projection', 'process_count',
              'named_count', 'protected_count', 'owned_fds_closed',
              'caller_grants_released', 'signals_sent'}
    _require(type(receipt) is dict and set(receipt) == fields, 'CAPTURE_FIELDS')
    _require(receipt['state'] == 'COMPLETE_GLOBAL_CENSUS_PROJECTED_CHILD_GROUP_FDS_CLOSED'
             and receipt['command'] == COMMAND, 'CAPTURE_SCOPE')
    _require(receipt['owned_fds_closed'] is True
             and receipt['caller_grants_released'] is False
             and type(receipt['signals_sent']) is int and receipt['signals_sent'] == 0,
             'CAPTURE_FD_OR_SIGNAL_REPORT')
    _require(type(ancestor_pids) is tuple and len(ancestor_pids) <= 16
             and all(_integer(pid, 1) for pid in ancestor_pids)
             and len(set(ancestor_pids)) == len(ancestor_pids), 'CAPTURE_ANCESTORS')
    actual = receipt['actual']
    actual_fields = {'pid', 'returncode', 'reaped', 'other_group_members_absent_before_reap',
                     'members_before_reap', 'timed_out', 'signals_sent'}
    _require(type(actual) is dict and set(actual) == actual_fields, 'CAPTURE_WAIT_FIELDS')
    pid = actual['pid']
    _require(_integer(pid, 1) and pid not in ancestor_pids
             and type(actual['returncode']) is int and actual['returncode'] == 0
             and actual['reaped'] is True
             and actual['other_group_members_absent_before_reap'] is True
             and actual['timed_out'] is False
             and type(actual['signals_sent']) is int and actual['signals_sent'] == 0,
             'CAPTURE_WAIT_REPORT')
    members = actual['members_before_reap']
    _require(type(members) is list and len(members) == 1
             and type(members[0]) is dict and set(members[0]) == {'pid', 'state'}
             and type(members[0]['pid']) is int and members[0]['pid'] == pid
             and type(members[0]['state']) is str and 1 <= len(members[0]['state']) <= 16
             and members[0]['state'].isascii() and members[0]['state'].startswith('Z')
             and all(33 <= ord(c) <= 126 for c in members[0]['state']),
             'CAPTURE_RETAINED_LEADER_REPORT')
    raw = receipt['raw']
    _require(type(raw) is dict and set(raw) == {'path', 'bytes', 'sha256', 'identity8'},
             'CAPTURE_RAW_FIELDS')
    label = raw['path']
    _require(type(label) is str and label.startswith('/')
             and str(PurePosixPath(label)) == label and '..' not in PurePosixPath(label).parts
             and not any(ord(c) < 32 for c in label), 'CAPTURE_RAW_LABEL')
    identity = raw['identity8']
    _require(type(identity) is list and len(identity) == 8
             and all(_integer(value) for value in identity)
             and identity[0] > 0 and identity[1] > 0
             and 0 < identity[2] <= MAX_RAW and raw['bytes'] == identity[2]
             and type(raw['bytes']) is int and stat.S_ISREG(identity[5])
             and stat.S_IMODE(identity[5]) == 0o600 and identity[7] == 1,
             'CAPTURE_RAW_IDENTITY_REPORT')
    census = parse(raw_chunks, protected_roots, maximum_bytes=MAX_RAW)
    _require(census.input_bytes == raw['bytes'] and census.input_sha256 == raw['sha256'],
             'CAPTURE_RAW_CONTENT')
    for key, value in (('process_count', len(census.process_ids)),
                       ('named_count', census.named_count),
                       ('protected_count', len(census.protected))):
        _require(type(receipt[key]) is int and receipt[key] == value, 'CAPTURE_COUNTERS')
    projection = census.legacy_fields(MAX_PROJECTION)
    projected = receipt['projection']
    _require(type(projected) is dict and set(projected) == {'bytes', 'sha256'}
             and type(projected['bytes']) is int and projected['bytes'] == len(projection),
             'CAPTURE_PROJECTION_LENGTH')
    _require(projected['sha256'] == hashlib.sha256(projection).hexdigest(),
             'CAPTURE_PROJECTION_CONTENT')
    return CheckedCapture(census, pid, tuple(identity), projection)
