# Faster Lightroom (Cloud) database queries with extra indexes

Lightroom (Cloud), the app called "Adobe Lightroom", keeps a SQLite search index of the library in
`Lightroom Library.lrlibrary/<catalog-id>/Managed Catalog.wfindex`. On a large library (here 868,000 photos,
3.47 million rows in `asset_sync_status_ui`, 1.33 million in `purgeCandidates`), some of the queries Lightroom
runs over and over take seconds each. Two extra indexes make the cache-related ones take milliseconds.

This page explains what to add, how to add it without disturbing Lightroom, and why the simpler ways fail.
Everything here was measured on Lightroom 9.6 (macOS, Apple silicon).

## The indexes

| Index | What it speeds up | Measured |
|---|---|---|
| `purgeCandidates(binaryType, hasLocalFile, isPurgeable, volumeGuidUsedByFile, fileSize, contentIdOrSha256)` | cache-size sums per file type and volume | 0.08–0.14 s → 0.0001–0.05 s |
| `purgeCandidates(binaryType, isPurgeable, contentIdOrSha256, hasLocalFile, fileSize)` | cached-settings cleanup (`EXCEPT` of digests) | 0.35 s → 0.15 s |

The exact statements, and the queries used to prove them, are in
[`cloud/templates/INDEX-PLAN.json`](../templates/INDEX-PLAN.json). Every index was checked by running each
query once with the index and once with `NOT INDEXED` in the same database snapshot; the typed results matched
exactly every time.

## An index that made Lightroom slower

`asset_sync_status_ui(keepLocallyConfiguration, prioritizedSyncStatus)` sped up the sync-status panel queries it
was built for, from 1.5 s warm (15 s cold) to 0.0001 s. But it broke another query on the same table: the status
lookup for a list of photos (`... FROM CARRAY(...) LEFT JOIN asset_sync_status_ui ON ... docId WHERE
keepLocallyConfiguration == ? AND prioritizedSyncStatus IN (...)`). SQLite chose the new index for it:

| State | Time | Plan |
|---|---|---|
| New index, no statistics | 10.7 s | new index, then scan the photo list |
| New index, after `ANALYZE` | 1.5 s | still the new index |
| Without the new index | 0.0006 s | Lightroom's own `asset_sync_status_ui_docId` |

Lightroom runs that lookup when it opens photos for editing. At 10.7 s it exceeds the Versions feature's
10-second limit ("establishing image owner took more than 10 seconds", "Boot version processing took more than
10 seconds"). The index is now marked "do not use" in the plan's `optional` list.

**Lesson:** an index can be picked by queries you didn't test. Before adding one, check the plans of all of
Lightroom's queries on that table (the diagnostic report's profile lists them), not only the ones you want to
speed up.

Statistics matter too. One status query that looks up a list of assets (`... IN CARRAY(...)`) took 6.5 s
because SQLite picked the wrong index. After `ANALYZE asset_sync_status_ui` it took 0.6 ms. Unlike indexes,
the statistics in `sqlite_stat1` survive restarts, so this only needs to be done once.

## The catch: Lightroom deletes them at every launch

When Lightroom starts, it deletes any index its built-in schema doesn't declare. The schema lives inside the
signed app, so the indexes have to be added again after each launch. Only Adobe can make them permanent.

## Why you can't just run `CREATE INDEX`

Lightroom's own index writers wait only about 5 seconds for a database lock, then give up. When they give up,
some views (the main grid, the loupe filmstrip and trash) report "fatal error ... will not update until app
restarts". Building one of these indexes holds the write lock for 2–10 seconds on a live library, which is enough
to trigger that.

Things that don't work:

- **One long transaction** that checks, builds and analyzes: about 40 s of lock, and hundreds of "database is
  locked" errors.
- **Short transactions timed for quiet moments:** fine for the two purge indexes (1.5–4 s), but the status index
  needed 7–10 s live (2 s on a private copy), well past Lightroom's patience.
- **Pausing Sync:** doesn't stop Lightroom's local indexer, which is the writer that fails.
- **Going through Lightroom's own writer:** the index database is written by a worker thread that only accepts a
  fixed set of requests, none of which runs arbitrary SQL.

## What works: freeze, build, resume

[`cloud/scripts/freeze_build.py`](../scripts/freeze_build.py) builds one index like this:

1. Wait until `PRAGMA data_version` has not changed for 30 s, so Lightroom isn't writing.
2. Start a separate timer that will resume Lightroom after 60 s no matter what.
3. Freeze Lightroom with `SIGSTOP`.
4. Try `BEGIN IMMEDIATE` without waiting. If Lightroom was in the middle of a write, resume it and try again
   after the next quiet window.
5. `CREATE INDEX`, `COMMIT`, then resume Lightroom with `SIGCONT`.
6. Prove each query returns the same typed results with and without the index.

While Lightroom is frozen it can't try to write, so it can't fail. SQLite's busy handler counts its own sleeps
rather than the clock, so frozen time doesn't use up its patience. A freeze of a few seconds is milder than the
Mac sleeping, which Lightroom handles all the time. Our connection never checkpoints the WAL; Lightroom does that
itself when it resumes.

Measured on a live library (Lightroom frozen for):

| Run | purge volume | purge hash | status |
|---|---|---|---|
| manual | — | 5.2 s | 10.5 s |
| first automatic | 3.1 s | 2.3 s | 9.3 s |

Lightroom logged no lock errors and no frozen views in either run.

**This is a direct write to the live database from outside Lightroom.** SQLite supports several processes sharing
a database in WAL mode, and an index is a standard database object, but it is not something Adobe supports. Make a
backup first and read the code.

## Doing it at every launch

[`cloud/scripts/index_renewal.py`](../scripts/index_renewal.py) notices a new Lightroom process and then:

1. Waits 90 s for it to settle.
2. Takes an APFS-clone rollback of `Managed Catalog.wfindex`.
3. Runs `freeze_build.py` for each index in the plan.
4. Scans Lightroom's console log for "database is locked".
5. Keeps only the newest rollback.

Each launch is attempted once; any problem holds the run until the next launch.

```sh
uv run --no-project python cloud/scripts/index_renewal.py once \
  --library "$HOME/Pictures/Lightroom Library.lrlibrary/<catalog-id>" \
  --state-dir "$HOME/Library/Application Support/FirstPair Lightroom Cloud Indexes" --dry-run
```

To run it automatically, fill in [`cloud/templates/index-renewal.plist`](../templates/index-renewal.plist) and
load it with `launchctl bootstrap`. To undo: unload the LaunchAgent and restart Lightroom (which deletes the
indexes), or `DROP INDEX` them by name.

## Candidates not in the default list

Lightroom's internal diagnostic report (generated here with `WFDiagnosticLog.makeInnerHTMLReport` from a menu
script; see [CLOUD-PERFORMANCE-DIAGNOSIS.md](CLOUD-PERFORMANCE-DIAGNOSIS.md)) includes a per-query profile. The largest remaining costs are queries that test sync-status bit masks (measured
while the narrow status index was present):

| Query shape | Today | With `(keepLocallyConfiguration, syncStatuses, assetId)` |
|---|---|---|
| albums containing assets matching a mask | 0.35 s | 0.036 s |
| assets matching a mask, plus unconfirmed deletions | 0.35 s | 0.036 s |
| albums kept offline that contain matching assets | 1.0–2.2 s | 0.7–1.2 s |

That index takes about 6.5 s to build on a private copy, so likely 20–30 s frozen live. It is listed under
`optional` in the plan. A bit-mask test (`syncStatuses & ?`) can't use an index range, so even with the index
SQLite reads every row for the current setting (868,000 here), although only a few dozen photos match.

This index also leads with `keepLocallyConfiguration`, so the photo-list status lookup above could pick it too.
Check that plan before using it. Every index also costs a little on each of Lightroom's own writes to that table.
Add one only when a measured query clearly benefits and no other query regresses.

## For Adobe

All of this could be done safely inside the app, with no freezing:

- Add the two purge indexes above to the index-store schema with `addIndex`.
- For the sync-status panel, add `(keepLocallyConfiguration, prioritizedSyncStatus)` only together with a query
  change (for example `CROSS JOIN` order or `+keepLocallyConfiguration`) that keeps the photo-list lookup on
  `asset_sync_status_ui_docId`.
- Run `ANALYZE asset_sync_status_ui`, or `PRAGMA optimize`, after large syncs.
- Track pending and error assets separately, or use a partial index whose condition matches the query text,
  instead of `syncStatuses & ?` scans over every row.
- Don't let a single busy database lock disable a view until restart; retry, or give the index-store writer a
  longer busy timeout.

See also [CLOUD-PERFORMANCE-DIAGNOSIS.md](CLOUD-PERFORMANCE-DIAGNOSIS.md) for how the slow queries were found.
