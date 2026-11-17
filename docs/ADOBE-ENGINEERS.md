# For Adobe engineers: Lightroom performance and Sync defects with proven fixes

For Adobe engineering. This note covers Lightroom Classic 15.6 and 16.0, and Lightroom desktop 9.6 and 10.0, on macOS. The test catalog holds about 800,000 photos, all synced. Every fix below ran inside the shipping app at runtime, against the live catalog, and was checked against Adobe's own code path, which served as an oracle: the stock query or function ran alongside and the results were compared. Unless a fix is marked "not installed", it produced identical results in those checks. Most fixes are a few lines and can be applied directly in the product.

The items are grouped by product and ordered by impact.

---

## Lightroom Classic

### 1. File triggers lose their index through type affinity (highest impact)

**Where:** `LrWFSyncStatusSchemaRules.lua`. Two TEMP triggers are recreated on every launch:
- `trigger_AgLibraryImageChangeCounter_update_for_fileModification` (on `AgLibraryFile.modTime`: Smart Preview builds, DNG conversion, metadata saves)
- `trigger_AgLibraryImageChangeCounter_update_for_fileRename` (folder moves, renames, relinks, Find Missing)

Both contain:

```sql
DELETE FROM AgLibraryImageSyncedAssetData
 WHERE image IN (SELECT id_local FROM Adobe_images WHERE rootFile = NEW.id_local)
   AND payloadKey IN (...)
```

**Cause:** `AgLibraryImageSyncedAssetData.image` has no declared type, and in practice most keys are stored as REAL. `Adobe_images.id_local` has INTEGER affinity, so with `SELECT id_local` on the right-hand side SQLite cannot use the `(image, payloadKey)` index. The plan becomes a full SCAN (rename) or an `ANY(image)` skip-scan (modification) over a table that grows to 50–70 million rows on a large synced catalog.

**Effect:**
- Relinking or moving a folder takes about 3 s per file. A 500-file relink took 26 minutes.
- Smart Preview builds stall.
- MainServer is held long enough that the Folders and Collections panels stop refreshing after a move or a new collection.
- Measured per DELETE: 7–39 s with the stock trigger, under 1 ms corrected.
- Per-file `changeFileLocation`: median 3.07 s before, 0.0009 s after.

**Fix:** in the DELETE subquery only, change `SELECT id_local` to `SELECT +id_local`. The unary `+` strips affinity, and the plan becomes `SEARCH … USING INDEX (image=? AND payloadKey=?)`.
- Verified on the live catalog: every image key is numeric and integral, the selected rows are identical (stock vs corrected), and counter updates and deletions are unchanged.
- **Better durable fix:** declare `image INTEGER` and normalize the existing REAL keys. The same affinity trap exists wherever the untyped `AgLibraryImageOzAssetIds.image` is compared with `Adobe_images.id_local`.

### 2. The tracked image map is rebuilt, copied and re-sent in full on every change

**Where:**
- `LrWFSyncStatusTrackedImageQueries`: `getTrackedImageIdMap`, `listenForTrackedImageChanges`, `watchForAssetIdToImageIdChanges`
- `LrWFSyncStatusOzIdQueries.getAssetIdToImageIdMap`
- `AgWFSyncTrackImagesQueries.isImageIdTracked`
- The UI receiver `AgWFSyncTrackImages`

**Cause and effect:** every change to `AgLibraryImageOzAssetIds` triggers a full rebuild of the image→asset map and of the matching `COUNT(*)`. On an 800K catalog, Sync assigns asset IDs to each new import even while Sync is paused, so this repeats continuously. Each rebuild involves:
- `gatherMap SELECT image, ozAssetId FROM AgLibraryImageOzAssetIds, Adobe_images WHERE … ozCatalogId=? AND UPPER(fileFormat)!='VIDEO' AND !='UNSET'`: up to 5.7 s per call, and 59.5 s of MainServer database time per 90 s window.
- A defensive Lua copy of about 800K entries (`AgLua_shallowCopy`): 24–97% of samples on the MainServer and UI threads.
- The whole map sent to the UI on every notification, even when exactly one key changed: 0.12–0.29 s to send, then 0.2–0.7 s to dequeue and materialize.
- The UI receiver counting every entry with `pairs()` for a debug message, even when debug logging is off.

