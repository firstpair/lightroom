from pathlib import Path
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('shuttle', REPO / 'scripts/shuttle.py')
shuttle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shuttle)


class ShuttleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        local, photo = self.base / 'SSD/Lightroom', self.base / 'Photo/Lightroom'
        for root in (local, photo):
            folder = root / 'Example'
            (folder / 'Example.lrcat-data').mkdir(parents=True)
            (folder / 'Example Sync.lrdata').mkdir()
            (folder / 'Example Helper.lrdata').mkdir()
            (folder / 'Example.lrcat').write_bytes(b'closed-fixture-catalog')
            (folder / 'Example.lrcat-data/mask.dat').write_bytes(b'owned-mask')
            (folder / 'Example Sync.lrdata/sourcesync.db').write_bytes(b'closed-fixture-sync')
            (folder / 'Example Helper.lrdata/helper.db').write_bytes(b'closed-fixture-helper')
            (folder / 'Example Previews.lrdata').mkdir()
            (folder / 'Example Smart Previews.lrdata').mkdir()
            (folder / 'AGENTS.md').write_text('fixture instructions')
        app = self.base / 'Classic.app'
        (app / 'Contents').mkdir(parents=True)
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleShortVersionString': '15.6', 'CFBundleVersion': '15.6.0', 'CFBundleName': 'Lightroom Classic'}))
        tool = self.base / 'unison'
        tool.write_bytes(b'fixture executable only; never launched')
        tool.chmod(0o700)
        lease = self.base / 'existing-photo-io.lock'
        lease.write_bytes(b'')
        self.config = {'schema': 1, 'host': 'laptop', 'peers': ['desktop'],
                       'local_root': str(local), 'photo_root': str(photo), 'photo_mount': str(photo.parent),
                       'photo_uuid': 'AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA',
                       'main_catalog': 'Example/Example.lrcat', 'state_dir': str(self.base / 'state/laptop'),
                       'local_backup_root': str(self.base / 'SSD/rollback'),
                       'photo_backup_root': str(self.base / 'Photo/rollback'),
                       'journal_root': str(self.base / 'private-journal/laptop'),
                       'owner_marker': str(self.base / 'Photo/owner.json'),
                       'shared_io_lease': str(lease), 'classic_app': str(app),
                       'transfer_budget_bytes': {'full': 1, 'main-core': 1}, 'minimum_free_bytes': 1,
                       'unison': {'path': str(tool), 'sha256': hashlib.sha256(tool.read_bytes()).hexdigest(),
                                  'version': '2.54.0'}, 'photo_preview_links': {}}
        self.config_path = self.base / 'fixture.private.json'
        self.write_config()

    def tearDown(self):
        self.temp.cleanup()

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config))

    def read_config(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            return shuttle.load_config(self.config_path)

    @contextlib.contextmanager
    def mocked_platform(self, unison_exit=0, propagate=None):
        def runner(argv, **kwargs):
            self.assertEqual(argv[0], self.config['unison']['path'])
            if propagate:
                propagate(argv)
            return subprocess.CompletedProcess(argv, unison_exit)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(shuttle, 'volume_gate', return_value={'fixtureVolume': True}))
            stack.enter_context(mock.patch.object(shuttle, 'tool_gate', return_value={'fixturePinnedTool': True}))
            stack.enter_context(mock.patch.object(shuttle, 'closed_gate', return_value={'openMainDescriptors': 0}))
            stack.enter_context(mock.patch.object(shuttle, 'clone_file', side_effect=shutil.copy2))
            stack.enter_context(mock.patch.object(shuttle.subprocess, 'run', side_effect=runner))
            stack.enter_context(mock.patch.dict(os.environ, {}, clear=True))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            yield

    def latest_result(self):
        paths = list(Path(self.config['journal_root']).glob('*/RESULT.json'))
        self.assertEqual(len(paths), 1)
        return paths[0], json.loads(paths[0].read_text())

    def receipt(self, result_path, result):
        rows = result['criticalFamiliesAfter']['local']['rows']
        hashes = []
        for row in rows:
            if row['kind'] != 'file':
                continue
            local = Path(self.config['local_root']) / row['path']
            photo = Path(self.config['photo_root']) / row['path']
            hashes.append({'path': row['path'], 'size': local.stat().st_size,
                           'localSha256': hashlib.sha256(local.read_bytes()).hexdigest(),
                           'photoSha256': hashlib.sha256(photo.read_bytes()).hexdigest()})
        value = {'schema': 1, 'runId': result['runId'], 'resultSha256': shuttle.sha_file(result_path),
                 'roots': result['roots'], 'tier': result['tier'], 'sourceStable': True,
                 'criticalFamilySHA256Equal': True, 'databaseFamilyMembershipEqual': True,
                 'missingExpectedFiles': [], 'staleDatabaseSidecars': [], 'criticalFiles': hashes}
        path = self.base / 'independent-fixture-receipt.json'
        path.write_text(json.dumps(value))
        return path, value

    def test_private_config_rejects_environment_overrides(self):
        for name in shuttle.UNSAFE_ENV:
            with self.subTest(name=name), mock.patch.dict(os.environ, {name: '/foreign'}, clear=True):
                with self.assertRaisesRegex(ValueError, 'Inherited'):
                    shuttle.load_config(self.config_path)

    def test_unsafe_roots_and_foreign_archive_state_are_rejected(self):
        self.config['state_dir'] = self.config['local_root'] + '/state'
        self.write_config()
        with self.assertRaisesRegex(ValueError, 'outside synchronization roots'):
            self.read_config()
        self.config['state_dir'] = str(self.base / 'state/laptop')
        state = Path(self.config['state_dir']); state.mkdir(parents=True)
        (state / 'old-user-profile.prf').write_text('root = old')
        with self.assertRaisesRegex(ValueError, 'foreign/legacy'):
            shuttle.owned_state(self.config, 'full')

    def test_main_scope_rejects_unison_pattern_metacharacters(self):
        for value in ('Ex*/Example.lrcat', 'Example/Ex[ample].lrcat', 'Ex?ample/Example.lrcat',
                      'Ex{ample}/Example.lrcat', 'Ex!ample/Example.lrcat'):
            with self.subTest(value=value):
                self.config['main_catalog'] = value
                self.write_config()
                with self.assertRaisesRegex(ValueError, 'pattern metacharacter'):
                    self.read_config()

    def test_archive_tier_is_immutable_in_owned_state(self):
        config = self.read_config()
        shuttle.mkdir_safe(Path(config['state_dir']))
        self.assertEqual(shuttle.owned_state(config, 'full')['tier'], 'full')
        self.assertEqual(shuttle.owned_state(config, 'full')['tier'], 'full')
        with self.assertRaisesRegex(ValueError, 'pair or tier'):
            shuttle.owned_state(config, 'main-core')

    def test_separate_host_pair_archives_do_not_alias_ssds(self):
        config = self.read_config()
        other = dict(config, host='desktop', peers=['laptop'], state_dir=str(self.base / 'state/desktop'))
        with mock.patch.dict(os.environ, {}, clear=True):
            left, right = shuttle.archive_environment(config), shuttle.archive_environment(other)
        self.assertNotEqual(left['UNISON'], right['UNISON'])
        self.assertNotEqual(left['UNISONLOCALHOSTNAME'], right['UNISONLOCALHOSTNAME'])
        profile = shuttle.render_profile(config, 'main-core', self.base / 'backups', self.base / 'log')
        self.assertNotIn('rootalias', profile)

    def test_stable_classic_version_and_prerelease_gate(self):
        self.assertEqual(shuttle.classic_gate(self.config)['version'], '15.6')
        path = Path(self.config['classic_app']) / 'Contents/Info.plist'
        for version, label in [('14.4', 'Classic'), ('16.0', 'Prerelease'), ('15.6', 'Lightroom Classic Beta')]:
            with self.subTest(version=version, label=label):
                path.write_bytes(plistlib.dumps({'CFBundleShortVersionString': version, 'CFBundleName': label}))
                with self.assertRaises(ValueError):
                    shuttle.classic_gate(self.config)

    def test_wrong_photo_uuid_does_not_admit_same_named_directory(self):
        payload = plistlib.dumps({'VolumeUUID': 'BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB',
                                 'MountPoint': self.config['photo_mount'], 'Mounted': True})
        with mock.patch.object(shuttle.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, payload)):
            with self.assertRaisesRegex(ValueError, 'Wrong Photo volume UUID'):
                shuttle.volume_gate(self.config)

    def test_diskutil_missing_mounted_key_needs_real_mountpoint(self):
        payload = plistlib.dumps({'VolumeUUID': self.config['photo_uuid'],
                                 'MountPoint': self.config['photo_mount']})
        with mock.patch.object(shuttle.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, payload)), \
             mock.patch.object(shuttle.os.path, 'ismount', return_value=False):
            with self.assertRaisesRegex(ValueError, 'not mounted'):
                shuttle.volume_gate(self.config)
        class Item:
            st_dev = -1
            st_ino = 99
        with mock.patch.object(shuttle.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, payload)), \
             mock.patch.object(shuttle.os.path, 'ismount', return_value=True), \
             mock.patch.object(shuttle, 'guarded', return_value=Item()):
            self.assertEqual(shuttle.volume_gate(self.config)['inode'], 99)
        explicit = plistlib.dumps({'VolumeUUID': self.config['photo_uuid'],
                                   'MountPoint': self.config['photo_mount'], 'Mounted': False})
        with mock.patch.object(shuttle.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, explicit)), \
             mock.patch.object(shuttle.os.path, 'ismount', return_value=True):
            with self.assertRaisesRegex(ValueError, 'not mounted'):
                shuttle.volume_gate(self.config)

    def test_main_alias_fd_blocks_while_ai_and_cwd_do_not(self):
        root = Path('/replica/Example')
        ai = b'p11\0cClassic\0\nf7u\0D0x20\0i2\0n/replica/AI/AI.lrcat\0'
        cwd = b'p12\0cShell\0\nfcwd\0n/replica/Example\0'
        self.assertEqual(shuttle.parse_main_fds(ai + cwd, [root], {(32, 1)}), [])
        actual = b'p13\0cClassic\0\nf9u\0D0x20\0i1\0n/elsewhere/main-alias.lrcat\0'
        hits = shuttle.parse_main_fds(actual, [root], {(32, 1)})
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0]['physicalMainCatalogMatch'])
        case = b'p14\0cClassic\0\nf10r\0n/REPLICA/EXAMPLE/Example.lrcat (deleted)\0'
        self.assertEqual(len(shuttle.parse_main_fds(case, [root])), 1)

    def test_only_exact_ignored_read_only_ds_store_fd_is_excluded(self):
        root = Path('/replica/Example')
        excluded = []
        raw = b'p30\0cmdworker_shared\0\nf3\0ar\0D0x20\0i2\0n/replica/Example/.DS_Store\0'
        self.assertEqual(shuttle.parse_main_fds(raw, [root], {(32, 1)}, excluded), [])
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]['access'], 'r')
        for access in (b'aw', b'au', b''):
            with self.subTest(access=access):
                changed = raw.replace(b'ar\0', access + b'\0')
                self.assertEqual(len(shuttle.parse_main_fds(changed, [root], {(32, 1)})), 1)
        alias = raw.replace(b'i2\0', b'i1\0')
        self.assertEqual(len(shuttle.parse_main_fds(alias, [root], {(32, 1)})), 1)
        included = raw.replace(b'/.DS_Store\0', b'/Example.lrcat-data/mask.dat\0')
        self.assertEqual(len(shuttle.parse_main_fds(included, [root], {(32, 1)})), 1)

    def test_main_core_keeps_standard_previews_and_never_merges_catalogs(self):
        config = self.read_config()
        profile = shuttle.render_profile(config, 'main-core', self.base / 'backups', self.base / 'log')
        self.assertIn('atomic = Path Example\n', profile)
        self.assertIn('ignore = Path Example/Example Smart Previews.lrdata\n', profile)
        self.assertNotIn('ignore = Path Example/Example Previews.lrdata\n', profile)
        self.assertNotIn('ignore = Path Example/Example Helper.lrdata\n', profile)
        self.assertIn('ignore = Path Example/Backups\n', profile)
        full = shuttle.render_profile(config, 'full', self.base / 'backups', self.base / 'log')
        self.assertNotIn('ignore = Path Example/Backups\n', full)
        self.assertNotIn('ignore = Path Example/Example Helper.lrdata\n', full)
        self.assertIn('mountpoint = .\n', full)
        for unsafe in ('follow =', 'merge =', 'prefer =', 'force =', 'ignorearchives', 'ignorelocks'):
            self.assertNotIn(unsafe, profile)
        self.assertIn('times = true\n', profile)
        self.assertIn('xattrs = true\n', profile)
        self.assertIn('rsrc = true\n', profile)
        self.assertIn('confirmbigdel = true\n', profile)
        self.assertFalse(shuttle.scope_description(config, 'full')['wholeLightroomFolderComplete'])

    def test_bootstrap_omits_native_atomic_force_properties_only_trap(self):
        config = self.read_config()
        profile = shuttle.render_profile(config, 'full', self.base / 'backups', self.base / 'log', bootstrap=True)
        self.assertNotIn('atomic =', profile)
        self.assertIn('path = Example\n', profile)
        self.assertIn('mountpoint = .\n', profile)
        routine = shuttle.render_profile(config, 'full', self.base / 'backups', self.base / 'log')
        self.assertIn('atomic = Path Example\n', routine)

    def test_only_exact_excluded_photo_preview_symlink_is_allowed(self):
        name = 'Example/Example Smart Previews.lrdata'
        path = Path(self.config['local_root']) / name
        path.rmdir()
        target = str(Path(self.config['photo_root']) / name)
        path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            shuttle.preview_gate(self.config, 'main-core')
        self.config['photo_preview_links'][name] = target
        shuttle.preview_gate(self.config, 'main-core')
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            shuttle.preview_gate(self.config, 'full')

    def test_included_standard_preview_symlink_cannot_be_declared_or_admitted(self):
        name = 'Example/Example Previews.lrdata'
        path = Path(self.config['local_root']) / name
        path.rmdir()
        target = str(Path(self.config['photo_root']) / name)
        path.symlink_to(target)
        self.config['photo_preview_links'][name] = target
        self.write_config()
        with self.assertRaisesRegex(ValueError, 'Only exact excluded Photo Smart Previews links'):
            self.read_config()
        with self.assertRaisesRegex(ValueError, 'Unexpected or included symlink'):
            shuttle.preview_gate(self.config, 'main-core')

    def test_critical_symlink_and_remaining_lock_are_held(self):
        root = Path(self.config['local_root'])
        catalog = root / self.config['main_catalog']
        lock = Path(str(catalog) + '.lock'); lock.write_text('not removed')
        with self.assertRaisesRegex(ValueError, 'Catalog lock remains'):
            shuttle.inventory_critical(root, self.config, True)
        lock.unlink()
        mask = catalog.parent / 'Example.lrcat-data/mask.dat'
        saved = self.base / 'external-mask'; saved.write_bytes(mask.read_bytes()); mask.unlink(); mask.symlink_to(saved)
        with self.assertRaisesRegex(ValueError, 'Unexpected symlink'):
            shuttle.inventory_critical(root, self.config, True)

    def test_bootstrap_retains_reader_wal_and_preserves_stale_destination_family(self):
        source, target = Path(self.config['local_root']), Path(self.config['photo_root'])
        name = self.config['main_catalog']
        (source / (name + '-wal')).write_bytes(b'')
        (target / name).write_bytes(b'previous-catalog')
        (target / (name + '-wal')).write_bytes(b'previous-wal')
        (target / (name + '-shm')).write_bytes(b'previous-shm')
        def propagate(argv):
            self.assertIn('-force', argv)
            shutil.copy2(source / name, target / name)
            shutil.copy2(source / (name + '-wal'), target / (name + '-wal'))
            (target / (name + '-shm')).unlink()
        with self.mocked_platform(propagate=propagate):
            code = shuttle.execute_transfer(self.read_config(), 'bootstrap', 'main-core', 'local')
        self.assertEqual(code, 0)
        path, result = self.latest_result()
        self.assertEqual(result['status'], 'verification-required')
        saved = Path(result['previousCriticalFamily']['photo'])
        self.assertEqual((saved / name).read_bytes(), b'previous-catalog')
        self.assertEqual((saved / (name + '-wal')).read_bytes(), b'previous-wal')
        self.assertEqual((saved / (name + '-shm')).read_bytes(), b'previous-shm')
        self.assertEqual((saved / 'Example/Example Helper.lrdata/helper.db').read_bytes(), b'closed-fixture-helper')
        self.assertEqual((target / (name + '-wal')).stat().st_size, 0)
        self.assertFalse((target / (name + '-shm')).exists())
        self.assertFalse(result['ownerTransferred'])
        self.assertEqual(json.loads(Path(self.config['owner_marker']).read_text())['phase'], 'verification-required')
        self.assertTrue((path.parent / 'UNISON-EXIT.json').is_file())

    def test_incoming_bootstrap_allows_empty_main_destination(self):
        marker = {'schema': 1, 'photoUuid': self.config['photo_uuid'],
                  'mainCatalog': self.config['main_catalog'], 'owner': None,
                  'phase': 'in-transit', 'previousOwner': 'laptop', 'releaseTo': 'desktop',
                  'generation': 1, 'tier': 'full'}
        Path(self.config['owner_marker']).write_text(json.dumps(marker))
        self.config.update(host='desktop', peers=['laptop'],
                           local_root=str(self.base / 'SSD2/Lightroom'),
                           local_backup_root=str(self.base / 'SSD2/rollback'),
                           state_dir=str(self.base / 'state/desktop-core'),
                           journal_root=str(self.base / 'private-journal/desktop'))
        Path(self.config['local_root']).mkdir(parents=True)
        self.write_config()
        def propagate(argv):
            self.assertEqual(argv[-1], self.config['photo_root'])
            profile = Path(self.config['state_dir']) / 'lightroom-shuttle-desktop.prf'
            self.assertIn('mountpoint = .\n', profile.read_text())
            shutil.copytree(Path(self.config['photo_root']) / 'Example',
                            Path(self.config['local_root']) / 'Example')
        with self.mocked_platform(propagate=propagate):
            self.assertEqual(shuttle.execute_transfer(self.read_config(), 'bootstrap', 'main-core', 'photo'), 0)
        path, result = self.latest_result()
        self.assertEqual(result['direction'], 'incoming')
        self.assertEqual(result['previousCriticalFamily'].keys(), {'local'})
        receipt, _ = self.receipt(path, result)
        with self.mocked_platform():
            shuttle.change_owner(self.read_config(), 'accept', receipt)
        self.assertEqual(shuttle.read_owner(self.config)['owner'], 'desktop')
        self.assertEqual(shuttle.read_owner(self.config)['phase'], 'active')

    def test_conflicted_exit_one_cannot_transfer_owner_even_with_receipt(self):
        with self.mocked_platform(unison_exit=1):
            self.assertEqual(shuttle.execute_transfer(self.read_config(), 'bootstrap', 'main-core', 'local'), 1)
        path, result = self.latest_result()
        receipt, _ = self.receipt(path, result)
        marker_before = Path(self.config['owner_marker']).read_bytes()
        with self.mocked_platform(), self.assertRaisesRegex(ValueError, 'No completed transfer'):
            shuttle.change_owner(self.read_config(), 'release', receipt, 'desktop')
        self.assertEqual(marker_before, Path(self.config['owner_marker']).read_bytes())
        self.assertEqual(result['status'], 'held')

    def test_complete_proof_releases_to_exact_peer_and_outgoing_old_host_is_blocked(self):
        with self.mocked_platform():
            shuttle.execute_transfer(self.read_config(), 'bootstrap', 'main-core', 'local')
        path, result = self.latest_result()
        receipt, _ = self.receipt(path, result)
        with self.mocked_platform():
            shuttle.change_owner(self.read_config(), 'release', receipt, 'desktop')
        marker = json.loads(Path(self.config['owner_marker']).read_text())
        self.assertEqual((marker['phase'], marker['owner'], marker['releaseTo']), ('in-transit', None, 'desktop'))
        with self.assertRaisesRegex(ValueError, 'owned elsewhere'):
            shuttle.admission(self.config, marker, 'sync', 'local')
        incoming = dict(self.config, host='desktop', peers=['laptop'])
        self.assertEqual(shuttle.admission(incoming, marker, 'sync', 'photo'), 'incoming')
        with self.assertRaisesRegex(ValueError, 'Incoming handoff'):
            shuttle.admission(incoming, marker, 'bootstrap', 'local')

    def test_forged_scope_or_omitted_sha_file_does_not_release(self):
        with self.mocked_platform():
            shuttle.execute_transfer(self.read_config(), 'bootstrap', 'main-core', 'local')
        path, result = self.latest_result()
        receipt, value = self.receipt(path, result)
        value['criticalFiles'].pop(); receipt.write_text(json.dumps(value))
        marker = shuttle.read_owner(self.config)
        with self.assertRaisesRegex(ValueError, 'critical-file coverage'):
            shuttle.verification(self.config, marker, receipt)
        receipt, value = self.receipt(path, result)
        value['tier'] = 'full'; receipt.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'scope/roots differ'):
            shuttle.verification(self.config, marker, receipt)

    def test_catalog_change_after_success_is_held_without_replaying_unison(self):
        with self.mocked_platform():
            shuttle.execute_transfer(self.read_config(), 'bootstrap', 'main-core', 'local')
        path, result = self.latest_result()
        receipt, _ = self.receipt(path, result)
        (Path(self.config['local_root']) / self.config['main_catalog']).write_bytes(b'late-native-write')
        with self.assertRaisesRegex(ValueError, 'changed since transfer'):
            shuttle.verification(self.config, shuttle.read_owner(self.config), receipt)
        self.assertEqual(json.loads((path.parent / 'UNISON-EXIT.json').read_text())['unisonExit'], 0)


if __name__ == '__main__':
    unittest.main()
