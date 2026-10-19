# Recover exact C2PA auxiliaries from closed Classic storage

Classic's `.lrcat-data` package can contain auxiliary payloads absent from
Cloud's cache. A qualified recovery exported 86 C2PA payloads matching Cloud's
requested sizes and SHA-256 hashes. Their cache placement was verified separately;
native adoption remained pending. This does not recreate signatures or reset edits.

## Prerequisites and extraction

Use macOS/APFS, a closed stable `.lrcat-data` package, and a new private output
directory on the same volume. The output's parent must already exist. The tool
rejects source open handles, symlinks, and source-family changes. It has no
ordinary-copy fallback when APFS cloning fails.

Supply a private JSON array of current auxiliary manifests. Each object needs
`type` equal to `c2pa`, `digest` as 32 uppercase hexadecimal characters, `sha256`
as 64 lowercase hexadecimal characters, and positive integer `fileSize`. Obtain
these from current read-only evidence; filenames are not identity proof.

```sh
uv run --script scripts/extract_bigtable_aux.py \
  --source "$HOME/Pictures/Lightroom/MyCatalog/MyCatalog.lrcat-data" \
  --manifest /private/path/current-aux-manifest.json \
  --output /private/path/new-aux-recovery
```

The script's inline metadata pins its optional dependency. It makes a complete
APFS clone through held source descriptors, verifies the original family, then
opens **only its private clone** in raw-byte read-only mode. Read-only mode alone
is insufficient: the binding can write housekeeping metadata. The
[RocksDict API](https://rocksdict.github.io/RocksDict/rocksdict.html) documents the
access mode; the isolated copy is an additional safeguard.

The observed BigTable key format is the uppercase ASCII digest. An export must
match both the requested whole-file SHA and size. Equal hashes can share one
export. Wrong hashes/sizes remain held, and different existing output is never
overwritten. An absent key establishes only absence of that key in this snapshot.

## Verification and next step

`SOURCE-FAMILY.json` retains original file identities. `RESULT.json` reports each
exact export/hold and the unchanged original-family check. `FAILURE.json` retains
a rejected run. Partial exports are not a completed recovery; use a new directory
for a qualified successor, preserving the failure.

The tool does not open a Lightroom SQLite catalog, discover manifests, write to
Cloud's cache, register files, or enable Sync. Keep manifests, snapshots, receipts
and payloads private. Exact bytes do not establish cryptographic C2PA validity.

Publication is separate: freshly bind the asset/revision/expected payload, verify
the installed native cache-path contract, use no-overwrite placement, and observe
ordinary native adoption. Do not edit annotations, availability flags, revisions
or queues through SQLite, or claim editing/Sync completion from an exported file.

## Undo and limits

The source is preserved. Retain private output until recovery is independently
accepted; there is no installed runtime component to disable. This is a finite
C2PA/raw-key route, not a reader for every Classic BigTable encoding.

Run synthetic extraction and existing package checks with:

```sh
uv run --no-project --with rocksdict==0.3.29 --with msgpack \
  python -m unittest discover -s tests -v
```
