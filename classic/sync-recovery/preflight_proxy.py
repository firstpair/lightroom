"""Read-only: find Smart Preview (proxy) records whose recorded volume/path no longer resolves, and check whether the
same preview file next to the catalog is byte-identical to what the cloud expects. Writes rows for render.py proxy.

  uv run --no-project --with msgpack python classic/sync-recovery/preflight_proxy.py \
      --sync-store "/path/<Catalog> Sync.lrdata/<cloud catalog id>" \
      --smart-previews "/path/<Catalog> Smart Previews.lrdata" --out proxies.json \
      [--queued | --volume-guid <GUID> [--synced-only]]

--queued (default) selects pending proxy uploads with fileMaybeOnOfflineVolume=1 in needsBinaryUpload.
--volume-guid selects every record on that volume ID; --synced-only keeps only records that already have a valid
server proxy link (re-registering those uploads nothing). A row is ok only if: the local file exists, its SHA-256 and
size equal the recorded spec, the spec SHA equals the document's importSource.proxySHA256, the document is not
deleted, and importSource.c2paIngredients is absent (the proxy-only setter would otherwise delete it).
Opens both stores with mode=ro and query_only. Never writes.
"""
import argparse, hashlib, json, os, sqlite3, urllib.parse
import msgpack


def ro(path):
    c = sqlite3.connect('file:' + urllib.parse.quote(path) + '?mode=ro', uri=True, timeout=10)
    c.execute('PRAGMA query_only=1'); return c


def unpack(b): return msgpack.unpackb(b, raw=False, strict_map_key=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sync-store', required=True); ap.add_argument('--smart-previews', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--volume-guid'); ap.add_argument('--synced-only', action='store_true')
    ap.add_argument('--queued', action='store_true')
    a = ap.parse_args()
    m = ro(os.path.join(a.sync_store, 'Managed Catalog.mcat')); m.text_factory = bytes
    if a.volume_guid:
        ids = [r[0].decode() for r in m.execute('SELECT fullDocId FROM docs')]
    else:
        w = ro(os.path.join(a.sync_store, 'Managed Catalog.wfindex'))
        ids = [r[0] for r in w.execute("SELECT docId FROM needsBinaryUpload WHERE binaryType='proxy' AND fileMaybeOnOfflineVolume=1")]
    out = []
    for doc_id in ids:
        row = m.execute('SELECT annotation, winningRevSequence FROM docs WHERE fullDocId = CAST(? AS TEXT)', (doc_id,)).fetchone()
        if not row: continue
        try: an = unpack(row[0])
        except Exception: continue
        if not isinstance(an, dict): continue
        spec = ((an.get('_localOnly') or {}).get('files') or {}).get('proxy', {}).get('2560')
        if not isinstance(spec, dict): continue
        if a.volume_guid and spec.get('volumeGuid') != a.volume_guid: continue
        link = (an.get('_serverProvidedMetadata') or {}).get('links', {}).get('/rels/proxy_type/2560')
        if a.synced_only and not (isinstance(link, dict) and not link.get('invalid')): continue
        body = unpack(m.execute('SELECT content FROM revs WHERE sequence = ?', (row[1],)).fetchone()[0])
        src = body.get('importSource') or {}
        rel = spec.get('relativePath') or ''
        path = os.path.join(a.smart_previews, rel.split('.lrdata/')[-1]) if '.lrdata/' in rel else None
        sha = hashlib.sha256(open(path, 'rb').read()).hexdigest() if path and os.path.isfile(path) else None
        why = 'ok'
        if body.get('_deleted') or body.get('deleted'): why = 'deleted'
        elif not sha: why = 'no local file'
        elif sha != spec.get('sha256'): why = 'local file differs from record'
        elif spec.get('sha256') != src.get('proxySHA256'): why = 'record differs from cloud'
        elif os.path.getsize(path) != spec.get('size'): why = 'size differs'
        elif src.get('c2paIngredients') is not None: why = 'c2pa ingredients present'
        out.append({'id': doc_id, 'path': path, 'size': os.path.getsize(path) if sha else None, 'volumeGuid': spec.get('volumeGuid'),
                    'relativePath': rel, 'ok': why == 'ok', 'why': why})
    with open(a.out, 'w') as f: json.dump(out, f, indent=1)
    counts = {}
    for r in out: counts[r['why']] = counts.get(r['why'], 0) + 1
    print(json.dumps({'rows': len(out), 'counts': counts}))


if __name__ == '__main__':
    main()
