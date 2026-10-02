# Specialist tool contracts

Existing manuscripts and long-book continuity use [manuscript-import and story-memory](24-manuscripts-and-story-memory.md). Coloring checks and single-sided imposition use [coloring-book](23-visual-production.md#coloring-book-print-production).

All commands use the existing `scripts/beyondwords.py` CLI and return its typed JSON result. Inputs are private JSON files. Select actual project ID/revision; never manufacture a success result. The agent handles these details, not the author. These tools are independent equivalents for specific publishing tasks, not affiliated clones or a claim of full commercial-service parity.

## Research desk: listing inspection, keyword candidates and history

`research-desk --workspace BOOK --project-id ID --input CONFIG` reads the existing permission-scoped ResearchStore. Optional max_age_hours defaults to 48. It produces source-linked listing cards with title, edition, price, ranks, status, missing fields and current permission/freshness; observed title phrases with distinct listing counts; and saved capture history. It makes no new network request. Refresh/import through `publishing_core.py research` first. Blocked/ambiguous records stay visible but cannot supply keyword or comparable evidence. A phrase count is not search volume; snapshots are not inferred historical sales. Keyword candidates require relevance and rights/metadata review before use.

`market-screen --input CONFIG`: observations, evidence, synthetic boolean, optional threshold (80000), minimum_books (3), max_age_hours (168). Observations follow validate_bsr in publishing_core.py, with explicit niche, work_id and selected_product_id. Evidence follows validate_evidence, also product_id, format, marketplace and explicit retain/derive booleans. Use `ebook` in this contract (the HTML extractor's `kindle` label must be normalized). Same niche/marketplace/store/format/currency, paid overall bookstore ranks, fresh source/observation, verified selected edition and known price/currency are required to count. Deduplicate work IDs across editions; the same selected product cannot count as several works. Conflicting same-time ranks require review. This configurable three-book threshold is a screening hypothesis, never a sales, royalty or success formula.

The source-linked guide choice cards distinguish observations, interpretations, contrary/missing evidence and next tests. Output concise dialogue by default. Generate an extended research document only when asked.

## Book-writing studio

Use plan/chapter/source/claim/review and their existing contract in 12-complete-workflow.md. `writing-context --workspace BOOK --project-id ID --input CONFIG` takes chapter_id. It returns the exact contract, accepted plan voice/promise/reader/buyer, current/previous chapter, source-bound continuity values and conflicts, chapter hash index and real review status. It does not claim to have read other full chapters: retrieve them when the edit needs them.

Host inference writes/revises the actual prose, then persists it. Fiction needs POV, causality, scene stakes, character choices and continuity; nonfiction needs sourced claims, useful examples and chapter ownership; visual books need a spread/panel brief and separate layout verification. A changed continuity value may be intentional over time—resolve it rather than blindly replacing text. Do not force every genre into takeaway boxes or an identical motivational ending. Preserve human edits and earlier versions.

For review, `editorial` packet/record/status connects full selected manuscript text to version-bound findings, cumulative batch coverage and the next revision/check. See [the handoff contract](25-editorial-handoff.md). Its model/human checks are not independent release approvals.

## Cover studio

`cover-compose --input CONFIG --destination NEW_FOLDER` takes art (local PNG/JPEG), title, author, optional subtitle/position(top/center/bottom)/casing/color, rights_basis, research_basis and provenance(human_provided/ai_assisted/ai_generated). Art must be at least 1600×2560; the tool refuses silent upscaling and preserves the input. It produces a 1600×2560 JPEG front cover, 200px thumbnail, original art, licensed fonts and composition.json with an editable type recipe. Render a changed recipe to a new revision. This is an ebook cover, not a print wrap. Center cropping requires visual inspection; title placement and contrast still need a human/host visual check.

`cover-directions` remains available for actual original typographic drafts and SVGs. Three palette variants are not three validated genre concepts. Research and author feedback should lead distinct concepts, with real available image tools for original artwork. Canva is optional when connected; local composition is available without it. No conversion-rate claim or resemblance-to-bestseller guarantee.

## Amazon ads desk

`ads-analyze --input CONFIG` reads a supplied authorized CSV. CONFIG has file, report, target_column, attribution_complete(bool), min_clicks(positive integer), max_test_spend_per_target(positive decimal string), decision_basis and optionally net_royalty_per_order/royalty_basis. The report object uses the existing report-import schema with kind=ads, account_label, marketplace, title_id, permission_basis, source_description, authorized=true, synthetic, basis, currency, period_start/end, source_total, attribution_window and column_map. Map date, amount (spend), currency, clicks, impressions, attributed_orders and attributed_sales to actual headers; map target_column separately. Inspect the report's actual grain; split different campaign/ad-group/match-type/currency contexts before aggregating identical target labels.

The analyzer reconciles totals and produces target-level observed CPC/order rate, explicit royalty scenarios, and proposed reviews: wait for attribution, gather evidence, inspect a target/listing, examine the spend cap, or consider a controlled test. User-specific thresholds must have an explicit rationale. Zero clicks or missing royalties stay unknown; no division by zero or retail-sales-as-income. These are review candidates, not automatic bid/pause commands, causal attribution or calibrated forecasts. An attributed order is not necessarily one unit; use a justified same-title/format net receipt assumption or leave it unknown.

Use report-import/finance for the durable account/report ledger and matching-period royalties minus separate spend/costs. Live campaign execution needs an actual connected host/API and bounded authorization; the bundled analyzer does not place ads. Use official current targeting fields; Sponsored Products is not a universal age/demographic targeting API.


Additional read-only operation: `publishing-check` tasks `cover-art`, `listing`, `voice`. Contracts and limitations: [native pixels and metadata](27-publisher-and-listing-quality.md), [original voice](28-original-voice.md). No workspace mutation, network request or approval is performed. Prepare inputs for the author and retain receipts privately. Ads `group_columns` and retail/royalty metric distinctions are specified in [the ads manager](29-amazon-ads-manager.md).
