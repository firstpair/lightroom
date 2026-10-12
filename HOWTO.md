# FirstPair Lightroom repair: how to start

Start with the problem you can reproduce: a missing original, a stalled import, repeated Sync work, or a preview whose settings will not load. The [repair cookbook](docs/firstpair-lightroom-repair.md) gives complete recipes. This page gets you from that symptom to a small, verifiable first action.

## 1. Keep a recovery copy

Back up your catalog and originals. For the advanced native tools, also preserve the closed `.lrcat`/WAL/SHM family, `.lrcat-data`, Sync and Helper packages. Quit Classic normally before making that closed copy, then verify it. Adobe's ordinary catalog backup does not include your photographs. [Adobe: catalog backup](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/back-catalog.html).

## 2. Use the ordinary repair when it fits

- **Missing photo or folder:** use Locate or Find Missing Folder to reconnect the existing entry and keep its edits. Check that the destination is the intended original before accepting it. [Location recipe](docs/firstpair-lightroom-repair.md#repair-locations-without-reimporting).
- **Missing Smart Preview:** select the admitted originals and use Library → Previews → Build Smart Previews. Verify availability and try the exact photo. [Preview recipe](docs/firstpair-lightroom-repair.md#verify-a-smart-preview-at-the-level-you-need).
- **Sync appears stuck:** identify the selected photos, direction and stage before retrying. Album activation, pending mappings, binary transfer and server completion are separate results. [Sync recipe](docs/firstpair-lightroom-repair.md#separate-sync-stages-and-counts).
- **Preview present, Edit waiting:** inspect the exact requested settings and required profiles/masks. Preserve edits while following the [settings recipe](docs/firstpair-lightroom-repair.md#recover-exact-settings-without-resetting-edits).

For general speed issues, begin with [Adobe's performance guidance](https://helpx.adobe.com/lightroom-classic/desktop/technical-support/performance-guidelines/optimize-performance-lightroom.html). If the symptom persists, use the cookbook's [problem table](docs/firstpair-lightroom-repair.md#choose-the-problem-before-choosing-the-repair) to choose the next observation.

## 3. Inspect the performance starter

The native reference controls used Classic 15.6 on macOS. The public successor supplies our own bounded map/copy/date and transport adapters. A new app/catalog needs its own native qualification. Affinity changes and the durable expression index are off by default; leave them off for this first run.

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```sh
git clone https://github.com/firstpair/lightroom.git
cd lightroom
uv run --no-project python -m unittest discover -s tests -v
uv run --no-project python scripts/manage.py --help
```

The repository selects the tested Python 3.14.6 through uv. Commands below run from this checkout. Use your catalog's absolute canonical path in place of the example.

## 4. Install and make one manual run

With Classic normally closed and your backup verified, inspect the dry run, then install at the new private destination:

```sh
uv run --no-project python scripts/manage.py install \
  --catalog /absolute/Example.lrcat --backup-confirmed --dry-run

uv run --no-project python scripts/manage.py install \
  --catalog /absolute/Example.lrcat --backup-confirmed
```

Installation puts the menu and private helper in place; startup remains disabled. Relaunch the intended catalog and choose **Scripts → Apply FirstPair performance fixes** once. Then inspect:

```sh
uv run --no-project python scripts/manage.py verify
```

Check the newest native callback and phase logs against [the README's acceptance steps](README.md#verify-the-manual-native-run). A missing callback is a reason to inspect that run, not to repeat the click. Successful disabled phases mean those advanced options stayed off. Keep transport startup/drain and later renewal receipts separate.

## 5. Enable renewal only after that run is accepted

Grant **FirstPair Lightroom Performance Helper.app** Accessibility access and System Events Automation access when macOS requests them. The helper lives in `~/Library/Application Support/FirstPair Lightroom`. Quit Classic normally before enabling:

```sh
uv run --no-project python scripts/manage.py enable --accept-menu-automation
```

Launch Classic normally and run `verify` again after installation and a completed drain/renewal cycle. The helper watches Classic launches and clicks the configured performance menu; it does not watch photo folders or import photographs. [Permission and lifecycle details](README.md#enable-the-startup-helper).

## 6. Stop future automation when needed

```sh
uv run --no-project python scripts/manage.py disable
```

This stops future owned dispatches. Current native requests retain their normal bounded cleanup. Keep their receipts, and use a normal Classic quit when safe. [The README](README.md#disable-and-undo) explains menu removal and the separate rollback of an optional durable index.

For folder admission, conversion/preview reuse, fingerprints or selected upload errors, follow the individual cookbook recipe. Those are separate reviewed operations; installing the performance starter does not execute them.
