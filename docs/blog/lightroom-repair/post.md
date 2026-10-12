---
title: "Making Lightroom usable again after years of stalled imports"
date: 2026-10-12
author: "First Pair Press"
slug: "lightroom-repair"
canonical_url: "https://firstpair.press/lightroom-repair/"
tags:
  - lightroom
  - photography
  - recovery
  - sqlite
  - open-source
---

# Making Lightroom usable again after years of stalled imports

![Illustration of Half Dome at sunset with photographs, cloud connections, a SQLite table and indexes.](../../../cover/lightroom-halfdome.png)

For years, importing into this Lightroom Classic catalog could mean a long wait, an unresponsive Library, delayed Smart Previews, and another round of Sync work that seemed to return after finishing. The photographs were still valuable. So were their edits, history, virtual copies and collections. Starting over would have abandoned the very things the catalog was meant to preserve.

After a sustained repair, the operator imported an October camera card through Classic's ordinary UI and reported fast import, Smart Preview building, folder hierarchy creation and collection creation. Sync resumed roughly half a minute after the new collection was created. That is a practical result worth sharing. It is an operator observation, not a controlled speed benchmark, and it does not mean every remaining cloud problem has disappeared.

The reusable work is now in [firstpair/lightroom](https://github.com/firstpair/lightroom): our own MIT-licensed performance helpers, a configurable installer and an extensive [repair cookbook](https://github.com/firstpair/lightroom/blob/main/docs/firstpair-lightroom-repair.md). The guide is organized around symptoms and repairs, with prerequisites, verification and undo for each one.

## The biggest gains were concrete

The early recovery repaired 14,063 existing original locations in a cohort with exact retained cloud-source byte identities, while keeping the original catalog entries and their edits. Another missing-import scope brought in 4,691 originals from 2026. Its 6,760 still-image Smart Previews included 6,105 newly built and 655 already present, with native availability and nonempty physical files verified.

Later, 143,046 already computed fingerprints were registered through 43 bounded native transactions and independently audited without decoding those originals again. Preview reuse published 473,531 Cloud asset bindings from 471,373 physical Classic previews. These are separate, sometimes overlapping scopes; they should not be summed into a new “photos fixed” total.

The final ten proxy-missing uploads also recovered through normal native cache setters and one stock retry. Each gained a server proxy link and a Main catalog association, with independent settings preserved. Lightroom represented eight as virtual copies and two as base records. A shared file does not mean the cloud records' edits should be merged.

What made those results useful was preservation. A repaired path kept its existing identity. An imported source had its own admission. A recovered upload retained its own cloud settings. A preview remained a preview, rather than becoming a substitute full-resolution original.

## Why the catalog could spend seconds on a tiny change

One bottleneck was an actually missing asset/catalog lookup index. The native lookup scanned roughly 701,000 association rows. A narrowly scoped index changed that equality lookup to an indexed search. The status callback subsequently returned much sooner in a different run, but other work was happening too, so we kept that as an observed improvement rather than a universal speed ratio.

Another problem was more surprising: a useful index already existed. A native temporary file-update trigger searched a Sync metadata table with roughly 51 million fine-grained field rows. Those were metadata fields, not 51 million photographs. An affinity mismatch between an untyped key and an integer-affinity subquery prevented the intended indexed access.

After complete numeric-key checks, selected-result equality and query-plan admission, changing only that expression recovered the existing index. A twenty-file native location-repair control then spent 0.02051 seconds total inside the location-change calls, compared with seconds per file in the preceding uncorrected batch. That measured body excludes hashing, queueing, admission and verification. It identifies a real bottleneck without claiming that all Sync became thousands of times faster.

The public package keeps that advanced correction disabled by default. It dynamically selects legitimate current controls, checks the complete global key population and requires fresh equality and plan evidence. The optional `UPPER(sha256)` expression index is also disabled by default because it changes durable schema. Both need actual current native qualification.

## Small Sync questions rebuilt a very large answer

The mapping investigation found a specific pending-state loop. A tracking lookup could reload the entire map when the requested image was absent or pending. The reload left it pending, so another lookup could reload the same map again.

The ordinary successful upload preparation asks that question once for asset information and again for develop information. With 695,483 entries in the inspected map, a still-pending image could cause about 1.39 million rows to be materialized. Assigned images, early exits and state transitions did not necessarily follow that route. We did not claim to have dynamically counted every SQL invocation in every request.

The same producer also appeared behind Library grid feedback. In one native capture, 403 grid-info events occupied 82.194 seconds of an 82.236-second interval. That helps explain why an apparently unrelated local operation could feel blocked while Sync was busy.

The remedies address separate costs: bounded incremental map/count reuse, an indexed point lookup, isolated native C copies and paired full/delta delivery to the UI. Returning the cached mutable table directly would let a consumer damage it, so complete equality and mutation-isolation controls were required. Transport acknowledgements come after the ordinary callback returns; gaps recover with a genuine native full map. Stopping future cycles leaves the current sender and decoder alive until both drain normally.

We also found format-only capture-date updates that could generate metadata work. A bounded predicate skips only a completely initialized, equivalent whole-second assignment, including specifically qualified matching offset forms. Real changes, fractional differences, missing fields and unsupported forms remain with the native setter. Its installer rewrites neither dates nor queue rows.

## Some stalled workers needed their destination admitted

Download workers encountered a different problem. Their full destination resolver could try to register a missing date folder while running through a reader. The repair first asked that resolver for paths only, then registered the reviewed folders through the normal native writer. The full resolver stayed in place and ordinary workers continued without rewritten pending paths.

The accepted scope registered 2,526 missing folders and verified all 3,144 planned folders across 63,101 queued assets. Twenty original controls subsequently completed their binary stage after a normal restart. That closes a concrete worker problem; it is not proof every download or server transaction finished.

A separate Smart Preview experiment used fresh scratch outputs from Adobe DNG Converter. A 392-file batch produced small DNG previews, and normal SDK preview building then recognized all 392 as already existing with zero failures. That version-specific cache reuse has tighter identity and structural requirements than normal conversion. The starter documents it but does not provide a universal cache publisher.

## Previews worked before every settings problem was solved

Cloud preview reuse needed an exact association between Classic's Smart Preview, the current Cloud asset and its literal native proxy filename. Collision suffixes mattered. A JPEG original could have a DNG proxy. APFS cloning provided independent inodes, so later writes could diverge while the initial bytes matched.

A complete 170-photo album was published and later natively recognized as local proxies with local settings. Its first invocation completed 54 new placements and held before replacing existing files; a separate recovery processed only the untouched 116. Both receipts remain. The result is an honest composite, not a rewritten successful history.

Two modern photos rendered offline and accepted Auto edits, followed by the operator's reported Command-Z. A later Sync showed the JPEG's Auto values arriving in Classic with a new history step. Editing worked, but exact Undo restoration was not established. Both Classic preview masters and both Cloud clones retained their exact bytes afterward. Future edit tests must capture numeric settings before, during, after Undo and after reconnect.

Two later legacy PENTAX controls rendered at Fit and 100% with network and original-source access denied, but both still required Legacy Settings Update before editing. No update, reset, edit or export was performed. Those render controls do not replace the modern controls or establish hundreds of thousands of offline-editable photos.

Settings recovery has its own exact identity. One cached XMP was normally adopted offline without changing its develop body or revision; a cold restart cleared Waiting for Settings. Bulk adoption remains unfinished. A roster of 50,443 exact-cache candidates is an admission result, not 50,443 completed recoveries, and profiles, masks and auxiliary data remain explicit gates.

## Keep a repair's evidence attached to the action

One DNG import and Smart Preview finished successfully before its external verifier failed. The TIFF library had interpreted the integer name of a held file descriptor as a pathname. The recovery supplied an explicit name while keeping that same descriptor and decoded all 28 preview tiles. It repeated verification, not Add, and preserved the original failure receipt.

That lesson also applies to Sync. A global revision sequence is not a per-photo old-plus-one counter. An association that appeared after a retry is not a failed precondition to erase. A callback returning from a queue withdrawal is not durability until the owner has flushed and the closed store confirms it. Keeping genuine errors made these distinctions visible.

Metadata needed similar care. A conflict badge does not identify which writer changed a file. Catalog settings, embedded DNG XMP, rating sidecars and untouched references can diverge. File modification order, a filename date or one nullable adjustment flag cannot resolve that history. The cookbook gives a field-by-field method instead of a bulk reset.

## What someone else can use

The repository's executable package contains our own configurable helpers, synthetic controls and installation/verification tooling. It derives from native controls accepted in Classic 15.6 on macOS, with Cloud 9.6 used for the related cache work. The public successor has source, syntax and temporary-installation tests; a new user's app and catalog still need their own actual native callback and preservation checks. Adobe implementation modules are imported from the installed app and are not redistributed.

For an ordinary broken location, start with [Adobe's Locate and Find Missing Folder instructions](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/locate-missing-photos.html). For broader trouble, the cookbook helps decide whether the next useful result is a repaired link, a faster indexed query, a released worker, a decoded preview, an adopted settings file or a server-accepted upload.

The October import is the practical reason for publishing this work: the catalog had become usable for its normal job again. The remaining original, settings and cloud holds stay visible while that result is shared.
