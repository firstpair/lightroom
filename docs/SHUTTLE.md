# Move a closed Lightroom catalog between two Macs with Unison

`scripts/shuttle.py` prepares a guarded physical-drive handoff. It synchronizes
one named catalog folder, retains each Mac's Unison history separately, and
requires an independent byte-verification receipt before releasing ownership.
It does not open SQLite, launch Lightroom, merge catalogs, or acknowledge Sync
work. A successful transfer is separate from successful native startup or cloud
convergence.

This implementation currently requires macOS, APFS rollback-clone support,
stable Lightroom Classic **15.6**, a pinned compatible Unison executable, and
Python through `uv`. Qualify another Classic version before changing that gate.
Public qualification covers synthetic catalog families and small native Unison
2.54 transport controls. The large production handoff is still awaiting complete
transport, verification and receiver acceptance; it is not a published completion
claim. This repository contains the transport and ownership utility, not a
ready-made independent critical-family verifier or an automatic handoff daemon.
Use an independently reviewed verifier before executing a production handoff.

## Scope and storage

Use a star: Mac A's SSD ↔ portable Photo volume ↔ Mac B's SSD. Always exchange
the closed working catalog through Photo. Each Mac has its own state directory,
stable `UNISONLOCALHOSTNAME`, literal SSD root, and pair archives. Do not copy one
Mac's archive files over the other's, alias different SSDs to the same root,
or change host/root/tier bindings to bypass a mismatch. Preserve both dedicated
state directories when upgrading Unison or moving the Macs. Archive names depend
on canonical host/root names, the whole root pair and archive format, rather than
just the profile's filename. Stable identities therefore matter even when the
portable disk's bytes are unchanged. [Unison archive naming source](https://github.com/bcpierce00/unison/blob/v2.54.0/src/update.ml#L74-L209).

Back up a host's state only after its Unison process has stopped. Keep each
host/tier backup in its own named directory on the portable disk, alongside its
private configuration and bound transport/verification receipts. Use an
independent snapshot and verified copies of the state files; do not hard-link
live archives or combine individual archive files from different runs. Restore
a backup only to that same host/root/tier identity. The utility retains the live
private state directory; it does not automatically publish a portable state
backup or copy one into the receiving Mac's state directory.

The configured roots can be the Lightroom parent directories, but the generated
profile selects only the catalog's immediate folder. Siblings such as original
photos, other catalogs, plugins, recovery archives and diagnostics stay outside
this operation. Every receipt explicitly reports
`wholeLightroomFolderComplete: false`.

| Tier | Included within the selected catalog folder | Excluded |
| --- | --- | --- |
| `full` | Catalog and all its present sidecars; `.lrcat-data`; Sync and Helper packages; standard and Smart Previews; Backups; other ordinary contents | `.ruff_cache`; `.DS_Store` names |
| `main-core` | Catalog and all its present sidecars; `.lrcat-data`; Sync and Helper packages; **standard Previews**; other ordinary contents | Smart Previews; Backups; `.ruff_cache`; `.DS_Store` names |

On a smaller receiver SSD, use `main-core` and explicitly declare a Smart
Previews symlink pointing at that same catalog's Smart Previews package on Photo.
The utility accepts only that exact declared link and only in the excluded
tier. It does not create the link or prove that Lightroom can use it. Standard
Previews remain on the receiver SSD. Connect Photo whenever that catalog is
open, then verify the actual package paths in Lightroom before resuming Sync.
Other symlinks in the catalog folder are held, including included preview links.
Only the excluded Smart Previews package can be declared in
`photo_preview_links`; a standard Previews declaration is rejected because
that package is included on the SSD in both tiers.

Choose one immutable tier for each dedicated host state: a large SSD can retain
`full`, while the smaller receiver uses `main-core`. A tier change requires a
new deliberately named state directory and an explicitly reviewed baseline.
It is not a routine switch on existing archives.

Do not equate an aggregate `du` size with additional allocated storage: APFS
clones can make a sum much larger than unique physical extents. The config must
declare a measured additional transfer budget and free-space reserve. The
utility checks that budget against destination capacity; it does not estimate
every preview or future copy-on-write allocation. Cross-volume transfer cannot
share APFS extents with the SSD source. Subsequent backups and changed clones
can consume more space.

## Private configuration

