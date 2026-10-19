import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import shutil

spec = importlib.util.spec_from_file_location('extract_aux', Path(__file__).resolve().parents[1]/'scripts/extract_bigtable_aux.py')
aux = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aux)
try:
    from rocksdict import Rdict, Options
except ImportError:
    Rdict = None


class ManifestTests(unittest.TestCase):
    def test_boolean_size_and_non_c2pa_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'manifest.json'
            valid = {'type':'c2pa','digest':'A'*32,'sha256':'1'*64,'fileSize':123}
            for changed in ({'fileSize':True}, {'type':'mask'}, {'digest':'../../escape'}):
                path.write_text(json.dumps([{**valid, **changed}]))
                with self.assertRaises(ValueError):
                    aux.manifest_rows(path)


@unittest.skipUnless(Rdict, 'install optional rocksdict dependency')
class RawStorageTests(unittest.TestCase):
    def test_exact_exports_aliases_and_mismatches_preserve_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); source=root/'fixture'; output=root/'exports'; output.mkdir()
            options=Options(raw_mode=True); options.create_if_missing(True)
            db=Rdict(str(source),options=options)
            value=b'opaque fixture bytes; not a real C2PA signature'
            db[b'A'*32]=value; db[b'B'*32]=value; db[b'C'*32]=b'different payload'
            db.close()
            before=aux.family(source)
            snapshot=root/'private-copy'; shutil.copytree(source,snapshot)
            row={'type':'c2pa','digest':'A'*32,'sha256':hashlib.sha256(value).hexdigest(),'fileSize':len(value)}
            rows=[row,{**row,'digest':'B'*32},{**row,'digest':'C'*32},{**row,'digest':'D'*32}]
            result=aux.extract_snapshot(snapshot,rows,output)
            self.assertEqual([r['status'] for r in result],['EXACT_EXPORT','EXACT_EXPORT','HASH_OR_SIZE_HELD','KEY_ABSENT'])
            self.assertEqual((output/row['sha256']).read_bytes(),value)
            self.assertEqual(aux.family(source),before)

    def test_existing_different_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve(); source=root/'fixture'; output=root/'exports'; output.mkdir()
            options=Options(raw_mode=True); options.create_if_missing(True)
            db=Rdict(str(source),options=options); db[b'A'*32]=b'payload'; db.close()
            snapshot=root/'private-copy'; shutil.copytree(source,snapshot)
            row={'type':'c2pa','digest':'A'*32,'sha256':hashlib.sha256(b'payload').hexdigest(),'fileSize':7}
            path=output/row['sha256']; path.write_bytes(b'preserve this')
            with self.assertRaises(RuntimeError):
                aux.extract_snapshot(snapshot,[row],output)
            self.assertEqual(path.read_bytes(),b'preserve this')

    @unittest.skipUnless(sys.platform=='darwin','requires macOS APFS clone API')
    def test_apfs_snapshot_and_read_leave_source_family_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve(); source=root/'fixture'
            options=Options(raw_mode=True); options.create_if_missing(True)
            db=Rdict(str(source),options=options); db[b'A'*32]=b'payload'; db.close()
            snapshot=root/'snapshot'
            before=aux.clone_closed_source(source,snapshot)
            self.assertEqual(aux.family(source),before)
            self.assertEqual((snapshot/'CURRENT').read_bytes(),(source/'CURRENT').read_bytes())