**Fixes (all verified with oracles, 0 mismatches over 10⁴–10⁶ calls):**

1. **Point lookup for `isImageIdTracked`.** Today a miss, or a `pending` value, reloads the whole map, and upload preparation calls it twice per image. Replace it with one indexed row:
   ```sql
   SELECT ozAssetId FROM AgLibraryImageOzAssetIds
     JOIN Adobe_images ON AgLibraryImageOzAssetIds.image = Adobe_images.id_local
    WHERE AgLibraryImageOzAssetIds.image = ? AND ozCatalogId = ?
      AND UPPER(fileFormat) != 'VIDEO' AND UPPER(fileFormat) != 'UNSET'
   ```
   49 IDs took 9.36 s with the stock code and 0.002 s with this lookup. The grid's Sync badges (`fetchFinalGridSyncInfo` → `imageIdHasFeedback` → `isImageIdTracked`) alone took 82.2 s of an 82.2 s window on a 161-image grid before this fix.

2. **Incremental map and count.** A TEMP journal records changed image IDs, and the cached map applies only those deltas. Fall back to a full read when a transaction is open, when `data_version` or `schema_version` changes, on a revision gap, or above 1,000 changes:
   ```sql
   CREATE TEMP TABLE map_revision(singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL);
   CREATE TEMP TABLE map_journal(revision INTEGER NOT NULL, image INTEGER NOT NULL);
   CREATE INDEX temp.map_journal_revision ON map_journal(revision, image);
   -- AFTER INSERT/DELETE/UPDATE OF image,ozCatalogId,ozAssetId ON AgLibraryImageOzAssetIds
   -- AFTER INSERT/DELETE/UPDATE OF id_local,fileFormat ON Adobe_images
   --   → bump revision; insert OLD/NEW image id into map_journal
   ```
   After installation, Smart Preview building went from 0 per minute (stalled for 3 hours) to about 105 per minute within a minute, and Main database time fell from 59.5 s to 3.4 s per 90 s.

3. **C copy.** Use the built-in C `table.shallowcopy` instead of the Lua copy: 1.5–2.2× faster, with results equal and outputs still isolated.

4. **Delta transport to the UI.** Send a full baseline, then sequenced add/remove deltas with ACKs. On any gap or decode failure, resync with a fresh full map. Send time fell from 0.27 s to 0.00005 s. The decoder took 0.165 s (one copy) against 0.385 s. 1,000-message runs in each direction were all ACKed with 0 mismatches.

5. **Debug count.** Gate the receiver's `pairs()` count behind the debug-enabled check.

### 3. Capture-time rewrite adds ".000" and requeues unchanged photos for upload

**Where:** `LrCatUpdateImage` → `AgMetadata.XMPDateToTimeStamp` → `AgLibraryDates.setCaptureDate`, and the `LrSourceSyncronizerDataObservers` change observers.

**Cause:** applying an incoming cloud document rewrites `captureTime`, `exif:DateTimeOriginal` and `photoshop:DateCreated` with a `.000` suffix even when the timestamp is identical. The observer then queues an upload, because it checks the current change counter without comparing it to `lastSynced`. Separately, `LrCatUpdateImage.maybeApplyKeywordChanges` calls `deleteDocFromCache` inside the apply transaction, which removes the echo suppression before the deferred notifications are sent (`postASAP` → `sendDeferredNotifications`).

**Effect:** the Sync count jumped to about 140K. Of 141,702 queued uploads, 131,465 differed only in date format. Another 9,732 differed only in face-region coordinate precision; `AgRegionMetadata` writes with `%.5f`, and the values match at 14 significant digits.

