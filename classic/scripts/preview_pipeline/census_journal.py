"""One-shot capture-attempt accounting with caller-supplied persistence.

The caller supplies a qualified durable writer and authenticates its saved
journal. This module neither performs IO nor proves child or FD settlement.
An invocation or post-invocation persistence failure requires retained ownership.
"""
from copy import deepcopy
import hashlib

from .census_receipts import COMMAND, MAX_PROJECTION

SCHEMA = 'CAPTURE_ATTEMPTS_V1'


class CaptureAttemptUnknown(RuntimeError):
    def __init__(self, journal, original_error):
        super().__init__('CAPTURE_ATTEMPT_OR_OUTCOME_PERSISTENCE_UNKNOWN')
        self.journal = journal
        self.original_error = original_error


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def _pin(value):
    _require(type(value) is dict and set(value) == {'path', 'bytes', 'sha256'}, 'CAPTURE_PIN')
    _require(type(value['path']) is str and value['path'].startswith('/')
             and type(value['bytes']) is int and value['bytes'] > 0
             and type(value['sha256']) is str and len(value['sha256']) == 64
             and all(c in '0123456789abcdef' for c in value['sha256']), 'CAPTURE_PIN_VALUE')
    return deepcopy(value)


class CaptureAttempts:
    """Persist intent before invoke; persist successful outcome before returning.

    Any failed call permanently stops this instance. Never retry it or substitute
    a new journal to replay an uncertain attempt. Sealing is only the producer's
    reported end of its inventory, not independent completeness/release proof.
    """
    def __init__(self, persist, maximum=128):
        _require(callable(persist) and type(maximum) is int and 1 <= maximum <= 128,
                 'CAPTURE_JOURNAL_CONFIGURATION')
        self._persist = persist
        self._maximum = maximum
        self._state = 'OPEN'
        self._attempts = []

    def snapshot(self):
        return dict(schema=SCHEMA, state=self._state, attempts=deepcopy(self._attempts),
                    resource_release_authorized=False)

    def capture(self, invoke):
        _require(self._state == 'OPEN' and len(self._attempts) < self._maximum
                 and callable(invoke), 'CAPTURE_JOURNAL_NOT_OPEN')
        record = dict(index=len(self._attempts), command=list(COMMAND), state='INTENT')
        self._attempts.append(record)
        self._state = 'INTENT'
        try:
            self._persist(self.snapshot())
        except BaseException:
            self._state = 'STOPPED_BEFORE_INVOKE'
            raise  # no invocation occurred through this instance
        try:
            result = invoke()
            _require(type(result) is tuple and len(result) == 4, 'CAPTURE_RETURN_SHAPE')
            code, output, error, receipt = result
            _require(type(code) is int and code == 0 and type(output) is bytes
                     and 0 < len(output) <= MAX_PROJECTION
                     and type(error) is bytes and error == b'', 'CAPTURE_RETURN_NOT_SUCCESS')
            record.update(state='OUTCOME', receipt=_pin(receipt),
                          projected_bytes=len(output),
                          projected_sha256=hashlib.sha256(output).hexdigest())
            self._state = 'OUTCOME'
            self._persist(self.snapshot())
        except BaseException as error:
            self._state = 'UNKNOWN'
            raise CaptureAttemptUnknown(self.snapshot(), error) from error
        self._state = 'OPEN'
        return result

    def seal(self):
        _require(self._state == 'OPEN' and self._attempts, 'CAPTURE_JOURNAL_CANNOT_SEAL')
        self._state = 'SEALED'
        try:
            self._persist(self.snapshot())
        except BaseException as error:
            self._state = 'UNKNOWN'
            raise CaptureAttemptUnknown(self.snapshot(), error) from error
        return self.snapshot()


def check_sealed_inventory(journal, expected_pins, checked_captures):
    """Check a reported sealed success inventory against independently bound pins.

    Authentication and completeness still depend on the real producer, its
    durable writer, complete invocation prefix and unchanged source. This accepts
    no failure/unknown prefix and never authorizes a reap or resource release.
    """
    _require(type(journal) is dict and set(journal) == {
        'schema', 'state', 'attempts', 'resource_release_authorized'}, 'CAPTURE_JOURNAL_FIELDS')
    _require(journal['schema'] == SCHEMA and journal['state'] == 'SEALED'
             and journal['resource_release_authorized'] is False, 'CAPTURE_JOURNAL_NOT_SEALED')
    rows = journal['attempts']
    _require(type(rows) is list and 1 <= len(rows) <= 128
             and type(expected_pins) is list and len(expected_pins) == len(rows)
             and type(checked_captures) is tuple and len(checked_captures) == len(rows),
             'CAPTURE_JOURNAL_COUNT')
    seen = set()
    for index, (row, expected, checked) in enumerate(zip(rows, expected_pins, checked_captures)):
        _require(type(row) is dict and set(row) == {
            'index', 'command', 'state', 'receipt', 'projected_bytes', 'projected_sha256'},
            'CAPTURE_JOURNAL_ROW_FIELDS')
        _require(type(row['index']) is int and row['index'] == index
                 and row['command'] == COMMAND and row['state'] == 'OUTCOME',
                 'CAPTURE_JOURNAL_ORDER_OR_OUTCOME')
        pin = _pin(row['receipt'])
        _require(pin == _pin(expected) and pin['path'] not in seen, 'CAPTURE_JOURNAL_PIN')
        seen.add(pin['path'])
        _require(type(row['projected_bytes']) is int and row['projected_bytes'] > 0
                 and type(row['projected_sha256']) is str
                 and len(row['projected_sha256']) == 64
                 and all(c in '0123456789abcdef' for c in row['projected_sha256']),
                 'CAPTURE_JOURNAL_PROJECTION')
        _require(type(checked.projection) is bytes
                 and row['projected_bytes'] == len(checked.projection)
                 and row['projected_sha256'] == hashlib.sha256(checked.projection).hexdigest(),
                 'CAPTURE_JOURNAL_PROJECTION_BINDING')
    return tuple(deepcopy(expected_pins))
