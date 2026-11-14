"""Durable one-use snapshot writer for the descriptor-capture journal.

The caller supplies and retains an authenticated, fresh, empty private directory
FD. This writer never opens a pathname outside that directory, launches a child,
closes the borrowed directory, or authorizes process/lease release. Each persist
consumes one exclusive filename before attempting IO. Any uncertainty latches;
neither writes nor uncertain numeric descriptors are retried.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import PurePosixPath
import stat
import threading

from .census_files import identity
from .census_journal import SCHEMA

MAX_SNAPSHOT = 1048576
MAX_RECORDS = 257  # INTENT + OUTCOME for 128 captures, then SEALED


class CaptureJournalWriteUnknown(RuntimeError):
    def __init__(self, record, original_error, retained_fds=(), uncertain_closes=()):
        super().__init__('CAPTURE_JOURNAL_WRITE_OR_DURABILITY_UNKNOWN')
        self.record = deepcopy(record)
        self.original_error = original_error
        self.retained_fds = tuple(retained_fds)
        self.uncertain_closes = tuple(uncertain_closes)


def _require(value, reason):
    if not value:
        raise ValueError(reason)


class DurableCaptureWriter:
    """Callable persistence adapter for CaptureAttempts, not a release proof.

    A successful persist means file data was fsynced, its descriptor closed once,
    and the held directory fsynced. It does not claim disk failure immunity or
    authenticate the caller's directory label. Failed writes leave their files
    and evidence in place; use a new operator decision, never replay this writer.
    """
    def __init__(self, directory_fd, directory_label):
        _require(type(directory_fd) is int and directory_fd >= 3, 'JOURNAL_DIRECTORY_FD')
        _require(type(directory_label) is str and directory_label.startswith('/')
                 and str(PurePosixPath(directory_label)) == directory_label
                 and '..' not in PurePosixPath(directory_label).parts, 'JOURNAL_DIRECTORY_LABEL')
        observed = os.fstat(directory_fd)
        _require(stat.S_ISDIR(observed.st_mode) and stat.S_IMODE(observed.st_mode) == 0o700
                 and observed.st_uid == os.getuid(), 'JOURNAL_PRIVATE_DIRECTORY')
        _require(os.listdir(directory_fd) == [], 'JOURNAL_FRESH_EMPTY_DIRECTORY')
        self._fd = directory_fd
        self._owner = (os.getpid(), threading.get_ident())
        self._label = directory_label
        self._binding = (observed.st_dev, observed.st_ino, observed.st_mode, observed.st_uid)
        self._records = []
        self._next = 0
        self._busy = False
        self._sealed = False
        self._unknown = None

    def records(self):
        """Reported successful snapshots; independent inventory audit still required."""
        return tuple(deepcopy(self._records))

    def __call__(self, snapshot):
        _require((os.getpid(), threading.get_ident()) == self._owner,
                 'JOURNAL_ORIGINAL_SERIAL_OWNER_REQUIRED')
        if self._unknown is not None:
            raise self._unknown
        _require(not self._busy and not self._sealed and self._next < MAX_RECORDS,
                 'JOURNAL_WRITER_NOT_OPEN')
        _require(type(snapshot) is dict and set(snapshot) == {
            'schema', 'state', 'attempts', 'resource_release_authorized'}, 'JOURNAL_SNAPSHOT_FIELDS')
        _require(snapshot['schema'] == SCHEMA and snapshot['resource_release_authorized'] is False
                 and snapshot['state'] in ('INTENT', 'OUTCOME', 'SEALED'), 'JOURNAL_SNAPSHOT_STATE')
        raw = (json.dumps(snapshot, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, allow_nan=False) + '\n').encode()
        _require(0 < len(raw) <= MAX_SNAPSHOT, 'JOURNAL_SNAPSHOT_BOUND')
        number = self._next
        self._next += 1
        self._busy = True
        name = f'{number:06d}.json'
        record = dict(index=number, name=name, phase='BIND_DIRECTORY',
                      path=str(PurePosixPath(self._label) / name),
                      snapshot_state=snapshot['state'], bytes=len(raw),
                      sha256=hashlib.sha256(raw).hexdigest(),
                      file_created=False, file_fsynced=False, file_closed=False,
                      directory_fsynced=False, resource_release_authorized=False)
        opened = None
        uncertain = []
        retained = []
        try:
            observed = os.fstat(self._fd)
            _require((observed.st_dev, observed.st_ino, observed.st_mode, observed.st_uid)
                     == self._binding, 'JOURNAL_DIRECTORY_BINDING_CHANGED')
            _require(set(os.listdir(self._fd)) == {r['name'] for r in self._records},
                     'JOURNAL_DIRECTORY_INVENTORY_CHANGED')
            record['phase'] = 'OPEN_EXCLUSIVE'
            opened = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                             | os.O_CLOEXEC, 0o600, dir_fd=self._fd)
            record['file_created'] = True
            st = os.fstat(opened)
            record['opened_identity'] = identity(st)
            _require(stat.S_ISREG(st.st_mode) and stat.S_IMODE(st.st_mode) == 0o600
                     and st.st_uid == os.getuid() and st.st_nlink == 1 and st.st_size == 0,
                     'JOURNAL_PRIVATE_NEW_FILE')
            record['phase'] = 'WRITE'
            offset = 0
            while offset < len(raw):
                count = os.write(opened, raw[offset:])
                _require(type(count) is int and 0 < count <= len(raw)-offset,
                         'JOURNAL_SHORT_OR_INVALID_WRITE')
                offset += count
            record['phase'] = 'FSYNC_FILE'
            os.fsync(opened)
            record['file_fsynced'] = True
            record['phase'] = 'CLOSE_FILE'
            stamp = identity(os.fstat(opened))
            record['preclose_identity'] = stamp
            _require(stamp[2] == len(raw)
                     and (stamp[0], stamp[1], stamp[5], stamp[6], stamp[7])
                     == (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_nlink),
                     'JOURNAL_WRITTEN_FILE_CHANGED')
            _require(identity(os.stat(name, dir_fd=self._fd, follow_symlinks=False)) == stamp,
                     'JOURNAL_VISIBLE_FILE_CHANGED')
            closing = opened
            opened = None  # consume before close; never inspect/retry after uncertainty
            try:
                os.close(closing)
            except BaseException as error:
                uncertain.append(dict(fd=closing, role='journal-snapshot',
                                      preclose_identity=stamp, error=repr(error), numeric_retry=False))
                raise
            record['file_closed'] = True
            record['phase'] = 'FSYNC_DIRECTORY'
            os.fsync(self._fd)
            record['directory_fsynced'] = True
            record['phase'] = 'DURABLE_REPORTED'
            self._records.append(deepcopy(record))
            self._sealed = snapshot['state'] == 'SEALED'
        except BaseException as original:
            if opened is not None:
                closing = opened
                opened = None
                try:
                    stamp = identity(os.fstat(closing))
                except BaseException as error:
                    retained.append(closing)
                    uncertain.append(dict(fd=closing, role='journal-snapshot',
                                          close_attempted=False, error=repr(error), numeric_retry=False))
                else:
                    try:
                        os.close(closing)
                    except BaseException as error:
                        uncertain.append(dict(fd=closing, role='journal-snapshot',
                                              preclose_identity=stamp, error=repr(error), numeric_retry=False))
            self._unknown = CaptureJournalWriteUnknown(record, original, retained, uncertain)
            raise self._unknown from original
        finally:
            self._busy = False
