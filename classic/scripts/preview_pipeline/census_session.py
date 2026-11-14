"""Compose journal and raw-capture readback; no live process or release authority."""
from dataclasses import dataclass, field
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import stat
import threading

from .census_files import check_capture_files, identity
from .census_journal import CaptureAttempts, check_sealed_inventory
from .census_readback import CheckedJournal, check_journal_files
from .census_store import DurableCaptureWriter


@dataclass(frozen=True)
class CheckedCaptureSession:
    journal: CheckedJournal
    captures: tuple
    receipt_pins: tuple
    resource_release_authorized: bool = field(default=False, init=False)


def _require(value, reason):
    if not value:
        raise ValueError(reason)


class CaptureSessionStopped(RuntimeError):
    def __init__(self, session, original_error):
        super().__init__('CAPTURE_SESSION_STOPPED_NO_AUTOMATIC_REPLAY')
        self.session = session
        self.original_error = original_error


class CaptureSessionProducer:
    """Connect a caller-authenticated capture callback to durable attempt IO.

    The callback signature is (fresh_capture_root, protected_roots, deadline,
    maximum_projection), returning the four-part owned-capture result. Its
    source, actual child handling and command identity require qualification by
    the caller; accepting a callback does not authenticate those runtime facts.
    Both directory descriptors are borrowed and remain with the caller.
    """
    def __init__(self, journal_fd, journal_label, capture_fd, capture_label,
                 invoke, *, maximum=128):
        _require(callable(invoke), 'CAPTURE_SESSION_CALLBACK_REQUIRED')
        root = identity(os.fstat(capture_fd))
        _require(stat.S_ISDIR(root[5]) and stat.S_IMODE(root[5]) == 0o700
                 and root[6] == os.getuid() and os.listdir(capture_fd) == [],
                 'CAPTURE_SESSION_FRESH_PRIVATE_CAPTURE_ROOT')
        _require(root[:2] != identity(os.fstat(journal_fd))[:2],
                 'CAPTURE_SESSION_DISTINCT_NAMESPACES')
        _require(type(capture_label) is str and capture_label.startswith('/')
                 and str(PurePosixPath(capture_label)) == capture_label
                 and '..' not in PurePosixPath(capture_label).parts, 'CAPTURE_SESSION_ROOT_LABEL')
        self._capture_fd = capture_fd
        self._owner = (os.getpid(), threading.get_ident())
        self._capture_label = capture_label
        self._capture_binding = (root[0], root[1], root[5], root[6])
        journal_root = identity(os.fstat(journal_fd))
        self._journal_binding = (journal_root[0], journal_root[1], journal_root[5], journal_root[6])
        self._journal_fd = journal_fd
        self._journal_label = journal_label
        self._writer = DurableCaptureWriter(journal_fd, journal_label)
        self._journal = CaptureAttempts(self._writer, maximum)
        self._invoke = invoke
        self._names = set()
        self._stopped = None
        self._sealed = False

    def _fence(self):
        root = identity(os.fstat(self._capture_fd))
        _require((root[0], root[1], root[5], root[6]) == self._capture_binding
                 and set(os.listdir(self._capture_fd)) == self._names,
                 'CAPTURE_SESSION_PRODUCER_NAMESPACE_CHANGED')

    def _open(self):
        _require((os.getpid(), threading.get_ident()) == self._owner,
                 'CAPTURE_SESSION_ORIGINAL_SERIAL_OWNER_REQUIRED')
        if self._stopped is not None:
            raise self._stopped
        _require(not self._sealed, 'CAPTURE_SESSION_ALREADY_SEALED')

    def capture(self, protected_roots, deadline, maximum_projection):
        self._open()
        try:
            self._fence()
            response = self._journal.capture(lambda: self._invoke(
                Path(self._capture_label), protected_roots, deadline, maximum_projection))
            label = PurePosixPath(response[3]['path'])
            _require(str(label) == response[3]['path'] and label.name == 'RESULT.json'
                     and str(label.parent.parent) == self._capture_label
                     and re.fullmatch(r'owned-census-[0-9a-f]{32}', label.parent.name)
                     and label.parent.name not in self._names,
                     'CAPTURE_SESSION_CALLBACK_RECEIPT_NAMESPACE')
            self._names.add(label.parent.name)
            self._fence()
            return response
        except BaseException as error:
            self._stopped = CaptureSessionStopped(self, error)
            raise self._stopped from error

    def seal_unused(self):
        """Report no attempted callback, never a global descriptor exclusion."""
        self._open()
        try:
            self._fence()
            journal_root = identity(os.fstat(self._journal_fd))
            _require((journal_root[0], journal_root[1], journal_root[5], journal_root[6])
                     == self._journal_binding and os.listdir(self._journal_fd) == []
                     and self._writer.records() == ()
                     and self._journal.snapshot() == dict(
                         schema='CAPTURE_ATTEMPTS_V1', state='OPEN', attempts=[],
                         resource_release_authorized=False),
                     'UNUSED_CAPTURE_REQUIRES_NO_INTENT_OR_INVOCATION')
            self._sealed = True
            return dict(schema='UNUSED_CAPTURE_SESSION_REPORTED_V1',
                        journal_root=dict(path=self._journal_label, identity8=list(journal_root)),
                        capture_root=dict(path=self._capture_label,
                                          identity8=list(identity(os.fstat(self._capture_fd)))),
                        snapshot_pins=[], receipt_pins=[], reported_captures=0,
                        resource_release_authorized=False)
        except BaseException as error:
            self._stopped = CaptureSessionStopped(self, error)
            raise self._stopped from error

    def seal(self):
        """Report the durable inventory; the parent must independently re-audit it."""
        self._open()
        try:
            self._fence()
            snapshot = self._journal.seal()
            self._sealed = True
            pins = [{key:row[key] for key in ('path', 'bytes', 'sha256')}
                    for row in self._writer.records()]
            return dict(schema='CAPTURE_SESSION_REPORTED_V1',
                        journal_root=dict(path=self._journal_label,
                                          identity8=list(identity(os.fstat(self._journal_fd)))),
                        capture_root=dict(path=self._capture_label,
                                          identity8=list(identity(os.fstat(self._capture_fd)))),
                        snapshot_pins=pins,
                        receipt_pins=[row['receipt'] for row in snapshot['attempts']],
                        reported_captures=len(snapshot['attempts']),
                        resource_release_authorized=False)
        except BaseException as error:
            self._stopped = CaptureSessionStopped(self, error)
            raise self._stopped from error


