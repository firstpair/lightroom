"""Actual temp-file readback; all worker and capture process facts are doubles."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from tests import test_preview_census_session as fixtures
from scripts.preview_pipeline.census_session import CaptureSessionProducer
from scripts.preview_pipeline import census_parent as parent

def close_double(carrier):
    # Explicit contract double; private qualification separately exercises the
    # existing source-bound close carrier. This does not prove uncertain close.
    while carrier['fds']:
        os.close(carrier['fds'].pop()['fd'])

class ParentTests(unittest.TestCase):
    fake_capture=fixtures.CaptureSessionTests.fake_capture
    def setUp(self):
        fixtures.CaptureSessionTests.setUp(self)
        self.journal_root.rename(self.root/'capture-journal');self.journal_root=self.root/'capture-journal'
        self.capture_root.rename(self.root/'capture-files');self.capture_root=self.root/'capture-files'
        self.child=SimpleNamespace(pid=43210,reaped=False,terminal=lambda:True)
        self.backend=SimpleNamespace(close_all=close_double,protected_roots=self.roots)
        producer=CaptureSessionProducer(self.journal_fd,str(self.journal_root),self.capture_fd,str(self.capture_root),lambda *args:self.fake_capture(0))
        producer.capture(self.roots,1,10000);self.report=producer.seal()
    def run_audit(self):return parent.audit_before_reap(self.child,self.root,self.report,self.backend)
    def test_actual_readback_does_not_reap_worker_or_release_grants(self):
        result=self.run_audit()
        self.assertTrue(result['worker_unreaped']);self.assertFalse(self.child.reaped)
        self.assertFalse(result['worker_reap_performed']);self.assertFalse(result['resource_release_authorized'])
        self.assertEqual(result['captures'],1)
        os.fstat(self.journal_fd);os.fstat(self.capture_fd)
    def test_live_or_already_reaped_worker_is_not_a_terminal_reservation(self):
        for reaped,terminal in ((True,True),(False,False)):
            self.child.reaped=reaped;self.child.terminal=lambda:terminal
            with self.assertRaisesRegex(ValueError,'UNREAPED_TERMINAL'):self.run_audit()
    def test_root_substitution_and_report_omission_refused(self):
        self.report['capture_root']['path']=str(self.root/'other')
        with self.assertRaisesRegex(ValueError,'NAMESPACE'):self.run_audit()
    def test_unreported_capture_count_or_receipt_refused(self):
        self.report['reported_captures']=2
        with self.assertRaisesRegex(ValueError,'COMPLETE_CAPTURE'):self.run_audit()
    def test_worker_reservation_rechecked_after_raw_audit(self):
        calls=[]
        def terminal():
            calls.append(True)
            return len(calls)==1
        self.child.terminal=terminal
        with self.assertRaisesRegex(ValueError,'RESERVATION_LOST'):self.run_audit()
        self.assertFalse(self.child.reaped)

if __name__=='__main__':unittest.main()
