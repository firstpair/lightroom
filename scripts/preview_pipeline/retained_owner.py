"""Retained publication-worker finish ordering; source-bound callbacks required.

No spawning, signals, acquisition, automatic recovery or release authority is
provided here. The caller authenticates the real worker, helper audit, no-signal
settlement implementation and resource leases. Reported dictionaries alone never
establish those facts.
"""
import math
import time


class OwnerRetained(RuntimeError):
    def __init__(self, owner, original_error):
        super().__init__('PUBLICATION_OWNER_RETAIN_CHILD_AND_RESOURCE_CARRIERS')
        self.owner = owner
        self.original_error = original_error


class KnownClosedReportingError(RuntimeError):
    def __init__(self, owner):
        super().__init__('PUBLICATION_OWNER_KNOWN_CLOSED_REPORTING_FAILED')
        self.owner = owner
        self.reporting_errors = tuple(owner.reporting_errors)


class RetainedPublicationOwner:
    """Audit helpers before reap, reap before CPU close, CPU before IO close.

    Both leases stay strongly owned on any unknown helper/group/close result.
    Successful closes are consumed once. Persistence failures after a successful
    helper audit are reporting errors: they cannot invent a hold after all actual
    settlement/close steps succeed. No method starts another job or retries one.
    """
    def __init__(self, child, cpu, io):
        self.child, self.cpu, self.io = child, cpu, io
        self.started = False
        self.helper_audit = self.worker_closure = None
        self.cpu_closed = self.io_closed = False
        self.resources_closed = False
        self.original_error = None
        self.reporting_errors = []

    def _report(self, persist, name, value):
        try:
            persist(name, value)
        except BaseException as error:
            self.reporting_errors.append((name, error))

    def finish(self, observation_seconds, audit_helpers, settle_without_signals, persist):
        if (self.started or type(observation_seconds) not in (int, float)
                or not math.isfinite(observation_seconds) or observation_seconds <= 0
                or not all(callable(f) for f in (audit_helpers, settle_without_signals, persist))):
            raise ValueError('ONE_SHOT_RETAINED_OWNER_FINISH_CONFIGURATION')
        self.started = True
        try:
            if self.child.reaped or not self.child.await_terminal(observation_seconds):
                raise RuntimeError('PUBLICATION_WORKER_OUTCOME_UNKNOWN_NO_SIGNALS')
            self.helper_audit = audit_helpers(self.child)
            report = self.helper_audit
            if (type(report) is not dict or type(report.get('worker_pid')) is not int
                    or report['worker_pid'] != self.child.pid
                    or report.get('worker_still_unreaped') is not True
                    or report.get('all_reported_helpers_groups_fds_closed') is not True
                    or report.get('resource_release_authorized') is not False
                    or self.child.reaped or not self.child.terminal()):
                raise RuntimeError('PUBLICATION_HELPERS_OR_WORKER_RESERVATION_UNPROVEN')
            self._report(persist, 'HELPERS-AUDITED.json', report)
            self.worker_closure = settle_without_signals(self.child, time.monotonic()+5)
            closure = self.worker_closure
            if (type(closure) is not dict or type(closure.get('pid')) is not int
                    or closure['pid'] != self.child.pid or type(closure.get('returncode')) is not int
                    or closure.get('reaped') is not True
                    or closure.get('other_group_members_absent_before_reap') is not True
                    or closure.get('timed_out') is not False
                    or type(closure.get('signals_sent')) is not int or closure['signals_sent'] != 0
                    or self.child.reaped is not True):
                raise RuntimeError('PUBLICATION_ACTUAL_GROUP_WAIT4_UNPROVEN')
            self._report(persist, 'WORKER-CLOSED.json', closure)
            self.cpu.close_after_verified_settlement(
                owner_reaped=True, groups_settled=True, external_children_settled=True)
            self.cpu_closed = True
            self.io.close_after_verified_settlement(
                owner_reaped=True, groups_settled=True, external_children_settled=True)
            self.io_closed = True
            self.resources_closed = True
        except BaseException as error:
            self.original_error = error
            raise OwnerRetained(self, error) from error
        result = dict(state='PUBLICATION_WORKER_HELPERS_AND_RESOURCES_CLOSED',
                      actual_worker_wait=self.worker_closure, cpu_closed=True, io_closed=True,
                      worker_exit_success=self.worker_closure['returncode'] == 0,
                      publication_success_not_inferred=True, automatic_retry=False)
        self._report(persist, 'OWNER-CLOSED.json', result)
        if self.reporting_errors:
            raise KnownClosedReportingError(self)
        return result
