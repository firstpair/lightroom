# Diagnose Cloud download throughput before tuning

This is an investigation method, not an installed Cloud performance fix.

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
that an existing limiter has changed. No HTTP tuning from this investigation has
been installed or measured end to end.

## Inspect database work

Capture actual native SQL profiles and EXPLAIN plans before adding indexes. In
the reference investigation, two serial read-only workers spent substantial time
in SQLite status queries. Private typed-result experiments found improvements
from covering indexes and from routing through an existing status index. Those
experiments used an isolated database and are not production speedup receipts.

Native schema initialization can drop unknown indexes. An external index added
to an open database is not a durable installation strategy. Require a qualified
native writer/startup route, exact typed-result equivalence and a rollback before
a live trial. Do not bypass read-only routing with fabricated table names.

## Verify a proposed change

Measure an unchanged baseline over a useful interval: completed files per minute,
bytes, CPU, queue depths, errors, timeouts and free space. Preserve the workset
and distinguish logical bytes from APFS allocated blocks. At an ordinary safe
lifecycle boundary, apply one guarded change, verify its effective value, then
repeat the measurements. Include server throttling and HTTP errors. Revert if
the change increases failures or fails to improve end-to-end completion. A faster
private query, higher configured number or lower UI counter is insufficient.

## Undo and limits

No production change is supplied by this guide. For a future configuration trial,
retain the exact prior file or its verified absence and restore it at a safe
boundary; verify the effective baseline after restart. Never replace a shared
limiter or mutate its private closure while requests are pending. Native UI access
and actual configuration-path resolution remain prerequisites for the next trial.