Keep configuration, archives, owner markers, run journals, rollback snapshots
and verification receipts out of the public repository. `.shuttle-private/`
and `*.private.json` are ignored. Do not put a state or rollback directory inside
either synchronized root.

Example structure; replace every placeholder with a measured, literal value:

```json
{
  "schema": 1,
  "host": "laptop",
  "peers": ["desktop"],
  "local_root": "/Users/you/Pictures/Lightroom",
  "photo_root": "/Volumes/Photo/Lightroom",
  "photo_mount": "/Volumes/Photo",
  "photo_uuid": "REPLACE-WITH-ACTUAL-VOLUME-UUID",
  "main_catalog": "Example/Example.lrcat",
  "state_dir": "/Users/you/Library/Application Support/Lightroom Shuttle/laptop-full",
  "local_backup_root": "/Users/you/Pictures/Lightroom-Shuttle-Rollback",
  "photo_backup_root": "/Volumes/Photo/Lightroom-Shuttle-Rollback",
  "journal_root": "/Users/you/Library/Application Support/Lightroom Shuttle/runs",
  "owner_marker": "/Volumes/Photo/Lightroom-Shuttle-Control/owner.json",
  "shared_io_lease": "/absolute/existing/shared-photo-io.lock",
  "classic_app": "/Applications/Adobe Lightroom Classic/Adobe Lightroom Classic.app",
  "transfer_budget_bytes": {"full": 139586437120, "main-core": 64424509440},
  "minimum_free_bytes": 34359738368,
  "unison": {
    "path": "/absolute/canonical/keg/bin/unison",
    "sha256": "REPLACE-WITH-WHOLE-EXECUTABLE-SHA256",
    "version": "2.54.0"
  },
  "photo_preview_links": {}
}
```

The receiver can declare:

```json
"photo_preview_links": {
  "Example/Example Smart Previews.lrdata":
    "/Volumes/Photo/Lightroom/Example/Example Smart Previews.lrdata"
}
```

All paths must be absolute and canonical, without symlink ancestors. The Main
catalog scope must be exactly `folder/name.lrcat`; pattern metacharacters are
rejected. An existing owner-marker parent directory and the shared regular
lease file must already be present. Use a proven shared lease honored by other
Photo workers; this utility never invents or replaces that lease. A Mac's own
persistent job lock is exclusive and nonblocking; the shared Photo lease waits
for earlier I/O work to finish. Neither lock inode is deleted after a run.

