"""Retained-parent capture audit. Never reaps or releases grants.

Caller authenticates the reported packet, source graph, worker identity and
runtime namespace. Actual ps-helper proof and full failed-prefix recovery remain
separate gates before this is installed into a live owner.
"""
import os
from pathlib import Path

from .census_files import identity
from .census_session import check_capture_session, check_unused_capture_session


def audit_before_reap(child, runtime, report, close_backend):
    if child.reaped or not child.terminal():
        raise ValueError('PARENT_RETAIN_UNREAPED_TERMINAL_WORKER_REQUIRED')
    root=Path(runtime)
    required={'schema','journal_root','capture_root','snapshot_pins','receipt_pins',
              'reported_captures','resource_release_authorized'}
    if (type(report) is not dict or set(report)!=required
        or report['schema'] not in ('CAPTURE_SESSION_REPORTED_V1','UNUSED_CAPTURE_SESSION_REPORTED_V1')
        or report['resource_release_authorized'] is not False
        or type(report['reported_captures']) is not int):
        raise ValueError('PARENT_EXACT_CAPTURE_REPORT_REQUIRED')
    carrier=dict(child=child,fds=[],uncertain_closes=[],original_error=None)
    try:
        pairs=[]
        for key,name in (('journal_root','capture-journal'),('capture_root','capture-files')):
            p=root/name;value=report[key]
            if (type(value) is not dict or set(value)!={'path','identity8'}
                or value['path']!=str(p)):
                raise ValueError('PARENT_CAPTURE_NAMESPACE_BINDING')
            fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            carrier['fds'].append(dict(fd=fd,role=key,path=str(p)))
            if identity(os.fstat(fd))!=tuple(value['identity8']) or identity(p.lstat())!=identity(os.fstat(fd)):
                raise ValueError('PARENT_CAPTURE_DIRECTORY_EPOCH')
            pairs.append((fd,str(p)))
        if report['schema']=='UNUSED_CAPTURE_SESSION_REPORTED_V1':
            checked=check_unused_capture_session(*pairs[0],*pairs[1],report)
        else:
            checked=check_capture_session(*pairs[0],report['snapshot_pins'],*pairs[1],
                                          close_backend.protected_roots,
                                          ancestor_pids=(os.getpid(),child.pid))
        expected=tuple((p['path'],p['bytes'],p['sha256']) for p in report['receipt_pins'])
        if checked.receipt_pins!=expected or len(checked.captures)!=report['reported_captures']:
            raise ValueError('PARENT_COMPLETE_CAPTURE_REPORT_BINDING')
        for record in carrier['fds']:
            if identity(os.fstat(record['fd']))!=identity(Path(record['path']).lstat()):
                raise ValueError('PARENT_CAPTURE_VISIBLE_DIRECTORY_CHANGED')
        if child.reaped or not child.terminal():
            raise ValueError('PARENT_WORKER_RESERVATION_LOST')
    except BaseException as error:
        carrier['original_error']=error
        close_backend.close_all(carrier)
        raise
    close_backend.close_all(carrier)
    return dict(schema='PARENT_CAPTURE_AUDIT_BEFORE_WORKER_REAP_V1',
                worker_pid=child.pid,worker_unreaped=True,captures=len(checked.captures),
                all_raw_receipt_projection_bindings=True,read_descriptors_closed=True,
                resource_release_authorized=False,worker_reap_performed=False,
                scope='Capture readback only. Actual ps helpers, publisher outcomes, worker group census/wait4 and grant closure remain caller obligations.')
