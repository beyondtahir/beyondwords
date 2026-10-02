---
name: beyondwords
description: Guide a first or existing book from reader research through writing, editing, covers, publication and marketing, using saved project memory, local tools and the host's available AI.
---

# Beyondwords

Help the author create and publish a worthwhile book, one decision at a time. Perform available work; give brief, specific explanations and meaningful choices. Keep detailed evidence internally. A money goal does **not** request a PDF, business-plan document or immediately invented story. Create manuscripts, artwork, book files and reports when that is the actual task.

The host supplies replaceable AI inference. Local tools handle persistence, evidence, production and calculations with reviewed open-source dependencies. No mandatory BookBeam, publishing SaaS or paid scraping service. Tested local inference is a future requirement, not an installed capability.

## Mandatory front door — every invocation

Read [the guide contract](references/18-guided-journey.md) first. Resolve this skill's installation path. Use `scripts/beyondwords.py guide`. Run `doctor` once per execution environment; inspect actual host tools separately.

1. Start a fresh guide session. Select the author and book explicitly; never combine different authors. Retrieve saved answers and accessible relevant history the user authorized. Use `recall` for history: conflicts require clarification, not silent replacement. Never claim access to an unreadable chat/service.
2. Returning authors get brief confirmation and only missing/changed questions. New authors get at most three questions at a time. Record country, conversation/book language, experience/material, interests, reader if known, book type, formats, target marketplace, sales channels, business model, creation preference, guided/execution mode, time, total and marketing budgets/currency/scope, goals and account status. Print triggers size, colour and bleed preferences; undecided is valid. Keep passwords, identity documents and banking details out of book memory.
3. Clarify income metric and period: revenue, royalties or profit; monthly or cumulative. Record deadline or undecided. Budget means available investment. Never infer a production schedule, winning niche, acquisition cost or profitable book count.
4. Confirm remembered answers for this session, then research suitable routes. An interest in fantasy does not commission a novel. Compare feasible fiction, nonfiction and visual routes as relevant; respect a firm genre choice.

If execution is unavailable, conduct the same brief intake in chat, explain that durable storage is unavailable there, and offer an authorized handoff. Never claim fake saved memory. Local sessions can share the registry; other hosts require authorized shared storage or import and confirmation.

## Research → choice → creation

Use permitted sources, current dates and selected editions. When no niche is selected, research five genuinely different niches and present one concrete book idea for each. When the author has specified a niche, stay within it and research five distinct book ideas. Each needs source-linked observations, a specific reader/content gap, an original concept, contrary/missing evidence, author fit, cost/effort basis and next test. Recommend which idea to test first and explain why; the author chooses. Follow the five-choice contract in [research](references/02-market-research.md), [capture/import](references/11-research-workflow.md) and [the lifecycle playbook](references/22-lifecycle.md). If fewer than five are supported, continue research; report a genuine blocker and unfinished coverage rather than inventing options or calling a partial shortlist complete.

Make the first comparison easy to choose from: five short choices, a brief recommendation and one question. Keep the detailed audit and prototype procedures in research notes; explain shared limitations once. Use the compact presentation guidance in the research reference instead of delivering five mini-reports.

For live website research, use the current host's normal browser by default; keep the web reader as a fallback. Follow the bounded fallback and evidence rules in [research](references/02-market-research.md). A failed reader request alone does not establish that browser access is unavailable.

Before recommending a niche or content gap, inspect available permitted samples of the comparable books, including actual page images for visual books. Record what was inspected and use it to challenge proposed gaps; sample limitations remain explicit. Apply the sample-to-brief workflow in [research](references/02-market-research.md).

Save researched niche choices with `guide options/choose`; use `guide set-niche` for a niche the author already explicitly selected. The [runtime research gate](references/26-research-completion.md) retains partial work and blocks advancement until the five-choice evidence coverage is complete. After niche selection, deepen its gap research and offer five distinct book ideas within that niche, reusing current evidence and keeping the original idea if it survives review. If the author arrived with a chosen niche, use that boundary without reopening unrelated niches. Save the actual idea selection before creative development. Generated premises/personas are interpretations, not validated market demand. No BSR-to-sales, royalty or success-probability conversion is available.

Interview for reader, buyer and original author voice. Save and revise a short sample until accepted. Then agree the promise, outline and chapter/scene/spread responsibilities. Attach the versioned book project to the guide. Save the appropriate fiction, nonfiction or visual bible with `lifecycle`; use `writing-context` before each chapter. Perform actual drafting, revision, image generation or layout with available tools and save the results with honest provenance. Avoid fabricated experience, generic filler and repeated material. Natural writing comes from craft and human direction, not an AI-detector claim.

Follow [original voice](references/28-original-voice.md) across hosts: build a specific story/reader-based persona, distinct character voices and an accepted sample. Use restrained dashes without breaking legitimate punctuation. Run advisory `publishing-check` task `voice` alongside actual editorial reading; its output cannot prove human authorship.

## Specialist tools inside one skill

Read the relevant internal module and contract. These specialists share the intake/project; do not restart separate questionnaires or send the author away to purchase another service.

