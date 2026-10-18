# Continuous preview processing

The current native window is qualified for eight photos. Processing a large
catalog therefore needs a persistent coordinator that advances those windows
without reconstructing their state manually. Increasing the size of the work
queue does not increase native concurrency or relax input and publication guards.

Two portable components now support that coordinator:

- `scripts/preview_pipeline/work_queue.py` accepts up to 10,000 metadata records
  per enqueue transaction. Each phase claim contains at most eight records. The
  claim is committed before work starts, and the result receipt is committed
  before the records advance to the next phase.
- `scripts/preview_pipeline/cohort_completion.py` distinguishes an actual child
  wait from independent recovery of an idle outer owner. A native success and a
  later startup failure remain separate outcomes. Recovery preserves the
  original nonzero exit and cannot substitute a successful startup terminal for
  a successful original render coordinator.

The queue phases are `PENDING → NATIVE_READY → STAGED → PUBLISHED → COMPLETE`.
An unfinished or held claim blocks further claims, including after reopening the
queue. It is never automatically replayed. A separately audited recovery receipt
is required to finish a held claim. Duplicate keys and duplicate completion
attempts are refused. Previously completed native renders may be adopted at
`NATIVE_READY` with their authenticated receipt, so they are not rendered again.

The queue owns only its private bookkeeping database. It never opens the catalog,
originals or preview payloads; launches no workers; and grants no IO, CPU, UI,
rendering or publication authority. The executor must authenticate the referenced
receipts, retain its resource owners through real process settlement, and retain
on any uncertain queue commit or close. The completion policy is only one part
of the proof: all native input, epoch, reader, output and process-group checks
still apply.

Qualification currently covers synthetic 10,000-record enqueue, restart with
unfinished work, simultaneous claims, all phase transitions, explicit recovery,
duplicate prevention and saved-render adoption. A separate versioned private
staging validator also accepted the saved receipts from eight real completed
renders, preserving their original outer exit137. No media was reread for that
metadata validation.

The continuous native executor is **not yet wired or qualified**. Staging runtime
and publisher integration must consume the new completion proof explicitly;
historical validators and receipts remain unchanged. These components are not a
claim of catalog-wide generation, production throughput, larger native batches,
or a new runtime admission.
