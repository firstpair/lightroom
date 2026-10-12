# Lightroom Queen forum announcement draft

Suggested thread title: **FirstPair Lightroom repair: making a large catalog usable again**

For years, this Lightroom Classic catalog suffered slow or failed imports, delayed Smart Previews, missing links and recurring Sync work. After a sustained repair, its owner imported an October camera card through Classic's ordinary UI and reported fast import, preview building, hierarchy creation and collection creation. Sync resumed roughly half a minute after creating the collection. That is an operator observation, not a controlled speed benchmark, but it is the reason I am sharing the work.

The reusable parts are in [firstpair/lightroom](https://github.com/firstpair/lightroom), under the MIT license, with an extensive [repair cookbook](https://github.com/firstpair/lightroom/blob/main/docs/firstpair-lightroom-repair.md). Each recipe gives prerequisites, a procedure, verification, undo and limits.

Some of the largest actual results were:

- Repairing 14,063 existing original locations in an exact retained source-byte cohort while preserving the original catalog entries and edits.
- Importing 4,691 previously missing 2026 originals and verifying 6,760 still Smart Previews, including 6,105 newly created.
- Registering 143,046 already computed fingerprints in bounded native transactions, with an independent preservation audit.
- Recovering the final ten proxy-missing uploads through native cache setters and one normal retry, with server proxy links and independent settings retained.
- Publishing preview reuse for 473,531 asset bindings, with separate native adoption and offline controls rather than calling the whole cohort editable.

These scopes overlap and should not be added together as a “photos fixed” total. Full-resolution-original recovery and some settings/cloud work remain open.

The performance investigation found different mechanisms: a missing asset/catalog index, a native SQL-affinity mismatch scanning roughly 51 million metadata-field rows despite an existing index, repeated map construction with about 700,000 entries, defensive copies and cross-state transfers, equivalent capture-date updates, and download workers needing destination folders registered through a writer.

The public installer provides our own bounded performance adapters and lifecycle helper. The affinity and durable expression-index options start disabled pending fresh native qualification. Folder admission is a separate reviewed example. Cache publication, converter reuse and format-specific fingerprints are documented research recipes rather than automatic universal repairs. Adobe's decompiled modules are not included.

The preview evidence is deliberately specific. Two modern photos rendered and accepted Auto edits offline; exact Undo restoration was not established for the JPEG after later Sync. A 170-photo album later had complete native local-proxy recognition. Two legacy PENTAX photos rendered at Fit and 100% under denied originals/network, but editing remained blocked by Legacy Settings Update. One exact XMP was normally adopted offline with its develop body/revision preserved; bulk adoption is unfinished.

For ordinary missing links, [Adobe's Locate and Find Missing Folder workflows](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/locate-missing-photos.html) are still the right starting point. The cookbook helps identify which further stage needs repair while retaining existing edits, history and associations.

I would welcome narrowly reproducible reports, with app version, symptom and a sanitized result. The reference controls used macOS on Apple silicon, Classic 15.6 and Lightroom desktop 9.6. A new catalog or app build needs its own acceptance.

---

Editorial handoff: this is prepared copy; no forum posting has occurred. Ask the moderators which category/approval fits this project before posting. The [Lightroom Queen forum terms](https://www.lightroomqueen.com/community/help/terms/) restrict self-promotion and provide a Plugin Directory exception for badged plugin developers; do not assume this draft qualifies for that exception.
