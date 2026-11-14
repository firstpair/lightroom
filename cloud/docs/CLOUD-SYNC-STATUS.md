# Reading Lightroom (Cloud) sync status

Use this page when the Sync indicator in Lightroom (Cloud) keeps showing activity, or when "View" on the Sync
panel opens an empty list.

## Where the status lives

`Managed Catalog.wfindex` has a table `asset_sync_status_ui` with **one row per photo for each of four
keep-locally configurations** (`keepLocallyConfiguration` 0–3). Each row's status is precomputed for that setting,
so the table has four times as many rows as the library has photos. The Preferences → Local Storage choices
(store Smart Previews locally, store originals locally) select which configuration counts.

`prioritizedSyncStatus` holds the photo's most important status, and `syncStatuses` holds all of them combined.
Both are bit flags. The values below come from Lightroom 9.6's own status definitions:

| Value | Status | Value | Status |
|---|---|---|---|
| 1 | NeedsMetadataUploaded | 131072 | OriginalDownloadError |
| 2 | NeedsOriginalUploaded | 262144 | ProxyDownloadError |
| 4 | NeedsOriginalDownloaded | 524288 | DevelopXmpDownloadError |
| 8 | NeedsOriginalDownloadedForOffline | 1048576 | NeedsOriginalDownloadToOutOfSpaceVolume |
| 16 | NeedsProxyDownloaded | 2097152 | NeedsProxyDownloadToOutOfSpaceVolume |
| 32 | NeedsDevelopXmpDownloaded | 4194304 | SyncPaused |
| 64 | Completed | 8388608 | SyncNoConnection |
| 128 | CompletedNoMaster | 16777216 | NeedsProxyDownloadedForOffline |
| 256 | StorageLimitExceeded | 33554432 | TrialOrSubscriptionExpired |
| 512 | InvalidLocalOriginal | 67108864 | StackComplete |
| 1024 | OriginalIsOnOfflineVolume | 134217728 | CompletedForOffline |
| 2048 | ProxyIsOnOfflineVolume | 268435456 | CompletedNoNegatives |
| 4096 | NeedsOriginalDownloadToOfflineVolume | 536870912 | InsufficientPermissionError |
| 8192 | NeedsProxyDownloadToOfflineVolume | 1073741824 | NeedsDevelopXmpUpload |
| 16384 | NeedsOriginalMigration | 2147483648 | InvalidAuxError |
| 32768 | NeedsProxyMigration | 4294967296 | InvalidXmpDevelopError |
| 65536 | NeedsOriginalUploadedButOnOfflineVolume | | |

## Finding what Sync is waiting for

Read the database only, from a copy or with `mode=ro`, and never write to it. Group by status for your current
configuration:

```sql
SELECT keepLocallyConfiguration, prioritizedSyncStatus, count(*)
FROM asset_sync_status_ui
WHERE prioritizedSyncStatus NOT IN (64, 128)
GROUP BY 1, 2 ORDER BY 3 DESC;
```

With "store Smart Previews locally" (configuration 1 in this library), everything was complete except 3 photos
in status 16777216 (NeedsProxyDownloadedForOffline). Large counts under other configurations, such as
148,000 × NeedsOriginalDownloadedForOffline, apply only if you switch that setting on, and are not what the
indicator shows.

Then look the stragglers up in `localStatusAndOzStatus` (`needsProxyDownload`, `hasLocalProxy`) and in the
`Managed Catalog.mcat` record (`docs` joined to `revs` on `winningRevSequence`; the content is MessagePack).

## A common cause: uploads that never finished

In our library the 3 stragglers were photos imported on an iPad whose upload never finished:

- **No server renditions:** the cloud record had no links at all (no original, Smart Preview or thumbnail).
- **Refused download:** asking Lightroom for the preview returns `SendNoDownloadableOriginal`. That answer
  comes from the photo's own record, not from the server, so retrying, online or offline, never helps.
- **Never settles:** Sync counts the photo as pending forever.
- **Empty View:** the grid can't show a photo without a thumbnail, so the Sync panel's View list is empty.

**Fix:** open Lightroom on the device that imported them, while it's online, so it can finish the upload.
Lightroom's web app gives the same advice for such records ("Sync has not finished… open Lightroom on
[device]").

**Don't delete them first.** The deletion syncs to every device, and the importing device's Lightroom would
likely remove its local copy, which may be the only real one. Deleted photos can be restored for about 60 days,
but nothing on the server can bring back an original that was never uploaded.

A related case: records whose original is recorded on a local volume that isn't mounted (for example
`Lightroom-Cloud-Originals` on an external drive) are also refused. Attach that drive and let Lightroom finish.
