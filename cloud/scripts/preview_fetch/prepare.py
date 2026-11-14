"""Prepare a Lightroom (Cloud) Smart Preview download run: roster of missing previews + rendered menu script.

Run with Lightroom (Cloud) quit (the roster is a consistent read-only snapshot of the closed store):

    uv run --no-project python cloud/scripts/preview_fetch/prepare.py \
        --library "$HOME/Pictures/Lightroom Library.lrlibrary/<catalog-id>" --out runs/fetch-1 \
        [--previous runs/fetch-0 ...]

Then copy <out>/script.lua over a script in Lightroom's Scripts folder that already appears in the Scripts menu
(Lightroom lists scripts present at launch and reads their contents when clicked), and choose it from the menu
within one hour. The script asks Lightroom's ordinary `getProxyPaths` for each photo (Lightroom downloads and
registers its own server preview), 12 requests of 32 photos at a time, and writes EVENTS.txt / PROGRESS.json to
<out>. Create <out>/STOP.json to stop admitting new work; in-flight requests finish normally.

Holds: photos whose current record is missing, deleted or conflicted; photos that a --previous run saw refused
with SendNoDownloadableOriginal (that refusal is decided from the photo's own record, not by the server, so
retrying won't help); and rows not marked needsProxyDownload.
"""
from pathlib import Path
import argparse, hashlib, json, secrets, sqlite3, subprocess, time

HERE = Path(__file__).resolve().parent


def known_refusals(previous):
    refused, uuid_of = {}, {}
    for run in previous:
        rows = Path(run) / "ROWS.jsonl"
        if rows.exists():
            for line in rows.open():
                r = json.loads(line); uuid_of.setdefault(r["localID"], r["assetUUID"])
        events = Path(run) / "EVENTS.txt"
        if events.exists():
            for line in events.open():
                f = line.rstrip("\n").split("\t")
                if len(f) == 4 and f[1] == "STATUS" and f[3] == "SendNoDownloadableOriginal":
                    refused[int(f[2])] = None
    return {i: uuid_of.get(i) for i in refused}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--library", required=True, help="the <catalog-id> folder inside 'Lightroom Library.lrlibrary'")
    ap.add_argument("--out", required=True, help="new run directory")
    ap.add_argument("--previous", nargs="*", default=[], help="earlier run directories (to hold known refusals)")
    ap.add_argument("--parallel", type=int, default=12); ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--max-retries", type=int, default=8); ap.add_argument("--retry-delay", type=int, default=600)
    ap.add_argument("--allow-running", action="store_true", help="read while Lightroom runs (not a consistent snapshot)")
    a = ap.parse_args()

    lib = Path(a.library).resolve()
    if not a.allow_running and subprocess.run(["pgrep", "-x", "Adobe Lightroom"], capture_output=True).returncode == 0:
        raise SystemExit("Quit Lightroom (Cloud) first, or pass --allow-running")
    refused = known_refusals(a.previous)
    wf = sqlite3.connect("file:" + str(lib / "Managed Catalog.wfindex") + "?mode=ro", uri=True)
    wf.execute("PRAGMA query_only=1"); wf.execute("BEGIN")
    rows = wf.execute("SELECT a.docId,a.assetId,l.needsProxyDownload FROM localStatusAndOzStatus l JOIN assets a ON a.docId=l.docId "
                      "WHERE l.subtype='image' AND l.isVersionDocument=0 AND l.hasLocalProxy=0 ORDER BY l.docId").fetchall()
    wf.rollback(); wf.close()
    mc = sqlite3.connect("file:" + str(lib / "Managed Catalog.mcat") + "?mode=ro", uri=True)
    mc.execute("PRAGMA query_only=1"); mc.execute("BEGIN")
    ids, held = [], []
    for local_id, uuid, need in rows:
        doc = mc.execute("SELECT deleted,hasConflicts FROM docs WHERE fullDocId=? AND localDocId=?", (uuid, local_id)).fetchone()
        if not doc or doc[0] or doc[1]:
            held.append({"localID": local_id, "assetUUID": uuid, "reason": "missing/deleted/conflicted record"})
        elif local_id in refused and refused[local_id] in (None, uuid):
            held.append({"localID": local_id, "assetUUID": uuid, "reason": "SendNoDownloadableOriginal in a previous run"})
        elif need != 1:
            held.append({"localID": local_id, "assetUUID": uuid, "reason": "needsProxyDownload != 1"})
        else:
            ids.append((local_id, uuid))
    mc.rollback(); mc.close()

    out = Path(a.out); out.mkdir(parents=True, exist_ok=False)
    (out / "IDS.lua").write_text("return {" + ",".join(str(i) for i, _ in ids) + "}\n")
    (out / "ROWS.jsonl").write_text("".join(json.dumps({"localID": i, "assetUUID": u}) + "\n" for i, u in ids))
    (out / "HOLDS.json").write_text(json.dumps(held, indent=1) + "\n")
    params = {"run": str(out.resolve()), "nonce": secrets.token_hex(16), "epoch": int(time.time()), "catalogID": lib.name,
              "pixelsPath": str(lib), "parallel": a.parallel, "batchSize": a.batch, "timeoutSeconds": 1800,
              "idsSHA256": hashlib.sha256((out / "IDS.lua").read_bytes()).hexdigest(), "maxRetries": a.max_retries,
              "retryDelay": a.retry_delay, "backoffBase": 120, "backoffMax": 900}
    script = (HERE / "template.lua").read_text().replace(
        "__PARAMS__", "{" + ",".join("[%s]=%s" % (json.dumps(k), json.dumps(v)) for k, v in params.items()) + "}")
    (out / "script.lua").write_text(script)
    summary = {"photos": len(ids), "holds": len(held), "expires": time.strftime("%H:%M", time.localtime(params["epoch"] + 3600)),
               "script": str(out / "script.lua")}
    (out / "PREPARED.json").write_text(json.dumps(dict(summary, params=params), indent=1) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
