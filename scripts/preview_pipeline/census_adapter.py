"""Journal an existing owned capture backend without widening its call surface.

The caller authenticates the backend/source graph and owns both directory FDs.
This adapter neither acquires resources nor establishes release authority.
"""
from pathlib import Path

from .census_session import CaptureSessionProducer, CaptureSessionStopped


class JournaledCaptureBackend:
    """Preserve a host's capture exception contract and fixed root arguments.

    A host may install this in place of its authenticated backend only in a new,
    explicitly source-bound worker. Existing host pre/post source and receipt
    checks must remain in place. Unsealed attempts, including known backend
    refusals, conservatively retain the session for independent recovery.
    """
    def __init__(self, backend, expected_root, protected_roots,
                 journal_fd, journal_label, capture_fd, capture_label):
        if not callable(getattr(backend, 'capture', None)):
            raise ValueError('OWNED_CAPTURE_BACKEND_REQUIRED')
        if not (isinstance(backend.CaptureUnknown, type)
                and issubclass(backend.CaptureUnknown, Exception)
                and isinstance(backend.CaptureRefusal, type)
                and issubclass(backend.CaptureRefusal, Exception)):
            raise ValueError('OWNED_CAPTURE_EXCEPTION_CONTRACT_REQUIRED')
        if not isinstance(expected_root, Path):
            raise ValueError('OWNED_CAPTURE_ROOT_PATH_REQUIRED')
        if not (type(protected_roots) is tuple and protected_roots
                and all(type(root) is str for root in protected_roots)):
            raise ValueError('OWNED_CAPTURE_FIXED_PROTECTED_ROOTS_REQUIRED')
        self.CaptureUnknown = backend.CaptureUnknown
        self.CaptureRefusal = backend.CaptureRefusal
        self._backend = backend
        self._expected_root = expected_root
        self._protected_roots = protected_roots
        self._session = CaptureSessionProducer(
            journal_fd, journal_label, capture_fd, capture_label, backend.capture)
        self._stopped = None

    def _unknown(self, error):
        # Strong references preserve the session, backend's actual child/FD
        # carrier and any combined close uncertainty; do not serialize instead.
        carrier = dict(adapter=self, session=self._session, backend=self._backend,
                       original_error=error)
        self._stopped = self.CaptureUnknown('JOURNALED_CAPTURE_RETAINED', carrier)
        raise self._stopped from error

    def capture(self, root, protected_roots, deadline, maximum_projection):
        if self._stopped is not None:
            raise self._stopped
        if root != self._expected_root or protected_roots != self._protected_roots:
            self._unknown(ValueError('OWNED_CAPTURE_CALL_SCOPE_CHANGED'))
        try:
            return self._session.capture(protected_roots, deadline, maximum_projection)
        except CaptureSessionStopped as error:
            self._unknown(error)

    def seal(self):
        """Return reported inventory, never parent audit or release permission."""
        if self._stopped is not None:
            raise self._stopped
        try:
            return self._session.seal()
        except CaptureSessionStopped as error:
            self._unknown(error)
