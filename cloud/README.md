# FirstPair Lightroom (Cloud) tools

Tools and findings for **Lightroom (Cloud)**, the app named "Adobe Lightroom", with a large library on macOS.
They were developed and measured on an 868,000-photo library with Lightroom 9.6 on Apple silicon. For
**Lightroom Classic**, see [`../classic/`](../classic/README.md).

Nothing here is supported by Adobe. These tools read Lightroom's databases, and two of them write to Lightroom's
index database (`freeze_build.py` and `index_renewal.py`). Back up `Lightroom Library.lrlibrary` while Lightroom
is quit, and read the code before running it. No library, photo, credential or Adobe code is included.

## What's here

| Topic | Code | Guide |
|---|---|---|
| Faster database queries: indexes Lightroom drops at launch, re-added safely at every launch (and one that made it slower) | [`scripts/freeze_build.py`](scripts/freeze_build.py), [`scripts/index_renewal.py`](scripts/index_renewal.py), [`templates/INDEX-PLAN.json`](templates/INDEX-PLAN.json), [`templates/index-renewal.plist`](templates/index-renewal.plist) | [CLOUD-INDEXES.md](docs/CLOUD-INDEXES.md) |
| Download every Smart Preview, with outage backoff and retries | [`scripts/preview_fetch/`](scripts/preview_fetch/) | [CLOUD-PREVIEW-DOWNLOAD.md](docs/CLOUD-PREVIEW-DOWNLOAD.md) |
| Why Sync stays busy with an empty View list; sync status codes | — | [CLOUD-SYNC-STATUS.md](docs/CLOUD-SYNC-STATUS.md) |
| Reuse Smart Previews you already have locally instead of downloading them | [`scripts/proxy_register.py`](scripts/proxy_register.py), [`scripts/proxy_register.lua`](scripts/proxy_register.lua) | [CLOUD-PROXY-REGISTRATION.md](docs/CLOUD-PROXY-REGISTRATION.md) |
| Recover exact C2PA auxiliary files from closed Classic BigTable storage | [`scripts/extract_bigtable_aux.py`](scripts/extract_bigtable_aux.py) | [BIGTABLE-AUXILIARIES.md](docs/BIGTABLE-AUXILIARIES.md) |
| How the slow queries, HTTP limits and lock behavior were found | — | [CLOUD-PERFORMANCE-DIAGNOSIS.md](docs/CLOUD-PERFORMANCE-DIAGNOSIS.md) |

## Test

From the repository root:

```sh
uv run --no-project python -m unittest discover -s cloud/tests -v
uv run --no-project --with lupa python -m unittest discover -s cloud/tests -v   # also runs the Lua controller controls
```

The tests use SQLite fixtures, a stand-in process for Lightroom (so freezing and resuming really happen) and
Lua 5.1 doubles of Lightroom's SDK. They do not run inside Lightroom.

## Main lessons

- **Don't hold Lightroom's database lock.** Lightroom's own writers give up after about 5 seconds, and some views
  then stay frozen until restart. Freeze the app for the few seconds a build needs, or don't write at all.
- **Pausing Sync doesn't stop the local indexer.**
- **Results:**
  - Statistics (`ANALYZE`) persist across restarts. Indexes don't: Lightroom deletes undeclared indexes at
    launch.
  - "No downloadable original" is decided from the photo's own record. Retrying never helps.
  - A Sync indicator stuck with an empty View usually means a few photos whose upload never finished on another
    device.