**Fix:** skip the setter when the parsed timestamp is the same whole second and all three fields are already set. This was verified with native controls covering offsets −08:00, +05:30, +14:00 and −00:00, +1 s, fractional and uninitialized cases. Queued no-op uploads were withdrawn with the native `deleteSyncedIds`; 14 protected tables were unchanged.

**Durable fix:**
- Compare values semantically before touching change counters, for both dates and face coordinates.
- Keep the echo cache until the deferred notifications have been delivered.

### 4. Uploads that never recover

1. **Missing develop XMP (404 `BinaryMissingError`).** A metadata revision refers to `develop.xmpCameraRaw.sha256`, but the XMP never reached the server. `clearErrorsAndRetrySync` regenerates the revision without re-uploading the XMP. In a set of 3,236 stuck assets, the stock retry fixed 2,903 and left 297 at 404.
   - **Workaround that fixed every remaining one (319 of 319):** a no-op develop re-save through the SDK, `applyDevelopSettings{Exposure2012 = e + 0.01}` and then back to `e`. Classic then regenerated and uploaded the XMP, and the proxy as well.
   - **Fix:** on 404 or a missing XMP, re-upload the XMP during the retry.

2. **Proxy re-upload rule.** In `WFCatBinaryUploader`, a proxy is re-sent only when the local SHA equals `importSource.proxySHA256` and the server link is absent or marked `invalid`. A link that returns 404 but is not marked invalid blocks re-upload forever.
   - **Fix:** mark the link invalid on 404.

3. **`UploadFailedMissingProxy` sticks.** `maybeEmitProxy` returns early on this sentinel, so the record stays "Uploading" even after the proxy exists again.
   - **Fix:** clear the sentinel automatically when the proxy file is present.

4. **Proxy path pinned to a volume that no longer exists.** `needsBinaryUpload` stores `localVolumeGuid` plus a volume-relative path. If the catalog moves to another disk or Mac, pending proxy uploads wait forever with `fileMaybeOnOfflineVolume=1`, even though the file sits next to the catalog with the right SHA.
   - **Workaround (verified):** proxy-only `root:subModel('setOriginalAndProxyInfo', id, {proxyFilePath=…, proxyFileSize=…})`, leaving out `filePath` and `fileSize`. This recorded the current path, and every stuck item uploaded within about 45 s.
   - **Fix:** resolve Smart Preview paths relative to the catalog's `Smart Previews.lrdata` when the recorded volume is absent.
   - The same setter drops the `_dontsendtooz` label when the proxy SHA changes the body revision. Labels should be preserved.
   - Path forms are also inconsistent in `WFFileUtils`: external volumes give `/Lightroom/…`, the boot volume gives `Users/…`.

5. **Orphaned queue states.**
   - `AgPendingOzDocs` rows in `needs_binary` with no row in any SourceSync download table never progress. Re-admitting them with `addSyncSourceIdsForSync('downloadBinary', ids, timestamp)` completed them (1,387 and 613 rows).
   - Rows left `updating` after an interrupted batch are never retried: `resetErrorState` only resets `state='error'`.
   - **Fix:** a startup consistency sweep for both cases.

### 5. Missing Classic indexes, and startup removes user-added ones

These were verified equal on live and copied catalogs. Ship them in the declared schema, because `WFSQLiteDatabase` startup (initializer 0.6) drops any index on a declared table that is not in `_indexes`.

```sql
-- Asset lookup by (ozAssetId, ozCatalogId): SCAN of 700K rows → SEARCH (status callback 905 s → 0.7 s)
CREATE INDEX ... ON AgLibraryImageOzAssetIds(ozAssetId, ozCatalogId);
-- LrCatAddOzDocQueue: WHERE UPPER(sha256)=?   63 ms → 8 µs
CREATE INDEX ... ON AgLibraryFileAssetMetadata(UPPER(sha256));
-- AgPendingOzDocs has only its primary key
CREATE INDEX ... ON AgPendingOzDocs(ozCatalogId, state, isLibImage);          -- count 23.7 ms → 1.0 ms
CREATE INDEX ... ON AgPendingOzDocs(id_local, state, ozCatalogId, ozDocId);   -- lookup 9 ms → 2 µs
CREATE INDEX ... ON AgPendingOzDocs(LOWER(fileName), ozDocId);
```

