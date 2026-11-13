"""Drive bounded preview phases without replacing their execution authorities.

Adapters own preparation, processes, resources and receipt authentication. A
controller never grants an admission or closes an adapter's resources. Exceptions
retain the queue, claim and adapter together; there is no automatic replay.
"""
import copy
from dataclasses import dataclass

from .work_queue import QueueOwnershipUnknown, UnsettledBatch, pin


PHASES = ('recognize', 'publish', 'stage', 'render')
RETAINED = []


@dataclass(frozen=True)
class Outcome:
    receipt: dict
    actual_wait: dict
    successful: bool


class ControllerOwnershipUnknown(RuntimeError):
    def __init__(self, controller, original):
        super().__init__('PHASE_OWNER_RETAINED_NO_REPLAY')
        self.controller, self.original = controller, original
        RETAINED.append(controller)


class PhaseFailed(RuntimeError):
    def __init__(self, claim, outcome):
        super().__init__('KNOWN_CLOSED_PHASE_FAILED_NO_REPLAY')
        self.claim, self.outcome = claim, outcome


def settled(outcome):
    if type(outcome) is not Outcome or type(outcome.successful) is not bool:
        raise ValueError('TYPED_PHASE_OUTCOME_REQUIRED')
    pin(outcome.receipt)
    w = outcome.actual_wait
    fields = {'pid', 'returncode', 'reaped', 'other_group_members_absent_before_reap',
              'members_before_reap', 'timed_out', 'scope'}
    if (type(w) is not dict or set(w) != fields or type(w['pid']) is not int
            or w['pid'] < 2 or type(w['returncode']) is not int
            or w['reaped'] is not True or w['timed_out'] is not False
            or w['other_group_members_absent_before_reap'] is not True
            or w['members_before_reap'] != [dict(pid=w['pid'], state='Z')]
            or w['scope'] != 'owned group only; separate sessions require independently audited proofs'
            or (outcome.successful and w['returncode'] != 0)):
        raise ValueError('ACTUAL_PHASE_CHILD_SETTLEMENT_REQUIRED')


class Controller:
    """Adapters implement execute(claim) and authenticate(claim, outcome).

    execute must retain every process/resource carrier on the adapter before
    launch. authenticate must verify exact claim membership, receipt bytes,
    functional checks and ALL contained/helper/group/FD settlements, including
    separate sessions. Returning literal True is its authenticated disposition.
    A top-level wait alone never establishes those facts.
    """

    def __init__(self, queue, adapters):
        if type(adapters) is not dict or set(adapters) != set(PHASES):
            raise ValueError('ALL_FOUR_EXPLICIT_PHASE_ADAPTERS_REQUIRED')
        for adapter in adapters.values():
            if not callable(getattr(adapter, 'execute', None)) or not callable(
                    getattr(adapter, 'authenticate', None)):
                raise ValueError('EXECUTION_AND_AUTHENTICATION_ADAPTER_REQUIRED')
        self.queue, self.adapters = queue, dict(adapters)
        self.claim = self.adapter = self.outcome = None
        self.unknown = False

    def _retain(self, error):
        self.unknown = True
        raise ControllerOwnershipUnknown(self, error) from error

    def advance(self, *, maximum_records=8):
        if type(maximum_records) is not int or not 1 <= maximum_records <= 8:
            raise ValueError('QUALIFIED_FINITE_PHASE_SIZE')
        if self.unknown or self.claim is not None:
            raise UnsettledBatch('CONTROLLER_OWNER_UNSETTLED')
        # Finish already-started photos before admitting another render window.
        for phase in PHASES:
            try:
                claim = self.queue.claim(phase, limit=maximum_records)
            except QueueOwnershipUnknown as error:
                self._retain(error)
            if claim is None:
                continue
            self.claim, self.adapter = claim, self.adapters[phase]
            try:
                self.outcome = copy.deepcopy(self.adapter.execute(copy.deepcopy(claim)))
                settled(self.outcome)
                if self.adapter.authenticate(copy.deepcopy(claim),
                                             copy.deepcopy(self.outcome)) is not True:
                    raise ValueError('FULL_PHASE_AUTHENTICATION_REQUIRED')
                if self.outcome.successful:
                    self.queue.finish(claim['id'], self.outcome.receipt)
                else:
                    self.queue.hold(claim['id'], self.outcome.receipt)
            except BaseException as error:
                self._retain(error)
            outcome = self.outcome
            self.claim = self.adapter = self.outcome = None
            if not outcome.successful:
                raise PhaseFailed(claim, outcome)
            return dict(phase=phase, records=len(claim['records']),
                        receipt=outcome.receipt)
        return None

    def drain(self, *, maximum_completed=10000, maximum_actions=5000):
        if (type(maximum_completed) is not int or not 1 <= maximum_completed <= 10000
                or type(maximum_actions) is not int or not 1 <= maximum_actions <= 5000):
            raise ValueError('BOUNDED_CONTINUOUS_WINDOW_REQUIRED')
        completed = actions = 0
        while actions < maximum_actions and completed < maximum_completed:
            # Never start another photo window after reaching the requested bound.
            # Adapters still receive at most the qualified eight-record claim.
            event = self.advance(maximum_records=min(8, maximum_completed - completed))
            if event is None:
                break
            actions += 1
            if event['phase'] == 'recognize':
                completed += event['records']
        return dict(actions=actions, completed=completed,
                    stopped_at_bound=(actions == maximum_actions or
                                      completed >= maximum_completed))
