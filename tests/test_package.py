from pathlib import Path
import argparse
import importlib.util
import json
import plistlib
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('manage',REPO/'scripts/manage.py')
manage=importlib.util.module_from_spec(spec);spec.loader.exec_module(manage)

def assert_packaged_source_dependencies(root, rendered):
    """Inspect source literals and resolvable local-prefix concatenations.

    Read/write runtime receipts have no source suffix and are intentionally not
    precreated. Adobe application imports belong to the external application.
    Embedded runOnServer text is scanned too, since it runs in another Lua state.
    """
    observed=set()
    for name,source in rendered.items():
        for literal in re.finditer(r'''(['"])([^'"\n]*\.(?:lua|sql|applescript))\1''',source):
            value=literal.group(2)
            if value.startswith(str(root)+'/'):
                path=Path(value)
            else:
                concat=re.search(r'([A-Za-z_]\w*)\s*(?:\.\.|&)\s*$',source[:literal.start()])
                if not concat:continue
                variable=concat.group(1)
                definitions=list(re.finditer(r'(?:(?:local\s+)?'+re.escape(variable)+r'\s*=|set\s+'+re.escape(variable)+r'''\s+to)\s*(['"])([^'"\n]*)\1''',source[:literal.start()]))
                if not definitions:continue
                prefix=definitions[-1].group(2)
                if not prefix.startswith(str(root)+'/'):continue
                path=Path(prefix+value)
            if not path.is_file():raise AssertionError(f'Missing packaged source: {path.relative_to(root)} referenced by {name}')
            observed.add(str(path.relative_to(root)))
    return observed

