# First Pair library publication

The full cookbook edition **1.0.0-ca28ff6b** was published on 2026-10-12.
Its manuscript and build inputs are bound to source commit
`ca28ff6bcb64e9776eeeb579e6d4d0d60d4dad1f`; reviewed artifacts were committed
separately. Later documentation changes do not imply a new artifact build.

- [Library entry](https://firstpair.org/books/lightroom-repair/)
- [Story](https://firstpair.press/lightroom-repair/)
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

The operator published the [story](https://firstpair.press/lightroom-repair/)
from Obsidian through Omnighost on 2026-10-12. The live canonical URL returned
HTTP 200 with the exact title, “Making Lightroom usable again after years of
stalled imports,” all seven source section headings and the hosted cover.
Its Omnighost HTML metadata records publication SHA
`1de3adc1b0f2308b3c9f842664c4c14963f77d2f5831a8e5e849cb0c33bda550`.
The [article source and stamped TextPack](blog/lightroom-repair/post.md)
remain unchanged; their verified source commit is a separate
handoff property, not a source-commit tag observed in the live HTML.
The [forum announcement](announcing-firstpair-lightroom-repair.md) remains
a draft. The catalog-only Story link was committed and pushed in FirstPair
`64d8ca1`, then deployed to production. The live catalog matches that commit;
the book page and expanded Technology shelf both show the canonical Story
link. Catalog validation, production build and the full 36-title smoke check
passed. All 35 other entries and the existing cookbook artifact fields remain
unchanged. No cookbook artifacts were rebuilt or re-uploaded. The story’s
hosted cover has the exact supplied SHA-256
`0189f72c3b5edbd02cb873867c1bfccb9ce30604c0dc85cf5d0e83b64682aa3c`.

These publication checks do not qualify the public runtime adapters in a native
Lightroom session. Follow the manual acceptance steps before enabling the
startup helper; affinity and the durable schema index remain off by default.
