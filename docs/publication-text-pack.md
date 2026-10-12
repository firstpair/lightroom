# Lightroom repair publication handoff

Repository: [firstpair/lightroom](https://github.com/firstpair/lightroom)

The canonical article is [docs/blog/lightroom-repair/post.md](blog/lightroom-repair/post.md). It follows the actual FirstPair source and TextPack conventions inspected in `publishing/skills/blog-textpack-delivery.md` and `publishing/scripts/textpack.py`: a committed and pushed source, deterministic zipped TextBundle payload, Ghost routing metadata, a complete source commit and a payload SHA. The current FirstPair posts route to `firstpair.press`; the builder's unrelated default domain must be overridden explicitly.

No forum, blog or iCloud delivery has been performed. GitHub source publication is a separate authorized handoff. The operator's cover is [lightroom-halfdome.png](../cover/lightroom-halfdome.png), referenced by the canonical post and bundled byte-for-byte into its TextPack.

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

After the finished article and any actual cover asset have been reviewed, committed and pushed, require the owning repository to be clean and exactly at its remote upstream. Use the current FirstPair stamper from the Lightroom repository root:

```sh
REPO_ROOT="$PWD" \
BLOG_DOMAIN=firstpair.press \
BLOG_TAGS=lightroom,photography,recovery,sqlite,open-source \
BLOG_EXCERPT='After years of stalled imports, a large Lightroom catalog handled an ordinary October card quickly. The reusable repairs preserve existing edits and separate indexed performance, previews, settings and Sync outcomes.' \
/Users/your-name/src/firstpair/publishing/scripts/stamp-versioned-blog.sh \
  docs/blog/lightroom-repair
```

Replace the example checkout path with the actual FirstPair tooling location; use the tested Python runtime. The builder enforces pushed source provenance and does not commit, push or post. Its output belongs in this article's `dist/` directory: the stable `.textpack`, a source-hash versioned link, and `VERSION.md`. Keep the zipped pack, not an unpacked `.textbundle`.

Commit and push generated artifacts only after inspecting their ZIP integrity, exact Markdown, routing metadata, full provenance and real bundled cover bytes if present. Delivery to a blog or iCloud requires its own explicit instruction and is outside this preparation.

## Forum copy

Use [announcing-firstpair-lightroom-repair.md](announcing-firstpair-lightroom-repair.md), including its moderator-category editorial note. Confirm repository and cookbook links against the actual published branch before posting.
