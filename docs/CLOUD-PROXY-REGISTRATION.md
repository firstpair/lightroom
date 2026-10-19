# Register placed Smart Preview clones with Lightroom Cloud's proxy loader

`scripts/proxy_register.py` makes Lightroom Cloud (desktop) recognize Smart
Preview files that were already cloned into its cache. Placement alone does not
register anything: in the reference library, 465,411 exact clones sat in
`proxies/2560` for five days with "Store a copy of all Smart Previews locally"
enabled and the index still said `needsProxyDownload`. The native loader only
annotates a document when it is asked for that document's proxy path.

The only native action is one ordinary user Script selected from Cloud's
**Scripts** menu. It issues the normal `getProxyPaths` request for 256 documents
at a time, reads each document before and after through the ordinary asset
stream, and holds a row when anything other than the added proxy annotation
changed. Python never opens a store for writing, never forges an annotation or
flag, and never touches the network.

Measured on the reference run: about 45 documents per second, four batches in
flight, 0 body/revision/label changes across the first 150,000 recognitions.

## What the loader does

For a document whose `importSource.proxySHA256` is present and whose clone is at
the literal native path (`proxies/2560/<first 3 hex>/<remaining 29 hex>` of the
asset id), the request returns `{imageId, proxyPath}` and native adds exactly

```
_localOnly.files.proxy["2560"] = {volumeGuid, relativePath, lastSaveTimestamp}
```

The expected hash, the public body, the revision and the stored labels are
unchanged. The index then flips `hasLocalProxy` to 1 and `needsProxyDownload`
to 0. When native declines a document it returns a status string such as
`SendNoDownloadableOriginal` instead of a path; the Script records that as a
per-row hold and continues.

## Prerequisites

- macOS, Lightroom Cloud desktop, Accessibility permission for the terminal that
  will select the menu entry, `uv` and the `msgpack` package (`uv run --with msgpack`).
- Clones already placed by a verified publication: whole-file SHA equal to the
  document's `importSource.proxySHA256`, independent inodes, no overwrite.
- A fresh Cloud launch under network and original-source denial. `launch`
  writes a `sandbox-exec` profile that denies outbound IP, `/Volumes`, the
  library's `originals` folder and any `--deny` path (give it the Classic Smart
  Previews folder and your originals). Verify zero sockets with
  `lsof -nP -p <pid> -a -i` before any native batch.
- A placeholder file named `Register known-hash Smart previews.lua` in
  `~/Library/Application Support/Adobe/Lightroom CC/Scripts` **before** launch:
  the menu lists the names present at launch and reads the file when selected.

## Procedure

```sh
LIB="$HOME/Pictures/Lightroom Library.lrlibrary/<catalog id>"
uv run --no-project --with msgpack python scripts/proxy_register.py ledger --library "$LIB" --output run/ledger
uv run --no-project python scripts/proxy_register.py launch --library "$LIB" --output run/launch --deny "<Classic Smart Previews.lrdata>"
uv run --no-project python scripts/proxy_register.py arm --library "$LIB" --launcher-evidence run/launch/LAUNCHER-EVIDENCE.json \
    --output run --authorization "<who authorized this run and when>"
uv run --no-project python scripts/proxy_register.py bind --ledger-complete run/ledger/COMPLETE.json --arm run/ARM-<nonce>.json --output run/native
uv run --no-project python scripts/proxy_register.py stage --run run/native
uv run --no-project python scripts/proxy_register.py guard --plan run/native/CONTROLLER-PLAN.json --plan-sha256 <sha> &
uv run --no-project python scripts/proxy_register.py select
```

The guard refreshes `LIVE-SOURCE-GUARD.lua` every second with the process
identity, the destination clones' five-field identities and the approved
batches. It approves only batch 1 until you create `CONTROL-ACCEPTED.json` in
the run directory. Inspect `BATCH-00001-NATIVE-AFTER.jsonl` first: every row
must show the three-field annotation and nothing else changed. Then accept.

Rows are skipped, never fabricated: already annotated documents, documents
whose live body or annotation differs from the closed ledger, and native
refusals are logged as holds and the run continues. The controller halts only
on request-level protocol or owner failures, and `STOP-NEW-ADMISSIONS.json`
stops future admissions without cancelling in-flight requests.

To retry after a halt, build a fresh arm and `bind --batches-from run/native`
(batch files are reused; the owner key is per nonce). Already registered rows
are skipped quickly.

## Verify

After the controller writes `CONTROLLER_CLOSED` and the guard writes
`GUARD-NATIVE-CLOSED-OBSERVATION.json`, quit Cloud normally and run

```sh
uv run --no-project --with msgpack python scripts/proxy_register.py postaudit --library "$LIB" \
    --ledger-rows run/ledger/NATIVE-INPUTS.jsonl --output run/postaudit
```

It classifies every ledger row by registration, body equality, revision, the
annotation minus the added proxy entry, label names and index flags. When
subtracting that entry, the observer removes an empty parent map only if that
parent was absent in the exact baseline. Existing empty maps, other proxy
classes, profile information and every unrelated annotation remain protected.

## Limits

- The ledger is a closed snapshot. Native refreshes `_localOnly.cameraProfileInfo`
  after a relaunch, so about one percent of rows drift and are skipped; rebuild
  the ledger and run a short second pass rather than weakening the before-guard.
- A `/rels/proxy_type/2560` link marked `invalid` is denied-download bookkeeping,
  not a loader fact. `localStatusAndOzStatus.proxySize` is the proxy class
  (2560), not a byte size.
- Registration proves a recognized local proxy. It is not settings readiness,
  a rendered-preview test, numeric-edit readiness or server convergence.
- Documents without `importSource.proxySHA256` need the separately qualified
  unknown-hash route and are held here.
