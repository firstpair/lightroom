# Continuous preview processing

The current native window is qualified for eight photos. Processing a large
catalog therefore needs a persistent coordinator that advances those windows
without reconstructing their state manually. Increasing the size of the work
queue does not increase native concurrency or relax input and publication guards.

Portable components now support that coordinator:

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
- `scripts/preview_pipeline/stage_context.py` binds one prepared eight-record
  stage context to its exact dependencies, compiled executable and prior native
  receipt. The continuous preparation selects one qualified engine, rather than
  repeating the Rust/Ox comparison used for qualification. It plans 32 encoded
  copies, retains native-hash verification, and explicitly authorizes no execution
  or resource acquisition.

The queue phases are `PENDING → NATIVE_READY → STAGED → PUBLISHED → COMPLETE`.
An unfinished or held claim blocks further claims, including after reopening the
queue. It is never automatically replayed. A separately audited recovery receipt
is required to finish a held claim. Duplicate keys and duplicate completion
attempts are refused. Previously completed native renders may be adopted at
`NATIVE_READY` with their authenticated receipt, so they are not rendered again.

`scripts/preview_pipeline/phase_inputs.py` retrieves prior receipt pins for an
exact active claim through primary-key lookups on the private queue. It checks
the batch, order, source bindings and phase state, and leaves the borrowed
connection open. This allows downstream adapters to find prior work without
depending on a live Python object from the preceding phase. It neither
authenticates those receipt files nor resolves an unfinished owner; restart and
hold restrictions still apply.

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

The private render adapter now binds those exact queue records, retains its
render-window process and capture carriers, and constructs the versioned proof
from the actual direct-child wait and verified Classic startup. Its source
controls cover both catalog companion modes, wrong claims and admission order,
failed native facts, uncertain settlement and false resource-closure claims.
Disposable Python peers exercise process wait/capture closure using explicit
source/proof doubles. This does not qualify an actual native execution through
the controller. Downstream adapter integration remains required.

The current render wrapper also reopens Classic before publication closes it
again. The continuous path must remove that redundant cycle: native completion,
staging and publication belong before the final reopen and recognition. The
versioned `cohort_completion_v2.py` adds a closed-Classic native-completion view
with settled root/native/helper waits and authenticated normal-close/reader-gate
references. It requires final startup later and grants neither publication nor
release authority. Legacy views still use their unchanged validator.

A private deferred-startup render-window author now removes the intermediate
reopen, retains the original native/reader/launch helper functions, and adds a
post-native closed-catalog census. Source controls and metadata-only preflight
pass. The new completion view is **not yet wired into the staging proof/runtime
or the full controller**, and no native invocation of that source has occurred.
The next integration must support the closed window explicitly, rather than
fabricating startup success for a legacy proof.
