"""Check saved process-list bytes and reported closure, never live ownership.

Caller authenticates producer, complete attempt inventory, receipt and raw file
identities separately. This parser cannot authorize release or prove a current
absence of a process. Exact names are observations, not executable identities.
"""
from dataclasses import dataclass, field
import hashlib

COMMAND = ['/bin/ps', '-axo', 'pid=,comm=']
MAXIMUM = 4 * 1024 * 1024


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def _pin(pin):
    _require(type(pin) is dict and set(pin) == {'path', 'bytes', 'sha256'}
             and type(pin['path']) is str and pin['path'].startswith('/')
             and type(pin['bytes']) is int and pin['bytes'] > 0
             and type(pin['sha256']) is str and len(pin['sha256']) == 64
             and all(c in '0123456789abcdef' for c in pin['sha256']), 'PROCESS_CAPTURE_INTENT_PIN')


@dataclass(frozen=True)
class CheckedProcesses:
    processes: tuple
    reported_child_pid: int
    resource_release_authorized: bool = field(default=False, init=False)


def check_closed_process_capture(result, intent, stdout, stderr, *, ancestor_pids=()):
    """Check reported closure even for a failed command; no absence authority."""
    _require(type(result) is dict and set(result) == {
        'schema', 'command', 'intent', 'actual', 'stdout', 'stderr',
        'owned_fds_closed', 'caller_grants_released', 'signals_sent'}, 'PROCESS_CAPTURE_FIELDS')
    _require(result['schema'] == 'OWNED_PROCESS_CAPTURE_RESULT_V1'
             and result['command'] == COMMAND and result['owned_fds_closed'] is True
             and result['caller_grants_released'] is False
             and type(result['signals_sent']) is int and result['signals_sent'] == 0,
             'PROCESS_CAPTURE_SCOPE')
    _pin(result['intent'])
    _require(type(intent) is dict and set(intent) == {
        'schema', 'command', 'indexName', 'maximum_bytes', 'signals_allowed',
        'resource_release_authorized'} and intent['schema'] == 'OWNED_PROCESS_CAPTURE_INTENT_V1'
             and intent['command'] == COMMAND and intent['signals_allowed'] is False
             and intent['resource_release_authorized'] is False
             and type(intent['maximum_bytes']) is int and 0 < intent['maximum_bytes'] <= MAXIMUM,
             'PROCESS_CAPTURE_INTENT')
    _require(type(ancestor_pids) is tuple and len(ancestor_pids) <= 16
             and all(type(pid) is int and pid > 0 for pid in ancestor_pids), 'PROCESS_CAPTURE_ANCESTORS')
    actual = result['actual']
    _require(type(actual) is dict and set(actual) == {
        'pid', 'returncode', 'reaped', 'other_group_members_absent_before_reap',
        'members_before_reap', 'timed_out', 'signals_sent'}, 'PROCESS_CAPTURE_WAIT_FIELDS')
    pid = actual['pid']
    _require(type(pid) is int and pid > 0 and pid not in ancestor_pids
             and type(actual['returncode']) is int and -255 <= actual['returncode'] <= 255
             and actual['reaped'] is True and actual['other_group_members_absent_before_reap'] is True
             and actual['timed_out'] is False and type(actual['signals_sent']) is int
             and actual['signals_sent'] == 0, 'PROCESS_CAPTURE_WAIT_REPORT')
    members = actual['members_before_reap']
    _require(type(members) is list and len(members) == 1 and type(members[0]) is dict
             and set(members[0]) == {'pid', 'state'} and type(members[0]['pid']) is int
             and members[0]['pid'] == pid and type(members[0]['state']) is str
             and 0 < len(members[0]['state']) <= 16 and members[0]['state'].startswith('Z')
             and all(33 <= ord(c) <= 126 for c in members[0]['state']), 'PROCESS_CAPTURE_GROUP_REPORT')
    _require(type(stdout) is bytes and len(stdout) <= intent['maximum_bytes']
             and type(stderr) is bytes and len(stderr) <= 1048576, 'PROCESS_CAPTURE_OUTPUT')
    for key, raw in (('stdout', stdout), ('stderr', stderr)):
        record = result[key]
        _require(type(record) is dict and set(record) == {'path', 'bytes', 'sha256', 'identity8'}
                 and type(record['bytes']) is int and record['bytes'] == len(raw)
                 and record['sha256'] == hashlib.sha256(raw).hexdigest(), 'PROCESS_CAPTURE_RAW_BINDING')
    return CheckedProcesses((), pid)


def check_process_capture(result, intent, stdout, stderr, *, ancestor_pids=()):
    closed = check_closed_process_capture(result, intent, stdout, stderr,
                                          ancestor_pids=ancestor_pids)
    _require(result['actual']['returncode'] == 0 and not stderr and stdout,
             'PROCESS_CAPTURE_SUCCESS_REQUIRED')
    _require(stdout.endswith(b'\n') and b'\x00' not in stdout, 'PROCESS_CAPTURE_COMPLETE_LINES')
    rows = []
    seen = set()
    for line in stdout.decode('utf-8', 'strict').splitlines():
        parts = line.split(None, 1)
        _require(len(parts) == 2 and parts[0].isascii() and parts[0].isdigit()
                 and int(parts[0]) > 0 and int(parts[0]) not in seen
                 and parts[1] and all(ord(c) >= 32 for c in parts[1]), 'PROCESS_CAPTURE_ROW')
        seen.add(int(parts[0])); rows.append((int(parts[0]), parts[1]))
    return CheckedProcesses(tuple(rows), closed.reported_child_pid)