Unset inherited `UNISON`, `UNISONLOCALHOSTNAME`, `UNISONBACKUPDIR` and
`UNISONMIRRORDIR`: the utility supplies its own dedicated state and backup paths.
Pin a canonical installed binary, not a mutable package-manager symlink.
The [2.54 release](https://github.com/bcpierce00/unison/releases/tag/v2.54.0)
removes wire/archive compatibility with versions before 2.52. Use the same
qualified version on both Macs and preserve the old installation, profiles and
archives before upgrading. Compatibility with a release family does not qualify
every build or optional preference. Retain an unmanaged installation rather than
overwriting it to repair a package-manager link.

## Initial outgoing transfer

Pause new imports, metadata writes, preview generation and Sync before a planned
handoff, then normally quit the Main catalog and let shutdown finish. Copy the
existing Sync package along with the catalog so its local state is preserved;
do not clear queues, relabel cloud records or recreate collections for migration.
If shutdown is stuck, resolve that separately; a copy of a live family is not an
acceptable substitute for closure.

Another isolated catalog, such as an AI render catalog, may remain open only
when the Main family has no open descriptors.
The utility checks all-process numeric descriptors, case variants of Main's
paths, and the Main database's device/inode. A remaining catalog lock, unexpected
symlink, wrong volume UUID, unmounted Photo, incompatible app or changed binary
holds the operation. `lsof` is a closure observation; it does not prevent a user
from reopening Main later. Leave Main closed through transport and verification.

One narrowly recorded exception is an exact `.DS_Store` basename inside Main
with an actual `lsof` access field of read-only `r`, provided its device/inode
does not match the catalog. That name is explicitly ignored by the generated
Unison profile. The closure receipt retains these observations as
`excludedIgnoredReadOnlyFDs`; a Spotlight read of that ignored file does not
prove Main is open. Writable or unknown-access `.DS_Store` descriptors,
catalog aliases under that name, and all included-file descriptors still hold.

```sh
uv run --no-project python scripts/shuttle.py --config /absolute/laptop.private.json status
uv run --no-project python scripts/shuttle.py --config /absolute/laptop.private.json preflight --tier full --source local
uv run --no-project python scripts/shuttle.py --config /absolute/laptop.private.json bootstrap --tier full --source local --execute
```

Without `--execute`, `bootstrap` and `sync` perform preflight only. `status`
does not authorize opening the catalog. The first transfer requires a local
source and no existing owner marker. Bootstrap explicitly makes the selected
source authoritative; it may remove obsolete destination members inside the
selected catalog folder. Never use it to choose between independently edited
catalogs.

Before bootstrap, the utility clones the complete existing destination critical
family into a fresh directory outside the synchronized root, on the same
volume. Critical means the database, present `-wal`, `-shm` and `-journal`,
`.lrcat-data`, Sync and Helper package contents. These are independent APFS clone
inodes, not hard links. Unison's central per-file backups provide additional
history, but do not replace a coherent database-family snapshot. The preservation
receipt records actual file identities; it does not claim a whole-file SHA read.

Present source WAL/SHM files are included, even when a previous read-only
observer created empty sidecars. Destination-only stale sidecars stay with the
preserved old family and are then handled by ordinary source-authoritative
Unison deletion. The utility never deletes WAL/SHM directly and never copies an
open catalog.

The generated bootstrap profile deliberately omits Unison's `atomic` directory
grouping. A native 2.54 test with two existing directories showed that combining
`atomic = Path folder` and `-force source` could return zero after copying only
directory properties, leaving child database files untouched. Removing grouping
for bootstrap copied the actual files and removed stale destination sidecars.
Opening/release remains blocked until independent complete critical-family
verification. Bootstrap is not a filesystem transaction.

## Verify, release, physically move, accept

Unison exit zero produces `RESULT.json` and a `verification-required` marker.
It does not transfer ownership. Run an independent closed-family verifier that
fully hashes every critical file on **both** roots, proves exact relative
membership and size equality including absent sidecars, and retains stable
per-root FD/path inventories before and after hashing. Do not open SQLite to
verify a byte transfer. Source and destination device/inode/ctime naturally
differ. Native 2.54 also rounded a sub-microsecond mtime remainder in the small
test; do not require cross-root nanosecond equality.

The accepted schema is:

```json
{
  "schema": 1,
  "runId": "EXACT-RESULT-RUN-ID",
  "resultSha256": "EXACT-RESULT-FILE-SHA256",
  "roots": {"local": "EXACT-LOCAL-ROOT", "photo": "EXACT-PHOTO-ROOT"},
  "tier": "full",
  "sourceStable": true,
  "criticalFamilySHA256Equal": true,
  "databaseFamilyMembershipEqual": true,
  "missingExpectedFiles": [],
  "staleDatabaseSidecars": [],
  "criticalFiles": [
    {"path": "Example/Example.lrcat", "size": 123,
     "localSha256": "EXACT-SHA256", "photoSha256": "SAME-SHA256"}
  ]
}
```

This is a receipt schema, not a JSON template to fill with assurances. Supply
every critical regular file exactly once, not just the illustrated database.
The independent verifier must produce these facts from actual held-file reads
and stable membership observations. The utility consumes that evidence; it does
not rerun the full payload hashes itself. A copied example or hand-written
Boolean declarations cannot qualify a transfer. The consumer binds the result/run/roots/tier and requires current
full critical inventories to remain equal to the result. Native database
validity, media completeness and cloud completion need separate evidence.

```sh
uv run --no-project python scripts/shuttle.py --config /absolute/laptop.private.json release --to desktop --receipt /absolute/VERIFIED.json --execute
```

Only then unmount Photo normally and connect it to the receiver. The released
marker names the exact receiving peer and leaves the old Mac without ownership.
Install the same stable Classic version on that Mac before proceeding. Keep
the old Mac's Main closed throughout the receiver work. Confirm the receiving
Mac's Adobe account, expected Sync catalog and original-file destinations: cloud
credentials and application preferences are not copied by this selected-folder
transport. Original photos are separate and must already be available at their
registered paths or be normally relinked after a verified copy.

Create
its empty Lightroom parent root and private, separately named state/config
directories; the selected catalog folder may be absent. Its first receiver
copy is explicitly source-authoritative from Photo:

```sh
uv run --no-project python scripts/shuttle.py --config /absolute/desktop.private.json preflight --tier main-core --source photo
uv run --no-project python scripts/shuttle.py --config /absolute/desktop.private.json bootstrap --tier main-core --source photo --execute
```

Independently verify that receiver transfer, install and check its explicitly
declared excluded Smart Previews link if needed, then accept the receiver's own
bound verification receipt:

```sh
uv run --no-project python scripts/shuttle.py --config /absolute/desktop.private.json accept --receipt /absolute/RECEIVER-VERIFIED.json --execute
```

Now open the exact received catalog, check locations and previews, confirm
the intended catalog is the one connected to Sync, and resume. Honor the owner
marker on both Macs. This script does not intercept a manual application launch
or configure Lightroom's cloud account. Do not start the old and new Main copies
against cloud Sync concurrently. If Photo supplies the originals or Smart
Previews, keep that physical volume attached while the owning catalog is open;
the utility's mount guard protects transport, not a later Lightroom session.

## Subsequent shuttles and conflicts

Quit the owning catalog, run its usual tier with `sync --source local --execute`,
independently verify, and release to the other peer. On the receiving peer use
its usual tier with `sync --source photo --execute`, verify and accept. Reuse
the original host's state directory and unchanged root identities each time;
the initial expensive fingerprinting baseline does not need to be discarded.

Routine profiles enable `atomic = Path folder` to hold simultaneous folder
updates as a conflict, and include no `force`, `prefer`, `merge`, `follow`,
`ignorearchives` or `ignorelocks`. `atomic` is conflict grouping, not atomic
replacement of a database family. Routine sync snapshots both critical families
because either side could be updated. The actual small 2.54 test reused its
archives for updates in each direction, then returned exit one and retained
both copies when both databases changed independently.

Batch mode skips unresolved conflicts. Exit one or any failure produces a held
marker and never releases ownership, even if some nonconflicting files were
copied. Preserve `INTENT.json`, `EXECUTED.prf`, actual `UNISON-EXIT.json`, output,
results and both rollback families. Review the exact held run and independently
edited catalogs before choosing a successor. The utility intentionally has no
automatic reset, blind retry or catalog text-merge command.

Times, extended attributes and resource forks are enabled; `maxthreads = 2`
limits transfer concurrency on a shared external disk. Unison's supported xattr
rules still apply; this is not an assertion that every macOS system attribute or
filesystem flag is replicated.

## Cold baselines, remounts and progress

The first run for a new root pair has no last-synchronized baseline. Even when
most files already exist at the destination, Unison normally fingerprints both
replicas before reconciliation. Hundreds of thousands of previews on a hard
drive can make this stage take hours with little change in free space. Growing
`fp...` cache files and a moving `Looking for changes` path indicate update
detection; they do not mean copying or verification has completed. A printed
UUID-prefix range is not a measured byte percentage or a handoff ETA.

Keep the complete dedicated state directory, including pair archives and
fingerprint caches, after a stopped run. On later runs, `fastcheck` can reuse
content fingerprints when the native time/length/inode and resource-fork checks
pass. A new host/root/tier baseline remains expensive; restoring one host's
history into another host's state directory does not eliminate that requirement.
[Unison fingerprint-cache source](https://github.com/bcpierce00/unison/blob/v2.54.0/src/fpcache.ml#L151-L254).

A portable disk's operating-system device number can change across mounts.
Unison 2.54's reviewed file fast-check predicate uses the file inode stamp,
modification time and length, not that device number. This supports the inference
that a device-number change alone need not force every unchanged file's content
to be read again. It is source evidence, not a measured Mac-to-Mac remount result.
The volume UUID, literal root and the host's own archive pair must still match;
the utility continues to require fresh per-run identities. [File-stamp source](https://github.com/bcpierce00/unison/blob/v2.54.0/src/fileinfo.ml#L190-L216).

Metadata rescanning is separate: changed ctime or properties can require fresh
xattr/ACL inspection even when data fingerprints remain reusable. Directory
walks, file replacements, timestamps, resource forks and filesystem differences
can still add work. Keep the inode checks enabled; do not use
`ignoreinodenumbers`, `ignorearchives` or `fastercheckUNSAFE` to manufacture a fast
baseline. [Property/ctime source](https://github.com/bcpierce00/unison/blob/v2.54.0/src/props.ml#L623-L659).

Preserve and inspect the current run's `stderr.txt`, `stdout.txt`, `unison.log`
and actual exit/result receipts. Exit zero and complete critical verification
remain required, regardless of a reassuring spinner or file count. Lightroom's
cloud Sync counter belongs to a separate process and is not Unison progress.

## Returning ownership and restoring a held family

For a normal return, quit Main on the current owning Mac, publish with that
Mac's usual `sync --source local`, verify and `release --to` the other peer.
Move Photo back; the other Mac runs its own usual `sync --source photo`, verifies
and `accept`s before opening Main. Reuse each host's unchanged private archive
identity and tier. Never keep using the old catalog merely because its SSD copy
is still present.

There is no cancel-release, reset-owner or automatic rollback command. If a
handoff has been released but the receiver cannot proceed, retain the
`in-transit` marker and keep both Main copies closed. Return through the normal
receiver/owner protocol once its prerequisites are met, or prepare a separately
reviewed recovery bound to the actual marker, current families and receipts.
Do not delete or hand-edit the marker to make an old Mac appear to own the copy.

If a run holds or a native catalog check later fails, use this manual recovery
sequence:

1. Keep both Main copies closed and stop additional work on the affected
   families. Preserve the actual failure, transport receipts, complete state
   directories and current closed families before changing anything.
2. Choose one coherent saved critical family from the exact preservation
   receipt. Account for every edit/import performed since that snapshot; a
   rollback can otherwise discard valid catalog work.
3. Restore into a separate recovery location first. Restore the whole recorded
   family together, including `.lrcat-data`, Sync, Helper and present database
   sidecars, and prove the recorded absent-sidecar membership. Never overlay an
   old database onto unrelated current WAL/SHM files.
4. Independently verify the recovery copy against the closed preserved source.
   Test native catalog validity with Sync disabled and preserve the current
   working copy. A per-file central Unison backup is not a coherent family.
5. Review the exact ownership/recovery successor before replacing a working
   family or reopening cloud Sync. Keep old and recovered receipts; do not rerun
   the held operation, discard pair archives or forge a success marker.

The utility does not automate those recovery choices. Its snapshots protect
catalog data and local Sync state; they do not roll back the cloud or restore
original photos that were outside the selected catalog folder.

## Validation and primary references

Run the repository tests with:

```sh
uv run --no-project python -m unittest discover -s tests -v
```

The bounded tests exercise wrong-volume and app-version rejection, Main
descriptor detection with an isolated AI catalog permitted, archive/tier
separation, unsafe paths/symlinks/environment overrides, coherent preservation,
empty receiver admission, and held/verified ownership transitions. Native
temporary-directory tests cover empty and existing bootstrap targets, critical
file replacement, stale WAL/SHM deletion, attributes/resource forks, archive
reuse in both directions, and conflict holding. They contain synthetic bytes;
actual catalog startup and cloud convergence remain separate qualification.

The public source adds a focused guard correction to that transport revision:
an explicitly declared standard Previews symlink is now rejected at configuration
loading and again at filesystem admission. The accepted excluded Smart Previews
route remains covered by its control. The correction was source-reviewed and
regression-tested; it has not been exercised in a production handoff. An already
running pinned predecessor must finish under its original source and receipts;
do not replace its executable with this successor mid-run.

See [Unison's manual source](https://github.com/bcpierce00/unison/blob/v2.54.0/doc/unison-manual.tex),
[2.54 release](https://github.com/bcpierce00/unison/releases/tag/v2.54.0),
[reconciliation source](https://github.com/bcpierce00/unison/blob/v2.54.0/src/recon.ml),
[archive implementation](https://github.com/bcpierce00/unison/blob/v2.54.0/src/update.ml),
[central backup implementation](https://github.com/bcpierce00/unison/blob/v2.54.0/src/stasher.ml),
and [macOS copy support](https://github.com/bcpierce00/unison/blob/v2.54.0/src/copy_stubs.c).
The manual explains [fast checks and removable-media mount guards](https://github.com/bcpierce00/unison/blob/v2.54.0/doc/unison-manual.tex#L2165-L2213).
Adobe documents [catalog creation and moving](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/create-catalogs.html)
and [Classic cloud synchronization](https://www.adobe.com/learn/lightroom-classic/web/sync-photos-lightroom-mobile).
