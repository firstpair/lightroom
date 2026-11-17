# Recover stuck Lightroom Classic cloud uploads

Three Scripts-menu actions, all built from Lightroom's own calls. Each is generated for an explicit list of photos,
checks the active catalog (and cloud catalog where relevant), runs once per Classic process, and logs every
callback to `<run-root>/runs/`.

| Problem | Symptom in the stores | Action | Reference result |
|---|---|---|---|
| Upload failed and was never retried | `_localOnly.ozError` set (e.g. 404 `BinaryMissingError`) | `retry`: stock `clearErrorsAndRetrySync` on the listed asset IDs | 2,903 of 3,236 cleared |
| The revision refers to a develop XMP the server never received | Still 404 after retry; `develop.xmpCameraRaw` present with no `/rels/xmp/develop` link, or a placeholder `importSource.sha256` | `resave`: SDK nudge of exposure by +0.01, then the exact original value. Classic uploads a fresh XMP and re-sends the proxy | 319 of 319 synced; final settings identical, two history steps per photo |
| Pending Smart Preview upload points to a volume that is gone (catalog moved to another disk or Mac) | `needsBinaryUpload` proxy row with `fileMaybeOnOfflineVolume=1` | `proxy`: proxy-only `setOriginalAndProxyInfo` with `{proxyFilePath, proxyFileSize}`, leaving out `filePath`/`fileSize`. Native code hashes the existing file and records its current path | 18 of 18 uploaded within about 45 s; 2,565 already-synced records repointed with 0 uploads |

**Do not rebuild Smart Previews to unstick an upload.** A rebuilt preview has a new SHA, and Classic re-sends a proxy
only when the local SHA equals `importSource.proxySHA256`.

## Use

1. Find the IDs, read-only. For proxies:
   ```sh
   uv run --no-project --with msgpack python classic/sync-recovery/preflight_proxy.py \
     --sync-store "/path/My Catalog Sync.lrdata/<cloud catalog id>" \
     --smart-previews "/path/My Catalog Smart Previews.lrdata" --out proxies.json
   ```
   Rows are only `ok` when:
   - the local file exists;
   - its SHA-256 and size equal both the recorded spec and the cloud's `proxySHA256`;
   - the document is not deleted;
   - it has no C2PA ingredients.

   `--volume-guid G --synced-only` lists already-synced records on a missing volume. Repointing them uploads nothing.
2. Render, for example: `uv run --no-project --with lupa python classic/sync-recovery/render.py proxy --items proxies.json
   --catalog "/path/My Catalog.lrcat" --cloud-catalog <id> --run-root /path/logs --out "<Scripts>/03) Sync recovery.lua"`.
3. Try 1–5 items first, check the result in the stores (error cleared, revision on server, no row in
   `needsBinaryUpload`), then run the rest in batches.
4. Remove the Scripts-menu file when you are done.

**Limits:**
- Checked with Classic 16.0 on macOS. These use private Lightroom modules, which may change between versions.
- The proxy action creates a new, server-accepted metadata revision for some photos. No binary is re-sent.
