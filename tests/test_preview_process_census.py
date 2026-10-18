import hashlib
import unittest
from scripts.preview_pipeline.process_census import check_process_capture, COMMAND

class ProcessCensusTests(unittest.TestCase):
    """Original synthetic bytes/reported wait facts; no process observations."""
    def fixture(self, raw=b' 12 /synthetic/app with spaces\n34 kernel_fixture\n'):
        intent=dict(schema='OWNED_PROCESS_CAPTURE_INTENT_V1',command=list(COMMAND),
                    indexName='owned-process-'+'a'*32,maximum_bytes=4194304,
                    signals_allowed=False,resource_release_authorized=False)
        actual=dict(pid=12345,returncode=0,reaped=True,other_group_members_absent_before_reap=True,
                    members_before_reap=[dict(pid=12345,state='Z')],timed_out=False,signals_sent=0)
        def record(name, data):return dict(path='/synthetic/'+name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),identity8=[])
        result=dict(schema='OWNED_PROCESS_CAPTURE_RESULT_V1',command=list(COMMAND),
                    intent=dict(path='/synthetic/INTENT.json',bytes=1,sha256='a'*64),actual=actual,
                    stdout=record('stdout',raw),stderr=record('stderr',b''),owned_fds_closed=True,
                    caller_grants_released=False,signals_sent=0)
        return result,intent,raw,b''
    def test_spaces_are_part_of_command_and_no_release_authority(self):
        checked=check_process_capture(*self.fixture())
        self.assertEqual(checked.processes,((12,'/synthetic/app with spaces'),(34,'kernel_fixture')))
        self.assertFalse(checked.resource_release_authorized)
    def test_malformed_duplicate_truncated_or_control_rows_refused(self):
        for raw in (b'12 path',b'12 one\n12 two\n',b'0 path\n',b'notpid x\n',b'12 \x00x\n',b'12 x\nmalformed\n'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):check_process_capture(*self.fixture(raw))
    def test_command_or_intent_substitution_refused(self):
        for position in (0,1):
            values=list(self.fixture());values[position]['command']=['/synthetic/other']
            with self.assertRaises(ValueError):check_process_capture(*values)
    def test_all_wait_group_signal_fd_fault_mutations_refused(self):
        mutations=[('returncode',1),('returncode',False),('reaped',False),('timed_out',True),
                   ('signals_sent',1),('other_group_members_absent_before_reap',False),
                   ('members_before_reap',[dict(pid=12345,state='S')]),
                   ('members_before_reap',[dict(pid=12345,state='Z'),dict(pid=12346,state='Z')])]
        for key,value in mutations:
            result,intent,out,err=self.fixture();result['actual'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):check_process_capture(result,intent,out,err)
    def test_hash_size_stderr_and_ancestor_substitutions_refused(self):
        result,intent,out,err=self.fixture();result['stdout']['sha256']='0'*64
        with self.assertRaises(ValueError):check_process_capture(result,intent,out,err)
        with self.assertRaises(ValueError):check_process_capture(*self.fixture(),ancestor_pids=(12345,))
        values=list(self.fixture());values[3]=b'error'
        with self.assertRaises(ValueError):check_process_capture(*values)
    def test_unknown_fields_and_claimed_release_refused(self):
        for key,value in (('caller_grants_released',True),('owned_fds_closed',False),('extra',True)):
            values=list(self.fixture());values[0][key]=value
            with self.assertRaises(ValueError):check_process_capture(*values)

if __name__=='__main__':unittest.main()
