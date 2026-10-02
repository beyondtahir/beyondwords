# Cover, illustrations and editions

Check actual host image-generation capability before promising generated illustrations. When unavailable, explain the missing capability and retain the art brief; do not claim an image was made. A text prompt is not a finished cover.

For characters, approve reference views, clothing, proportions, style and recurring assets before page generation. Record generation provenance and usage rights. Verify consistency visually; shared prompts/seeds alone do not guarantee it.

Keep artwork separate from editable title/author typography. Use a vector/layout composition layer for text, spacing, contrast and safe areas. Review the cover at thumbnail and full size. Do not create fake bestseller badges, official endorsements or lookalike branding. Track font licenses and embedding permissions; do not distribute font files unless the license and intended distribution permit it.

One canonical structured book produces channel-specific editions: reflowable EPUB, supported fixed-layout EPUB, printer-specific PDF and direct-sale PDF. Do not rasterize a text book into images merely to preserve appearance. Preserve semantic headings, table of contents, reading order, language tags and meaningful alt text. Test RTL layout where supported.

Use maintained printer profiles for trim, bleed, gutter, binding, paper, spine and cover dimensions. Recalculate after page-count changes. Print cover and print interior are distinct artifacts. Do not put an ebook cover into a print interior and declare the file universally ready.

EPUB validation: run the actual EPUBCheck executable and save its output/version. Visual validation: render/preview representative devices and pages, including small screens and enlarged fonts. PDF validation: page boxes, embedded fonts, resolution, overflow, margins, pagination and printer requirements. Passing EPUBCheck does not prove factual quality or retailer acceptance.

Current tools produce simple text EPUB/PDF, typographic SVG directions and artwork-plus-type ebook covers. See 19-specialist-tools.md. Fixed-layout/illustrated/complex-script production is not validated by the text exporter; use a dedicated layout route and inspect it. Do not claim visual or market evaluation from file generation.

The official ebook-cover guidance reviewed on 1 October 2026 recommends a 1600×2560 image and RGB JPEG, with 300 DPI and a 5 MB file-size profile. The compositor now writes DPI metadata and rejects outputs exceeding its conservative file-size check; validate current guidance again for each release. DPI metadata does not increase image detail. See https://kdp.amazon.com/en_US/help/topic/G6GTK3T3NUHKLEFX.


Before generating front/back artwork, follow [native pixel planning and verification](27-publisher-and-listing-quality.md#native-pixels-before-cover-generation). A resized raster or edited DPI label is not native high-resolution art. Audit actual pixels, crop and placement using `publishing-check` task `cover-art`; keep ebook and print checks separate.
