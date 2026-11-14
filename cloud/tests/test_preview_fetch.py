"""Controls for cloud/scripts/preview_fetch/template.lua under Lua 5.1 (lupa); Lightroom's SDK, Rx and event loop are doubles.

Run: uv run --no-project --with lupa python -m unittest discover -s cloud/tests
Skipped when lupa is unavailable. These exercise the authored Lua only, not Lightroom itself.
"""
import json, hashlib, tempfile, pathlib, sys, heapq, itertools, unittest
try:
    import lupa.lua51 as L
except ImportError:  # optional dependency
    L = None

HERE = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'preview_fetch'
TEMPLATE = (HERE / 'template.lua').read_text()
CAT = "0123456789abcdef0123456789abcdef"
PIXELS = "/Users/example/Pictures/Lightroom Library.lrlibrary/" + CAT


class Sim:
    def __init__(self, n_ids, responder, *, paused=False, max_retries=8, retry_delay=600, parallel=12, batch=32,
                 entry=True, stop_at=None, unpause_at=None):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.ids = list(range(1000, 1000 + n_ids))
        (self.dir / 'IDS.lua').write_text('return {' + ','.join(map(str, self.ids)) + '}\n')
        sha = hashlib.sha256((self.dir / 'IDS.lua').read_bytes()).hexdigest()
        self.now = 1_800_000_000
        self.q = []; self.seq = itertools.count()
        self.responder = responder; self.active = 0; self.max_active = 0; self.admitted = []
        self.stop_at = stop_at; self.unpause_at = unpause_at
        params = {'run': str(self.dir), 'nonce': 'n' * 32, 'epoch': self.now, 'catalogID': CAT, 'pixelsPath': PIXELS, 'parallel': parallel,
                  'batchSize': batch, 'timeoutSeconds': 1800, 'idsSHA256': sha, 'maxRetries': max_retries,
                  'retryDelay': retry_delay, 'backoffBase': 120, 'backoffMax': 900}
        self.script = TEMPLATE.replace('__PARAMS__', '{' + ','.join(f'[{json.dumps(k)}]={json.dumps(v)}' for k, v in params.items()) + '}')
        self.lua = L.LuaRuntime(unpack_returned_tuples=True)
        g = self.lua.globals()
        sim = self
        g.os.time = lambda *a: sim.now
        self.lua.execute("""
        function _mk_sad() local s={} function s:setDisposable(d) self.d=d end function s:dispose() if self.d then self.d:dispose() end end return s end
        """)
        mods = self.lua.table()
        mods['Rx'] = self.lua.eval('{SingleAssignmentDisposable=_mk_sad}')
        loop = self.lua.table(); loop['afterDelay'] = lambda d, f: sim.schedule(d, f); mods['AgEventLoop'] = loop
        lib = self.lua.table()
        lib['withActiveUserModel'] = lambda cb: cb(sim.user_model())
        lib['withActiveCatalogModel'] = lambda cb: cb(sim.cat_model())
        mods['AgLibrary'] = lib
        g['import'] = lambda name: mods[name]
        crypto = self.lua.table(); crypto['digestFile'] = lambda path, alg: hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest().upper()
        old_require = g.require
        g.require = lambda name: crypto if name == 'WFCrypto' else old_require(name)
        self.paused = paused
        self.user_obs = None

    # --- doubles
    def observable(self, subscribe):
        t = self.lua.table(); t['subscribe'] = lambda self_, on_next, on_err=None, on_done=None: subscribe(on_next, on_err, on_done)
        m = self.lua.table(); m['value'] = lambda self_: t
        return m

    def disposable(self, fn=lambda: None):
        d = self.lua.table(); d['dispose'] = lambda self_: fn(); return d

    def user_model(self):
        def sub(on_next, on_err, on_done):
            self.user_obs = on_next
            self.schedule(0, lambda: on_next(self.lua.table_from({'syncPaused': self.paused})))
            return self.disposable()
        return self.observable(sub)

    def cat_model(self):
        sim = self
        def sub(on_next, on_err, on_done):
            self.schedule(0, lambda: on_next(self.lua.table_from({'hasCatalog': True, 'ozCatalogId': CAT, 'pixelsPath': PIXELS})))
            return self.disposable()
        m = self.observable(sub)
        m['subModel'] = lambda self_, name, ids: sim.request(name, list(ids.values()))
        return m

    def request(self, name, ids):
        assert name == 'getProxyPaths'
        self.active += 1; self.max_active = max(self.max_active, self.active); self.admitted.append((self.now, ids))
        closed = {'v': False}
        def sub(on_next, on_err, on_done):
            delay, rows = self.responder(self, ids)
            def deliver():
                if closed['v']: return
                on_next(self.lua.table_from({i + 1: self.lua.table_from({'imageId': r[0], 'proxyPath': r[1]}) for i, r in enumerate(rows)}))
            self.schedule(delay, deliver)
            return self.disposable()
        m = self.observable(sub)
        def close(_s):
            if not closed['v']: closed['v'] = True; self.active -= 1
        m['close'] = close
        return m

    def schedule(self, d, f):
        heapq.heappush(self.q, (self.now + max(0, d), next(self.seq), f))

    # --- driver
    def run(self, horizon=10 * 24 * 3600):
        self.lua.execute(self.script)
        end = self.now + horizon
        while self.q and self.now <= end:
            t, _, f = heapq.heappop(self.q)
            self.now = max(self.now, t)
            if self.stop_at is not None and self.now >= self.stop_at and not (self.dir / 'STOP.json').exists():
                (self.dir / 'STOP.json').write_text('{}')
            if self.unpause_at is not None and self.now >= self.unpause_at and self.paused:
                self.paused = False
                if self.user_obs: self.user_obs(self.lua.table_from({'syncPaused': False}))
            f()
        return self

    def events(self):
        return [l.split('\t') for l in (self.dir / 'EVENTS.txt').read_text().splitlines()]

    def progress(self):
        return json.loads((self.dir / 'PROGRESS.json').read_text())


