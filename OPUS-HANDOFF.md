# Lightroom continuation handoff

Latest operational state: 106,155 Smart Previews are verified, with twelve
eligible exceptions still open: two isolated export calls that never returned,
three returned HEIC errors and seven exports not yet attempted. Both stalled
runs were recovered through normal Lightroom quit followed by source-proven idle
Python stops; their exit137 records are retained separately from SDK completion.
No originals, catalog identities or completed previews were replaced.

A new 32-job packet was selected from the authenticated queue with completed
keys excluded. Lightroom settings and native locators were captured and audited
for all 32, with original-file guards and current catalog bindings checked. The
entire packet has now completed rendering, Rust/Ox staging, publication,
independent storage verification and Lightroom cache loads/decodes. The monitor-fit
checkpoint for that packet is 258. A watcher-lock refusal stopped one recognition pair before its
callback; a fresh guarded continuation completed the four remaining keys without
replaying successful callbacks, rendering or publication. The original refusal
and partial exit remain preserved separately from the completed combined audit.
The next 32 untouched candidates were selected using the authenticated completed
packet. Their settings, native locators and original-file guards are now bound.
The first eight completed native rendering, both staging engines, publication,
independent storage verification and all native cache loads/decodes, advancing
the verified monitor-fit checkpoint to 266. Twenty-four metadata-bound jobs remain
in this packet. The next eight rendered successfully, but their outer owner
retained reservations after a normal-reopen startup helper error. Independent
recovery stopped only the proven-idle Python owner; its actual exit137 remains
preserved. One guarded manual startup attempt verified all seven phases in the
same open Classic process. All reservations are closed. Those eight render
outputs are preserved and unpublished: the existing staging proof requires an
original outer exit0. A distinct versioned recovery-aware validator now passes
its controls and accepted all eight saved native results without payload reads,
while preserving exit137. The staging runtime and publisher still need to be
wired to that versioned proof before those outputs can be published.
No rendering replay or receipt substitution is authorized by that recovery.
Sixteen jobs in this packet remain unrendered; the verified count stays 266.

Continuous-processing work now includes a durable metadata queue with 10,000-item
ingestion and eight-item phase claims, restart/hold handling, duplicate prevention
and explicit saved-render adoption. The eight unpublished real renders were
adopted at `NATIVE_READY`; a render claim correctly returns no work for them.
The executor is not yet continuous. Integration and qualification remain next;
see [continuous processing](docs/preview-continuous-processing.md). No IO hold or
new native run was created by this source work.
Highest native tiers are on Quasar, without
upscaling; lower tiers and old Ten files are preserved. Alexy is open in Classic
15.6 with all seven startup checks verified. Every owning helper and reservation
is closed. The full backlog and twelve Smart Preview exceptions remain open.

A changed build-only tool was isolated through a source-backed runtime-reuse
contract. Missing temporary timestamp-analysis evidence was replaced by a fresh
inspection of the installed bytecode. A terminal-record field projection was
saved separately for the recognition selector. Historical receipts, failed
preparations and original tool outputs remain unchanged; none required a native
render or publication replay.

A prelaunch coordinator check confused global packet positions with local reader
positions. All readers had closed and no renderer launched. Independent recovery
closed the idle owner; its exit137 remains separate from the corrected render’s
actual success. A checkpoint-driven private source author now validates those
index domains independently. Six controls reproduce the old failure and check
all four cohort positions. The final eight-job source subsequently completed
successfully; its publication is complete and partial recognition is recorded above.

The finite Unison timed run is independently recovered and closed, and both
sealed-return hashes were checked. Its original exit137 remains distinct from
its saved functional results. There is no remaining Unison IO hold.
Capture qualification and the subsequent actual eight-preview publication and
native recognition are complete for that finite cohort. The complete
takeover goal, including the large-preview backlog, remains incomplete.


Current operational checkpoint: four continuous 10,000-file Smart Preview windows
completed with independent callback/output audits and actual direct-owner closure.
A fifth stopped after a returned callback reported 248 successes and two errors.
The successes were independently verified, bringing that partial run's total to
63,095 valid/nonempty previews. The two
HEIC errors are isolated alongside nine previously queued exports; originals are
unchanged. Only proven-idle Python controllers were stopped during recovery,
and the owning-tool terminal and fresh lock-bundle release were recorded.