For the last index, change `LrWFSyncStatusDestPathQueries` to test `LOWER(fileName)=? AND ozDocId NOT IN (?) LIMIT 1` for each name, instead of building the full filename set for every destination.

**Not installed:**
- `getSyncingAssets` (`LrCatAssetOperations`) took 56–87 s per request. Its `syncStatus <> 2` predicate scans; `syncStatus < 2 OR syncStatus > 2` uses the index (33 ms → 21 µs).
- A covering index for the CameraRaw `processVersion IN (…) GROUP BY` startup query (11.7 s) was 4.6× faster in a projection.

### 6. Transactions, scheduling and request plumbing

- **Silent autocommit.** `doInSessionWithTransaction` swallows a failed `SAVEPOINT` (SQLITE_BUSY, "statements in progress") and runs the body in autocommit, after which `RELEASE` fails with "no such savepoint". Writes therefore commit without atomicity.
  - **Fix:** wait or fail; never fall through to autocommit.
- **Provenance written outside a transaction.**
  - `AgLibraryImageQueries.readCAIAuthenticationData` is a nominal read that migrates legacy `caiAuthenticationInfo` into `AgProvenanceInfoEntity`, through `PreviewDataQueries.getStillPreviewData` (`doInSession`, no transaction).
  - `DngProxyInfoQueries.updateCaiAuthenticationInfo` and the `LrCatUpdateImage` provenance path do the same.
  - The guard only warns. `Session.close` then fails with "pending transaction", the `processDownloadComplete` batch never posts `PendingPayloadsProcessed`, and `processingDocs` stays true until restart.
  - **Fix:** make reads free of side effects, put provenance writes inside a transaction, and make batch completion exception-safe.
- **Smart Preview builds hang at N−2 of N.**
  - `DngProxyInfoQueries.updateCaiAuthenticationInfo` indexes a nil authentication argument, and `AgLibraryProxyBuilder` then calls `unpack(nil)`. The exception skips completion accounting.
  - The builder shares `hasCAISign` across yielding per-image tasks, which is a race candidate.
  - **Fix:** nil-guard the argument, keep the flag per task, and do accounting in a `finally`.
- **Busy-polling worklist.** `AgPersistentWorklist` busy-polls when `stopProcessFlag=true`: 1,000 identical task queries ran in 22 ms, with no timed wait. The harvested-metadata worklist was left stopped after an import ended.
  - **Fix:** wait on a timer or condition while stopped, and clear the flag on every import exit path.
- **Dropped request priority.** `AgDataRequest.waitForNamedRequest` drops the caller's `priority`, so nil becomes normal. Interactive preview reads waited a median 2.97 s before the handler, which took 0.0002 s. Raising only those reads to asap made them 2.2× faster.
  - **Fix:** forward the priority.
- **Yield after every item.** `LrCatDownloadOperations` calls `yieldToScheduler` after every ready item: median wait 1.94 s, against a callback body of 0.09 s.
  - **Fix:** yield per batch.
- **Read-only reader creates folders.** When the Sync download location changes, the reader's `getBinaryDownloadData` calls the full destination resolver, which tries `findOrCreateFolder`. It throws "Store provider is read-only", and the `callOnDataServer` error handler closes the request without calling completion. The 20 processing slots leak, and downloads stop until restart.
  - **Fix:** create folders on the writer, and route errors to completion.
