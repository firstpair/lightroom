# Lightroom repair publication handoff

Repository: [firstpair/lightroom](https://github.com/firstpair/lightroom)

The canonical article is [docs/blog/lightroom-repair/post.md](blog/lightroom-repair/post.md). It follows the actual FirstPair source and TextPack conventions inspected in `publishing/skills/blog-textpack-delivery.md` and `publishing/scripts/textpack.py`: a committed and pushed source, deterministic zipped TextBundle payload, Ghost routing metadata, a complete source commit and a payload SHA. The current FirstPair posts route to `firstpair.press`; the builder's unrelated default domain must be overridden explicitly.

The source is published on GitHub. The FirstPair workflow delivers the stamped, committed and pushed TextPack to `~/icloud/blogs` with a byte comparison; that file delivery does not publish a Ghost story or forum post. The operator's cover is [lightroom-halfdome.png](../cover/lightroom-halfdome.png), referenced by the canonical post and bundled byte-for-byte into its TextPack.

| Field | Prepared value |
| --- | --- |
| Title | Making Lightroom usable again after years of stalled imports |
| Slug | lightroom-repair |
| Date | 2026-10-12 |
| Author | First Pair Press |
| Blog routing domain | firstpair.press |
| Tags | lightroom, photography, recovery, sqlite, open-source |
| Excerpt | After years of stalled imports, a large Lightroom catalog handled an ordinary October card quickly. The reusable repairs preserve existing edits and separate indexed performance, previews, settings and Sync outcomes. |
| Status | Prepared article; no blog publication |

## TextPack stamping

After the finished article and any actual cover asset have been reviewed, committed and pushed, require the owning repository to be clean and exactly at its remote upstream. Use the current FirstPair stamper from the Lightroom repository root, with its `python3` selected from the tested uv-managed interpreter directory:

```sh
uv run --no-project python - <<'PY'
from pathlib import Path
import os, subprocess, sys
scripts = Path.home() / 'src/firstpair/publishing/scripts'
env = dict(os.environ)
env.update(
    PATH=str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', ''),
    REPO_ROOT=str(Path.cwd()),
    BLOG_DOMAIN='firstpair.press', BLOG_SLUG='lightroom-repair',
    BLOG_VERSION='1.0.0',
    BLOG_TAGS='lightroom,photography,recovery,sqlite,open-source',
    BLOG_EXCERPT='After years of stalled imports, a large Lightroom catalog handled an ordinary October card quickly. The reusable repairs preserve existing edits and separate indexed performance, previews, settings and Sync outcomes.',
)
subprocess.run(['bash', str(scripts / 'stamp-versioned-blog.sh'),
                'docs/blog/lightroom-repair'], env=env, check=True)
PY
```

Set `scripts` to your actual FirstPair tooling checkout. Use the same uv-managed environment for the delivery script after the generated handoff has been committed and pushed. The builder enforces pushed source provenance and does not commit, push or post. Its output belongs in this article's `dist/` directory: the stable `.textpack`, a source-hash versioned link, and `VERSION.md`. Keep the zipped pack, not an unpacked `.textbundle`.

Commit and push generated artifacts only after inspecting their ZIP integrity, exact Markdown, routing metadata, full provenance and bundled cover bytes. Then run FirstPair's `publish-versioned-blog.sh docs/blog/lightroom-repair` against the clean, pushed repository. Its normal destination is `~/icloud/blogs`, and it requires the tracked stable pack, versioned link and marker before copying and verifying with `cmp`. This delivery is part of the documented FirstPair workflow; it does not post the story to Ghost or the forum.

## Verified stamped handoff

The actual edition 1.0.0 pack is [lightroom-repair.textpack](blog/lightroom-repair/dist/lightroom-repair.textpack), with its [version marker](blog/lightroom-repair/dist/VERSION.md). The versioned handoff is `lightroom-repair (1.0.0-ba02f1).textpack`. It contains the exact article and supplied cover, routes to `firstpair.press` / `lightroom-repair`, and embeds the full [pushed source commit](https://github.com/firstpair/lightroom/commit/ba02f11ff29e1e1c7bc320e5bfd6cb79cde2f297) plus a portable payload SHA. ZIP integrity, cover bytes, source ancestry and version-link target were verified locally before the artifact commit.

## Forum copy

Use [announcing-firstpair-lightroom-repair.md](announcing-firstpair-lightroom-repair.md), including its moderator-category editorial note. Confirm repository and cookbook links against the actual published branch before posting.
