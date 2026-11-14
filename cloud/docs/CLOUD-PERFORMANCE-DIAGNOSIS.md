# Diagnose Cloud download throughput before tuning

The reference Lightroom Cloud 9.6 session now has four natively installed covering
indexes and genuine status-table statistics. Query improvements are verified;
one guarded post-restart renewal has completed; end-to-end throughput remains
under investigation.
These Cloud changes are separate from the Classic startup installer.

## Prerequisites

Preserve the current downloader owner, its pending requests and its actual
completion journal. Record app version and process birth. Use a native diagnostic
report from that session where available. Reports can contain signed URLs and
credentials: retain them privately and publish only sanitized findings. Keep a
disk reserve and stop new admissions before exhausting it.

## Separate the queues

Count scheduler slots, HTTP transfers, returned paths, indexed local proxies,
settings readiness and editable photos separately. A completed path request can
lag a file becoming local; neither proves full Sync convergence.

In one captured native report, twenty scheduled items coexisted with five active
HTTP requests. Each request cost two units against a simultaneous-cost allowance
of ten. That observation identified a possible constraint, not proof that more
concurrency would improve throughput. The observed installed HTTP client reads
`Nimbus.maxNumSimultaneousHttpRequests`, default ten, when constructing its limiter.
The limiter captures the numeric constructor target; no public target setter was
found in the inspected module. A configuration-file change alone does not prove
that an existing limiter has changed. A guarded startup trial set this budget
to twenty. After a normal restart,
the native runtime reported numeric twenty, ten outstanding cost-two tasks,
and a simultaneous cost of twenty. Ten concurrent tasks are therefore observed,
not inferred from configuration alone.

The longer sequential observation gained 478 local previews in 10.6 minutes
(about 45/minute), versus about 44/minute in the earlier five-task window.
Different assets, caches and network conditions prevent a controlled causal
comparison. This trial did not establish a material sustained throughput gain;
it is not a general recommendation to increase concurrency.

## Inspect database work

Capture actual native SQL profiles and EXPLAIN plans before adding indexes.
The reference session identified broad status scans, an asset-list join choosing
a broad scan over its existing photo-ID index, and cache-size/settings-cache
queries performing table lookups through narrow indexes.

The following covering keys passed private controls and actual native
installation. These are schema descriptions, **not external live SQLite commands**:

| Owned index | Table and ordered key |
| --- | --- |
| `firstpair_status_ui_configuration_status_cover_v1` | `asset_sync_status_ui(keepLocallyConfiguration, prioritizedSyncStatus, volumeGuidUsedByOriginal, volumeGuidUsedByProxy, spaceId, isSearchable)` |
| `firstpair_status_ui_configuration_mask_cover_v1` | `asset_sync_status_ui(keepLocallyConfiguration, syncStatuses, assetId)` |
| `firstpair_purge_volume_cover_v1` | `purgeCandidates(binaryType, hasLocalFile, isPurgeable, volumeGuidUsedByFile, fileSize, contentIdOrSha256)` |
| `firstpair_purge_hash_cover_v2` | `purgeCandidates(binaryType, isPurgeable, contentIdOrSha256, hasLocalFile, fileSize)` |

Native installation used a quiet index family, rollback snapshots and the app's
native database API, with `busy_timeout=0`, one write transaction, exact schema
checks and typed before/after query equality. Index creation made no data-row
changes. A separate genuine `ANALYZE asset_sync_status_ui` populated optimizer
metadata; no statistics were fabricated and other tables' statistics stayed
unchanged. Catalog records, develop revisions and asset Sync flags were not rewritten.

Representative **same native transaction** controls:

| Query | Before | After |
| --- | ---: | ---: |
| Broad volume/status lookup, covering-index trial | 10.88 s | 0.012 s |
| 19-photo status join, statistics trial | 0.819 s | 0.000057 s |
| Cache volume-size sum, cache-index trial | 2.83 s | 0.052 s |
| Settings-cache digest exclusion, 95,946 rows | 1.62 s | 0.163 s |

All selected typed results matched. These are scoped SQL timings, affected by
cache state and data distribution; they are not whole-app speedup ratios.
A later application diagnostic confirmed the asset-list join itself selecting
the existing photo-ID index. Cumulative profile maxima still include older work.
A private 128-document delete/reinsert control showed additional write cost;
read improvements must be assessed against actual sustained Sync writes.

Use real prepared placeholders and the normal binding API. Replacing numeric
parameters with `CAST(value AS REAL)` changed affinity and index selection in
this typeless schema; that earlier diagnostic was not production-query
equivalence. Index existence alone is insufficient.

Native schema initialization can drop unknown indexes. A combined renewal
installer passed isolated full-script controls for missing fixes, exact no-op,
conflicting definitions and rollback after an injected failure. Those controls
used authored Lua and SQLite/model doubles, not a native cold-start test.
A private, operator-enabled startup controller has since completed one actual
post-restart renewal: native commit, database close, and automatic restoration
of its own maintenance pause. The first attempt held before installation because
the source changed during private snapshot readback. Its failure remains retained.

The corrected successor requires an unchanged source DB/WAL across snapshot
acquisition, then records later source activity separately from validation of
the already-captured private copy. It retains fresh native transaction admission
and never restores an old whole database over newer edits. Eighteen authored
controls cover acquisition refusals, post-acquisition changes, pause ownership
and request lifecycle. This is one recovered real restart qualification, not
proof of every future launch or a shipped public Cloud automation feature.
Do not bypass read-only routing with fabricated table names or install into the signed bundle.

## Verify a proposed change

Measure an unchanged baseline over a useful interval: completed files per minute,
bytes, CPU, queue depths, errors, timeouts and free space. Preserve the workset
and distinguish logical bytes from APFS allocated blocks. At an ordinary safe
lifecycle boundary, apply one guarded change, verify its effective value, then
repeat the measurements. Include server throttling and HTTP errors. Revert if
the change increases failures or fails to improve end-to-end completion. A faster
private query, higher configured number or lower UI counter is insufficient.

## Undo and limits

This guide documents the reference changes; it supplies no automatic Cloud
installer. Undo owned indexes through the qualified native writer after current
request and later-edit checks. Preserve current records instead of restoring an
old whole database merely to remove an index. Statistics changes need their own
scoped rollback. For a future HTTP configuration trial,
retain the exact prior file or its verified absence and restore it at a safe
boundary; verify the effective baseline after restart. Never replace a shared
limiter or mutate its private closure while requests are pending. The actual configuration path and default-limit behavior have been observed,
and a budget-twenty restart trial has now been observed. Its native concurrency
increased, but its longer sequential throughput measurement remained close to
the earlier baseline. Keep measured concurrency separate from useful speedup.

## Keep maintenance pauses out of the download admission loop

The first controller continued submitting while normal Cloud Sync was paused,
producing thousands of `CannotSyncDownloadToFileError` results. These were
refusals, not completed downloads or evidence of missing originals. The affected
identities were retained and freshly matched against current uncached records.
A successor observes the native user's boolean `syncPaused` before every batch:
paused or unknown means wait; existing requests retain their ownership. Stop
and drain controllers before maintenance, then hand off only reviewed
unsubmitted work. Never replay an active request, Reset settings, or forge status
fields to clear these refusals. Keep native returned paths, indexed local proxies,
held errors and server convergence separate.
