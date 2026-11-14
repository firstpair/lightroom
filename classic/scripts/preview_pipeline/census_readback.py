"""Read every pinned durable capture-journal snapshot beneath a held directory.

The caller authenticates that directory, producer source, expected inventory and
actual owner terminal. A checked journal still requires independent raw-capture
verification. This module neither observes live processes nor releases grants.
"""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat

from .census_files import CaptureFileCloseUnknown, identity
from .census_journal import SCHEMA
from .census_receipts import COMMAND, MAX_PROJECTION
from .census_store import MAX_RECORDS, MAX_SNAPSHOT


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'JOURNAL_DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('JOURNAL_NONFINITE_JSON_VALUE: ' + value)


def _pin(value):
    _require(type(value) is dict and set(value) == {'path', 'bytes', 'sha256'},
             'JOURNAL_PIN_FIELDS')
    _require(type(value['path']) is str and value['path'].startswith('/')
             and type(value['bytes']) is int and 0 < value['bytes'] <= MAX_SNAPSHOT
             and type(value['sha256']) is str
             and re.fullmatch(r'[0-9a-f]{64}', value['sha256']), 'JOURNAL_PIN_VALUES')
    return value['path'], value['bytes'], value['sha256']


def _outcome(row, index):
    _require(type(row) is dict and set(row) == {
        'index', 'command', 'state', 'receipt', 'projected_bytes', 'projected_sha256'},
        'JOURNAL_OUTCOME_FIELDS')
    _require(type(row['index']) is int and row['index'] == index
             and row['command'] == COMMAND and row['state'] == 'OUTCOME',
             'JOURNAL_OUTCOME_ORDER')
    _pin(row['receipt'])
    _require(type(row['projected_bytes']) is int and 0 < row['projected_bytes'] <= MAX_PROJECTION
             and type(row['projected_sha256']) is str
             and re.fullmatch(r'[0-9a-f]{64}', row['projected_sha256']),
             'JOURNAL_OUTCOME_PROJECTION')


def _close_once(fd, original):
    record = dict(fd=fd, role='journal-snapshot-readback', close_attempted=False,
                  numeric_retry=False)
    try:
        record['preclose_identity'] = identity(os.fstat(fd))
    except BaseException as error:
        record['error'] = repr(error)
        raise CaptureFileCloseUnknown([record], original) from original
    try:
        record['close_attempted'] = True
        os.close(fd)
    except BaseException as error:
        record['error'] = repr(error)
        raise CaptureFileCloseUnknown([record], original) from original


@dataclass(frozen=True)
class CheckedJournal:
    snapshot_bytes: bytes
    snapshot_pins: tuple
    resource_release_authorized: bool = field(default=False, init=False)

    def snapshot(self):
        return json.loads(self.snapshot_bytes)


def check_journal_files(directory_fd, directory_label, expected_pins):
    """Check the complete sealed INTENT/OUTCOME/.../SEALED snapshot inventory.

    All files are opened relative to the borrowed FD with nofollow, bounds,
    byte pins and held/visible fences. An omitted attempt cannot be excluded by
    a peer-provided subset alone: caller-authenticated producer provenance and
    inventory remain required. Every unknown close preserves the original cause.
    """
    _require(type(directory_fd) is int and directory_fd >= 3, 'JOURNAL_ROOT_FD')
    _require(type(directory_label) is str and directory_label.startswith('/')
             and str(PurePosixPath(directory_label)) == directory_label
             and '..' not in PurePosixPath(directory_label).parts, 'JOURNAL_ROOT_LABEL')
    _require(type(expected_pins) is list and 3 <= len(expected_pins) <= MAX_RECORDS
             and len(expected_pins) % 2 == 1, 'JOURNAL_COMPLETE_SNAPSHOT_COUNT')
    pins = tuple(_pin(pin) for pin in expected_pins)
    names = [f'{index:06d}.json' for index in range(len(pins))]
    for name, pin in zip(names, pins):
        _require(pin[0] == str(PurePosixPath(directory_label) / name), 'JOURNAL_SNAPSHOT_NAMESPACE')
    root = identity(os.fstat(directory_fd))
    _require(stat.S_ISDIR(root[5]) and stat.S_IMODE(root[5]) == 0o700
             and root[6] == os.getuid(), 'JOURNAL_PRIVATE_ROOT')
    _require(set(os.listdir(directory_fd)) == set(names), 'JOURNAL_COMPLETE_DIRECTORY_INVENTORY')
    completed = []
    receipts = set()
    final = None
    for index, (name, pin) in enumerate(zip(names, pins)):
        fd = None
        original = None
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                         dir_fd=directory_fd)
            before = identity(os.fstat(fd))
            _require(stat.S_ISREG(before[5]) and stat.S_IMODE(before[5]) == 0o600
                     and before[6] == os.getuid() and before[7] == 1
                     and before[2] == pin[1], 'JOURNAL_PRIVATE_SNAPSHOT')
            data = bytearray()
            while len(data) <= pin[1]:
                part = os.read(fd, min(65536, pin[1] + 1 - len(data)))
                if not part:
                    break
                data.extend(part)
            raw = bytes(data)
            _require(len(raw) == pin[1] and hashlib.sha256(raw).hexdigest() == pin[2],
                     'JOURNAL_SNAPSHOT_BYTES')
            value = json.loads(raw, object_pairs_hook=_unique, parse_constant=_reject_constant)
            _require(type(value) is dict and set(value) == {
                'schema', 'state', 'attempts', 'resource_release_authorized'}, 'JOURNAL_SNAPSHOT_FIELDS')
            _require(value['schema'] == SCHEMA and value['resource_release_authorized'] is False
                     and type(value['attempts']) is list, 'JOURNAL_SNAPSHOT_SCOPE')
            canonical = (json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=True, allow_nan=False) + '\n').encode()
            _require(raw == canonical, 'JOURNAL_CANONICAL_SNAPSHOT')
            rows = value['attempts']
            if index == len(pins)-1:
                _require(value['state'] == 'SEALED' and rows == completed
                         and 1 <= len(completed) <= 128, 'JOURNAL_FINAL_SEAL')
                final = raw
            elif index % 2 == 0:
                attempt = index//2
                _require(value['state'] == 'INTENT' and len(rows) == attempt+1
                         and type(rows[-1]) is dict and type(rows[-1].get('index')) is int
                         and rows[:-1] == completed and rows[-1] == {
                             'index': attempt, 'command': COMMAND, 'state': 'INTENT'},
                         'JOURNAL_DURABLE_INTENT_PREFIX')
            else:
                attempt = index//2
                _require(value['state'] == 'OUTCOME' and len(rows) == attempt+1
                         and rows[:-1] == completed, 'JOURNAL_DURABLE_OUTCOME_PREFIX')
                _outcome(rows[-1], attempt)
                label = rows[-1]['receipt']['path']
                _require(label not in receipts, 'JOURNAL_DUPLICATE_CAPTURE_RECEIPT')
                receipts.add(label)
                completed.append(rows[-1])
            _require(identity(os.fstat(fd)) == before
                     and identity(os.stat(name, dir_fd=directory_fd, follow_symlinks=False)) == before,
                     'JOURNAL_HELD_OR_VISIBLE_SNAPSHOT_CHANGED')
        except BaseException as error:
            original = error
            raise
        finally:
            if fd is not None:
                _close_once(fd, original)
    _require(identity(os.fstat(directory_fd)) == root
             and set(os.listdir(directory_fd)) == set(names), 'JOURNAL_ROOT_CHANGED')
    return CheckedJournal(final, pins)
