"""Render one sync-recovery Scripts-menu file from a template and a JSON item list.

  uv run --no-project --with lupa python classic/sync-recovery/render.py retry  --items ids.json   ...
  uv run --no-project --with lupa python classic/sync-recovery/render.py resave --items photos.json ...
  uv run --no-project --with lupa python classic/sync-recovery/render.py proxy  --items proxies.json ...

Common options: --catalog /path/Catalog.lrcat --run-root /path/logs --out "/path/Scripts/NN) Name.lua"
retry and proxy also need --cloud-catalog <32-hex Lightroom cloud catalog id>.

Item files:
  retry:  ["<asset id>", ...]
  resave: [{"localId": 123, "path": "/absolute/original/path.dng"}, ...]
  proxy:  [{"id": "<asset id>", "path": "/absolute/Smart Previews.lrdata/.../X.dng", "size": 12345}, ...]
          (produce with preflight_proxy.py; rows with ok=false are skipped)
"""
import argparse, hashlib, json, re, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = {'retry': 'RetrySync.lua', 'resave': 'DevelopResave.lua', 'proxy': 'ProxyPathRefresh.lua'}


def lua(v):
    return '"' + str(v).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


def items_lua(kind, items):
    if kind == 'retry':
        assert all(re.fullmatch(r'[0-9a-f]{32}', i) for i in items), 'asset ids must be 32 lowercase hex'
        return ', '.join(lua(i) for i in items)
    if kind == 'resave':
        return ',\n'.join('  { %d, %s }' % (int(i['localId']), lua(i['path'])) for i in items)
    items = [i for i in items if i.get('ok', True)]
    assert items and all(re.fullmatch(r'[0-9a-f]{32}', i['id']) for i in items), 'no proxy rows passed preflight'
    return ',\n'.join('  { id=%s, path=%s, size=%d }' % (lua(i['id']), lua(i['path']), int(i['size'])) for i in items)


def render(kind, items, catalog, run_root, cloud_catalog=None, key=None):
    src = (HERE / 'templates' / TEMPLATES[kind]).read_text()
    key = key or 'firstpairSyncRecovery_%s_%d' % (kind, int(time.time()))
    subs = {'__CATALOG__': lua(catalog), '__RUNROOT__': lua(run_root.rstrip('/')), '__KEY__': lua(key),
            '__ITEMS__': items_lua(kind, items), '__IDS__': items_lua(kind, items)}
    if '__CLOUD_CATALOG__' in src:
        assert cloud_catalog and re.fullmatch(r'[0-9a-f]{32}', cloud_catalog), '--cloud-catalog required'
        subs['__CLOUD_CATALOG__'] = lua(cloud_catalog)
    for k, v in subs.items():
        if k in src:
            assert src.count(k) == 1, k
            src = src.replace(k, v)
    assert not re.search(r'__(CATALOG|RUNROOT|KEY|ITEMS|IDS|CLOUD_CATALOG)__', src), 'unfilled placeholder'
    return src


def compile_check(code):
    from lupa import lua51
    f = lua51.LuaRuntime().eval('function(s) local f, e = loadstring(s); if not f then error(e) end; return true end')
    return f(code)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('kind', choices=sorted(TEMPLATES))
    ap.add_argument('--items', required=True); ap.add_argument('--catalog', required=True)
    ap.add_argument('--run-root', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--cloud-catalog'); ap.add_argument('--key')
    a = ap.parse_args()
    code = render(a.kind, json.loads(Path(a.items).read_text()), a.catalog, a.run_root, a.cloud_catalog, a.key)
    compile_check(code)
    Path(a.out).write_text(code)
    print(json.dumps({'kind': a.kind, 'out': a.out, 'sha256': hashlib.sha256(code.encode()).hexdigest()}))
