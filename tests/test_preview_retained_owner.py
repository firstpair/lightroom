"""Ordering/failure controls; every process, lease and persistence fact is a double."""
from types import SimpleNamespace
import unittest
from scripts.preview_pipeline.retained_owner import RetainedPublicationOwner, OwnerRetained, KnownClosedReportingError

class RetainedOwnerTests(unittest.TestCase):
    def setUp(self):
        self.events=[];self.waited=0;self.code=0
        self.child=SimpleNamespace(pid=12345,reaped=False,terminal=lambda:True,
                                   await_terminal=lambda timeout:self.events.append('terminal')or True)
        def close(role):
            self.events.append(role)
        self.cpu=SimpleNamespace(close_after_verified_settlement=lambda **kw:close('cpu'))
        self.io=SimpleNamespace(close_after_verified_settlement=lambda **kw:close('io'))
        self.owner=RetainedPublicationOwner(self.child,self.cpu,self.io)
    def audit(self,child):
        self.events.append('audit');self.assertFalse(child.reaped)
        return dict(worker_pid=child.pid,worker_still_unreaped=True,
                    all_reported_helpers_groups_fds_closed=True,resource_release_authorized=False)
    def settle(self,child,deadline):
        self.events.append('wait4');self.waited+=1;child.reaped=True
        return dict(pid=child.pid,returncode=self.code,reaped=True,
                    other_group_members_absent_before_reap=True,timed_out=False,signals_sent=0)
    def persist(self,name,value):self.events.append(name)
    def finish(self,**kw):
        return self.owner.finish(1,kw.get('audit',self.audit),kw.get('settle',self.settle),kw.get('persist',self.persist))
    def test_success_order_helper_audit_before_wait_before_reverse_close(self):
        result=self.finish();self.assertEqual(self.events,['terminal','audit','HELPERS-AUDITED.json','wait4','WORKER-CLOSED.json','cpu','io','OWNER-CLOSED.json'])
        self.assertTrue(self.owner.resources_closed);self.assertTrue(result['publication_success_not_inferred'])
    def test_known_failed_worker_still_closes_without_false_functional_pass(self):
        self.code=7;result=self.finish();self.assertFalse(result['worker_exit_success']);self.assertTrue(self.owner.resources_closed)
    def test_observation_timeout_neither_reaps_nor_closes(self):
        self.child.await_terminal=lambda _:False
        with self.assertRaises(OwnerRetained):self.finish()
        self.assertEqual((self.waited,self.events),(0,[]));self.assertFalse(self.owner.resources_closed)
    def test_helper_audit_failure_keeps_original_cause_and_both_leases(self):
        error=RuntimeError('original missing helper outcome')
        def audit(_):raise error
        with self.assertRaises(OwnerRetained)as caught:self.finish(audit=audit)
        self.assertIs(caught.exception.original_error,error);self.assertIs(caught.exception.owner.cpu,self.cpu)
        self.assertEqual(self.waited,0);self.assertFalse(self.child.reaped)
    def test_false_helper_binding_or_release_claim_refused_before_reap(self):
        for field,value in (('worker_pid',False),('worker_pid',999),('worker_still_unreaped',False),('resource_release_authorized',True)):
            self.setUp()
            def audit(child):
                report=self.audit(child);report[field]=value;return report
            with self.subTest(field=field),self.assertRaises(OwnerRetained):self.finish(audit=audit)
            self.assertEqual(self.waited,0)
    def test_group_settlement_unknown_does_not_close_or_retry(self):
        error=RuntimeError('original group census uncertainty')
        def settle(*_):raise error
        with self.assertRaises(OwnerRetained)as caught:self.finish(settle=settle)
        self.assertIs(caught.exception.original_error,error);self.assertNotIn('cpu',self.events)
        with self.assertRaises(ValueError):self.finish()
    def test_malformed_or_signalling_settlement_does_not_release(self):
        def settle(child,deadline):
            result=self.settle(child,deadline);result['signals_sent']=1;return result
        with self.assertRaises(OwnerRetained):self.finish(settle=settle)
        self.assertNotIn('cpu',self.events)
    def test_cpu_close_uncertainty_preserves_io_and_never_numeric_retries(self):
        error=OSError('original cpu close carrier')
        def close(**_):self.events.append('cpu-attempt');raise error
        self.cpu.close_after_verified_settlement=close
        with self.assertRaises(OwnerRetained)as caught:self.finish()
        self.assertIs(caught.exception.original_error,error);self.assertTrue(self.child.reaped)
        self.assertFalse(self.owner.cpu_closed);self.assertNotIn('io',self.events)
        with self.assertRaises(ValueError):self.finish()
        self.assertEqual(self.events.count('cpu-attempt'),1)
    def test_io_close_uncertainty_consumes_successful_cpu_close_once(self):
        def close(**_):self.events.append('io-attempt');raise OSError('original io uncertainty')
        self.io.close_after_verified_settlement=close
        with self.assertRaises(OwnerRetained):self.finish()
        self.assertTrue(self.owner.cpu_closed);self.assertFalse(self.owner.io_closed)
        self.assertEqual(self.events.count('cpu'),1)
    def test_parent_report_failure_after_audit_does_not_invent_hold_after_actual_close(self):
        error=OSError('original report fsync failure')
        def persist(name,value):self.events.append(name);raise error
        with self.assertRaises(KnownClosedReportingError)as caught:self.finish(persist=persist)
        self.assertTrue(caught.exception.owner.resources_closed);self.assertEqual(self.waited,1)
        self.assertEqual(len(caught.exception.reporting_errors),3)
        self.assertTrue(all(value is error for _,value in caught.exception.reporting_errors))
    def test_settlement_error_retains_reporting_error_as_well(self):
        def persist(*_):raise OSError('original reporting error')
        error=RuntimeError('original wait failure')
        def settle(*_):raise error
        with self.assertRaises(OwnerRetained)as caught:self.finish(persist=persist,settle=settle)
        self.assertIs(caught.exception.original_error,error);self.assertEqual(len(self.owner.reporting_errors),1)
    def test_successful_finish_cannot_be_reused(self):
        self.finish()
        with self.assertRaises(ValueError):self.finish()
        self.assertEqual(self.waited,1);self.assertEqual(self.events.count('cpu'),1)

if __name__=='__main__':unittest.main()
