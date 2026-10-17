from pathlib import Path
import hashlib
import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('proxy_register', REPO / 'scripts/proxy_register.py')
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)

try:
    import msgpack
except ImportError:  # pragma: no cover
    msgpack = None

UUID = 'f2843d1cfcfcf74b96ef39d96ad714bb'
UUID2 = '4c2c604c32cf4184a828d399bc16995b'
PROXY_SHA = '18b7c1f1e83ee7c4ee0d5e13617cd0eae48f502e17bdb9d3dd112ea406473649'


def body(proxy_sha=PROXY_SHA):
    return {'type': 'asset', 'subtype': 'image', 'develop': {'croppedWidth': 3104, 'crsVersion': '11.1'},
            'importSource': {'contentType': 'image/dng', 'fileName': 'example.dng', 'proxySHA256': proxy_sha, 'willNotUploadMaster': True},
            'captureDate': '2010-07-21T19:02:38.000-04:00'}


def annotation(proxy_entry=None, invalid=False):
    link = {'href': '/v2/catalogs/x/assets/y/revisions/z/proxies/p'}
    if invalid:
        link['invalid'] = True
    files = {'xmp_develop': {'fileSize': 5799, 'path': '/tmp/settings/abc', 'sha256': 'abc'}}
    if proxy_entry:
        files['proxy'] = {'2560': proxy_entry}
    return {'_localOnly': {'files': files, 'cameraProfileInfo': {'isStandard': True}},
            '_serverProvidedMetadata': {'links': {'/rels/proxy_type/2560': link, '/rels/proxy_create': {'href': '/v2/x', 'templated': True}}}}


class LuaLiteralTests(unittest.TestCase):
    def test_roundtrip_shapes(self):
        value = {'a': 1, 'b': 2.5, 'c': 'x"y\\z\n', 'd': [1, 'two', True], 'e': {'nested': False}, 'drop': None}
        text = pr.lua(value)
        self.assertEqual(text, '{["a"]=1,["b"]=2.5,["c"]="x\\034y\\092z\\010",["d"]={1,"two",true},["e"]={["nested"]=false}}')

    def test_integer_precision_guard(self):
        with self.assertRaises(RuntimeError):
            pr.lua(2 ** 53)

    def test_non_string_keys_rejected(self):
        with self.assertRaises(RuntimeError):
            pr.lua({1: 'x'})


