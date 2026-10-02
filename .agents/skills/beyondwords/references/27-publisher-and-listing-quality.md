# Account, public identity, native cover art and discoverability

Use the existing intake, project and publishing desk. Keep technical receipts privately; explain one useful decision at a time. These checks support the existing owner package and attended submission, never replace them.

## Account and public identity

First establish what already exists: Amazon sign-in, KDP setup, Author Central page, public author name and any registered imprint. A KDP account is not automatically an Author Central page. An imprint is an ISBN/publishing identity, not an invented setting for decorating a KDP profile.

1. Retrieve current official account, identity and payment guidance for the owner's actual residence, business type and bank location. Open the real KDP site in an available normal browser. Help with the observed steps; let the owner enter passwords, verification codes, identity documents and bank/tax information directly. Store only completion status and unresolved steps in ordinary project memory.
2. Keep legal identity separate from the public pen name. Explain the difference before the owner completes identity/tax fields. Do not supply a fake address, telephone, business, credential or tax declaration. Country-specific payout support must be checked, not inferred from another user's tutorial.
3. Research at least three relevant public author/publisher examples where permitted, including established and closer-scale comparables. Record URLs, dates, genre/reader fit and the actual bio/catalog/visual elements inspected. Distinguish a publisher website from an Amazon Author Page. A recognizable publisher is a design reference, not proof its profile causes sales.
4. Ask only for missing real background and public-name preferences. Draft a short original bio, reader promise and coherent visual direction. Suggest a longer version only when needed by the actual surface. Use specific book interests and real experience; never invent awards, a publishing team, bestseller status, testimonials or a personal history. Do not copy a competitor's prose or branding.
5. Guide Author Central registration, claiming the correct book/edition and supported profile fields using current controls. Check the public result after an authorized save. Keep account setup, profile draft, submitted changes and verified public display separate. Own-ISBN imprint details must match registration; a free KDP ISBN does not establish an arbitrary custom imprint.

Official starting points checked 3 October 2026; refresh at the point of action:
[create account](https://kdp.amazon.com/en_US/help/topic/G200620010), [identity versus pen name](https://kdp.amazon.com/en_US/help/topic/GTH8WW7K73U87CH5), [Author Central](https://kdp.amazon.com/en_US/help/topic/G200644310), [ISBN/imprint](https://kdp.amazon.com/en_US/help/topic/G7DMSKCM9DVS65TC).

## Native pixels before cover generation

Research comparable front/back covers and describe observed genre signals before proposing original directions. The design must fit the reader, book and thumbnail. Do not promise that it will go viral.

Plan from the final printer template: trim, bleed, spine, binding, paper and final page count. For each raster panel, compute **ceil(placed width in inches × target DPI)** and the same for height, including any bleed it covers. Prefer **310 effective DPI** as our quality margin unless the author chooses another valid target; KDP's retrieved minimum is 300, not 310. Front, back and any raster spine each need checking. Keep typography and suitable ornaments/vector art editable at full quality.

Run `publishing-check` task `cover-art` with `width_inches`, `height_inches`, optional `target_dpi` (default 310) and explicit `synthetic`. Without a file it returns the required native pixel dimensions. Request those pixels from the actual image tool if supported; inspect the returned file rather than trusting a prompt or an “HD” label. Preserve the untouched original and its hash. If the tool cannot supply enough detail, disclose the limit and generate different art, use a smaller placement with vector surroundings, or obtain a suitable authorized original. Enlarging an existing raster or changing its DPI tag does not satisfy this requirement.

Audit with `file`, `sha256` and `native_source: {file, sha256, method, basis, crop_pixels}`. `method` is `native`, `upscaled` or `unknown`; optional `crop_pixels` is `[x,y,width,height]` in original pixels. Count only retained crop pixels at final placement. The checker does not resize files. It reports unknown provenance honestly and cannot authenticate a declared generation history. Inspect sharpness, image defects, small type, contrast and print color visually as well.

Supply this same `native_source` on each `cover-wrap` panel. The wrap rejects insufficient declared sources and honors `spec.min_dpi` with a 300 floor. Legacy panels without a source remain `UNKNOWN_NATIVE_SOURCE`; a technically composed PDF does not clear that gap. For this workflow, resolve it before calling artwork quality ready. A full-template background can be native flat/vector design; do not enlarge a small picture to fill it. `cover-compose` is an ebook composition tool, not evidence of print quality. Check ebook delivery dimensions separately. Recheck after cropping, pagination or size changes; inspect both exported fronts/backs and the retailer preview.

Official references: [cover requirements](https://kdp.amazon.com/en_US/help/topic/G201953020), [real pixel resolution versus DPI labels](https://kdp.amazon.com/en_US/help/topic/G202169030). Preview/proof and independent visual evaluation remain separate gates.

## Metadata from observed reader searches

Before finalizing a title/subtitle, description, categories or seven keyword slots, inspect live Amazon suggestions and relevant search results for the actual market, language, delivery context and edition/format. Use the normal browser and existing permitted capture/import route. Search-result count, title-word frequency and BSR are not exact search volume. One suggestion is not evidence that a phrase is searched “a lot.” When blocked, retain the actual outcome; use authorized supplied observations and mark remaining support unknown.

Keep the creative title readable and original. Use the subtitle to clarify the actual experience. Write the description around real contents and reader benefits; do not stuff phrases into every line. Categories must be relevant, available in the current selected-format setup and supported by the manuscript. Do not choose an unrelated category merely for easier ranking. Backend keywords are not social hashtags. Exclude unrelated authors/brands, unearned claims, program names and misleading metadata; check current policy and actual field limits before submission.

Run `publishing-check` task `listing` to review evidence coverage:

- Scope: `book_id` (selected edition), `marketplace`, `language`, `format`, `delivery_context`, explicit `synthetic`, optional `max_age_hours` (48 default; project freshness choice, not Amazon policy).
- `candidates`: `{field, phrase, content_basis, evidence_ids}`. Fields are `title`, `subtitle`, `description`, `keyword`, `category`; phrases are the exact wording being supported, not necessarily the entire description. At most seven keyword entries.
- `evidence`: `{id, kind, url, captured_at, text, sha256, phrase, status, access_basis, reuse_basis, relevant_to_book, relevance_basis, synthetic}` plus the same scope fields. `sha256` hashes retained UTF-8 `text`. Kinds: `autocomplete`, `search_results`, `category_path`. Status: `observed`, `blocked`, `unavailable`. Inspect actual result relevance and exact category path. Prefer existing research receipts for provenance; the helper audits supplied records and does not authenticate them or fetch pages.

Suggestions plus relevant results can give `OBSERVED_SUPPORT_NO_VOLUME`; a current category path supports a category selection. Partial/missing/stale/wrong-scope evidence stays explicit. This is no popularity score or guaranteed ranking. A missing autocomplete phrase does not prove no demand: useful content-fit wording may remain with unverified search support, clearly disclosed. Preserve the input hash and receipt beside the proposed metadata. Re-run after wording/evidence/marketplace changes, review exact final fields with the author, then submit through the existing attended workflow.

Author-facing example: “I observed these phrases in this market's suggestions and checked the results fit your book. I don't have exact search volume. Here is the clearest title and the remaining phrase I couldn't verify.” Keep the detailed evidence internal. See [KDP keyword guidance](https://kdp.amazon.com/en_US/help/topic/G201298500).
