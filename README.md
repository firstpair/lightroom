# FirstPair Lightroom repair

Authored starter scripts and a practical [repair cookbook](docs/firstpair-lightroom-repair.md) for a large Lightroom Classic catalog. Public source: <https://github.com/firstpair/lightroom>.

The complete cookbook is published in the [First Pair library](https://firstpair.org/books/lightroom-repair/): [PDF](https://firstpair.org/lightroom-repair/pdf/), [EPUB](https://firstpair.org/lightroom-repair/epub/), [HTML](https://firstpair.org/read/lightroom-repair/) and [chapters](https://firstpair.org/read/lightroom-repair/chapters/). Read the [story of the repairs](https://firstpair.press/lightroom-repair/). Start with the [HOWTO](HOWTO.md), then use the recipes for your symptom. [Publication and verification](docs/LIBRARY-PUBLICATION.md).

The performance package derives from guards actually run in **Lightroom Classic 15.6 on macOS**. Those private installed controls had real native callbacks, equality checks, normal restart application, and bounded transport cleanup/renewal. This configurable public successor has passed source, syntax and temporary-installation tests; it has **not** yet been run in another user's native Lightroom session. It uses version-sensitive private imports and fails closed when owner, SQL, types, dependency bytes or callback facts differ. It is not an Adobe-supported universal fix.

No catalog, photo, preview, credentials, private diagnostic tree, Adobe Lua module body or bytecode is included. The Python tools never open a catalog database. Runtime SQL goes through Lightroom's own store provider. The startup watcher watches **Classic launches**, not photo folders; it never imports `~/foto` or resumes paused Sync.

## What the performance code addresses

| Mechanism | Guarded change | Limits |
|---|---|---|
| SQL affinity against a 51-million-row metadata table | In the exact native TEMP modTime/fileRename trigger, change only the selected image-ID RHS to unary `+id_local`, so SQLite can seek its existing `(image,payloadKey)` index | Full global numeric/integral image-key gate, selected-row equality, exact original trigger ownership, current indexed plan, native transaction and scoped restoration. Public default **off**. |
| Repeated roughly 700,000-entry Sync maps | TEMP revision/journal tracks changes; map/count queries reuse a generation or consult bounded deltas | New isolated output maps, nullable count semantics, generation/schema checks, journal-gap/native fallbacks, periodic native equality oracles and finite call/time/journal limits. |
| Redundant map copies and cross-state transport | Native C shallow copy is admitted only after equality/isolation controls and a measured 1.2× copy benefit; paired full/delta transports preserve separate mutable maps | Exact current listeners, epoch/sequence/positive ACK gates, zero-event cleanup, native owner deadlines, ordinary fallback and bounded restoration. Copy microbenchmark is not total application speed. |
| Folder resolver stranding download workers | Separately register freshly resolved destination folders through the native writer, then leave the complete native resolver unchanged | This is distinct from fileRename affinity. [Example adapter](examples/folder_resolver.lua) is not automatic and refuses registration without independent preservation admission; no queue-path rewrite. |
| Equivalent capture-date setter calls | Skip only a completely initialized, proven equivalent whole-second date assignment, including matched supported offset forms | Genuine changes, missing fields, fractional differences, `Z`/unsupported forms and predicate errors use the native setter. |
| Startup and renewal | One nonce-bound menu dispatch per exact PID/start lifecycle, followed by actual native callbacks; in-app checks every 300 seconds | Existing requests/transport must drain. No callback or old status never authorizes a repeat click. Runtime guards are finite, not permanent globals. |

An optional native-created expression index supports `UPPER(sha256)` lookups. Creating it is a durable schema change, so it is also disabled by default. This is separate from the TEMP affinity fix.

## Inspect and test first

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), clone this repository, and run:

```sh
git clone https://github.com/firstpair/lightroom.git
cd lightroom
uv run --no-project python -m unittest discover -s tests -v
uv run --no-project python scripts/manage.py --help
```

The repository's `.python-version` selects the tested CPython 3.14.6 through uv. Run these commands from the repository root. The installed LaunchAgent pins the exact interpreter and uv executable used for installation.

The tests reproduce SQLite's numeric-TEXT affinity counterexample, verify complete pin rebinding and the existence of rendered local source dependencies, stage the package against temporary fixture files, check overwrite refusal and unchanged fixture bytes, protect a foreign LaunchAgent from bootout, and require actual callbacks for success classification. They do not execute Lightroom imports or model a whole catalog as verified. See the [package validation record](docs/PACKAGE-VALIDATION.md).

## Install with startup disabled

