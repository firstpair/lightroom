# Lightroom Classic 16.0 runtime fixes

One Scripts-menu action, `APPLY16.lua`, installs three fixes in the running Classic 16.0 process. All three are
runtime-only: they last until Classic quits, so run the action after each launch. They were run natively on a large
(about 800,000-photo, fully synced) catalog in November 2026. Every phase compared its result against Lightroom's own code
path and found 0 mismatches.

| Phase | What it changes | Measured on the reference catalog |
|---|---|---|
| `trigger` | In the two TEMP triggers `trigger_AgLibraryImageChangeCounter_update_for_fileModification` and `…_update_for_fileRename`, only the DELETE subquery `SELECT id_local` becomes `SELECT +id_local`, so SQLite seeks the `(image, payloadKey)` index instead of scanning `AgLibraryImageSyncedAssetData` | 7–39 s per DELETE → under 1 ms. Folder moves, relinks and Smart Preview builds stop stalling |
| `point` | `isImageIdTracked` answered by one indexed row instead of rebuilding the full image→asset map | 49 lookups: 9.4 s → 0.002 s |
| `mapcount` | The tracked image map and its `COUNT(*)` are kept incrementally from a TEMP change journal; returned maps are copied with the built-in C `table.shallowcopy` | Main database time 59.5 s → 3.4 s per 90 s; Smart Preview building resumed from 0 to about 105 per minute |

Each phase first checks that it is talking to the Main writer of the expected catalog and that the live SQL equals the
stock 16.0 text. If anything differs, it changes nothing. It is idempotent, compares its own answers against Lightroom's
original code on a schedule (first calls plus every Nth), and restores the original when it reaches its bounds
(6 h terms, renewed up to 8 times while clean).

**Busy-catalog install (v3).** While Classic is busy, it cannot open a savepoint ("statements in progress"). v2 then
returned `WAIT_TRANSACTION` forever, which left Classic without the fixes exactly when it needed them. v3 installs anyway
in autocommit and touches only TEMP objects:
- `trigger`: if the corrected CREATE fails, it recreates the original trigger.
- `mapcount`: if creation fails partway, it drops its TEMP objects.
- If the body finished but Classic's RELEASE then errors, it is treated as installed.

## Build and install

```sh
uv run --no-project --with lupa python classic/lrc16/build.py \
  --catalog "/absolute/path/My Catalog.lrcat" \
  --run-root "/absolute/path/lrc16-logs" \
  --out "$HOME/Library/Application Support/Adobe/Lightroom/Scripts/02) Apply performance fixes.lua"
```

The builder compiles the outer script and every embedded body with Lua 5.1 before writing. Restart Classic once so the
Scripts menu lists the new file. After that, choose **Scripts → Apply performance fixes** after each launch and read
`<run-root>/runs/run-<time>/native.txt`. Each phase reports `true`, `ALREADY_ACTIVE` or a reason it changed nothing.
To automate this, adapt the 15.6 startup watcher in this repository (`classic/scripts/manage.py`) so that it clicks
once per launch and backs off on any `WAIT_*` answer.

**Undo:** quit Classic. Every change is TEMP or in-memory.

**Limits:**
- Checked against Classic 16.0 on macOS only. Any other version fails closed on the SQL text check.
- This is not an Adobe-supported fix. See [../../docs/ADOBE-ENGINEERS.md](../../docs/ADOBE-ENGINEERS.md) for the
  durable product changes.
