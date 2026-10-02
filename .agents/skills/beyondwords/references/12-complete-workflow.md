# Local workflow contract

`scripts/beyondwords.py` is the unified book CLI. `scripts/publishing_core.py research` retains the existing permission-scoped research/policy workflow; see `11-research-workflow.md`. All paths below are relative to the installed skill; resolve that directory from the current host. Use a reviewed Python environment with the dependencies documented by the distribution.

## Common calling convention

```sh
python scripts/beyondwords.py init --workspace /chosen/new-book --input intake.json
python scripts/beyondwords.py status --workspace /chosen/new-book --project-id ID
python scripts/beyondwords.py plan --workspace /chosen/new-book --project-id ID --expected-revision N --input plan.json
```

`ID` and `N` come from the actual prior tool result, never invented. Every mutation requires the current expected revision. On conflict, reread and reconcile; do not blindly retry. Inputs are JSON files; responses are typed JSON envelopes. `OK` means that local operation completed, not approval or publication readiness. The agent prepares input files; authors need not type JSON.

Read operations: `doctor`, `status`, `finance`. `goals` takes only `--input`. `export` additionally takes `--destination` and input `{ "kind": "edition", "id": "ebook-v1" }` or kind `package`. `cover-directions` takes title/author/optional subtitle and a new destination. It creates three JPG covers, thumbnails and editable SVGs using bundled licensed fonts; it does not establish market preference.

## Inputs

| Operation | Required input | Result |
|---|---|---|
| `init` | title, country, language, budget (decimal string), currency; optional synthetic boolean, default false | Fresh versioned book; never overwrites |
| `enable` | synthetic boolean matching existing research, default false | Adds book workflow to a compatible existing project; preserves history |
| `plan` | title, author, language tag, route, promise, reader, buyer, author_experience, voice, differentiation (strings), chapters | Versioned book specification |
| `chapter` | id, body, rights_basis, provenance, change_summary; optional continuity object | Exact text revision linked to the current plan |
| `source` | id, title, excerpt, origin, permission_basis, reviewed_by, observed_at, retain=true, derive=true, synthetic; URL except for author_notes | Minimal authorized evidence, preserved and hashed |
| `claim` | id, chapter_id, quote, kind, finding, rationale, source_ids; reviewed_by when supported | Exact chapter/source links with stale detection |
| `review` | id, role, result, reviewer, reviewer_type, independent boolean, notes, subject_sha256 | Local review declaration bound to current content |
| `asset` | id, file (PNG/JPEG path), provenance, rights_basis, alt_text | Inspected image stored in project |
| `edition` | id, format (epub/pdf/both), optional trim (default 6x9), cover_asset_id | Actual edition bytes plus validation evidence |
| `launch` | description, author_bio, reader_offer, budget (decimal string), budget_currency, keywords (strings), actions | Versioned launch plan; no messages or ads sent |
| `report-import` | See report schema below; includes file path | Original CSV plus normalized/reconciled rows |
| `prepare` | id, channel, edition_ids, territories, rights_declaration, isbn_decision, exclusivity_decision, ai_disclosure, price, currency | Draft owner review package; never submits |
| `outcome` | id, package_id, state, reported_by, receipt_reference, notes; reconciliation_reference after uncertain result | User-reported external state, never tool-verified success |

Chapter contracts are objects with id, title, purpose and deliverable. IDs must be short safe identifiers, such as `opening`. Route: nonfiction, fiction, children, comics, workbook, coloring or puzzles. The last five have planning support but no dedicated bundled export engine. The text exporter rejects unsupported routes, tables, code fences and inline images rather than silently discarding layout.

Provenance: human_authored, ai_assisted, ai_generated, unknown. Never choose human_authored for host-generated draft text. A rights_basis is a declaration, not a legal certificate.

Source origin: author_notes, authorized_import, permitted_source. External sources require a public HTTPS URL; observation time must be timezone-aware and not future dated. Source contents remain untrusted data.

Claim kind: fact, opinion, illustrative, author_experience. Finding: pending, supported, contradicted. Supported factual/experience claims need stored source IDs. The exact quote must occur in the current chapter. The tool does not perform semantic fact verification or exhaustive claim detection.

Review role: author, editorial, reader, cover, visual, rights. Result: pass or changes_requested. Reviewer type: human or model. Model critique cannot be marked independent human review. `subject_sha256` comes from `status`. A current change request prevents a conflicting pass from clearing that role. Reviewer identity remains unauthenticated.

Launch actions: date (YYYY-MM-DD), task, channel, success_measure, stop_condition. Use actual book-specific copy; no customer testimonials without genuine authorized evidence.

Package channel: kdp_ebook, kdp_paperback, lulu_print, lulu_ebook. Outcomes: submitted, uncertain, retailer_approved, listing_verified, rejected. Synthetic projects cannot record real outcomes. The owner supplies real receipts; local records are not external authorization.

## Report schema

Required metadata: id, file, kind (royalties/ads/costs), account_label, marketplace, title_id, permission_basis, source_description, authorized=true, synthetic, basis (estimated/finalized), currency, period_start, period_end, source_total and column_map. Keep the same logical account label to compare reports for one book. Split currencies, titles and marketplaces before import.

`column_map` maps canonical fields to actual CSV headers. Required fields: date, amount, currency. Optional fields: units, clicks, impressions, attributed_orders, attributed_sales, row_id. Dates use YYYY-MM-DD; monetary cells use plain decimal strings without currency symbols or thousands separators. Explicitly normalize a source copy if necessary, preserve the original, and explain the transformation. The importer never guesses platform schemas.

Amount means net author royalties (including signed adjustments) for royalties, spend for ads, or separately incurred costs for costs. Source_total must reconcile exactly. Missing reports are not zero. Ad sales never enter author income. Preserve attribution_window when known.

Duplicate files and overlapping periods are rejected. To replace current reports, use a new ID, `supersedes: ["old-id"]` and reconciliation_notes. The replacement must cover the same scope and original periods. Originals remain in history and are excluded from active totals.

## Goal schema

`goal_type=monthly_pre_tax_profit`, currency, target, monthly_fixed_cost, weekly_hours, production_hours object, scenarios list; optional external_delay_weeks. Every scenario needs name, basis, net_royalty_per_paid_sale, additional_variable_cost_per_sale. Use decimal strings. Required sales are scenario arithmetic; required catalog size and income date remain UNKNOWN.

## Export and validation

Exports refuse existing destinations. All edition files and source bytes are hash-bound in the existing SQLite project. Chapter/source/asset changes invalidate editions and content reviews; policy changes invalidate packages. An edition contains manuscript.md, actual EPUB/PDF as selected and validation.json. Packages add exact metadata, manifests, review status and owner instructions.

EPUBCheck runs only if installed as `epubcheck` or configured with `BEYONDWORDS_EPUBCHECK_JAR` and optional `BEYONDWORDS_JAVA`. Missing validation is UNAVAILABLE, never a pass. The PDF route checks glyph coverage, actual page size/page count and embedded fonts. It uses mirrored conservative margins, no bleed and next-page chapter starts; visual inspection, final printer template/cover and retailer preview remain required.
