"""Actual empty tempfile namespaces; no process, capture or exclusion proof."""
import os
import unittest
from tests import test_preview_census_session as fixtures
from scripts.preview_pipeline.census_session import CaptureSessionProducer,CaptureSessionStopped,check_unused_capture_session

class UnusedTests(unittest.TestCase):
    setUp=fixtures.CaptureSessionTests.setUp
    fake_capture=fixtures.CaptureSessionTests.fake_capture
    def producer(self):
        return CaptureSessionProducer(self.journal_fd,str(self.journal_root),self.capture_fd,str(self.capture_root),lambda*a:self.fake_capture(0))
    def check(self,report):
        return check_unused_capture_session(self.journal_fd,str(self.journal_root),self.capture_fd,str(self.capture_root),report)
    def test_unused_branch_has_no_observation_or_release_authority(self):
        producer=self.producer();report=producer.seal_unused();result=self.check(report)
        self.assertEqual(result.captures,());self.assertFalse(result.resource_release_authorized)
        self.assertEqual((self.receipts,os.listdir(self.journal_fd),os.listdir(self.capture_fd)),([],[],[]))
        with self.assertRaises(ValueError):producer.capture(self.roots,1,1000)
    def test_attempted_capture_cannot_be_relabelled_uninvoked(self):
        producer=self.producer();producer.capture(self.roots,1,1000)
        with self.assertRaises(CaptureSessionStopped):producer.seal_unused()
        self.assertEqual(len(self.receipts),1)
    def test_partially_written_intent_blocks_unused_report(self):
        producer=self.producer();(self.journal_root/'000000.json').write_text('original partial intent')
        with self.assertRaises(CaptureSessionStopped):producer.seal_unused()
    def test_unreported_capture_directory_blocks_unused_report(self):
        producer=self.producer();(self.capture_root/'owned-census-original').mkdir(mode=0o700)
        with self.assertRaises(CaptureSessionStopped):producer.seal_unused()
    def test_reader_refuses_new_intent_and_preserves_borrowed_fds(self):
        report=self.producer().seal_unused();(self.journal_root/'000000.json').write_text('original intent')
        with self.assertRaises(ValueError):self.check(report)
        os.fstat(self.journal_fd);os.fstat(self.capture_fd)
    def test_wrong_schema_count_and_release_claim_refused(self):
        for key,value in (('schema','CAPTURE_SESSION_REPORTED_V1'),('reported_captures',False),('reported_captures',1),('resource_release_authorized',True)):
            self.setUp();report=self.producer().seal_unused();report[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(report)
    def test_same_root_or_changed_label_cannot_substitute(self):
        report=self.producer().seal_unused()
        with self.assertRaises(ValueError):check_unused_capture_session(self.journal_fd,str(self.journal_root),self.journal_fd,str(self.capture_root),report)
        with self.assertRaises(ValueError):check_unused_capture_session(self.journal_fd,str(self.journal_root),self.capture_fd,'/synthetic/wrong',report)

if __name__=='__main__':unittest.main()
