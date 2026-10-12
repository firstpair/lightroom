slug: lightroom-repair
shelf: technology
default_edition: full

# FirstPair publication contract

## Ownership

This repository owns the cookbook in `docs/firstpair-lightroom-repair.md`, its authored code, the unchanged supplied cover in `cover/lightroom-halfdome.png`, `book.build.json`, `docs/book/`, and the built `dist/` package and version manifest. The source is public at <https://github.com/firstpair/lightroom>. FirstPair owns the catalog entry, stable reader/download routes, upload manifests and delivery metadata. Follow the shared rules in `~/src/firstpair/AGENTS.md`.

The cookbook and our authored wrappers are MIT licensed. Adobe implementation modules are not distributed. The full edition contains the complete public cookbook; it excludes private catalogs, media, credentials, signed links, incident asset identities and proprietary implementation bodies. Publication does not qualify the generalized runtime adapters inside another Lightroom session.

## Build

Commit and push all source changes before building a publication handoff. Verify the complete repository's clean, exact upstream state with the canonical preflight:

```sh
cd /absolute/path/to/lightroom
uv run --no-project python "$HOME/src/firstpair/publishing/scripts/git_publish_preflight.py" .
"$HOME/src/firstpair/publishing/scripts/build-library-book.sh" --repo-root "$PWD" --print-plan
"$HOME/src/firstpair/publishing/scripts/build-library-book.sh" --repo-root "$PWD"
"$HOME/src/firstpair/publishing/scripts/verify-library-book.sh" "$PWD/dist"
```

The builder verifies the shared pinned toolchain and emits PDF, EPUB, self-contained HTML, split chapters and `dist/VERSION.md`. It uses the unchanged wide artwork with `contain`; no crop or image transformation is performed. The source-link filter points exported links at the exact source commit. Inspect the latest PDF pages with Poppler, including the cover, evidence tables, commands and chapter transitions. Keep `build/` and visual-check intermediates ignored. Commit and push the reviewed `dist/` artifacts and manifest before publication.

## Publish

This title's intended edition is **full**, the complete public cookbook. Both this source repository and FirstPair must be clean and pushed before publication. Preserve unrelated FirstPair worktrees and changes. Resolve the plan before uploading:

```sh
cd "$HOME/src/firstpair"
npm run library:publish -- /absolute/path/to/lightroom \
  --slug lightroom-repair --full \
  --title "FirstPair Lightroom Repair" \
  --description "A practical cookbook for preserving and repairing a large Lightroom catalog, previews and Sync." \
  --kicker "A verified repair cookbook" --tags "lightroom,photography,sqlite,repair" \
  --dry-run --no-build --no-smoke --no-deploy --no-icloud
```

After the authorized full-edition plan and artifacts are reviewed, run the same command without the dry-run suppression flags. It uploads only this book, records its catalog/routes, delivers versioned regular PDF/EPUB files to `~/icloud/books`, and verifies the deployed site. Commit and push the FirstPair metadata produced in that same publication session; an upload without its committed manifests is unfinished.

Reader-facing routes are `https://firstpair.org/lightroom-repair/pdf/`, `/lightroom-repair/epub/`, `/read/lightroom-repair/`, and `/read/lightroom-repair/chapters/`. Raw object-storage URLs belong in FirstPair manifests, not in reader-facing prose. The project story's canonical URL is `https://firstpair.press/lightroom-repair/`; its source and textpack remain in `docs/blog/lightroom-repair/`.