@unittest.skipIf(msgpack is None, 'msgpack unavailable')
class LedgerFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name).resolve()
        self.library = base / 'Lightroom Library.lrlibrary' / '4ba16cf9c14246758947a0ddbc109900'
        (self.library / 'proxies/2560' / UUID[:3]).mkdir(parents=True)
        (self.library / 'proxies/2560' / UUID2[:3]).mkdir(parents=True)
        (self.library / 'proxies/2560' / UUID[:3] / UUID[3:]).write_bytes(b'clone-bytes')
        (self.library / 'proxies/2560' / UUID2[:3] / UUID2[3:]).write_bytes(b'clone-bytes-2')
        wf = sqlite3.connect(self.library / 'Managed Catalog.wfindex')
        wf.executescript('''CREATE TABLE assets(docId INTEGER PRIMARY KEY, assetId, subtype);
            CREATE TABLE localStatusAndOzStatus(docId INTEGER PRIMARY KEY, needsOriginalDownload, hasLocalOriginal, needsProxyDownload,
              hasLocalProxy, proxySize, needsDevelopXmpDownload, subtype, isVersionDocument);''')
        wf.execute('INSERT INTO assets VALUES (8214,?, "image")', (UUID,))
        wf.execute('INSERT INTO assets VALUES (8215,?, "image")', (UUID2,))
        wf.execute('INSERT INTO localStatusAndOzStatus VALUES (8214,0.0,0.0,1.0,0.0,2560,0.0,"image",0.0)')
        wf.execute('INSERT INTO localStatusAndOzStatus VALUES (8215,0.0,0.0,0.0,1.0,2560,0.0,"image",0.0)')
        wf.commit()
        wf.close()
        mc = sqlite3.connect(self.library / 'Managed Catalog.mcat')
        mc.executescript('''CREATE TABLE docs(localDocId INTEGER PRIMARY KEY, fullDocId TEXT UNIQUE NOT NULL, winningRevSequence INTEGER,
              mostRecentRevSequence INTEGER, deleted BOOLEAN DEFAULT 0, hasConflicts BOOLEAN DEFAULT 0, annotation BLOB, spaceId TEXT, type TEXT, subtype TEXT);
            CREATE TABLE revs(sequence INTEGER PRIMARY KEY AUTOINCREMENT, localDocId INTEGER NOT NULL, revId TEXT NOT NULL, parentRevSequence INTEGER,
              current BOOLEAN, deleted BOOLEAN DEFAULT 0, content BLOB);
            CREATE TABLE labels(localDocId INTEGER, revSequence INTEGER, name STRING, UNIQUE(localDocId, name));''')
        mc.execute('INSERT INTO revs(sequence,localDocId,revId,current,content) VALUES (22619,8214,"rev1",1,?)', (msgpack.packb(body(), use_bin_type=True),))
        mc.execute('INSERT INTO docs VALUES (8214,?,22619,22619,0,0,?,NULL,"asset","image")', (UUID, msgpack.packb(annotation(invalid=True), use_bin_type=True)))
        mc.execute('INSERT INTO labels VALUES (8214,22619,"oz")')
        mc.commit()
        mc.close()
        self.out = base / 'ledger'

    def tearDown(self):
        self.temp.cleanup()

    def run_ledger(self):
        pr.main(['ledger', '--library', str(self.library), '--output', str(self.out), '--volume-uuid', 'TEST-UUID'])
        return json.loads((self.out / 'COMPLETE.json').read_bytes())

    def test_ledger_rows_and_bind(self):
        with mock.patch('sys.stdout'):
            complete = self.run_ledger()
        self.assertEqual((complete['rows'], complete['holds']), (1, 0))
        row = json.loads((self.out / 'NATIVE-INPUTS.jsonl').read_bytes().splitlines()[0])
        self.assertEqual(row['expectedProxySHA256'], PROXY_SHA)
        self.assertTrue(row['proxyLinkFacts']['invalid'])
        self.assertEqual(row['expectedRelativePath'], row['expectedPath'].lstrip('/'))
        self.assertEqual(row['storedLabels'], {'oz': True})
        arm = {'state': 'ARMED_KNOWN_SHA_PROXY_NATIVE_REGISTRATION', 'epoch': 1, 'nonce': 'ab' * 16, 'cloudPID': 1,
               'cloudProcessIdentity': 'x', 'catalogID': self.library.name, 'pixelsPath': str(self.library), 'appData': '/tmp/app',
               'volumeGuid': 'TEST-UUID', 'launcherEvidence': None, 'armWindowSeconds': 10, 'guardFreshnessSeconds': 30, 'parallelBatches': 4}
        evidence = Path(self.temp.name) / 'evidence.json'
        evidence.write_text('{}')
        arm['launcherEvidence'] = {'path': str(evidence), 'sha256': hashlib.sha256(b'{}').hexdigest()}
        arm_path = Path(self.temp.name) / 'ARM.json'
        arm_path.write_text(json.dumps(arm))
        run = Path(self.temp.name) / 'native'
        with mock.patch('sys.stdout'):
            pr.main(['bind', '--ledger-complete', str(self.out / 'COMPLETE.json'), '--arm', str(arm_path), '--output', str(run)])
        plan = json.loads((run / 'CONTROLLER-PLAN.json').read_bytes())
        self.assertEqual(plan['count'], 1)
        script = (run / (pr.SCRIPT_NAME + '.lua')).read_text()
        self.assertNotIn('__PLAN__', script)
        self.assertIn('ROOT_BOUND_KNOWN_SHA_PROXY_REGISTRATION', script)
        batch = (run / 'BATCH-00001.lua').read_text()
        self.assertIn('["expectedProxySHA256"]="%s"' % PROXY_SHA, batch)
        self.assertIn('["_changeCounter"]=22619', batch)
        # plan-only rebinding reuses the batch files under a fresh nonce
        arm['nonce'] = 'cd' * 16
        arm_path.write_text(json.dumps(arm))
        run2 = Path(self.temp.name) / 'native2'
        with mock.patch('sys.stdout'):
            pr.main(['bind', '--ledger-complete', str(self.out / 'COMPLETE.json'), '--arm', str(arm_path), '--output', str(run2), '--batches-from', str(run)])
        plan2 = json.loads((run2 / 'CONTROLLER-PLAN.json').read_bytes())
        self.assertEqual(plan2['batchConfig']['sha256'], plan['batchConfig']['sha256'])
        self.assertEqual(plan2['nonce'], 'cd' * 16)

    def test_already_annotated_and_missing_hash_are_held(self):
        mc = sqlite3.connect(self.library / 'Managed Catalog.mcat')
        mc.execute('UPDATE docs SET annotation=? WHERE localDocId=8214',
                   (msgpack.packb(annotation({'volumeGuid': 'v', 'relativePath': 'r', 'lastSaveTimestamp': 't'}), use_bin_type=True),))
        mc.commit()
        mc.close()
        with mock.patch('sys.stdout'):
            complete = self.run_ledger()
        self.assertEqual(complete['holdCounts'], {'PROXY_ANNOTATION_PRESENT': 1})

    def test_template_has_single_plan_slot(self):
        text = pr.TEMPLATE.read_text()
        self.assertEqual(text.count('__PLAN__'), 1)
        self.assertIn("root:subModel('getProxyPaths',ids)", text)
        self.assertIn('ROW_RETURN_PATH_MISMATCH_HELD', text)


if __name__ == '__main__':
    unittest.main()