1. Make and independently verify a complete backup while Classic is normally closed: `.lrcat` and current WAL/SHM family, `.lrcat-data`, Sync and Helper packages. Preserve originals separately. A normal catalog backup does not copy original photos; see [Adobe's catalog backup guide](https://helpx.adobe.com/lightroom-classic/help/back-catalog.html).
2. Quit Classic normally. Set the exact canonical catalog path below. Paths with quotes, backslashes or control characters are rejected; spaces are supported.
3. First inspect the dry run, then install. The destination must be new; existing menu/helper/agent files are never overwritten.

```sh
uv run --no-project python scripts/manage.py install \
  --catalog "$HOME/Pictures/Lightroom/Example/Example.lrcat" \
  --backup-confirmed --dry-run

uv run --no-project python scripts/manage.py install \
  --catalog "$HOME/Pictures/Lightroom/Example/Example.lrcat" \
  --backup-confirmed
```

`--backup-confirmed` records the operator's assurance; this installer does not independently prove the backup. Do not supply it before verifying your backup. Files live in `~/Library/Application Support/FirstPair Lightroom`. The installer builds an AppleScript helper using macOS `osacompile`, installs the authored menu in `~/Library/Application Support/Adobe/Lightroom/Scripts`, and prepares a LaunchAgent. It does **not** start automation or execute the helper.

For a local staging exercise, add `--stage-only --root /absolute/new/staging-directory`. It writes only that staging tree, builds no helper, installs no menu and cannot be enabled. `--app` and `--scripts-dir` allow explicit application/script locations. Staging is not native qualification.

## Verify the manual native run

Relaunch Classic normally, open the configured catalog, and invoke **Scripts → Apply FirstPair performance fixes** once. If the Scripts menu is absent, check that the menu file is in the directory above and relaunch normally. Do not repeatedly invoke the script because a callback is missing.

```sh
uv run --no-project python scripts/manage.py verify
```

Read the newest `runs/run-*/UI.txt`, `native.txt`, phase logs and `maintenance/events.txt`. A native run needs `native callback result=true` and `PHASE 0` through `PHASE 6 ok=true`. Disabled affinity/schema phases explicitly log or return disabled/skipped, so a successful callback with defaults is **not** proof those fixes ran. Transport startup, drain/restoration and later renewal require their own emitted receipts. `verify` checks source pins and reports the finite recent run outcomes; it does not certify cloud-server completion, all catalog preservation, every future renewal or import throughput.

Restoration also requires exact ownership of the installed wrapper and, for map/count cleanup, the retained installed TEMP definitions. A foreign owner or changed definition produces `HELD_RESTORATION`: its methods, owned global and journal stay in place, and old wrapper aliases use native query fallback. Inspect that retained state; do not reset globals or drop TEMP objects to force a fresh installation.

### Qualify affinity and the optional index

Both start disabled. Before using `--enable-affinity` in a **new** installation, inspect the exact current native TEMP SQL and ownership, complete global key-type guard and actual EXPLAIN plan. This successor selects 20 current legitimate root-file IDs, without private hardcoded catalog IDs, and compares all selected rows before replacing either trigger. Empty or differing scopes fail closed. That finite row comparison does not replace the whole key-type gate or become universal preservation proof. Bind an independent full before/after catalog protection snapshot and genuine native callback before calling the generalized fix accepted.

`--enable-schema-index` additionally authorizes the exact native schema-only expression index after the independently verified backup. It checks existing SQL ownership, transaction completion, unchanged row counts/`total_changes`, target integrity and the lookup plan. It does not silently rebuild a foreign index.

These flags are opt-in research controls. Do not weaken a failed current native gate to make a version appear supported; preserve the actual error and inspect it. The known original date module byte hash is retained, so another 15.6 build can also be held.

## Enable the startup helper

After one manually verified native run, grant these permissions to **FirstPair Lightroom Performance Helper.app**, inside the installation directory:

- **System Settings → Privacy & Security → Accessibility:** allow the helper to inspect/click the one configured Scripts menu item.
- **System Settings → Privacy & Security → Automation:** allow the helper to control **System Events** when macOS requests it. The helper uses System Events to address the exact Classic PID; it does not require a Terminal-wide automation grant or direct Adobe app Apple-event automation.

The helper can bring that exact Classic process to the foreground to select the menu. It checks bundle ID, PID, configured catalog window, one unique enabled menu target, nonce and expiry. The permission prompt itself may require a deliberate first helper launch after you enable startup; approve the named helper, then inspect its result. A permission failure is retained, not retried automatically.

```sh
uv run --no-project python scripts/manage.py enable --accept-menu-automation
launchctl print "gui/$(id -u)/com.firstpair.lightroom.performance-startup"
uv run --no-project python scripts/manage.py verify
```

Quit Classic normally before running `enable`, then launch it normally after the command succeeds. The enabling command refuses an open Classic process, staged fixtures, altered pins, changed launch configuration and installations with no successful manual native receipt. The generated LaunchAgent is byte-pinned and must match the exact configured launcher arguments before bootstrap. Enabling also writes the explicit authorization marker for bounded in-app renewal. The agent checks every 30 seconds for one exact Classic executable/PID/start time. Native in-app maintenance renews only after pending-request and transport release gates. Inspect actual receipts after your next normal Classic restart and again after a complete drain/renewal cycle; the private control's restart receipt does not prove your installation.

## Disable and undo

```sh
uv run --no-project python scripts/manage.py disable
```

This marks the owned installation paused, removes future renewal authorization and unloads only its owned LaunchAgent. The in-app maintenance check stops future submissions when it observes that marker change. It does not cancel native requests, edit queues, pause Sync, stop intake, quit apps or reset settings. The current finite native owners retain normal cleanup; a normal Classic quit releases all connection-local TEMP objects/runtime wrappers. Remove the exact installed `FirstPair) Apply FirstPair performance fixes.lua` after Classic is closed if you want to remove the menu. Keep logs until you have verified cleanup.

The optional persistent SHA index survives quitting. This starter does not drop a catalog index externally. Revert it only through a reviewed native owner-bound schema operation or your verified catalog-family backup, with later edits/imports accounted for. Disabling runtime wrappers does not require rolling back a catalog or deleting originals.

## Reading and publication

### Physical-drive catalog shuttle

The separate [Unison shuttle guide](docs/SHUTTLE.md) documents
`scripts/shuttle.py`: a closed Main catalog can move between two Mac SSDs through
one UUID-guarded portable volume, while each Mac retains its own host/root/tier
archives. Only one Mac owns the working catalog at a time; normally quit Main
and finish its writes before each transport, then verify and accept ownership
on the receiver before opening it or resuming cloud Sync.
The `full` tier copies the selected catalog folder including Backups and both
preview packages; `main-core` keeps the catalog, Sync, Helper and standard
Previews on a smaller SSD, with an explicitly declared Photo-resident Smart
Previews link. Neither tier copies the entire Lightroom parent or diagnostics.

It requires a pinned Unison executable and stable Classic 15.6, preserves a
coherent previous critical family using independent APFS clones, and holds
ownership until a separately produced complete critical-file SHA receipt is
accepted. The independent production verifier is not bundled: the illustrated
receipt schema must be populated by actual full closed-file verification,
not operator assurances. Routine conflicts remain held, with no blind retry,
automatic owner reset or catalog merge. The guide explains normal ownership
return and manual recovery of a coherent preserved family.

This source has synthetic tests and small native Unison 2.54 transport tests;
the large production handoff is still awaiting completion. Those controls do
not certify another catalog's startup, original media or cloud convergence.
The public revision also rejects standard Previews symlink declarations;
that guard correction has regression coverage, with production qualification pending.
It does not install a launch gate, start Lightroom or execute catalog SQL.
The first baseline may spend hours fingerprinting existing previews; later
`fastcheck` reuse depends on each host retaining its own archives and valid
native file stamps. A device-number change alone is not a content-change check
in the reviewed Unison source; actual Mac-to-Mac reuse remains to be measured.

```sh
uv run --no-project python scripts/shuttle.py --help
```

All configuration, UUIDs, host paths, binary pins, archives, journals and receipts
belong in private locations outside the synchronized roots and public repo. Read
the guide before preparing a configuration or executing a handoff.

- [Start here: HOWTO](HOWTO.md)
- [Reusable repair cookbook](docs/firstpair-lightroom-repair.md)
- [Lightroom Queen announcement draft](docs/announcing-firstpair-lightroom-repair.md)
- [Published story](https://firstpair.press/lightroom-repair/), [article source](docs/blog/lightroom-repair/post.md) and [TextPack handoff](docs/publication-text-pack.md).

Private experience includes successfully preserved native repairs and offline preview controls. Matching fingerprints, rendered previews, requested XMP byte identity, native settings adoption, current editing readiness and cloud convergence remain separate claims. The cookbook states each recipe's evidence and remaining holds.

## License

Our authored code and documentation use the [MIT License](LICENSE). Adobe implementation modules are imported from the installed application, are not included here, and are not covered by this license.