The operator then prioritized an exact older-fork Unison interoperability test.
Its fixed fourth attempt passed all four cases/twelve calls and closed before
Photo resumed. The preview successor now records explicit per-photo failures in
a no-retry queue, audits successful outputs and all original epochs, then advances
only after the parent acknowledgement. Missing accounting, foreign IDs and unknown
ownership still retain the job. All 31 local control tests passed; the native successor then completed another
2,500 previews through ten audited callbacks, bringing the current reconciled
total to 65,595 verified and 40,572 accepted files pending. At the operator’s request it has now
yielded IO for a separately admitted Unison camera observation. That admission
expired unstarted; the source-bound workspace/deadline and full-lock audit released
its scheduling-only hold. Photo’s first restart refused a changed installed UV
launcher pin before UI entry. It was independently closed, the original manifest
was preserved, and only that pin was updated after testing the exact configured
offline Python launcher. The fresh window then created and independently verified
4,250 previews without errors before the operator requested another Unison test
window. It stopped at the next SDK callback boundary; the actual coordinator
returned exit0, direct SDK owner/helper groups settled, and its IO/CPU reservations
closed. The reconciled total is69,845verified and36,322eligible files pending.
Photo yielded for both Unison tests; their actual closure is now confirmed and
a fresh Photo controller is live. Exact terminal and scheduling records are in the private handoff.
The full objective remains incomplete.

Work from this checkout. Repository layout and source-promotion rules are in
[docs/development-layout.md](docs/development-layout.md).

The complete local operational handoff is
[.private/photo/OPUS-HANDOFF.md](.private/photo/OPUS-HANDOFF.md). It is deliberately
ignored: it contains machine paths, catalog identities and private receipt
references. The complete investigation and retained helper sources live under
`.private/`; they must not be committed or pushed.

The overall takeover, receiver coherence and full-catalog preview objective is
**active and incomplete**. Public component tests are not native completion
receipts. Continue from actual recorded process and ownership evidence, preserve
old media and previews, and never replay an expired or consumed admission.

Keep the detailed private handoff updated after meaningful work. Update this
entry point when the repository architecture or continuation location changes.

## Immediate operational priority

Continue with jobs 25–32 in the current guarded 32-job packet. The preceding
packet and this packet’s first twenty-four keys are complete; do not repeat them. Twelve Smart Preview exceptions remain:
two calls that never returned, three known HEIC errors and seven exports not yet
attempted. Preserve these records; diagnose eligibility and the unreturned calls
before any further attempt. Receiver reuse, retained previews, original media,
Cloud identity and edits remain protected.

The detailed private handoff binds the latest actual terminals, publication and
native recognition receipts. It also preserves the full cleanup/date/migration
scope. Use those current records rather than older live-handle notes below.

## Repository and continuation status

The working branch is `work/photo-preview-integration` in the
`firstpair/lightroom` repository. Commit and push reviewed portable changes as
they become ready; keep the full operational handoff current locally. The
ignored investigation is not a substitute for tracked, reusable implementation.

The latest published eight-image cohort completed all four native recognition
pairs normally. Independent checks verified the captured cache loads, decodes,
current catalog bindings, file epochs and actual ownership closure. An earlier
cohort's recovered composite remains separate historical evidence; it was not
rewritten as a normal batch success.

A further eight-image render window completed and reopened the catalog through
the normal verified startup path. Its encoded outputs passed independent full
hash, image decode and embedded color-profile checks. Both engines staged those outputs and independent checks verified the staged
copies. Publication then retained ownership before the first capture because
a global descriptor census exceeded its output bound. A source-bound recovery
closed the read-only diagnostic processes and idle worker, collected the actual
outer terminal, verified resource closure and reopened the catalog normally.
No preview key was written by that failed attempt. A qualified census-handling
successor is required before a fresh publication attempt; the saved renders and
staged outputs must not be regenerated. A bounded complete-stream descriptor
projection is now implemented and tested, including a large synthetic listing
and an independently checked local read-only capture. It is not yet integrated
into production publication. A pure reported-capture verifier now also checks
full raw hashes, counts, projection and serialized settlement fields. Its synthetic
controls and saved-capture readback passed; it cannot authenticate a real wait or
release resources. A descriptor-relative file adapter now checks pinned receipts
and raw captures with nofollow opens, held/visible identity fences and combined
close-uncertainty preservation. Eight disposable-file controls pass; no live
process census, media, catalog or production publication was invoked by them.
The caller still needs an authenticated complete execution journal: a valid
supplied subset does not prove all attempts are accounted for. Parent
capture-prefix and retained-failure integration
must be qualified before a new attempt. Exact process and receipt details
remain in the private handoff. Full-catalog generation and final
receiver/coherence audits remain incomplete.

