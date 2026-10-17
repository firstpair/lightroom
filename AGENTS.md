# Working on FirstPair Lightroom repair

This repository contains authored repair wrappers and reusable documentation.
The reference investigation's private `Adobe.md` is an evidence log, not a
distributable catalog or a completion receipt.

- Continue Photo/preview development from this checkout. Follow
  `docs/development-layout.md`; the detailed local handoff and unpromoted
  investigation are under ignored `.private/photo/`. Historical compatibility
  paths are not a second source repository. Keep private receipts and
  machine-bound source out of Git; promote reviewed portable components into
  `scripts/preview_pipeline/` with original synthetic tests.

- Keep `docs/firstpair-lightroom-repair.md` organized by symptoms and recipes.
  Update its prerequisites, mechanism, verification, undo and limits when a
  finding changes what another operator should do. Put dated publication prose
  in the blog, not in the cookbook's instructions.
- Distinguish source review, synthetic tests, native installation, native
  completion, persisted verification, offline editing and server convergence.
  Never promote a prepared batch or a private predecessor's result into public
  runtime qualification.
- Preserve original files, edits, history, virtual copies and cloud identities.
  Use Lightroom's own writer/session for live changes. Never write externally
  to an open catalog or forge Sync acknowledgements, revisions or flags.
- Keep method, transaction, dependency and cleanup ownership guards. On a
  mismatch, retain evidence and fall back or hold; do not overwrite a foreign
  owner, repeat a pending request or weaken a guard to admit another version.
- Do not commit catalogs, media, credentials, signed URLs, personal paths,
  catalog/cloud identifiers, generated private receipts, Adobe bytecode or
  decompiled Adobe module bodies.
- Use `uv` for Python. Run `uv run --no-project python -m unittest discover -s
  tests -v` for installer/runtime-template changes. Parser and fixture tests
  do not replace native qualification.
- Keep the README's CLI, permission steps, defaults and restoration instructions
  aligned with the implementation. Verify rendered dependency paths and byte
  pins when changing runtime templates.
- Blog source lives in `docs/blog/lightroom-repair/post.md`. Build
  TextPacks from committed, pushed inputs with the documented FirstPair
  workflow, then commit and push the generated handoff. Preparing a post does
  not authorize posting it to a forum or blog.
- Cookbook publication follows [FIRSTPAIR.md](FIRSTPAIR.md) and the shared
  `~/src/firstpair/AGENTS.md`. Build from clean, pushed source, verify PDF,
  EPUB and both HTML readers, then publish only this title's artifacts and
  retain the generated FirstPair manifests in the same committed session.
