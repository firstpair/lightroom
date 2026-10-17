# Development layout

The Lightroom checkout owns the repair tooling, catalog shuttle, preview
pipeline development and operator documentation. Continue work from this
repository, rather than a separate investigation directory.

| Location | Purpose | Git policy |
|---|---|---|
| `scripts/manage.py`, `templates/` | Configurable repair installer and runtime templates | Reviewed public source |
| `scripts/shuttle.py` | Guarded catalog shuttle | Reviewed public source |
| `scripts/preview_pipeline/` | Portable, independently reviewed preview components | Public source and synthetic tests |
| `tests/` | Synthetic and disposable tests for public components | Public, no real catalog fixtures |
| `docs/` | Cookbook, design and operator guidance | Public, anonymized |
| `OPUS-HANDOFF.md` | Public continuation entry point | Public, no private receipts |
| `.private/photo/` | Complete local investigation, machine-bound source, runtime journals and detailed handoff | Ignored, never stage |
| `.private/photo-helpers/` | Retained temporary operation scripts | Ignored, never stage |
| `.private/photo-migration-*.json` | Local relocation and identity checks | Ignored, never stage |

## What moved

The former investigation directory was relocated into `.private/photo/` with
a same-filesystem directory rename. Its former location remains a compatibility
symlink. Retained temporary helper scripts were also moved into the checkout,
with compatibility symlinks at their former locations. No catalog or preview
payload was copied, rewritten or deleted by this relocation.

Compatibility links preserve old textual paths, not every possible canonical
path check. A relocation is not native runtime requalification. Before the next
operation, inspect its current source, ownership rules, canonical-path checks
and exact pins. Never rewrite old receipts, refresh a consumed admission, or
claim a missing parent terminal from a worker receipt.

## Complete descriptor census projection

`scripts/preview_pipeline/descriptor_census.py` consumes a complete, bounded
`lsof -Fpcftn` stream. It validates every field, hashes all input bytes and
retains exact protected PID/descriptor/type/name records. Unrelated names do
not need to occupy the publisher's in-memory capture buffer. The legacy field
projection keeps every observed PID and, if no protected descriptor exists,
one actual unrelated name as the nonempty-listing witness. Its smaller listing
must not be presented as the original raw capture or its total descriptor count.

Protected roots are literal path boundaries, without filesystem resolution.
Callers must explicitly include catalog sidecar names and admitted aliases;
protecting a catalog filename does not implicitly include its `-wal` or `-shm`
siblings. The caller still authenticates the raw capture and its file epoch,
requires actual command success and stderr policy, proves child/group/FD
settlement, checks process membership and applies the existing descriptor
exclusion rules. Parser success is not an ownership or publication grant.

`scripts/preview_pipeline/census_receipts.py` also checks a reported capture
against the complete raw byte stream: command, reported wait/group/FD fields,
raw identity shape, full hash, counters and reconstructed projection must agree.
Its result always carries no resource-release authority. The caller still
binds the receipt and raw file to the actual invocation, checks held/visible
file epochs and stderr policy, proves the real owning-tool terminal and applies
the exclusion rules. The pure verifier neither opens files nor observes or
signals processes. Source tests do not qualify its production integration.

`scripts/preview_pipeline/census_files.py` adds a file-reading adapter beneath
a caller-held directory descriptor. It accepts only pinned direct capture
children, opens files without following symlinks, checks private modes and link
counts, reads bounded receipt/raw bytes, and fences held and visible file
identities before closing its own descriptors. Multiple close uncertainties
preserve their identities and the original failure; descriptors are never
retried. The borrowed root descriptor stays with its caller. Disposable tests
cover substitution, replacement during reading and close failures.

This adapter still cannot prove that the supplied inventory includes every
attempted capture. The production parent must authenticate a complete execution
journal and audit the capture prefix before reaping its worker or releasing
grants. Missing records, failed prefixes and uncertain closes require retained
ownership until independently resolved. No current publisher uses this adapter.

`scripts/preview_pipeline/census_journal.py` supplies the source-level attempt
state machine: a caller-qualified writer must persist intent before invocation,
then receipt/projection bindings before returning success, and finally a sealed
inventory. Invocation or post-invocation persistence failures stop the instance
and require retained ownership; they never trigger a retry. The reader checks
the reported sequence against expected receipt pins and independently checked
capture projections. Eight inert tests cover ordering, missing/substituted
records, reentry and persistence faults. The writer is injected: these tests do
not establish durable storage, real child settlement or complete production
instrumentation. The actual writer, capture wrapper and parent lifecycle still
need integration and qualification before this can support publication.

