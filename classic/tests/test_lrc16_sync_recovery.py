"""Source-level tests for classic/lrc16 and classic/sync-recovery. These do not run Lightroom."""
import importlib.util, json, re, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    import lupa  # noqa: F401
    HAVE_LUPA = True
except ImportError:
    HAVE_LUPA = False


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


class Lrc16Build(unittest.TestCase):
    def test_sources_are_path_free(self):
        for p in (ROOT / 'lrc16' / 'server').glob('*.lua'):
            t = p.read_text()
            self.assertEqual(t.count('__CATALOG__'), 1, p.name)
            self.assertNotRegex(t, r'/Users/|/Volumes/|[0-9a-f]{32}', p.name)

    @unittest.skipUnless(HAVE_LUPA, 'needs lupa (uv run --with lupa)')
    def test_build_embeds_catalog_and_compiles(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'APPLY16.lua'
            cat = '/Users/someone/Pictures/My "Quoted" Catalog.lrcat'
            r = subprocess.run([sys.executable, str(ROOT / 'lrc16' / 'build.py'), '--catalog', cat, '--run-root', d + '/logs/',
                                '--out', str(out)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)['revision'], 'lrc16-apply-v3')
            t = out.read_text()
            self.assertEqual(t.count('My \\"Quoted\\" Catalog.lrcat'), 4)  # UI gate + three server owner gates
            for marker in ('AUTOCOMMIT savepoint not open', 'RESTORED_ORIGINAL', 'DROPPED_PARTIAL', 'BODY_DONE_RELEASE_ERROR', '+id_local'):
                self.assertIn(marker, t)


class SyncRecoveryRender(unittest.TestCase):
    def setUp(self):
        self.r = load('render', ROOT / 'sync-recovery' / 'render.py')
        self.a = '0123456789abcdef0123456789abcdef'

    def check(self, code):
        self.assertNotRegex(code, r'__(CATALOG|RUNROOT|KEY|ITEMS|IDS|CLOUD_CATALOG)__')
        if HAVE_LUPA: self.assertTrue(self.r.compile_check(code))

    def test_retry(self):
        self.check(self.r.render('retry', [self.a], '/c/a.lrcat', '/logs', self.a))

    def test_resave(self):
        self.check(self.r.render('resave', [{'localId': 12, 'path': '/p/x "y".dng'}], '/c/a.lrcat', '/logs'))

    def test_proxy_skips_failed_rows(self):
        code = self.r.render('proxy', [{'id': self.a, 'path': '/sp/A.dng', 'size': 5, 'ok': True},
                                       {'id': 'f' * 32, 'path': '/sp/B.dng', 'size': 6, 'ok': False}], '/c/a.lrcat', '/logs', self.a)
        self.check(code); self.assertIn('/sp/A.dng', code); self.assertNotIn('/sp/B.dng', code)

    def test_rejects_bad_input(self):
        with self.assertRaises(AssertionError): self.r.render('retry', ['not-an-id'], '/c/a.lrcat', '/logs', self.a)
        with self.assertRaises(AssertionError): self.r.render('retry', [self.a], '/c/a.lrcat', '/logs', None)
        with self.assertRaises(AssertionError):
            self.r.render('proxy', [{'id': self.a, 'path': '/x', 'size': 1, 'ok': False}], '/c/a.lrcat', '/logs', self.a)


if __name__ == '__main__':
    unittest.main()
