from copy import deepcopy
import errno
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.preview_pipeline.census_files import CaptureFileCloseUnknown
from scripts.preview_pipeline.census_journal import CaptureAttempts, check_sealed_inventory
from scripts.preview_pipeline.census_readback import check_journal_files
from scripts.preview_pipeline.census_store import DurableCaptureWriter


class CaptureJournalReadbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        writer = DurableCaptureWriter(self.fd, str(self.root))
        journal = CaptureAttempts(writer)
        self.capture_pins = []
        self.captures = []
        for index in range(2):
            projection = ('original projection %d' % index).encode()
            pin = dict(path='/synthetic/capture%d/RESULT.json' % index,
                       bytes=100, sha256=str(index+1)*64)
            self.capture_pins.append(pin)
            self.captures.append(SimpleNamespace(projection=projection))
            journal.capture(lambda p=pin, output=projection: (0, output, b'', p))
        journal.seal()
        self.pins = [{k:row[k] for k in ('path', 'bytes', 'sha256')} for row in writer.records()]

    def check(self, pins=None):
        return check_journal_files(self.fd, str(self.root), self.pins if pins is None else pins)

    def edit(self, index, transform=None, raw=None):
        path = self.root/f'{index:06d}.json'
        if raw is None:
            value = json.loads(path.read_bytes())
            transform(value)
            raw = (json.dumps(value, sort_keys=True, separators=(',', ':'),
                              ensure_ascii=True) + '\n').encode()
        path.write_bytes(raw)
        self.pins[index].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

    def test_real_writer_readback_and_independent_projection_binding(self):
        checked = self.check()
        self.assertEqual(checked.snapshot()['state'], 'SEALED')
        self.assertEqual(len(checked.snapshot_pins), 5)
        self.assertFalse(checked.resource_release_authorized)
        self.assertEqual(check_sealed_inventory(checked.snapshot(), self.capture_pins,
                                               tuple(self.captures)), tuple(self.capture_pins))
        changed = checked.snapshot()
        changed['attempts'].clear()
        self.assertEqual(len(checked.snapshot()['attempts']), 2)
        os.fstat(self.fd)

    def test_omitted_snapshot_inventory_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'DIRECTORY_INVENTORY'):
            self.check(self.pins[:3])

    def test_unsealed_prefix_is_not_completion(self):
        for path in (self.root/'000003.json', self.root/'000004.json'):
            path.unlink()
        with self.assertRaises(ValueError):
            self.check(self.pins[:3])

    def test_missing_and_extra_records_refused(self):
        (self.root/'000004.json').unlink()
        with self.assertRaises(ValueError):
            self.check()
        (self.root/'unexpected').write_bytes(b'preserve')
        with self.assertRaises(ValueError):
            self.check()

    def test_snapshot_pin_mismatch_refused(self):
        pins = deepcopy(self.pins)
        pins[1]['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'SNAPSHOT_BYTES'):
            self.check(pins)

    def test_path_traversal_and_reordered_pin_refused(self):
        for label in (str(self.root/'../foreign.json'), '/foreign/000000.json',
                      str(self.root/'000001.json')):
            pins = deepcopy(self.pins)
            pins[0]['path'] = label
            with self.subTest(path=label), self.assertRaises(ValueError):
                self.check(pins)

    def test_symlink_never_followed(self):
        path = self.root/'000001.json'
        path.unlink()
        path.symlink_to(self.root/'000000.json')
        with self.assertRaises(OSError):
            self.check()

    def test_hardlink_and_public_permissions_refused(self):
        with tempfile.TemporaryDirectory() as other:
            os.link(self.root/'000000.json', Path(other)/'extra-link')
            with self.assertRaisesRegex(ValueError, 'PRIVATE_SNAPSHOT'):
                self.check()
        (self.root/'000000.json').chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'PRIVATE_SNAPSHOT'):
            self.check()

    def test_changed_earlier_outcome_not_hidden_by_final_seal(self):
        self.edit(3, lambda value: value['attempts'][0].update(projected_sha256='a'*64))
        with self.assertRaisesRegex(ValueError, 'OUTCOME_PREFIX'):
            self.check()

    def test_invented_release_and_boolean_intent_index_refused(self):
        self.edit(0, lambda value: value.update(resource_release_authorized=True))
        with self.assertRaisesRegex(ValueError, 'SNAPSHOT_SCOPE'):
            self.check()
        self.edit(0, lambda value: (value.update(resource_release_authorized=False),
                                    value['attempts'][0].update(index=False)))
        with self.assertRaisesRegex(ValueError, 'INTENT_PREFIX'):
            self.check()

    def test_duplicate_json_keys_and_noncanonical_bytes_refused(self):
        raw = (self.root/'000000.json').read_bytes()
        self.edit(0, raw=raw.replace(b'"state":"INTENT"',
                                    b'"state":"INTENT","state":"INTENT"', 1))
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_JSON_KEY'):
            self.check()
        self.edit(0, raw=b' ' + raw)
        with self.assertRaisesRegex(ValueError, 'CANONICAL_SNAPSHOT'):
            self.check()

    def test_boolean_pin_size_and_overbound_size_refused(self):
        for value in (True, 1048577):
            pins = deepcopy(self.pins)
            pins[0]['bytes'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.check(pins)

    def test_midread_path_replacement_refused(self):
        real_read = os.read
        replaced = []

        def read(fd, size):
            data = real_read(fd, size)
            if not replaced:
                replaced.append(True)
                replacement = self.root/'replacement'
                replacement.write_bytes((self.root/'000000.json').read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, self.root/'000000.json')
            return data

        with patch('scripts.preview_pipeline.census_readback.os.read', side_effect=read):
            with self.assertRaisesRegex(ValueError, 'HELD_OR_VISIBLE'):
                self.check()

    def test_uncertain_close_never_retried_and_original_error_preserved(self):
        pins = deepcopy(self.pins)
        pins[0]['sha256'] = '0'*64
        real_close = os.close

        def close(fd):
            real_close(fd)
            raise OSError(errno.EINTR, 'uncertain close')

        with patch('scripts.preview_pipeline.census_readback.os.close', side_effect=close) as closer:
            with self.assertRaises(CaptureFileCloseUnknown) as caught:
                self.check(pins)
        self.assertEqual(closer.call_count, 1)
        self.assertIsInstance(caught.exception.original_error, ValueError)
        row = caught.exception.uncertain_closes[0]
        self.assertEqual(len(row['preclose_identity']), 8)
        self.assertFalse(row['numeric_retry'])


if __name__ == '__main__':
    unittest.main()