Synthetic tests cover a protected record beyond the old capture size, fragmented
UTF-8 input, malformed/truncated fields, literal path boundaries and resource
limits. A local read-only process-listing control also compared projected
records against a separate full-capture scan. Production publication integration
and its retained-failure lifecycle remain separate qualification work.

## Moving source into the public tree

The private workspace contains reusable implementation alongside one-off
scripts, private identifiers, generated receipts, binaries and Adobe-derived
investigation material. Moving it into the checkout does **not** make that
material suitable for Git. Promote components deliberately:

1. Preserve the historical source and receipts in the private workspace.
2. Extract authored, reusable code into the appropriate tracked component.
3. Replace machine paths and identities with explicit inputs. Preserve refusal,
   ownership and settlement checks; do not relax them to make a run pass.
4. Add original synthetic tests and record exactly what they qualify.
5. Review the complete staged diff for personal data, credentials, media,
   private receipts and Adobe-derived bodies before committing.

The first preview component is `recognition_selection.py`: a pure pair selector
from an independently verified eight-key publication. It requires actual parent
tool closure, preserves the whole-publication provenance and creates independent
pair views. It does not publish files, touch a catalog or call Lightroom.

`workspace_paths.py` resolves one explicitly recorded old-root symlink into
the relocated workspace. Both roots' identities are checked; unrecorded aliases,
nested symlinks, traversal and root replacement are refused. It changes no
receipt strings, performs no payload reads, and supplies no lock or lifetime
proof. Callers still authenticate metadata and fence their reads.

`inherited_lock.py` verifies an explicitly passed regular-file description and
confirms its exclusive nonblocking flock. It never opens, closes or unlocks the
description. A parent can therefore retain a watcher lock across serial helper
processes, avoiding competing reopen attempts between quit and modal handling.
Disposable independent contenders verify that child exit does not release the
parent's copy, and that closing the parent permits fresh acquisition. The local
optional helper entry passed one read-only inspection with actual settlement;
normal-quit sequence integration has since completed bounded local close and
modal-handling windows with actual helper settlement. No installed startup flag was
changed, and the in-process native renewal timer is not excluded by this lock.

The remaining renderer, publisher, lifecycle coordinator and native cache
recognition implementation is preserved locally, pending component-by-component
portability and distribution review. Its existence is not a public installation
or full-catalog completion claim.

## Runtime continuation

Use the detailed ignored handoff at `.private/photo/OPUS-HANDOFF.md`, plus its
current state documents and pinned receipts. Keep that handoff current after
actual terminals, recovery and changes in next action. Keep this public entry
point focused on architecture and completion limits.

The last local continuation has a normally reopened catalog and eight freshly
audited preview publications with completed native recognition. The original
publication parent tool terminal was recovered from its authentic saved session
event; the earlier evidence-gap audit remains preserved. A separately versioned
metadata contract uses the relocation resolver and passed the existing
preservation controls. Four serial recognition runtimes then completed their
actual callbacks, loads, decodes and settlement, followed by an independent
audit. The exact private receipts remain in the operational handoff. This
qualifies that local recognition continuation, not relocation of every remaining
renderer or an installation on another machine.

Whole-catalog preview generation and final takeover/coherence verification
remain incomplete. The catalog, original media and installed services remain
at their existing external locations. This repository migration does not move
them or change their ownership.

`candidate_page.py` provides bounded, cursor-based selection from authenticated
planning rows. It retains every consumed exclusion and duplicate-key alias as
an observation, and does not consume a row beyond a selected batch boundary.
The caller must authenticate the sealed queue and completed-key evidence,
perform indexed queries, and freshly bind catalog/source metadata. Its cursor
records observation progress; it grants no rendering or completion authority.
The operational rolling controller has not yet adopted this component.

## Branch publication

Publish reviewed portable work on `work/photo-preview-integration` and keep its
upstream tracking on `origin`. A push publishes repository source and operator
documentation; it does not publish ignored operational evidence or qualify a
native run. Preserve used local source versions and receipts when creating
successors, and promote reusable implementations with synthetic tests before
adding them to the tracked tree.

`preentry_refusal.py` is a pure classifier for a reviewed helper refusal before
UI entry. A supervisor supplies the source digest and exact diagnostic byte
variants, including separately qualified recorded paths. It also supplies
independently authenticated actual wait/group observations. Source drift,
partial diagnostics, callback activity, live helpers and incomplete settlement
are refused. Original diagnostics are preserved and identified separately;
the classifier never acquires a lease, signals a process or authorizes a retry.
Synthetic controls cover both exact path variants and failures of each required
condition. The local binding additionally accepted the retained real refusal
without another UI operation. This does not qualify arbitrary helper errors.
