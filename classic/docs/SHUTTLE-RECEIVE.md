# Receive a shuttled catalog before opening it

For the Mac that receives a Lightroom Classic catalog carried on a portable
volume. The sending Mac closed the catalog, copied the catalog folder to the
volume and compared every file by SHA-256. This Mac still holds an older copy.
Do these steps before Classic opens anything.

This is the plain-copy route. It uses `classic/scripts/shuttle_receive.sh` and does not
use the guarded `classic/scripts/shuttle.py` of [SHUTTLE.md](SHUTTLE.md), its Unison
archives or its owner marker. See "Limits" for what that leaves unchecked.

## What travels

| Item | Copied |
|---|---|
| `NAME.lrcat` | yes |
| `NAME.lrcat-data` | yes |
| `NAME Helper.lrdata` | yes |
| `NAME Sync.lrdata` | yes |
| `NAME Previews.lrdata`, `NAME Smart Previews.lrdata` | no; this Mac keeps its own |
| Backups, original photos, plug-ins, preferences | no |

The copy on the volume replaces this Mac's catalog as a whole. It is not a
merge.

## Before copying

1. **Check for work done here since this Mac last sent the catalog out.** Any
   edit, rating, keyword, import or collection change made in this Mac's copy
   after that point is not in the arriving catalog. If there is any, stop and
   decide which catalog continues; the two cannot be combined by copying.
2. **Quit Classic on both Macs.** Only one copy may be open at a time, because
   both share one cloud identity. The sending Mac's copy stays closed from now
   on, or is opened only with its network blocked and syncing paused.
3. **Skip the Back Up Catalog prompt** when quitting.
4. Attach the volume and get this repository's current `main`.

## Copy and compare

Replace the three values. `SRC` is the catalog folder on the volume, `DST` the
catalog folder on this Mac, `NAME` the catalog name without `.lrcat`.

```sh
SRC="/Volumes/PORTABLE/Lightroom/NAME"
DST="/path/on/this/Mac/Lightroom/NAME"
NAME="NAME"

classic/scripts/shuttle_receive.sh check "$SRC" "$DST" "$NAME"
classic/scripts/shuttle_receive.sh copy  "$SRC" "$DST" "$NAME"
```

`check` changes nothing. It stops if Classic is running, if either catalog has a
`.lock` file, if either has a write-ahead log or journal with content, or if
this Mac's catalog file is open.

`copy` runs the same checks and then:

1. Confirms the copy fits with 10 GB to spare.
2. Moves this Mac's older catalog items, with any leftover `-wal`, `-shm`,
   `-journal` or `.lock` file, into `NAME-before-<date>-<time>` beside the
   catalog folder. It deletes nothing. Previews stay in place.
3. Copies the four items from the volume.
4. Reads both copies in full and compares SHA-256 for every file.

Expected last lines:

```
N files compared, 0 differ
received. Open …/NAME.lrcat only after the steps in classic/docs/SHUTTLE-RECEIVE.md
```

If it prints `DIFFERENT` or `STOP`, do not open the catalog. The older copy is
intact in the set-aside folder. `classic/scripts/shuttle_receive.sh verify` repeats the
comparison alone.

## Before opening

- [ ] The comparison ended with "0 differ".
- [ ] No `NAME.lrcat-wal`, `-shm`, `-journal` or `.lock` sits beside the new
      catalog.
- [ ] The portable volume stays attached if it holds the originals.
- [ ] Plug-ins the catalog expects are installed on this Mac. They do not
      travel with the catalog.
- [ ] To read the catalog with SQLite beforehand, use `immutable=1` or a copy.
      A read with `mode=ro` creates `-wal` and `-shm` files.

## Opening

1. Launch the release build on the received catalog by path, not by name:

   ```sh
   open -a "/Applications/Adobe Lightroom Classic/Adobe Lightroom Classic.app" "$DST/$NAME.lrcat"
   ```

2. Confirm the title bar shows the received catalog, not a default or recent
   one.
3. Check a folder that was changed on the sending Mac, and one collection made
   there.
4. Folders on volumes that are not attached to this Mac show as missing. That
   is expected; do not remove or relink them here.
5. Open the cloud icon and confirm this is the catalog that syncs, then let
   syncing resume. The sending Mac must not sync from now on.
6. Previews: Classic reuses this Mac's existing preview cache for photos that
   did not change and renders again for the ones that did. This is expected
   behaviour and was not measured for this handoff.

## Afterwards

- Keep the `NAME-before-…` folder until the received catalog has been used and
  quit cleanly at least once. Then it can be deleted by hand.
- The copy on the volume is now the older one. Before the next trip back,
  set it aside or remove it; the sending script refuses to overwrite it.

## Limits

- The script proves the bytes on this Mac equal the bytes on the volume. It
  does not prove the catalog opens, that the database is sound or that the
  cloud agrees.
- It does not detect that this Mac's copy was edited after the last handoff.
  That is step 1, and it is a human check.
- It does not read or update the owner marker of `classic/scripts/shuttle.py`. If a
  marker exists on the volume from an earlier guarded run, it still names its
  earlier owner. Do not edit it by hand; treat it as stale for this handoff and
  rely on the rule that only one copy is open.
- It does not prevent anyone from opening the older copy later. Only the
  set-aside rename does, on this Mac.
- Tested on a synthetic catalog folder only: checks, set-aside, copy,
  comparison, a deliberate mismatch and a `.lock` refusal.