A source-level capture-attempt journal now persists intent before an injected
capture callback, receipt/projection bindings before returning, and a sealed
inventory afterward. Eight inert controls passed, including failure ordering,
no replay after uncertainty and independent projection binding. Its injected
writer now has a descriptor-relative filesystem adapter with fourteen
temporary-file/fault controls: exclusive bounded snapshots, file/directory fsync,
one-shot close and uncertainty preservation. No real process census or publisher
uses this journal yet. Independent descriptor-relative saved-journal readback is
now component-qualified with fourteen corruption, ordering and close controls.
Portable producer/parent composition now joins both directory inventories,
durable attempts and independently read raw capture/projection bindings; thirteen
original controls pass with explicit fake capture/process reports. The versioned
live capture adapter and actual parent lifecycle still require integration and
qualification. These components grant no process, publication or release
authority, and do not establish storage-device failure immunity.

The owned-capture adapter now preserves fixed scope and the original uncertainty
carrier while routing calls into that durable session. Five portable controls and
four private installation-boundary controls pass; the full 135-test repository
suite passes on both interpreters. Installation is source-only, with no live
publisher change, process census, media read or publication. Next: a new worker
and parent must bind this dependency graph and audit the sealed capture prefix
before worker reap and resource closure, then qualify actual failure recovery.

The parent capture audit now requires a terminal, unreaped direct worker, verifies
all journal/raw/projection bindings and reported counts, and rechecks the worker
reservation before returning. It never reaps or releases grants. Five controls
pass, plus five private controls using the existing close carrier; the full
140-test suite passes on both interpreters. A new private worker/publisher schema
passes read-only preflight for all eight saved keys and 40 sources. Live entry is
explicitly disabled: separate `ps` helper closure receipts, the complete parent
ordering and failed-prefix recovery still need qualification. Existing publisher
versions, admissions and saved renders remain untouched.

The missing process-list helper now has an owned component: durable intent before
the fixed read-only command, group census before actual wait4, complete bounded
output and close carriers. Eight component controls pass, including an actual
process listing and natural-exit fixture recovery. A separate saved-byte checker
passes six synthetic controls; all 146 repository tests pass. No SDK/media or
publisher operation occurred. Complete process-attempt inventory and the new
parent/worker failure path remain to be composed before live publication.

Complete process-attempt inventory is now composed: exact intent/result/raw/seal
namespace checks, fixed-command host routing, and both helper inventories audited
while the worker remains unreaped. Nine namespace, seven host and four combined
parent controls pass. One actual fixed process-list call through the adapter also
passed saved-inventory readback and closed normally. Full repository tests:148 on
both interpreters. The new source-only worker preflight still validates all eight
saved keys, now44sources. No publication or recopy occurred. Next is actual owner
ordering and ordinary/zero-call failure finalization; live entry remains disabled.

Retained-owner finish ordering is now component-qualified: helper audit before
actual worker group settlement, then CPU before IO close; unknowns retain their
original carriers without retry. Three actual original Python/disposable-lock
cases passed for exit0, exit7 and a parent reporting-callback fault. Explicit
unused-capture proofs supply no process observation or exclusion authority.
All168repositorytests pass on both interpreters. Actual monitor-preview publisher
failure finalization and installation remain pending; none of these source tests
changed preview data or authorized publication.

The bulk Classic build now runs with the documented macOS background scheduling
policy so it can yield under contention. The command succeeded and observed
scheduler priority fell while callbacks continued. This is not a hard eight-core
cap. Restore normal foreground scheduling for the same verified Classic launch
when bulk generation stops or completes; that cleanup remains pending and is
recorded in the private handoff. No automatic restorer is installed. Current
ownership/adoption, Lux/Ten cache aliases and the stable Classic15.6 launch were
also rechecked without payload hashing or catalog writes.

Capitola’s local status and handoff now identify the current controller and
preview location. The older live-looking status was preserved as history. Counts
separate callback attempts, verified successes, known failures and whole-job
closure; a running prefix cannot authorize copying under the held IO lease.
All118,299inputrows resolved by asset identity;12,040current paths outside the
authorized source root remain recorded/skipped. Eligible distinct files total
106,167;92aliases bring the ordinary unsynced collection to106,259members.
The current read-only capacity observation remains above both volume reserves.