def check_capture_session(journal_fd, journal_label, snapshot_pins,
                          capture_fd, capture_label, protected_roots, *, ancestor_pids=()):
    """Verify every sealed journal attempt against independently checked raw bytes.

    Both directories are borrowed, caller-authenticated private namespaces. The
    capture namespace must contain exactly the recorded capture directories.
    An unsealed/failed prefix is not accepted as success; its actual owners must
    remain with the caller until separately resolved. Source authentication and
    actual worker/parent terminal evidence remain separate prerequisites.
    """
    capture_root = identity(os.fstat(capture_fd))
    journal_root = identity(os.fstat(journal_fd))
    _require(stat.S_ISDIR(capture_root[5]) and stat.S_IMODE(capture_root[5]) == 0o700
             and capture_root[6] == os.getuid(), 'CAPTURE_SESSION_PRIVATE_ROOT')
    _require(capture_root[:2] != journal_root[:2], 'CAPTURE_SESSION_DISTINCT_NAMESPACES')
    journal = check_journal_files(journal_fd, journal_label, snapshot_pins)
    snapshot = journal.snapshot()
    pins = [row['receipt'] for row in snapshot['attempts']]
    names = {PurePosixPath(pin['path']).parent.name for pin in pins}
    _require(len(names) == len(pins) and set(os.listdir(capture_fd)) == names,
             'CAPTURE_SESSION_COMPLETE_CAPTURE_DIRECTORY_INVENTORY')
    checked = check_capture_files(capture_fd, capture_label, pins, protected_roots,
                                  ancestor_pids=ancestor_pids)
    bound = check_sealed_inventory(snapshot, pins, checked.captures)
    _require(identity(os.fstat(capture_fd)) == capture_root
             and set(os.listdir(capture_fd)) == names, 'CAPTURE_SESSION_ROOT_CHANGED')
    # A tuple of scalar pins cannot expose mutable journal dictionaries or FDs.
    immutable_pins = tuple((pin['path'], pin['bytes'], pin['sha256']) for pin in bound)
    return CheckedCaptureSession(journal, checked.captures, immutable_pins)


@dataclass(frozen=True)
class CheckedUnusedCaptureSession:
    captures: tuple = field(default=(), init=False)
    receipt_pins: tuple = field(default=(), init=False)
    resource_release_authorized: bool = field(default=False, init=False)


def check_unused_capture_session(journal_fd, journal_label, capture_fd, capture_label, report):
    """Check an authenticated producer's never-invoked branch, not file absence.

    Empty directories alone cannot prove history. The caller must authenticate
    the one-use producer and its source-bound persist-before-invoke contract.
    The result supplies no process observation or protected-path exclusion.
    """
    _require(type(report) is dict and set(report) == {
        'schema', 'journal_root', 'capture_root', 'snapshot_pins', 'receipt_pins',
        'reported_captures', 'resource_release_authorized'}, 'UNUSED_CAPTURE_REPORT_FIELDS')
    _require(report['schema'] == 'UNUSED_CAPTURE_SESSION_REPORTED_V1'
             and report['snapshot_pins'] == [] and report['receipt_pins'] == []
             and type(report['reported_captures']) is int and report['reported_captures'] == 0
             and report['resource_release_authorized'] is False, 'UNUSED_CAPTURE_REPORT_SCOPE')
    seen = set()
    for key, fd, label in (('journal_root', journal_fd, journal_label),
                           ('capture_root', capture_fd, capture_label)):
        before = identity(os.fstat(fd))
        _require(stat.S_ISDIR(before[5]) and stat.S_IMODE(before[5]) == 0o700
                 and before[6] == os.getuid() and before[:2] not in seen
                 and report[key] == dict(path=label, identity8=list(before)),
                 'UNUSED_CAPTURE_DISTINCT_PRIVATE_ROOT_BINDING')
        seen.add(before[:2])
        _require(os.listdir(fd) == [] and identity(os.fstat(fd)) == before,
                 'UNUSED_CAPTURE_NONEMPTY_OR_CHANGED_ROOT')
    return CheckedUnusedCaptureSession()
