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