- **Lost heartbeat commit.** In `SourceSyncDataStore`, the heartbeat clears `_dirty` before `RELEASE SAVEPOINT 'Auto Sync'`. A BUSY release is never retried, and committed work is lost on close.
- **Metadata upload settings ignored.** Throughput is fixed at 25 IDs per 10 s pulse (`uploadTimer/2`), and `syncNoOfUploads` is ignored.
- **Download settings read once.** `syncDownloadTimer`, `syncNoOfDownloads` and `syncProcessingCountLimit` are read only once, at module load.
- **Pending-count trigger misses updates.** The TEMP `AgPendingOzDocs_status_changes` counter has INSERT and DELETE triggers but no UPDATE trigger, so a state change does not refresh the count.

### 7. Correctness bugs seen in passing

- **Two cloud assets collapse onto one image.** When two cloud assets with identical bytes resolve to the same destination, `createImageFromOzAsset` / `addToLibrary` logs "did not create new libImage entity", applies the second payload to the first image, and replaces its mapping. One asset's settings are silently lost.
  - **Fix:** resolve a unique destination per asset (or create a virtual copy), and fail instead of replacing the mapping.
- **Existing-master reuse is skipped.** `LrCatAddOzDocQueue.addNewPayloadToQueue` returns early on an unchanged revision before matching, and `getBinaryDownloadData` reads the persisted `existingMaster.imageId`, not the association just created. So a linked local original can still be downloaded again.
- **Doubled WHERE.** `recordCorruptMaskInfo` runs `SELECT auxId FROM AgOzCorruptedAuxIds WHERE WHERE …`, which is a syntax error.
- **Redundant trigger work.** `after_agLibraryFile_update` re-parses `importHash` on every `AgLibraryFile` update, including folder-only moves.
  - **Fix:** add `WHEN NEW.importHash IS NOT OLD.importHash`.
- **Stale dimensions after relink.** After a relink, `AgHarvestedMetadata.updateSoonForImage` keeps the Smart Preview's dimensions (it has no `fileWidth`/`fileHeight` setter), and it can take `bitDepth` from the preview.
- **Remove and Hide resolve the physical path.** On case-insensitive volumes, case-variant folder records (for example `/Users/Name` and `/Users/name`) cause Remove to warn about the other record's photos.
- **Inaccurate Sync count.** `max(union, incoming pendingCount)` in `LrCatAssetOperations` mixes populations.
- **SDK `addPhoto` is a full import.** `addOnePhotoToLibrary` runs a complete import lifecycle per file: about 4 s per photo, not atomic inside `withWriteAccessDo`, and adjacent JPEG sidecars are not discovered. A bulk add API is needed.
- **Pause does not persist.** `pauseSync` does not persist `ozAutoSyncEnabled=0`.
- **Lost diagnostics.** Release builds disable `dumpSuspendedTaskTracebacks`, so stalls leave no evidence.

---

## Lightroom (Cloud desktop)

### 8. `Managed Catalog.wfindex`: missing covering indexes and statistics

Lightroom's own query profile (`WFDiagnosticLog`) showed a single reader spending 964 s across 1,616 status queries. Installed live, these were verified as identical typed results with and without the index (`NOT INDEXED`), on the same snapshot:

```sql
CREATE INDEX ... ON asset_sync_status_ui(keepLocallyConfiguration, prioritizedSyncStatus,
                                         volumeGuidUsedByOriginal, volumeGuidUsedByProxy, spaceId, isSearchable);
CREATE INDEX ... ON purgeCandidates(binaryType, hasLocalFile, isPurgeable, volumeGuidUsedByFile, fileSize, contentIdOrSha256);
CREATE INDEX ... ON purgeCandidates(binaryType, isPurgeable, contentIdOrSha256, hasLocalFile, fileSize);
ANALYZE asset_sync_status_ui;
```

| Query | Before | After |
|---|---|---|
| volume distinct | 10.88 s | 0.012 s |
| status distinct | 9.10 s | 0.044 s |
| searchable `LIMIT 1` | 5.44 s | 0.00002 s |
| aux local sum | 83 ms | 0.5 ms |
| XMP digest `EXCEPT` | 359 ms | 154 ms |

