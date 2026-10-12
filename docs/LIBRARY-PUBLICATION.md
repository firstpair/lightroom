# First Pair library publication

The full cookbook edition **1.0.0-ca28ff6b** was published on 2026-10-12.
Its manuscript and build inputs are bound to source commit
`ca28ff6bcb64e9776eeeb579e6d4d0d60d4dad1f`; reviewed artifacts were committed
separately. Later documentation changes do not imply a new artifact build.

- [Library entry](https://firstpair.org/books/lightroom-repair/)
- [PDF](https://firstpair.org/lightroom-repair/pdf/)
- [EPUB](https://firstpair.org/lightroom-repair/epub/)
- [HTML reader](https://firstpair.org/read/lightroom-repair/)
- [Chapter reader](https://firstpair.org/read/lightroom-repair/chapters/)
- [HOWTO](../HOWTO.md)

All 29 manuscript sections were independently checked against the EPUB and
both HTML editions. The 22-page PDF was rendered and visually reviewed;
its destinations and the EPUB's local links resolve. The supplied cover
is unchanged in the EPUB, HTML, TextPack and uploaded cover/headboard.
The artifact hashes and detailed checks are in
[BUILD-VALIDATION.json](../dist/BUILD-VALIDATION.json).

The FirstPair publisher passed clean/pushed source and library preflights,
uploaded only this title, and delivered versioned PDF/EPUB regular files to
iCloud Books. Exact comparisons passed. The catalog validator, production
build and full 36-title local smoke check passed. After production deployment,
the live catalog matched the committed entry, PDF/EPUB downloads returned
HTTP 200 and the exact artifact SHA-256 values, and both HTML readers rendered
inline with library navigation. The live book page's four format and source
links were independently checked. All 35 preexisting catalog entries remained
unchanged. Publication manifests were committed and pushed in the same session.

For this first release, upload and checks used `library:publish --no-deploy`,
then the owned library metadata was committed/pushed before an ordinary
`vercel deploy --prod --yes`. Use [FIRSTPAIR.md](../FIRSTPAIR.md) for the full
source/build/publication contract. Do not re-upload unchanged artifacts for
a catalog-only link or description update.

The [story source and TextPack](blog/lightroom-repair/post.md) use slug
`lightroom-repair`, targeting `https://firstpair.press/lightroom-repair/`.
The stamped pack is committed, pushed and delivered to iCloud Blogs. Ghost
posting is a separate action; a library Story link should be enabled once
the canonical post is published and verified. The
[forum announcement](announcing-firstpair-lightroom-repair.md) remains a draft.

These publication checks do not qualify the public runtime adapters in a native
Lightroom session. Follow the manual acceptance steps before enabling the
startup helper; affinity and the durable schema index remain off by default.
