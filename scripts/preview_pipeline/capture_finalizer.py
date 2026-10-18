"""One-shot worker-side capture finalization, without release authority.

Callers authenticate sessions, complete attempt accounting, persistence and the
directory-close implementation. A session's own seal validates whether it was
used. Incomplete attempts cannot become an unused report by choosing False.
No child is started, signalled or reaped, and no reservation is released here.
"""


class FinalizationRetained(RuntimeError):
    def __init__(self, owner, failure):
        super().__init__('CAPTURE_FINALIZATION_RETAIN_OWNER_NO_RETRY')
        self.owner = owner
        self.original_failure = owner.original_failure
        self.finalization_failure = failure


class ClosedFinalizationReportingError(RuntimeError):
    def __init__(self, owner, failure):
        super().__init__('CAPTURE_DIRECTORIES_CLOSED_REPORTING_FAILED')
        self.owner = owner
        self.original_failure = owner.original_failure
        self.reporting_failure = failure


class CaptureFinalizer:
    """Keep sessions and their close carrier alive through every failure.

    Directory closure follows both durable reports. A final reporting error
    after acknowledged closure does not invent a descriptor hold. Neither a
    report nor this object replaces the parent's independent helper audit.
    """
    def __init__(self, process_session, descriptor_session, directory_owner):
        self.process_session = process_session
        self.descriptor_session = descriptor_session
        self.directory_owner = directory_owner
        self.started = False
        self.original_failure = self.finalization_failure = None
        self.process_report = self.descriptor_report = None
        self.close_attempted = self.directories_closed = False

    def finish(self, *, process_used, descriptor_used, persist,
               close_directories, original_failure=None):
        if (self.started or type(process_used) is not bool
                or type(descriptor_used) is not bool
                or not callable(persist) or not callable(close_directories)
                or (original_failure is not None
                    and not isinstance(original_failure, BaseException))):
            raise ValueError('ONE_SHOT_CAPTURE_FINALIZATION_CONFIGURATION')
        self.started = True
        self.original_failure = original_failure
        try:
            self.process_report = (self.process_session.seal() if process_used
                                   else self.process_session.seal_unused())
            persist('PROCESS-SESSION.json', self.process_report)
            self.descriptor_report = (self.descriptor_session.seal() if descriptor_used
                                      else self.descriptor_session.seal_unused())
            persist('CAPTURE-SESSION.json', self.descriptor_report)
            self.close_attempted = True
            # The caller must positively acknowledge its actual one-shot close.
            if close_directories(self.directory_owner) is not True:
                raise RuntimeError('CAPTURE_DIRECTORY_CLOSE_UNPROVEN')
            self.directories_closed = True
        except BaseException as failure:
            self.finalization_failure = failure
            raise FinalizationRetained(self, failure) from failure
        result = dict(state='CAPTURE_REPORTS_SAVED_DIRECTORIES_CLOSED',
                      capture_directory_descriptors_closed=True,
                      worker_operation_success_not_inferred=True,
                      parent_helper_audit_still_required=True,
                      resource_release_authorized=False)
        try:
            persist('CAPTURE-FINALIZED.json', result)
        except BaseException as failure:
            raise ClosedFinalizationReportingError(self, failure) from failure
        return result