def run_all():
    def ok_paths(sim, ids):
        return 20, [(i, f'/p/{i}') for i in ids]


    def check(name, cond, info=''):
        print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else '  ' + str(info)))
        return cond


    results = []
    # 1 normal
    s = Sim(1000, ok_paths).run(); p = s.progress(); ev = s.events()
    results.append(check('normal: all paths, closed, no retries', ev[-1][1] == 'CLOSED' and p['paths'] == 1000 and p['retryQueued'] == 0 and s.max_active <= 12, p))

    # 2 outage window then recovery
    T0 = 1_800_000_000; OUT = (T0 + 600, T0 + 600 + 2 * 3600)
    def outage(sim, ids):
        if OUT[0] <= sim.now < OUT[1]:
            return 1, [(i, 'CannotSyncDownloadToFileError') for i in ids]
        return 20, [(i, f'/p/{i}') for i in ids]
    s = Sim(20000, outage).run(); p = s.progress(); ev = s.events()
    during = [a for a in s.admitted if OUT[0] <= a[0] < OUT[1]]
    results.append(check('outage: every id eventually downloaded', p['paths'] == 20000 and p['retryExhausted'] == 0 and ev[-1][1] == 'CLOSED', p))
    results.append(check('outage: backoff limits admissions during 2h outage', len(during) < 60, len(during)))
    results.append(check('outage: backoff and recovery recorded', any(e[1] == 'OUTAGE_BACKOFF' for e in ev) and any(e[1] == 'OUTAGE_RECOVERED' for e in ev)))
    results.append(check('outage: concurrency never above 12', s.max_active <= 12, s.max_active))
    # unique path count == ids (no double download of a successful id)
    paths = [e[2] for e in ev if e[1] == 'ROW_PATH']
    results.append(check('outage: each id path-returned exactly once', len(paths) == len(set(paths)) == 20000, (len(paths), len(set(paths)))))

    # 3 permanently refused ids exhaust and close
    BAD = set(range(1000, 1010))
    def some_bad(sim, ids):
        return 5, [(i, 'CannotSyncDownloadToFileError' if i in BAD else f'/p/{i}') for i in ids]
    s = Sim(500, some_bad, max_retries=3, retry_delay=60).run(); p = s.progress(); ev = s.events()
    results.append(check('persistent refusals: exhausted after max retries, run closes', ev[-1][1] == 'CLOSED' and p['retryExhausted'] == 10 and p['paths'] == 490 and p['retryAdmitted'] == 30, p))

    # 4 non-retryable status not retried
    def norig(sim, ids):
        return 5, [(i, 'SendNoDownloadableOriginal' if i == 1003 else f'/p/{i}') for i in ids]
    s = Sim(100, norig).run(); p = s.progress()
    results.append(check('SendNoDownloadableOriginal is final, not retried', p['retryQueued'] == 0 and p['statuses'] == 1 and p['paths'] == 99, p))

    # 5 STOP stops admissions, drains, closes
    s = Sim(20000, ok_paths, stop_at=T0 + 100).run(); p = s.progress(); ev = s.events()
    after = [a for a in s.admitted if a[0] > T0 + 100]
    results.append(check('STOP: no admissions after STOP, closed', ev[-1][1] == 'CLOSED' and not after and any(e[1] == 'STOP_OBSERVED' for e in ev), (len(after), ev[-1])))

    # 6 Sync paused gates admissions until unpaused
    s = Sim(200, ok_paths, paused=True, unpause_at=T0 + 300).run(); p = s.progress()
    results.append(check('paused: nothing admitted while paused, completes after unpause', all(a[0] >= T0 + 300 for a in s.admitted) and p['paths'] == 200, (s.admitted[:1], p)))

    # 7 replay guard
    s = Sim(10, ok_paths).run()
    try:
        s.lua.execute(s.script); replay = False
    except Exception as e:
        replay = 'no replay' in str(e)
    results.append(check('replay: second entry refused by persistent lock', replay))

    # 8 compile-only check of the template with placeholder params
    lua = L.LuaRuntime()
    f = lua.eval('function(s) local fn,err=loadstring(s) if not fn then error(err) end return true end')
    results.append(check('compiles under Lua 5.1', f(TEMPLATE.replace('__PARAMS__', '{}'))))

    return results


@unittest.skipIf(L is None, "lupa unavailable")
class PreviewFetchController(unittest.TestCase):
    def test_all_controls(self):
        results = run_all()
        self.assertTrue(results and all(results), results)


if __name__ == "__main__":
    unittest.main()
