# Downloading every Smart Preview into Lightroom (Cloud)

Lightroom (Cloud) can keep a 2560-pixel Smart Preview of every photo on the Mac, so you can edit offline
without downloading originals. Turning on "Store a copy of all Smart Previews locally" asks Lightroom to fetch
them in the background, but on a large library that can take days and stalls easily. The controller here asks
Lightroom directly, in parallel batches, and survives network outages.

It uses only Lightroom's ordinary `getProxyPaths` request, the same one the app uses when it needs a preview.
Lightroom downloads its own server preview and registers it. Originals are not downloaded.

## Files

- [`cloud/scripts/preview_fetch/prepare.py`](../scripts/preview_fetch/prepare.py): builds the list of photos
  without a local Smart Preview, holds the ones that can't be downloaded, and renders the menu script.
- [`cloud/scripts/preview_fetch/template.lua`](../scripts/preview_fetch/template.lua): the controller that runs
  inside Lightroom.
- [`cloud/tests/test_preview_fetch.py`](../tests/test_preview_fetch.py): 12 simulated controls (normal run,
  2-hour outage, permanent refusals, STOP, Sync paused, no replay). They run under Lua 5.1 with lupa, not in
  Lightroom.

## How to run it

1. Quit Lightroom (Cloud) and prepare a run:

   ```sh
   uv run --no-project python cloud/scripts/preview_fetch/prepare.py \
     --library "$HOME/Pictures/Lightroom Library.lrlibrary/<catalog-id>" --out runs/fetch-1
   ```

   Pass `--previous runs/fetch-0` to hold photos an earlier run saw refused.
2. Copy `runs/fetch-1/script.lua` over a script that already appears in Lightroom's Scripts menu, in
   `~/Library/Application Support/Adobe/Lightroom CC/Scripts/`. Lightroom lists the scripts present when it
   launches and reads a script's contents when you choose it, so add a placeholder file before launching.
3. Open Lightroom, leave Sync running, and choose the script from the Scripts menu within an hour. A second
   choice is refused, because each run can be entered only once.
4. Watch `runs/fetch-1/PROGRESS.json` and `EVENTS.txt`. Count progress by the photos still missing a preview,
   not by the run's own counter (Lightroom keeps downloading on its own too):

   ```sql
   SELECT count(*) FROM localStatusAndOzStatus
   WHERE subtype='image' AND isVersionDocument=0 AND hasLocalProxy=0;
   ```

5. To stop, create `runs/fetch-1/STOP.json`. Requests already in flight finish normally. Leave Lightroom open
   while it runs; quitting the app ends the run.

## What it does when things go wrong

- **Sync paused:** it admits nothing while your Sync is paused and resumes when you resume Sync.
- **Outages:** a batch that comes back with no previews and mostly `CannotSyncDownloadToFileError` means
  Lightroom lost its connection. The controller stops admitting work, waits 2 minutes (doubling up to 15), then
  probes with a single batch before going back to full speed.
- **Retries:** photos refused with `CannotSync…` or `Transient…` are retried after 10 minutes, up to 8 times.
- **Final refusals:** `SendNoDownloadableOriginal` is never retried. It is decided from the photo's own record,
  for example an upload that never finished; see [CLOUD-SYNC-STATUS.md](CLOUD-SYNC-STATUS.md).

Before the backoff existed, a 2-hour outage made the controller burn through about 58,000 photos with
`CannotSync` refusals in minutes. With it, a 45-minute outage cost 524 refusals, all of which succeeded on retry.

## Measured

On an 868,000-photo library in China, with a direct connection to Adobe:

- **Final run:** 87,257 photos, all downloaded, and the 529 refused during an outage succeeded on retry. It
  finished overnight with no errors.
- **Rate:** 165–490 previews a minute between outages, and about 1.3 MB of disk per preview.
- **Left over:** 45 photos refused as "no downloadable original" and about 1,200 records with nothing to
  download (phone/iCloud placeholders).

**HTTP concurrency:** Lightroom's default budget allows 5 preview downloads at once. A `config.lua` in
`~/Library/Application Support/Adobe/Lightroom CC/` with `Nimbus.maxNumSimultaneousHttpRequests = 20` doubled that
to 10 (each preview costs 2), confirmed by Lightroom's own diagnostics. Throughput rose only about 20% over a
6-hour comparison, because this network was the limit.

## Watching disk space

Each preview takes about 1.3 MB. A simple watchdog that creates `STOP.json` below a free-space floor keeps a
long run from filling the disk:

```sh
while sleep 60; do
  free=$(df -g / | awk 'NR==2{print $4}')
  [ "$free" -lt 20 ] && echo '{"reason":"disk floor"}' > runs/fetch-1/STOP.json && break
done
```
