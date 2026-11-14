# FirstPair Lightroom repair

Tools, measurements and a [repair cookbook](docs/firstpair-lightroom-repair.md) from recovering a very large
Lightroom setup on macOS: an 868,000-photo cloud library, a Lightroom Classic catalog of the same size, and the
Lightroom (Cloud) desktop app. Public source: <https://github.com/firstpair/lightroom>.

The repository has two halves:

| Folder | For | Highlights |
|---|---|---|
| [`classic/`](classic/README.md) | **Lightroom Classic** | Performance installer for slow Sync work on huge catalogs, physical-drive catalog shuttle, runtime templates |
| [`cloud/`](cloud/README.md) | **Lightroom (Cloud)**, the app named "Adobe Lightroom" | Indexes re-added safely at every launch, full Smart Preview download with outage backoff, sync status decoding, Smart Preview reuse, C2PA auxiliary recovery |

Shared material stays here:

- [Repair cookbook](docs/firstpair-lightroom-repair.md), organized by symptom, also published in the
  [First Pair library](https://firstpair.org/books/lightroom-repair/) as
  [PDF](https://firstpair.org/lightroom-repair/pdf/), [EPUB](https://firstpair.org/lightroom-repair/epub/)
  and [HTML](https://firstpair.org/read/lightroom-repair/).
- [Story of the repairs](https://firstpair.press/lightroom-repair/) ([source](docs/blog/lightroom-repair/post.md)).
- [Publication and verification](docs/LIBRARY-PUBLICATION.md).

Nothing here is supported by Adobe. No catalog, photo, preview, credential, private diagnostic tree or Adobe code
is included. Each folder's README says what its code changes, how it was tested and how to undo it. Back up first
and read the code before running anything.

## Test

```sh
uv run --no-project python -m unittest discover -s classic/tests -v
uv run --no-project --with lupa python -m unittest discover -s cloud/tests -v
```

## License

Our authored code and documentation use the [MIT License](LICENSE). Adobe implementation modules are imported
from the installed applications, are not included here, and are not covered by this license.
