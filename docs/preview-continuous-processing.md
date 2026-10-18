# Continuous preview processing

The current native window is qualified for eight photos. Processing a large
catalog therefore needs a persistent coordinator that advances those windows
without reconstructing their state manually. Increasing the size of the work
queue does not increase native concurrency or relax input and publication guards.

Three portable components now support that coordinator:

- `scripts/preview_pipeline/work_queue.py` accepts up to 10,000 metadata records
  per enqueue transaction. Each phase claim contains at most eight records. The
  claim is committed before work starts, and the result receipt is committed
  before the records advance to the next phase.
- `scripts/preview_pipeline/cohort_completion.py` distinguishes an actual child
  wait from independent recovery of an idle outer owner. A native success and a
  later startup failure remain separate outcomes. Recovery preserves the
  original nonzero exit and cannot substitute a successful startup terminal for
  a successful original render coordinator.
- `scripts/preview_pipeline/phase_controller.py` runs the four phases through
  explicit execution/authentication adapters. It finishes downstream work before
  claiming another render window, commits each claim before calling its adapter,
  and advances only after both actual child settlement and the adapter's full
  contained-process/resource/receipt audit. It retains the adapter, claim and queue
  together on exceptions or uncertain queue commits. Known closed failures become
  held claims and stop the run. Execution cannot mutate the original claim later
  supplied to authentication.

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

The first real eight-job queue cohort has completed all three downstream
phases: staging, publication and native cache recognition. Each phase persisted
its claim, drove its contained child processes automatically, authenticated its
result, and advanced the queue only after actual group/resource settlement.
Independent readback verified 64 staged JPEG copies. Publication placed 32 files
and eight highest native tiers, followed by eight successful cache loads and
decodes. The original failed outer render-owner receipt remains preserved; none
of the eight renders was repeated.

Rendering and the transitions between these phase owners are **not yet wired
into one unattended catalog-wide controller**. The queue's 10,000-record ingestion
capacity does not establish 10,000-photo runtime qualification, larger native
windows, throughput, or an authority to replay held work. Historical validators
and receipts remain unchanged.

The reusable controller passed a complete synthetic 10,000-record run through
5,000 phase actions, plus restart, failure, uncertain settlement, authentication,
commit and bounded-completion controls. These adapters are test doubles. The
controller has not launched a native cohort; connecting the real adapters remains
required before claiming unattended generation. The next native window's source
can now be authored from the verified checkpoint and packet without manually
editing global packet ordinals or the local eight-reader counter.
