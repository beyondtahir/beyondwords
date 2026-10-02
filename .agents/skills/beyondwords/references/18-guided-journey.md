# Conversation and saved intake

Call `python <skill>/scripts/beyondwords.py guide --input <private-input.json>` with Python 3.11+. Here only, `--workspace` overrides the **memory directory**, not the book folder. Normally omit it: `BEYONDWORDS_MEMORY_DIR`, or `~/.local/share/beyondwords/memory` on macOS/Linux, `%LOCALAPPDATA%/beyondwords/memory` on Windows. Keep memory outside the installed skill and distributable source. Plugin upgrades preserve it.

`guide.sqlite3` stores append-only profile snapshots transactionally. Intake/choices live here; existing BookStore remains authoritative for manuscript and research artifacts. Local declarations do not authenticate humans or authorize account actions. Hashes detect accidental changes, not an owner rewriting both content and hash.

## Entry actions

- `start` lists profile IDs/labels only; never silently select the first. `create` needs `label`, `book_label`, explicit `synthetic` boolean. IDs/revision are returned.
- `start` with `profile_id` lists books; add `journey_id` to start a fresh session. Returned `session_id`, saved answers and missing questions drive dialogue. Do not reuse another invocation's session to skip confirmation.
- Every mutation includes selected IDs and `--expected-revision N`. Reload after stale revision; do not overwrite another session.
- `answer` needs `answers` and `origin`. Save actual author statements, not assistant suggestions. `recall` has the same inputs for authorized history; conflicting candidates are returned without overwriting saved answers. Ask the author and resolve using `answer`.
- `confirm` needs the new `session_id` and records confirmation of shown answers. Changed answers invalidate it. One session is confirmed per book; another session reloads and confirms.
- `new-book` needs `book_label`. Only country, conversation language and experience carry across books; budget/goals/formats/book language do not.

Results specify conversation delivery and no automatic document creation. Render short dialogue, not JSON. Undecided is honest where supported; never insert it without the author's answer merely to advance. Missing income metric/period needs clarification. A deadline may remain undecided, preventing a promised date.

## Intake fields

Text: country, conversation_language, book_language, experience, existing_material, interests, reader, account_status, book_type, target_marketplace, business_model. Formats accepts a legacy single value or a list: ebook/print/both/undecided/paperback/hardcover/pdf/epub/printable. publishing_channels is a list of kdp/lulu/etsy/direct/shopify/other/undecided. marketing_budget uses the same amount/currency/scope structure as budget. content_creation_preference is self/ai_assisted/delegated/undecided; operating_mode is guided/execution. Existing profiles keep their data and are asked only for missing fields. No migration invents new preferences.

```json
{
  "time":{"hours":"3","period":"day"},
  "budget":{"amount":"200","currency":"USD","scope":"total"},
  "goal":{"kind":"income","amount":"5000","currency":"USD","period":"monthly","metric":"undecided","deadline":"undecided"},
  "print_preferences":{"trim":"undecided","color":"undecided","bleed":"undecided"}
}
```

Numbers illustrate syntax, never defaults. Time periods day/week/undecided; unknown hours null. Budget scopes total/monthly/per_book/undecided; unknown amount/currency null. Goal kind income/creative/none; income metric revenue/royalties/pre_tax_profit/undecided, period monthly/cumulative/undecided. Print preferences required for print/both/paperback/hardcover; revisit with final layout.

An income target starts a short clarification, then feasible-route/cost research. `goals` calculates conditional required sales. It cannot predict demand, book count or earnings date. No assumed hours, royalties or acquisition costs disguised as researched inputs.

## Research and voice actions

Require selected IDs, confirmed `session_id` and revision.

`options` uses `kind: niches` or `gaps` and 1–5 objects: id, title, reader, buyer, author_fit, effort_and_cost, interpretation, next_test; lists observed_facts, missing_evidence, contrary_evidence; sources and fact_sources (one list of source IDs per fact). Each source needs evidence_id, HTTPS source_url, title, captured_at, access_basis, permission_reference, excerpt, explicit retain/derive booleans, and synthetic marker where applicable. max_age_hours defaults to 168 as an operating choice, not a retailer rule. Record when the source was captured, not when an assistant rewrote notes. Source shape/freshness is checked; authenticity, relevance and entailment require research judgment.

Partial batches of 1–5 cards can be saved, but cannot advance to selection or writing. A completed comparison requires five distinct concepts: five distinct `niche` values for `niches`, or one selected niche for `gaps`. Each card also supplies `proposed_book`, `fact_quotes` (one exact retained excerpt for each observed fact) and `inspections`. Each inspection identifies a source ID, kind (`listing`, `review`, `sample`), actual scope and exact quote. Its source records the work and selected product ID, verified edition, marketplace and format. See [the full coverage contract](26-research-completion.md). This validates declared coverage, not commercial demand or interpretation quality.

If the author already chose a niche, use `set-niche` with `niche` and their actual `decision_basis`. It records an author choice, not researched demand; no fabricated parent comparison is necessary. The next step is five ideas in that niche. Updating it resets dependent choices, persona and sample. Legacy incomplete records remain readable but cannot authorize production; current coverage is recalculated on resume.

`choose`: kind, option_id, returned options_sha256, decision_basis (actual author choice or explicit delegated scope). Changing options invalidates dependent choices/persona/sample. Refresh stale sources. Without retail access, permitted previews/readers can support a provisional test choice, not an invented profitability claim.

`persona`: reader, buyer, author_contribution, tone, rhythm, vocabulary, viewpoint, emotional_range, avoid, owned_examples. Optional specific fields: reader_age, genre, sentence_length, humor, cultural_context, expertise_basis, author_personality, storytelling_style, pacing, example_style, dialogue_style, formatting_preference. Interview; do not invent experience. “No owned examples yet” is valid when true. Develop original craft traits, not impersonation.

`sample`: body, provenance (human_provided/ai_assisted/ai_generated). `accept-sample`: current sample_sha256, decision_basis. Revisions reset acceptance. This records creative direction, never independent editorial approval.

After acceptance, initialize/use a book project through the existing CLI. `attach-book` needs book_workspace/book_project_id; `resume` reads its actual status for the next task. No automatic project/story from an income goal. Low-level book commands remain accessible for existing projects; this guide is a workflow controller, not a security boundary against an unrestricted host bypassing it. Specialists follow the same front door.

When guide research/voice changes, reconcile the actual book plan and affected chapters before relying on reviews. A guide decision cannot certify that existing manuscript content reflects a changed voice sample.

## Transfer

`export` with selected IDs returns an intake-only hash-checked handoff. Save privately only for a requested transfer. `import` needs authorized=true and handoff. It creates a separate profile, confirms again and never restores approvals/account permissions. Transfer actual book/research projects separately, preserving hashes. An unreadable chat/service is not shared memory; another host needs authorized shared storage or import.

`mode` takes operating_mode guided/execution and decision_basis. It preserves creative choices and resets session confirmation; it grants no account authority. See [the lifecycle playbook](22-lifecycle.md) for the full ongoing workflow.
