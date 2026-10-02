# Illustrated books and template-bound covers

Use actual authorized, reviewed artwork. Image generation belongs to the available host; no model or Canva service is bundled. For children, comics, art, activity, coloring and illustrated nonfiction: develop the page/spread plan, generate or import art, inspect consistency, compose lettering deliberately, then build the edition. A prompt or uninspected AI image is not a completed page. Complex-script lettering needs a capable layout tool plus fluent review; rasterization preserves visible lettering but does not prove shaping or accessibility quality.

## Image-page PDF and fixed-layout EPUB

`visual-book --input INPUT --destination NEW_DIRECTORY` requires title, author, BCP47 language, explicit synthetic, formats [pdf and/or epub], spec and pages. `edition` can save the same result in the versioned BookStore using id, layout:"fixed", spec, pages, formats after a book plan exists. Export it through the normal edition export.

Spec fields: trim_width, trim_height, bleed in inches; bleed_edges none/outer/all; min_dpi; min_pages/max_pages; platform kdp/lulu/direct/etsy; binding ebook/pdf/paperback/hardcover/printable; policy_url, policy_reviewed_at, policy_basis; safe_margin. Supply values from the current chosen platform specification, not defaults. Policy review expires after 30 days as an operating check. KDP print uses outer-edge bleed; Lulu print uses all-edge bleed. The code checks supported hardcover trims and binding minima, but paper/ink-specific upper limits and eligibility still need current source review.

Each page: file, sha256, alt, rights_basis, provenance (human_provided/ai_assisted/ai_generated), safe_area_reviewed:true. Explicit blank:true creates a deliberate blank; repeated bytes require intentional_repeat:true. Validate actual artwork before setting review flags. Effective DPI comes from pixels and physical size; changing metadata cannot rescue a small image. Deliberate crop/compose happens before export. No silent stretching, transparency flattening, guessed trim or overwritten destination.

Output: actual PDF, fixed-layout EPUB, editable composition recipe and validation JSON. PDF has alternating TrimBox for outside bleed, no printer marks. EPUB excludes print bleed and declares pre-paginated viewport pages with alt text. EPUBCheck runs when installed, otherwise reports unavailable. Image-page EPUB has limited text accessibility compared with semantic text; read-aloud, selectable text and sophisticated panel navigation are not bundled. Color conversion is RGB, not a printer ICC proof. Device/Kindle Previewer, print proof and independent visual/accessibility review remain required.

## Coloring-book print production

After the author chooses an evidence-backed concept and reviews original artwork, `coloring-book` task `check` takes title, author, language, synthetic, spec (as above), formats `["pdf"]`, single_sided (boolean), frontmatter (explicit page entries, possibly empty) and artworks (1–300 reviewed nonblank page entries). It checks source hashes, pixel dimensions/effective DPI, aspect ratios and identical pixels despite changed file metadata. It reports near-blank, heavy-fill, extensive-midtones and colored-pixel flags for review. These thresholds are heuristics, not a measure of artistic quality or closed shapes. No artwork is silently upscaled, recolored or regenerated.

For single_sided:true, artwork starts on odd-numbered pages, with blank reverse pages. Odd frontmatter receives a deliberate alignment blank. The final imposed count must fit the supplied current specification; it is never padded merely to reach a minimum. A blank reverse is not a guarantee against marker bleed-through. Choose frontmatter/page count as part of the actual book design.

Task `build` takes the same input plus the check's review_sha256 and a new destination. If a visual flag is deliberately accepted, include issue_reviews entries with artwork (one-based number), issue, reviewed_by and reason. Correct resolution/aspect failures instead of overriding them. Recheck after any recipe/artwork change. Exact duplicate-byte artwork also needs the existing intentional_repeat decision. Author-declared acceptance is not independent editorial/reader approval.

Output includes interior.pdf, contact-sheet.jpg, coloring-check.json, validation.json, portable recipe.json and frozen original artwork. Contact sheets are review thumbnails; print uses the original pixels. The check and build make no external calls. Coloring interaction on Kindle is not implemented; discuss a purposeful separate ebook companion rather than calling a PDF an interactive ebook.

To save this in the current book project, use `edition` with id, layout:"coloring", spec, artworks, frontmatter, single_sided, formats, review_sha256 and optional issue_reviews after a coloring plan exists. Title/author/language/synthetic come from that plan/project and must match the check. The existing `export` includes the actual files; changes to artwork or imposition invalidate content reviews.

## Print cover wrap

Use the actual current printer template generated for the final interior. `cover-wrap` takes synthetic, spec, template, interior, panels and a new destination. Template and interior each have file, sha256, binding, page_count, paper, ink, trim_width/height. The template must be a one-page PDF; interior must be PDF with the declared page count, real trim and bleed dimensions. The tool verifies hashes and geometry, not authenticity of the supplied template. Do not substitute a guessed spine formula or reuse another page count's template.

Panels have file, sha256, rights_basis, safe_area_reviewed:true, x/y/width/height in inches. First panel covers the entire measured template including bleed; further panels permit compositing. All need at least 300 effective DPI and matching aspect ratio. Review actual template hinges, safe zones, spine text and barcode areas before composition. The template guide itself is not printed into the exported cover. Output is cover-wrap.pdf, recipe.json and validation.json; publication_ready remains false pending actual preview/review.

Current primary references checked for the implementation (refresh for each real project):

- [KDP trim, bleed and margins](https://kdp.amazon.com/en_US/help/topic/GVBQ3CMEQW3W2VL6)
- [KDP paperback covers](https://kdp.amazon.com/en_US/help/topic/G201953020)
- [Lulu interior basics](https://help.lulu.com/en/support/solutions/articles/64000255590-interior-formatting-the-basics)
- [Lulu creation guide](https://assets.lulu.com/media/guides/en/lulu-book-creation-guide.pdf)
- [W3C EPUB 3.3](https://www.w3.org/TR/epub-33/)

Copyright © 2023 W3C®. This software/document includes implementation material derived from EPUB 3.3, https://www.w3.org/TR/epub-33/. The referenced Recommendation is dated 13 January 2026; copyright © 1999–2026 International Digital Publishing Forum and World Wide Web Consortium. [Document license](https://www.w3.org/copyright/document-license-2023/). No endorsement is implied.
