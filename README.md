# FirstPair Lightroom repair

Tools, measurements and a [repair cookbook](docs/firstpair-lightroom-repair.md) from recovering a very large
Lightroom setup on macOS: an 868,000-photo cloud library, a Lightroom Classic catalog of the same size, and the
Lightroom (Cloud) desktop app. Public source: <https://github.com/firstpair/lightroom>.

The repository has two halves:

| Folder | For | Highlights |
|---|---|---|
| [`classic/`](classic/README.md) | **Lightroom Classic** | Performance installer for slow Sync work on huge catalogs, [Classic 16.0 runtime fixes](classic/lrc16/README.md), [stuck-upload recovery](classic/sync-recovery/README.md), physical-drive catalog shuttle, runtime templates |
| [`cloud/`](cloud/README.md) | **Lightroom (Cloud)**, the app named "Adobe Lightroom" | Indexes re-added safely at every launch, full Smart Preview download with outage backoff, sync status decoding, Smart Preview reuse, C2PA auxiliary recovery |

Shared material stays here:

- [Repair cookbook](docs/firstpair-lightroom-repair.md), organized by symptom, also published in the
  [First Pair library](https://firstpair.org/books/lightroom-repair/) as
  [PDF](https://firstpair.org/lightroom-repair/pdf/), [EPUB](https://firstpair.org/lightroom-repair/epub/)
  and [HTML](https://firstpair.org/read/lightroom-repair/).
- [Story of the repairs](https://firstpair.press/lightroom-repair/) ([source](docs/blog/lightroom-repair/post.md)).
- [Publication and verification](docs/LIBRARY-PUBLICATION.md).

Development also includes reviewed Classic preview-pipeline components under
[`classic/scripts/preview_pipeline/`](classic/scripts/preview_pipeline/). See
[development layout](docs/development-layout.md) and [OPUS-HANDOFF.md](OPUS-HANDOFF.md).
Local operational investigations belong in the ignored `.private/` workspace, never in
public commits. These components do not yet constitute a portable native preview
generator or a completed catalog takeover.

Nothing here is supported by Adobe. No catalog, photo, preview, credential, private diagnostic tree or Adobe code
is included. Each folder's README says what its code changes, how it was tested and how to undo it. Back up first
and read the code before running anything.

For Adobe engineers, [docs/ADOBE-ENGINEERS.md](docs/ADOBE-ENGINEERS.md) lists each product defect with the fix that worked and how it was measured.

## Test

```sh
uv run --no-project python -m unittest discover -s classic/tests -v
uv run --no-project --with lupa python -m unittest discover -s cloud/tests -v
```

## License

Our authored code and documentation use the [MIT License](LICENSE). Adobe implementation modules are imported
from the installed applications, are not included here, and are not covered by this license.
