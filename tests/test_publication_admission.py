import copy
import unittest
from scripts.preview_pipeline.publication_admission import SCHEMA, validate

class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.args = dict(runtime='/private/run', normal_close='/private/close',
                         reservation='/private/run/reservation', worker='/private/worker.py',
                         worker_sha256='a'*64, selected_keys=[['one','digest'],['two','digest']],
                         source_pins=[{'path':'/private/source','sha256':'b'*64}],
                         prerequisite_pins=[{'path':'/private/proof','sha256':'c'*64}], now=100)
        self.value = dict(schema=SCHEMA,runtime=self.args['runtime'],normalClose=self.args['normal_close'],
                          reservation=self.args['reservation'],worker=self.args['worker'],
                          workerSHA256=self.args['worker_sha256'],selectedKeys=self.args['selected_keys'],
                          sourcePins=self.args['source_pins'],prerequisitePins=self.args['prerequisite_pins'],
                          expiresUnix=700,maximumKeys=2,nativeRenderCalls=0,originalPayloadReads=0,
                          preserveTenOriginals=True,automaticRetry=False,fullCatalogReleased=False)
    def test_exact_finite_admission(self):
        self.assertEqual(validate(self.value,**self.args),700)
    def test_every_owner_binding_rejects_substitution(self):
        for field in ('runtime','normalClose','reservation','worker','workerSHA256','selectedKeys','sourcePins','prerequisitePins'):
            with self.subTest(field=field):
                value=copy.deepcopy(self.value);value[field]=None
                with self.assertRaises(ValueError):validate(value,**self.args)
    def test_unknown_or_missing_fields_reject(self):
        for value in (dict(self.value,unreviewed=True),{k:v for k,v in self.value.items()if k!='worker'}):
            with self.assertRaises(ValueError):validate(value,**self.args)
    def test_deadline_expired_nonfinite_or_excessive(self):
        for expiry in (100,99,1001,float('nan'),float('inf'),True):
            with self.subTest(expiry=expiry),self.assertRaises(ValueError):
                validate(dict(self.value,expiresUnix=expiry),**self.args)
    def test_no_implicit_render_read_retry_or_full_catalog_authority(self):
        for field,bad in (('nativeRenderCalls',1),('originalPayloadReads',1),('automaticRetry',True),('fullCatalogReleased',True),('preserveTenOriginals',False),('maximumKeys',True)):
            with self.subTest(field=field),self.assertRaises(ValueError):
                validate(dict(self.value,**{field:bad}),**self.args)
    def test_duplicate_or_unbounded_keys_reject_even_when_both_sides_match(self):
        for keys in ([],[['one','digest']]*2,[[str(i),'digest']for i in range(9)]):
            args=dict(self.args,selected_keys=keys)
            with self.assertRaises(ValueError):
                validate(dict(self.value,selectedKeys=keys,maximumKeys=len(keys)),**args)