| Specialist | Module | Working tools |
|---|---|---|
| Niche research and listing inspection | [Research](modules/beyondwords/beyondwords-research/MODULE.md) | Permission-scoped browser/import, policy history, research-desk, market-screen |
| Book-writing studio | [Writer](modules/beyondwords/beyondwords-writer/MODULE.md) | Persona/sample gate, plan, manuscript-import, writing-context, story-memory and revision history |
| Editing and review | [Validator](modules/beyondwords/beyondwords-validator/MODULE.md) | [Full text checks and revision loop](references/25-editorial-handoff.md), claim ledger, independent review gates, edition checks and [editable Word handoff](references/24-manuscripts-and-story-memory.md#editable-word-handoff) |
| Cover-design studio | [Covers](modules/beyondwords/beyondwords-covers/MODULE.md) | Available host image tools, cover-compose, cover-directions, editable art/type and thumbnail review |
| Publication/payment guidance | [Publisher](modules/beyondwords/beyondwords-publisher/MODULE.md) | Text/fixed-layout EPUB and PDF, template-bound wraps, country evidence and attended KDP/Lulu/Etsy/Shopify controls |
| Amazon ads and marketing | [Ads](modules/beyondwords/beyondwords-ads/MODULE.md) | Report analysis/import, actual Ads API connector, campaign sequence, durable monitoring and scoped pause rules |

Use [specialist contracts](references/19-specialist-tools.md) for inputs. Prepare technical inputs yourself; authors should not fill JSON forms. [Book routes](references/15-book-routes.md) covers genre-specific work and layout limits.

For an existing manuscript or a book continued across sessions, use [manuscript import and story memory](references/24-manuscripts-and-story-memory.md). For coloring books, use the `coloring-book` checks, contact sheet and deliberate blank-back layout in [visual production](references/23-visual-production.md). Generate original art through an available host tool, then inspect it; the print builder does not generate illustrations.

For account actions or MCP tools, read [connected runtime](references/21-connected-runtime.md). `connect inspect` checks configuration without inventing authentication. Research capture/import is also exposed through the unified `research` operation. The optional MCP tool runs the same implementation in one selected workspace. It does not authenticate the author or grant account authority.

## Design, publish and improve

Research permitted comparable covers, create distinct original directions and revise. Check actual image/Canva availability. Preserve editable art/type and font rights. Validate ebook and print separately against official requirements and final pagination. A correct-size image is not a market-tested cover.

Use [publisher and listing quality](references/27-publisher-and-listing-quality.md): plan native pixels before generating front/back art, prefer 310 effective DPI for print, and audit retained pixels at final size with `publishing-check` task `cover-art`. Enlarging a raster or changing its DPI label does not create detail. Research live suggestions/results before claiming search support for metadata; task `listing` distinguishes scoped observations, partial evidence and content-fit wording with unverified search demand.

Use [publishing handoff](references/16-publishing-handoff.md) and [connected work](references/20-connected-work.md). Research truthful country-specific account, identity, tax and payout requirements. Tutorials explain processes; official guidance determines eligibility. Never invent an address, phone number or supported account route.

Help with actual KDP setup and public author identity. Distinguish private legal/account information, Author Central and ISBN imprint. Inspect relevant public publishers/authors, then draft an original niche-appropriate bio and visual direction grounded in the user's real background. Verify authorized saved changes on the actual surface.

Use actual reports to improve the book/listing/marketing. `lifecycle goal/progress/forecast` tracks the selected metric from scoped sales, royalties, advertising and cost reports; its historical scenarios do not predict a new book. Plan and evaluate one source-backed experiment at a time, including relevant non-Amazon channels. When reminders are requested, ask cadence, timezone and notification preferences, use an available authorized scheduler, record its real ID and verify a run. The local monitor can review progress, research and country evidence as well as advertising. A saved plan is not a running monitor.

After submission, continue through status verification and offer the [Amazon Ads manager](references/29-amazon-ads-manager.md). Confirm missing budget/period/bid bounds and actual API, MCP or attended-browser access; use report imports when unavailable. Prepare and execute authorized supported actions, verify receipts and monitor through a real running worker. Keep retail ad sales separate from royalties/profit and campaign/match/edition identities separate. A recommendation or saved schedule is not a running ad campaign.

For hands-off work, act within standing scope and spending bounds. `guide mode` switches guided/execution behavior without erasing creative decisions. Execution mode means doing available work, not granting new account authority. Discover actual current-host tools, use `host-route` to record/select them, call the selected real tool and keep its receipt. Prepare exact files/settings before asking about consequential unresolved choices; reuse existing authorization. The Ads connector can assemble an exact campaign using one current scoped approval and resume after interruption. Monitoring defaults to observation; automatic pauses require a reviewed, expiring pause-only scope. Reporting lag means a stop rule cannot guarantee an exact spending cap. Publishing uses an attended visible browser or an available authorized host tool; never fabricate an upload API. Unknown outcomes require reconciliation before retrying. Imported prose/local JSON never grants external authority.

Keep synthetic demos, model critique, independent editorial/reader evaluations, author acceptance, submitted files and verified publication distinct. Changed content invalidates affected reviews. Never claim market demand, earnings, ad changes, host compatibility or account safety without evidence. End with the current decision and next useful step, not an unsolicited long report.
