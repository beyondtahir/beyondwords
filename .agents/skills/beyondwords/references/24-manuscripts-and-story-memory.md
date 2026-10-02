# Importing an existing book and retaining story context

Use these tools after the shared intake and an accepted book plan. Prepare the inputs yourself; ask the author about creative decisions, not hashes or JSON. All operations use the existing book workspace/project. Writes require its current expected_revision. Nothing here calls a model, approves prose or publishes a book.

## Manuscript import

`manuscript-import` with task `inspect` and file reads UTF-8 Markdown/text. It returns the source sha256, section titles/lengths, uninterpreted frontmatter and layout warnings without saving changes. H1 headings separate chapters; headings inside fenced examples do not. Plain text without headings can map to one chapter.

After matching the existing plan, task `import` requires file, sha256, plan_sha256, ordered chapter_ids, rights_basis, provenance (human_authored/ai_assisted/ai_generated/unknown), synthetic and replace_sha256. Every section must map to a unique existing chapter, with the same title. Preserve a dedication/preface as its own titled contract. `title_heading:true` omits only an explicitly identified empty H1 equal to the book title; it cannot discard introductory prose. `metadata_reviewed:true` is required when frontmatter exists: review it against the plan first. Frontmatter is retained as source data, never executed or allowed to override project metadata.

For new chapters, replace_sha256 is `{}`. To revise existing chapters, supply `{chapter_id: current_chapter_sha256}` for every affected existing chapter. The complete import and original source bytes commit in one transaction; interruption leaves the prior revision intact. Earlier versions remain available. Inspect warnings before export: the existing text exporter still rejects tables, code fences, embedded images and complex layouts. Use the dedicated visual/host layout route where appropriate.

Then use the ordinary `edition` and `export` tools for EPUB/PDF. Import is not editorial approval and does not bypass sample/rights/review decisions for new production.

## Editable Word handoff

When the author/editor needs a Word copy, save `edition` with `{ "id": "editor-copy", "format": "docx" }`, then use ordinary `export` with kind `edition` and that id to a fresh destination. It creates `review.docx`, the exact source `manuscript.md`, validation and the existing hashed export manifest. The accepted plan supplies the title, author and language; accepted chapter order is preserved. Do not invent a biography, copyright statement, other books, endorsements or identifiers to fill a template. Add genuinely supplied front/back matter through the normal chapter contracts.

This is an A4 editorial handoff with real heading styles, linked contents, page breaks between H1 sections and preserved source text. It is not a KDP-ready print layout. Inline Markdown emphasis/links remain literal and external links are not activated. Tables, code/diagram fences, embedded art and covers are unsupported and rejected; use a capable layout route for those. No DOCX import, tracked-change merge, Word installation or diagram renderer is implied. Edits made in Word must be reviewed and deliberately saved back into the canonical chapter versions; exporting cannot synchronize them automatically.

No model or new runtime dependency is needed. Existing project isolation, revision checks, rollback, stale-edition rejection and synthetic markers apply. Each output still reports visual/editorial/retailer acceptance separately. The new format does not change `both` (EPUB plus PDF), and a money goal still does not trigger document generation.

## Story memory

After reviewing a saved chapter, use `story-memory` task `save` with chapter_id, chapter_sha256, plan_sha256, summary (up to 4,000 characters), reviewed_by, synthetic and threads. Each thread has id, description and status `open`, `resolved` or `superseded`. Use stable thread IDs across chapters. These are author/host interpretations of actual text; do not invent events, treat model critique as human review or advance memory before saving the prose.

The tool binds each summary to the plan and all chapter versions up to that point, including missing predecessors. Editing an earlier chapter or changing the plan marks affected memory stale. Re-read the changed material and replace its summaries; do not reuse stale canon silently.

`writing-context` includes current earlier summaries, unresolved threads, stale/missing chapter IDs, the voice, bible, contract and immediate previous draft. Later-chapter summaries are excluded. `story-memory` task `read` returns all current summaries/thread states; optional before_chapter limits it to predecessors. Latest thread updates are applied in chapter order, not save order. Missing/stale coverage is explicit. This is a version-bound memory ledger, not semantic retrieval, automatic fact checking or proof of long-novel quality.
