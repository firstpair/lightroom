"""Read pinned capture files beneath a caller-owned directory descriptor.

This checks saved evidence, never live processes. The caller authenticates the
root descriptor, source/receipt inventory and actual parent terminal separately.
Missing records remain unknown; this API cannot establish inventory completeness
or authorize a publication, reap or grant release.
"""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat

from .census_receipts import MAX_RAW, check_reported_capture


class CaptureFileCloseUnknown(RuntimeError):
    """Every uncertain close retains its pre-close identity; never retry an FD."""

    def __init__(self, failures, original_error):
        super().__init__('CAPTURE_AUDIT_DESCRIPTOR_CLOSE_UNKNOWN')
        self.uncertain_closes = tuple(failures)
        self.original_error = original_error


@dataclass(frozen=True)
class CheckedFiles:
    captures: tuple
    resource_release_authorized: bool = field(default=False, init=False)


def identity(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns,
            st.st_mode, st.st_uid, st.st_nlink)


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def _private_file(st):
    _require(stat.S_ISREG(st.st_mode) and stat.S_IMODE(st.st_mode) == 0o600
             and st.st_uid == os.getuid() and st.st_nlink == 1, 'CAPTURE_PRIVATE_FILE')


def _close_all(descriptors, original):
    failures = []
    for fd, role in reversed(descriptors):
        record = dict(fd=fd, role=role, close_attempted=False, numeric_retry=False)
        try:
            record['preclose_identity'] = identity(os.fstat(fd))
        except BaseException as error:
            record['error'] = repr(error)
            failures.append(record)  # still known open; no unvalidated close
            continue
        try:
            record['close_attempted'] = True
            os.close(fd)
        except BaseException as error:
            record['error'] = repr(error)
            failures.append(record)
    if failures:
        raise CaptureFileCloseUnknown(failures, original) from original


def check_capture_files(root_fd, root_label, records, protected_roots, *, ancestor_pids=()):
    """Audit a nonempty bounded reported success inventory, keeping the root FD.

    Records must point to direct owned-census-<32hex>/RESULT.json descendants.
    Files are opened relative to held descriptors, nofollow, byte-bound and
    epoch-fenced. A valid inventory can still omit an attempted child: its
    completeness must come from the caller's authenticated execution journal.
    On any failure the caller must retain ownership until separately resolved.
    """
    _require(type(root_label) is str and root_label.startswith('/')
             and str(PurePosixPath(root_label)) == root_label
             and '..' not in PurePosixPath(root_label).parts, 'CAPTURE_ROOT_LABEL')
    root = os.fstat(root_fd)
    _require(stat.S_ISDIR(root.st_mode) and root.st_uid == os.getuid(), 'CAPTURE_ROOT_FD')
    _require(type(records) is list and 1 <= len(records) <= 128, 'CAPTURE_INVENTORY_BOUND')
    seen = set()
    checked = []
    for pin in records:
        _require(type(pin) is dict and set(pin) == {'path', 'bytes', 'sha256'}, 'CAPTURE_PIN_FIELDS')
        label = pin['path']
        _require(type(label) is str, 'CAPTURE_PIN_LABEL')
        path = PurePosixPath(label)
        _require(str(path) == label and str(path.parent.parent) == root_label
                 and path.name == 'RESULT.json'
                 and re.fullmatch(r'owned-census-[0-9a-f]{32}', path.parent.name)
                 and label not in seen, 'CAPTURE_PIN_NAMESPACE_OR_DUPLICATE')
        seen.add(label)
        _require(type(pin['bytes']) is int and 0 < pin['bytes'] <= 65536
                 and type(pin['sha256']) is str
                 and re.fullmatch(r'[0-9a-f]{64}', pin['sha256']), 'CAPTURE_PIN_BOUND')
        descriptors = []
        original = None
        try:
            directory = os.open(path.parent.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=root_fd)
            descriptors.append((directory, 'capture-directory'))
            directory_identity = identity(os.fstat(directory))
            _require(stat.S_IMODE(directory_identity[5]) == 0o700
                     and directory_identity[6] == os.getuid(), 'CAPTURE_PRIVATE_DIRECTORY')
            receipt_fd = os.open('RESULT.json', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            descriptors.append((receipt_fd, 'capture-receipt'))
            receipt_stat = os.fstat(receipt_fd); _private_file(receipt_stat)
            receipt_identity = identity(receipt_stat)
            _require(receipt_stat.st_size == pin['bytes'], 'CAPTURE_RECEIPT_SIZE')
            data = bytearray()
            while len(data) <= pin['bytes']:
                chunk = os.read(receipt_fd, min(65536, pin['bytes'] + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            _require(len(data) == pin['bytes']
                     and hashlib.sha256(data).hexdigest() == pin['sha256'], 'CAPTURE_RECEIPT_BYTES')
            receipt = json.loads(data)
            _require(receipt['raw']['path'] == str(path.parent / 'stdout'), 'CAPTURE_RAW_NAMESPACE')
            raw_fd = os.open('stdout', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            descriptors.append((raw_fd, 'capture-raw'))
            raw_stat = os.fstat(raw_fd); _private_file(raw_stat)
            raw_identity = identity(raw_stat)
            _require(0 < raw_stat.st_size <= MAX_RAW
                     and list(raw_identity) == receipt['raw']['identity8'], 'CAPTURE_RAW_EPOCH')
            result = check_reported_capture(receipt, iter(lambda: os.read(raw_fd, 65536), b''),
                                            protected_roots, ancestor_pids=ancestor_pids)
            for fd, name, before in ((receipt_fd, 'RESULT.json', receipt_identity),
                                     (raw_fd, 'stdout', raw_identity)):
                _require(identity(os.fstat(fd)) == before
                         and identity(os.stat(name, dir_fd=directory, follow_symlinks=False)) == before,
                         'CAPTURE_FILE_EPOCH_CHANGED')
            _require(identity(os.fstat(directory)) == directory_identity
                     and identity(os.stat(path.parent.name, dir_fd=root_fd,
                                          follow_symlinks=False)) == directory_identity,
                     'CAPTURE_DIRECTORY_CHANGED')
            checked.append(result)
        except BaseException as error:
            original = error
            raise
        finally:
            _close_all(descriptors, original)
    return CheckedFiles(tuple(checked))