class PackageTests(unittest.TestCase):
    def test_affinity_equivalence_requires_full_numeric_type_gate(self):
        db=sqlite3.connect(':memory:')
        db.executescript('CREATE TABLE images(id INTEGER PRIMARY KEY); CREATE TABLE metadata(image,payload); CREATE INDEX metadata_key ON metadata(image,payload); INSERT INTO images VALUES(1); INSERT INTO metadata VALUES(1,"x");')
        original='SELECT rowid FROM metadata WHERE image IN (SELECT id FROM images)'
        corrected='SELECT rowid FROM metadata WHERE image IN (SELECT +id FROM images)'
        self.assertEqual(db.execute(original).fetchall(),db.execute(corrected).fetchall())
        plan=[r[3] for r in db.execute('EXPLAIN QUERY PLAN '+corrected)]
        self.assertTrue(any('SEARCH' in r and 'metadata_key' in r for r in plan))
        db.execute('INSERT INTO metadata VALUES(?,?)',('1','x'))
        self.assertNotEqual(db.execute(original).fetchall(),db.execute(corrected).fetchall())
        self.assertEqual(db.execute("SELECT COUNT(*) FROM metadata WHERE typeof(image) NOT IN ('integer','real') OR image!=CAST(image AS INTEGER)").fetchone()[0],1)
        db.close()
    def test_render_resolves_complete_dependency_closure(self):
        config={'root':'/tmp/FirstPair','app':'/tmp/Classic.app','catalog':'/tmp/Example.lrcat','affinity':False,'schema_index':False,'backup_confirmed':True}
        rendered=manage.render(config)
        self.assertEqual(len(rendered),22)
        for name,text in rendered.items():
            self.assertNotIn('@@',text,name);self.assertNotIn('/Users/private-owner',text,name)
            self.assertNotIn('Diagnostics-',text,name)
        self.assertIn('AFFINITY_DISABLED_PUBLIC_STARTER',rendered['runtime/menu.lua'])
        self.assertIn("if not false then return 'schema index creation disabled",rendered['runtime/menu.lua'])
    def test_stage_install_retains_catalog_and_is_never_enabled(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder).resolve();app=base/'Classic.app';(app/'Contents/MacOS').mkdir(parents=True)
            (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleShortVersionString':'15.6'}))
            (app/'Contents/MacOS/Adobe Lightroom Classic').write_bytes(b'fixture-not-executable')
            catalog=base/'Example.lrcat';catalog.write_bytes(b'not-a-database')
            root=base/'installed'
            command=[sys.executable,str(REPO/'scripts/manage.py'),'install','--root',str(root),'--app',str(app),'--catalog',str(catalog),'--backup-confirmed','--stage-only']
            run=subprocess.run(command,capture_output=True,text=True);self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(catalog.read_bytes(),b'not-a-database');self.assertFalse((root/'ENABLED').exists())
            self.assertTrue(manage.verified_config(root)['stage_only'])
            run=subprocess.run(command,capture_output=True,text=True);self.assertNotEqual(run.returncode,0);self.assertIn('already exists',run.stderr)
            (root/'runtime/date/Predicate.lua').write_text('changed')
            with self.assertRaises(ValueError):manage.verified_config(root)
    def test_rendered_local_source_dependencies_exist_in_staged_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()/'staged'
            config={'root':str(root),'app':'/external/Classic.app','catalog':'/external/Example.lrcat','affinity':False,'schema_index':False,'backup_confirmed':True}
            rendered=manage.render(config)
            for name,source in rendered.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(source)
            dependencies=assert_packaged_source_dependencies(root,rendered)
            self.assertEqual(dependencies,set(rendered)-{'runtime/menu.lua','Helper.applescript'})
            quoted_pins=set(re.findall(r'''['"]([0-9a-f]{64})['"]''','\n'.join(rendered.values())))
            self.assertLessEqual({manage.sha(root/name) for name in dependencies if name.endswith(('.lua','.sql'))},quoted_pins)
            # A missing physical source must fail even when render/hash closure
            # and every source's syntax remain valid.
            victim=root/sorted(dependencies)[0];victim.unlink()
            with self.assertRaisesRegex(AssertionError,'Missing packaged source'):
                assert_packaged_source_dependencies(root,rendered)
    def test_altered_startup_plist_cannot_verify_or_enable(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder).resolve();app=base/'Classic.app';(app/'Contents/MacOS').mkdir(parents=True)
            (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleShortVersionString':'15.6'}))
            (app/'Contents/MacOS/Adobe Lightroom Classic').write_bytes(b'fixture-not-executable')
            catalog=base/'Example.lrcat';catalog.write_bytes(b'not-a-database');root=base/'installed'
            command=[sys.executable,str(REPO/'scripts/manage.py'),'install','--root',str(root),'--app',str(app),'--catalog',str(catalog),'--backup-confirmed','--stage-only']
            run=subprocess.run(command,capture_output=True,text=True);self.assertEqual(run.returncode,0,run.stderr)
            plist_path=root/'startup.plist';plist=plistlib.loads(plist_path.read_bytes())
            plist['ProgramArguments']=['/bin/sh','-c','unexpected command'];plist_path.write_bytes(plistlib.dumps(plist))
            with self.assertRaisesRegex(ValueError,'startup.plist'):manage.verified_config(root)
            with mock.patch.object(Path,'home',return_value=base),mock.patch.object(manage.subprocess,'run') as dispatch:
                with self.assertRaisesRegex(ValueError,'startup.plist'):manage.enable(argparse.Namespace(root=str(root),accept_menu_automation=True))
                dispatch.assert_not_called()
            self.assertFalse((root/'ENABLED').exists());self.assertFalse((base/'Library/LaunchAgents').exists())
            # Even a rewritten manifest pin cannot substitute a foreign launch
            # command for the exact configuration-derived Label/argv contract.
            manifest_path=root/'manifest.json';manifest=json.loads(manifest_path.read_text())
            manifest['sha256'][str(plist_path)]=manage.sha(plist_path);manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'Unexpected startup Label'):manage.verified_config(root)
    def test_no_callback_never_proves_success(self):
        self.assertEqual(manage.outcome('submitted','PHASE 0 ok=true'),'waiting_native_callback')
        self.assertEqual(manage.outcome('native callback result=true','PHASE 0 ok=true'),'failed_phase_receipt')
        self.assertEqual(manage.outcome('native callback result=false',''),'failed_native')
    def test_disable_never_unloads_foreign_launchagent(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);root=base/'installed';root.mkdir()
            (root/'config.json').write_text('{}');(root/'manage.py').write_text('fixture')
            (root/'AUTOMATIC-RENEWAL-AUTHORIZED').write_text(manage.RENEWAL_AUTHORIZATION)
            destination=base/'Library/LaunchAgents'/(manage.LABEL+'.plist');destination.parent.mkdir(parents=True)
            original=plistlib.dumps({'Label':manage.LABEL,'ProgramArguments':['/some/other/manage.py','watch']})
            destination.write_bytes(original)
            with mock.patch.object(Path,'home',return_value=base),mock.patch.object(manage.subprocess,'run') as run:
                with self.assertRaisesRegex(ValueError,'another installation'):manage.disable(argparse.Namespace(root=str(root)))
                run.assert_not_called()
            self.assertEqual(destination.read_bytes(),original);self.assertTrue((root/'PAUSED').exists())
            self.assertFalse((root/'AUTOMATIC-RENEWAL-AUTHORIZED').exists())
    def test_public_templates_exclude_media_and_native_bodies(self):
        for p in (REPO/'templates').rglob('*'):
            if p.is_file():
                self.assertLess(p.stat().st_size,50000)
                self.assertNotIn(p.suffix.lower(),('.lrcat','.mcat','.db','.dng','.jpg'))
                content=p.read_text();self.assertNotIn('string.dump(',content);self.assertNotIn('/Users/private-owner',content)

if __name__=='__main__':unittest.main()
