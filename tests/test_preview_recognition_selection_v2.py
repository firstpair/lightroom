import copy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
from scripts.preview_pipeline import recognition_selection_v2 as selection
from test_preview_recognition_selection import publication

def direct():
 p=publication();p['state']='EIGHT_ORIGINAL_STANDARD_INSERTS_DIRECT_WORKER_VERIFIED_V2';del p['priorRootToolTerminal']
 raw=dict(pid=123,returncode=0,reaped=True,other_group_members_absent_before_reap=True,members_before_reap=[dict(pid=123,state='Z')],timed_out=False,signals_sent=0)
 p['actualWorkerWait']={k:v for k,v in raw.items()if k!='signals_sent'};p['actualWorkerWait']['scope']='owned group only; separate sessions require independently audited proofs'
 p['publicationWorkerTerminal']=dict(schema='DIRECT_PUBLICATION_WORKER_TERMINAL_V1',actualWait=raw,phaseReceipt=dict(path='/synthetic/phase.json',bytes=100,sha256='b'*64),helpersSettled=True,ioCPUClosed=True)
 return p
class DirectSelectionTests(unittest.TestCase):
 pin=dict(path='/synthetic/audit.json',bytes=100,sha256='a'*64)
 def test_all_pairs_preserve_actual_worker_without_tool_event(self):
  p=direct();before=copy.deepcopy(p)
  for pair in selection.PAIRS:
   v=selection.project_pair(p,self.pin,list(pair));self.assertEqual(len(v['records']),2);self.assertNotIn('priorRootToolTerminal',v);self.assertEqual(v['publicationWorkerTerminal'],p['publicationWorkerTerminal']);v['publicationWorkerTerminal']['actualWait']['pid']=1;self.assertEqual(p,before)
 def test_private_file_loader_can_use_the_contract(self):
  import importlib.util
  path=Path(__file__).resolve().parents[1]/'scripts/preview_pipeline/recognition_selection_v2.py'
  spec=importlib.util.spec_from_file_location('original_private_loader_control',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  self.assertEqual(len(module.project_pair(direct(),self.pin,[1,2])['records']),2)
 def test_legacy_or_invented_tool_receipt_does_not_pass(self):
  with self.assertRaises(ValueError):selection.project_pair(publication(),self.pin,[1,2])
  p=direct();p['priorRootToolTerminal']=dict(session=12,exitCode=0,noRunningSession=True)
  with self.assertRaises(ValueError):selection.project_pair(p,self.pin,[1,2])
 def test_missing_settlement_or_different_actual_wait_refused(self):
  for fault in ('helper','io','pid','signal','pending','otherkey'):
   p=direct()
   if fault=='helper':p['publicationWorkerTerminal']['helpersSettled']=False
   elif fault=='io':p['publicationWorkerTerminal']['ioCPUClosed']=False
   elif fault=='pid':p['publicationWorkerTerminal']['actualWait']['pid']=999
   elif fault=='signal':p['publicationWorkerTerminal']['actualWait']['signals_sent']=1
   elif fault=='pending':p['actualWorkerWait']['reaped']=False
   else:p['records'][7]['selectedSQLRowsExact']=False
   with self.subTest(fault=fault),self.assertRaises(ValueError):selection.project_pair(p,self.pin,[1,2])
if __name__=='__main__':unittest.main()