**Run ANALYZE with the status index.** Without statistics, the planner picks the new status index for the `CARRAY(assetLocalIds)` photo-list join (6.5 s). With `ANALYZE` it returns to the `docId` index (0.000057 s).

**Do not add a narrow index.** A narrow `(keepLocallyConfiguration, prioritizedSyncStatus)` index made that same join take 10.7 s and caused "boot version took more than 10 seconds" timeouts in Versions.

**Other changes:**
- Declare these indexes through `addIndex`, because startup drops undeclared ones. Run `PRAGMA optimize` after large syncs.
- Bitmask filters (`syncStatuses & ?`) cannot use an index (single calls up to 15.8 s). Add explicit pending and error columns, or a partial index.

### 9. Cloud reliability defects

- **One busy lock freezes the grid until restart.** Index-store writers give up after about 5 s busy. After one "database is locked", `HicAssetListDataSource` reports a "fatal error … will not update until app restarts", and the main grid, loupe filmstrip and trash freeze until restart.
  - **Fix:** retry, or use a longer busy timeout. A transient lock should never be fatal.
- **`getProxyPaths` can block the queue.** For documents waiting for settings (`needsDevelopXmpDownload=1`) while offline, it never answers and blocks every request queued behind it.
  - **Fix:** fail or time out per row.
- **"Waiting for Settings" persists.** It stays after the exact XMP has been adopted locally, and only a restart clears it, because terminal status callbacks are suppressed.
  - **Fix:** re-emit the status when the annotation completes.
- **The Edit panel's Reset is the wrong fix.** The gate applies to both pending and failed `settingsXmpStatus`, and its message ("missing from another client on …") pushes users to Reset, which discards settings.
  - **Fix:** offer a retry and an accurate message.
- **No hash check on cached settings.** `PixelProviderExternalXmpDevelopPathCheckTask` adopts `settings/<sha>` without checking that the computed SHA matches the name.
- **Pause looks like a network failure.** A paused Sync maps to the same `CannotSyncDownloadToFileError` as no internet.
- **Offline mode stops adoption.** `NmbUserModel` offline mode calls `stopSyncing`, which stops the idle downloader, so local caches are never adopted while offline.
- **WAL never checkpointed.** The wfindex WAL grew to 104 GB next to a 4.6 GB database, and normal quit did not checkpoint it. Checkpoint on quit, and use a size limit.
- **Fixed HTTP concurrency.** `Nimbus.maxNumSimultaneousHttpRequests` defaults to 10 and is read once.
- **Original export fails.** It fails with `xmp_develop_unavailable` when `getXmpDevelop():take(1)` yields nil. "Original" export also rewrites EXIF, XMP and IPTC, so it is not byte-original.
- **Cached flags stored as REAL.** In wfindex they are stored as `1.0`/`0.0`.

---

## Suggested order

1. The `+id_local` triggers, or declaring `image INTEGER` (item 1). These are two one-character changes with the largest single effect on moves, relinks, previews and UI responsiveness.
2. Point lookup and incremental tracked map, C copy and UI deltas (item 2).
3. The ".000" capture-date equivalence check, and comparing against lastSynced in the observers (item 3).
4. The declared indexes and statistics for Classic (item 5) and Cloud (item 8).
5. Upload recovery: 404 means invalid, re-upload the XMP, catalog-relative proxy paths, and the startup queue sweep (item 4).
6. Transaction and exception safety: savepoint fallthrough, provenance writes, completion on error (item 6), and the Cloud lock-is-fatal bug (item 9).

The runtime implementations are public at <https://github.com/firstpair/lightroom>:
- `classic/lrc16/`: the trigger, point-lookup and incremental-map fixes for Classic 16.0.
- `classic/sync-recovery/`: the upload recovery actions.
- `classic/templates/runtime/`: the 15.6 versions, including the delta transport.
- `cloud/`: the Cloud index installer.
